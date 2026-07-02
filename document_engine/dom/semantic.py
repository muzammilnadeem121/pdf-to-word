"""Stage 6 output: semantically grouped elements — paragraphs merged
across continuation, image+caption pairs, list groups, table structures."""

from typing import Optional
from pydantic import BaseModel, Field
from document_engine.dom.base import BaseElement, BBox
from document_engine.dom.layout import LayoutRole


class SemanticElementType(str):
    pass


class SemanticElement(BaseElement):
    """One semantically complete unit — a merged paragraph, an image+caption
    pair, a full list, a full table, or a standalone heading."""
    element_type: str            # 'heading' | 'paragraph' | 'list' | 'image_caption' | 'table' | 'quotation' | 'reference' | 'footnote'
    text: str = ""
    heading_level: Optional[int] = None
    list_items: list[str] = Field(default_factory=list)
    image_id: Optional[str] = None
    caption_text: Optional[str] = None
    table_data: list[list[str]] = Field(default_factory=list)
    sequence: int = 0
    source_block_ids: list[str] = Field(default_factory=list)


class DocumentSemantic(BaseModel):
    source_path: str
    elements: list[SemanticElement] = Field(default_factory=list)