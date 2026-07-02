"""
Stage 5 — Reading Order
-------------------------
Takes Stage 4's classified LayoutBlocks (still in raw page/y order) and
Stage 2's column detection, and produces the sequence a human would
actually read: right-to-left column-first for RTL multi-column pages,
top-to-bottom within each column, headers/footers/page-numbers excluded
from body flow (kept but flagged), and paragraphs continuing across
pages linked via continues_from_id.
"""

import logging
from pathlib import Path
from typing import Optional

from document_engine.dom.layout import DocumentLayout, LayoutBlock, LayoutRole, PageLayout
from document_engine.dom.reading_order import (
    DocumentReadingOrder, OrderedBlock, PageReadingOrder,
)
from document_engine.dom.visual import DocumentVisual, PageVisual

logger = logging.getLogger(__name__)

# Roles excluded from the main body reading sequence
_NON_FLOW_ROLES = {LayoutRole.HEADER, LayoutRole.FOOTER, LayoutRole.PAGE_NUMBER}


class ReadingOrderEngine:
    """
    Performs Stage 5: (DocumentLayout, DocumentVisual) -> DocumentReadingOrder.
    """

    def analyze(
        self, doc_layout: DocumentLayout, doc_visual: DocumentVisual
    ) -> DocumentReadingOrder:
        visual_by_page = {p.page_number: p for p in doc_visual.pages}
        pages: list[PageReadingOrder] = []

        prev_last_paragraph: Optional[OrderedBlock] = None

        for page_layout in doc_layout.pages:
            page_visual = visual_by_page.get(page_layout.page_number)
            try:
                page_order, prev_last_paragraph = self._order_page(
                    page_layout, page_visual, prev_last_paragraph
                )
                pages.append(page_order)
            except Exception as exc:
                logger.error(
                    "Stage 5 ordering failed on page %d: %s — using original order.",
                    page_layout.page_number, exc,
                )
                pages.append(self._fallback_order(page_layout))

        logger.info("Stage 5 complete: %d pages ordered.", len(pages))
        return DocumentReadingOrder(source_path=doc_layout.source_path, pages=pages)

    def extract_and_save(
        self, doc_layout: DocumentLayout, doc_visual: DocumentVisual, debug_output_path: str
    ) -> DocumentReadingOrder:
        result = self.analyze(doc_layout, doc_visual)
        Path(debug_output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    # ------------------------------------------------------------------

    def _order_page(
        self,
        page_layout: PageLayout,
        page_visual: Optional[PageVisual],
        prev_last_paragraph: Optional[OrderedBlock],
    ) -> tuple[PageReadingOrder, Optional[OrderedBlock]]:

        flow_blocks     = [b for b in page_layout.blocks if b.role not in _NON_FLOW_ROLES]
        non_flow_blocks = [b for b in page_layout.blocks if b.role in _NON_FLOW_ROLES]

        columns = page_visual.columns if page_visual and page_visual.columns else []

        if columns:
            ordered = self._order_by_columns(flow_blocks, columns)
        else:
            # Single column: simple top-to-bottom
            ordered = sorted(flow_blocks, key=lambda b: b.bbox.y0 if b.bbox else 0)

        result_blocks: list[OrderedBlock] = []
        sequence = 0
        last_paragraph: Optional[OrderedBlock] = prev_last_paragraph

        for block in ordered:
            continues_from = None
            # First paragraph on the page continuing the previous page's last paragraph:
            if (
                sequence == 0 and
                block.role == LayoutRole.PARAGRAPH and
                last_paragraph is not None and
                not block.text.strip()[:1].isupper()  # heuristic: doesn't start a new sentence look
            ):
                continues_from = last_paragraph.id

            ob = OrderedBlock(
                page_number=block.page_number,
                bbox=block.bbox,
                text=block.text,
                role=block.role,
                heading_level=block.heading_level,
                sequence=sequence,
                continues_from_id=continues_from,
                source_layout_block_id=block.id,
            )
            result_blocks.append(ob)
            if block.role == LayoutRole.PARAGRAPH:
                last_paragraph = ob
            sequence += 1

        for block in non_flow_blocks:
            result_blocks.append(OrderedBlock(
                page_number=block.page_number,
                bbox=block.bbox,
                text=block.text,
                role=block.role,
                heading_level=block.heading_level,
                sequence=-1,   # non-flow: not part of reading sequence
                source_layout_block_id=block.id,
            ))

        return PageReadingOrder(
            page_number=page_layout.page_number, blocks=result_blocks
        ), last_paragraph

    def _order_by_columns(
        self, blocks: list[LayoutBlock], columns
    ) -> list[LayoutBlock]:
        """
        RTL reading order: rightmost column first (lowest index per our
        Stage 2 convention, where index 0 is already assigned left-to-right;
        for RTL we reverse column traversal), top-to-bottom within each.
        """
        span_id_to_col: dict[str, int] = {}
        for col in columns:
            for sid in col.span_ids:
                span_id_to_col[sid] = col.index

        def block_column(block: LayoutBlock) -> int:
            # A LayoutBlock has no direct span_id link at this stage;
            # approximate via x-position against column boundaries instead.
            if not block.bbox or not columns:
                return 0
            x_center = (block.bbox.x0 + block.bbox.x1) / 2
            for col in sorted(columns, key=lambda c: c.index):
                if col.bbox and col.bbox.x0 <= x_center <= col.bbox.x1:
                    return col.index
            return 0

        num_cols = len(columns)
        # RTL: read rightmost (highest index) column first
        return sorted(
            blocks,
            key=lambda b: (
                (num_cols - 1) - block_column(b),
                b.bbox.y0 if b.bbox else 0,
            ),
        )

    def _fallback_order(self, page_layout: PageLayout) -> PageReadingOrder:
        blocks = [
            OrderedBlock(
                page_number=b.page_number, bbox=b.bbox, text=b.text, role=b.role,
                heading_level=b.heading_level, sequence=i,
                source_layout_block_id=b.id,
            )
            for i, b in enumerate(page_layout.blocks)
        ]
        return PageReadingOrder(page_number=page_layout.page_number, blocks=blocks)