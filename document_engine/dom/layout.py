"""
Stage 4 layout analysis models.

Assigns semantic roles to Stage 3's merged text lines: heading,
paragraph, list item, caption, footnote, page number, header, footer,
quotation, reference. Classification is driven by measurable signals
(font size, position, indentation, repetition) — never guessed.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from document_engine.dom.base import BaseElement, BBox


class LayoutRole(str, Enum):
    HEADING     = "heading"
    PARAGRAPH   = "paragraph"
    LIST_ITEM   = "list_item"
    CAPTION     = "caption"
    FOOTNOTE    = "footnote"
    PAGE_NUMBER = "page_number"
    HEADER      = "header"
    FOOTER      = "footer"
    QUOTATION   = "quotation"
    REFERENCE   = "reference"
    UNKNOWN     = "unknown"


class LayoutBlock(BaseElement):
    """
    One classified line of text with its assigned semantic role.

    source_line_id  : ID of the Stage 3 TextLine this was built from.
    heading_level   : 1-3 for HEADING role, None otherwise.
    list_level      : 0-based nesting depth for LIST_ITEM role.
    reason          : Human-readable explanation of the classification,
                       for debugging — mirrors the old ScanDetector pattern.
    """
    text:            str
    role:            LayoutRole
    heading_level:   Optional[int] = None
    list_level:      int = 0
    font_size:       Optional[float] = None
    is_bold:         bool = False
    is_italic:       bool = False
    is_rtl:          bool = False
    source_line_id:  Optional[str] = None
    reason:          str = ""


class PageLayout(BaseElement):
    """Complete Stage 4 output for one page: its lines, all classified."""
    blocks: list[LayoutBlock] = Field(default_factory=list)


class DocumentLayout(BaseModel):
    """
    Complete Stage 4 output for a document — input to Stage 5.

    detected_header_pattern / detected_footer_pattern : the normalized
    repeated text found across pages, if any. Useful for debugging and
    for Stage 6 to confirm/override.
    """
    source_path: str
    pages: list[PageLayout] = Field(default_factory=list)
    detected_header_pattern: Optional[str] = None
    detected_footer_pattern: Optional[str] = None