"""
Stage 7 — the canonical Document Object Model.

This is the final, complete, self-sufficient representation of the
document. No exporter (Stage 8) is allowed to access the PDF or any
earlier-stage object directly — every exporter consumes only this.
"""

from typing import Optional
from pydantic import BaseModel, Field

from document_engine.dom.semantic import SemanticElement
from document_engine.dom.raw import DocumentMetadataRaw, ImageRaw
from document_engine.dom.visual import Margins


class DocumentPage(BaseModel):
    page_number: int
    width: float
    height: float
    elements: list[SemanticElement] = Field(default_factory=list)


class Document(BaseModel):
    """The canonical, self-sufficient Document Object Model."""
    source_path: str
    metadata:    DocumentMetadataRaw
    pages:       list[DocumentPage] = Field(default_factory=list)
    images:      list[ImageRaw]     = Field(default_factory=list)  # for exporters needing to embed originals

    def all_elements(self) -> list[SemanticElement]:
        result = []
        for page in self.pages:
            result.extend(page.elements)
        return sorted(result, key=lambda e: (e.page_number, e.sequence))