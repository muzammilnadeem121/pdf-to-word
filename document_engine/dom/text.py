"""
Stage 3 text analysis models.

Represents clean, logical text derived from Stage 1's raw character
spans: merged into words, lines, and paragraph-level text blocks,
with RTL/Unicode repair already applied. No semantic classification
(heading/body/caption) happens yet — that's Stage 4/6.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from document_engine.dom.base import BaseElement, BBox


class TextSource(str, Enum):
    """Where this text came from — needed for confidence and dedup."""
    EMBEDDED = "embedded"   # Direct PDF text extraction (Stage 1 spans)
    OCR      = "ocr"        # Recognized via OCR engine


class TextLine(BaseElement):
    """
    One visually merged line of text — spans on the same line joined
    into a single logical string, in correct reading order (RTL fixed).

    source_span_ids : IDs of the Stage 1 TextSpanRaw elements merged
                       into this line. Empty if source is OCR.
    """
    text:              str
    source:            TextSource
    is_rtl:             bool = False
    language:           Optional[str] = None   # ISO 639-1, e.g. 'ur', 'en'
    font_size:          Optional[float] = None
    is_bold:            bool = False
    is_italic:          bool = False
    ocr_confidence:     Optional[float] = None
    source_span_ids:    list[str] = Field(default_factory=list)


class TextBlock(BaseElement):
    """
    A group of TextLines that are visually contiguous — merged by
    vertical proximity, not yet classified as heading/paragraph/etc.

    This is the unit Stage 4 (Layout Analysis) will classify.
    """
    lines:        list[TextLine] = Field(default_factory=list)
    dominant_language: Optional[str] = None

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def char_count(self) -> int:
        return sum(len(line.text.replace(" ", "")) for line in self.lines)


class PageTextAnalysis(BaseElement):
    """
    Complete Stage 3 output for one page.

    is_scanned  : True if the page had insufficient embedded text and
                  required OCR for all its text.
    is_mixed    : True if the page had some embedded text plus
                  image regions that also received OCR.
    """
    is_scanned:  bool = False
    is_mixed:    bool = False
    blocks:      list[TextBlock] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(b.full_text for b in self.blocks)


class DocumentText(BaseModel):
    """Complete Stage 3 output for a document — input to Stage 4."""
    source_path: str
    pages:       list[PageTextAnalysis] = Field(default_factory=list)