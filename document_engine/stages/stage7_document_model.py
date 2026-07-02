"""
Stage 7 — Document Model Builder
-----------------------------------
Assembles the final Document from all prior stage outputs. This is the
last stage that touches Stage 1-6 objects — everything after this
consumes Document exclusively.
"""

import logging
from pathlib import Path

from document_engine.dom.document import Document, DocumentPage
from document_engine.dom.raw import DocumentRaw
from document_engine.dom.semantic import DocumentSemantic

logger = logging.getLogger(__name__)


class DocumentModelBuilder:

    def build(self, doc_raw: DocumentRaw, doc_semantic: DocumentSemantic) -> Document:
        pages_by_number: dict[int, DocumentPage] = {
            p.page_number: DocumentPage(page_number=p.page_number, width=p.width, height=p.height)
            for p in doc_raw.pages
        }

        for element in doc_semantic.elements:
            page = pages_by_number.get(element.page_number)
            if page:
                page.elements.append(element)

        all_images = [img for p in doc_raw.pages for img in p.images]

        document = Document(
            source_path=doc_raw.source_path,
            metadata=doc_raw.metadata,
            pages=sorted(pages_by_number.values(), key=lambda p: p.page_number),
            images=all_images,
        )

        logger.info(
            "Stage 7 complete: Document built with %d pages, %d total elements.",
            len(document.pages), sum(len(p.elements) for p in document.pages),
        )
        return document

    def extract_and_save(
        self, doc_raw: DocumentRaw, doc_semantic: DocumentSemantic, debug_output_path: str
    ) -> Document:
        result = self.build(doc_raw, doc_semantic)
        Path(debug_output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result