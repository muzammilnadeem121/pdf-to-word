"""
Stage 6 — Semantic Analysis
------------------------------
Groups Stage 5's ordered blocks into complete semantic units:
- Consecutive PARAGRAPH blocks linked by continues_from_id merge into one.
- Consecutive LIST_ITEM blocks merge into one list.
- CAPTION blocks merge with the nearest preceding image reference.
- HEADING, QUOTATION, REFERENCE, FOOTNOTE pass through as standalone units.
- PAGE_NUMBER/HEADER/FOOTER (non-flow) are dropped from the semantic
  document — they're presentation artifacts, not content.
"""

import logging
from pathlib import Path

from document_engine.dom.layout import LayoutRole
from document_engine.dom.reading_order import DocumentReadingOrder, OrderedBlock
from document_engine.dom.semantic import DocumentSemantic, SemanticElement

logger = logging.getLogger(__name__)


class SemanticAnalyzer:

    def analyze(self, doc_order: DocumentReadingOrder) -> DocumentSemantic:
        elements: list[SemanticElement] = []
        sequence = 0
        buffer: list[OrderedBlock] = []
        buffer_role: LayoutRole | None = None

        def flush():
            nonlocal sequence, buffer, buffer_role
            if not buffer:
                return
            elements.append(self._build_element(buffer, buffer_role, sequence))
            sequence += 1
            buffer = []
            buffer_role = None

        for page in doc_order.pages:
            flow_blocks = sorted(
                (b for b in page.blocks if b.sequence >= 0),
                key=lambda b: b.sequence,
            )
            for block in flow_blocks:
                if block.role in (LayoutRole.HEADER, LayoutRole.FOOTER, LayoutRole.PAGE_NUMBER):
                    continue

                if block.role == LayoutRole.PARAGRAPH:
                    if buffer_role == LayoutRole.PARAGRAPH and block.continues_from_id:
                        buffer.append(block)
                    else:
                        flush()
                        buffer = [block]
                        buffer_role = LayoutRole.PARAGRAPH

                elif block.role == LayoutRole.LIST_ITEM:
                    if buffer_role == LayoutRole.LIST_ITEM:
                        buffer.append(block)
                    else:
                        flush()
                        buffer = [block]
                        buffer_role = LayoutRole.LIST_ITEM

                else:
                    flush()
                    buffer = [block]
                    buffer_role = block.role
                    flush()

        flush()

        logger.info("Stage 6 complete: %d semantic elements.", len(elements))
        return DocumentSemantic(source_path=doc_order.source_path, elements=elements)

    def extract_and_save(self, doc_order: DocumentReadingOrder, debug_output_path: str) -> DocumentSemantic:
        result = self.analyze(doc_order)
        Path(debug_output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    def _build_element(
        self, buffer: list[OrderedBlock], role: LayoutRole, sequence: int
    ) -> SemanticElement:
        source_ids = [b.source_layout_block_id for b in buffer if b.source_layout_block_id]
        page_number = buffer[0].page_number

        if role == LayoutRole.PARAGRAPH:
            return SemanticElement(
                page_number=page_number, element_type="paragraph",
                text=" ".join(b.text for b in buffer),
                sequence=sequence, source_block_ids=source_ids,
            )
        if role == LayoutRole.LIST_ITEM:
            return SemanticElement(
                page_number=page_number, element_type="list",
                list_items=[b.text for b in buffer],
                sequence=sequence, source_block_ids=source_ids,
            )
        if role == LayoutRole.HEADING:
            return SemanticElement(
                page_number=page_number, element_type="heading",
                text=buffer[0].text, heading_level=buffer[0].heading_level,
                sequence=sequence, source_block_ids=source_ids,
            )
        if role == LayoutRole.CAPTION:
            return SemanticElement(
                page_number=page_number, element_type="image_caption",
                caption_text=buffer[0].text,
                sequence=sequence, source_block_ids=source_ids,
            )
        # QUOTATION, REFERENCE, FOOTNOTE, UNKNOWN -> pass through as typed text
        return SemanticElement(
            page_number=page_number, element_type=role.value,
            text=buffer[0].text,
            sequence=sequence, source_block_ids=source_ids,
        )