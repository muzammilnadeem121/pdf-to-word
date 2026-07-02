"""
Stage 1 raw extraction models.

These represent facts about a PDF with zero interpretation:
what characters exist, where, in what font, what vector graphics
are drawn, what images are embedded. No classification of any kind
happens at this layer — that begins at Stage 4 (Layout Analysis).
"""

from typing import Optional

from pydantic import BaseModel, Field

from document_engine.dom.base import BaseElement, BBox


class FontInfo(BaseModel):
    """Raw font attributes for a text span, as reported by PyMuPDF."""
    name:      str
    size:      float
    color_rgb: Optional[tuple[int, int, int]] = None  # None = default/black
    is_bold:   bool = False
    is_italic: bool = False


class TextSpanRaw(BaseElement):
    """
    A single contiguous run of text sharing one font/size/color,
    exactly as PyMuPDF's get_text('dict') reports it.

    This is the smallest text unit at Stage 1. Later stages merge
    spans into words, lines, and paragraphs.
    """
    text: str
    font: FontInfo


class DrawingRaw(BaseElement):
    """
    A single vector graphic path: filled rectangle, stroked line,
    curve, or polygon — exactly as PyMuPDF's get_drawings() reports it.

    fill_rgb / stroke_rgb are None when that property isn't set on
    the path (e.g. a stroke-only rectangle has fill_rgb=None).
    """
    fill_rgb:     Optional[tuple[int, int, int]] = None
    stroke_rgb:   Optional[tuple[int, int, int]] = None
    stroke_width: float = 0.0
    is_line:      bool  = False   # True if height or width is near-zero


class ImageRaw(BaseElement):
    """
    A single embedded raster image, exactly as it appears in the
    PDF's XObject table — before any size/relevance filtering.
    """
    xref:        int
    width_px:    int
    height_px:   int
    colorspace:  str


class PageRaw(BaseElement):
    """
    All raw facts extracted from a single PDF page.

    Nothing on this page has been classified yet — it's the complete
    unfiltered inventory of what exists: every span, every drawing,
    every image, plus the page's physical dimensions and rotation.
    """
    width:      float
    height:     float
    rotation:   int = 0
    text_spans: list[TextSpanRaw] = Field(default_factory=list)
    drawings:   list[DrawingRaw]  = Field(default_factory=list)
    images:     list[ImageRaw]    = Field(default_factory=list)


class DocumentMetadataRaw(BaseModel):
    """PDF-level metadata from the document info dictionary."""
    title:        Optional[str] = None
    author:       Optional[str] = None
    subject:      Optional[str] = None
    creator:      Optional[str] = None
    producer:     Optional[str] = None
    creation_date: Optional[str] = None
    page_count:   int = 0


class DocumentRaw(BaseModel):
    """
    Complete Stage 1 output for one PDF file.

    This is the sole input to Stage 2 (Visual Analysis). Nothing
    downstream ever re-opens the PDF file — everything needed lives
    in this object.
    """
    source_path: str
    metadata:    DocumentMetadataRaw
    pages:       list[PageRaw] = Field(default_factory=list)