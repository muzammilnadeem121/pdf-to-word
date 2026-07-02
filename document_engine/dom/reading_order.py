"""Stage 5 output models: the correctly sequenced reading order."""

from typing import Optional
from pydantic import BaseModel, Field
from document_engine.dom.base import BaseElement, BBox
from document_engine.dom.layout import LayoutRole


class OrderedBlock(BaseElement):
    text: str
    role: LayoutRole
    heading_level: Optional[int] = None
    sequence: int                          # -1 = non-flow (header/footer/page#)
    continues_from_id: Optional[str] = None
    source_layout_block_id: Optional[str] = None


class PageReadingOrder(BaseElement):
    blocks: list[OrderedBlock] = Field(default_factory=list)


class DocumentReadingOrder(BaseModel):
    source_path: str
    pages: list[PageReadingOrder] = Field(default_factory=list)