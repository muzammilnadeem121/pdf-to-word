"""
Stage 2 visual analysis models.

Represents the visual structure of a page: margins, columns,
separator lines, and candidate table/image regions — all purely
geometric facts derived from Stage 1's raw extraction. No semantic
meaning is assigned yet.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from document_engine.dom.base import BaseElement, BBox


class Orientation(str, Enum):
    HORIZONTAL = "horizontal"
    VERTICAL   = "vertical"


class Margins(BaseModel):
    """
    Estimated content margins for a page, derived from the bounding
    extent of all text spans and drawings.
    """
    top:    float
    bottom: float
    left:   float
    right:  float


class ColumnRegion(BaseElement):
    """
    A detected vertical column of content on a page.

    index         : 0-based column index, left-to-right in PDF coordinate
                     space (Stage 5 handles RTL reading order separately).
    span_ids      : IDs of TextSpanRaw elements whose x-center falls in
                     this column's x-range.
    """
    index:    int
    span_ids: list[str] = Field(default_factory=list)


class Separator(BaseElement):
    """
    A detected horizontal or vertical rule/divider line, sourced from
    a DrawingRaw flagged as is_line=True in Stage 1.
    """
    orientation: Orientation
    source_drawing_id: str


class TableRegion(BaseElement):
    """
    A candidate table region — a rectangular area with grid-like
    intersecting lines, or a dense cluster of aligned rectangles.

    This is a geometric candidate only. Stage 4/6 confirms whether
    it actually contains tabular text data.
    """
    row_lines:    list[str] = Field(default_factory=list)   # Separator IDs
    column_lines: list[str] = Field(default_factory=list)   # Separator IDs


class ImageRegion(BaseElement):
    """
    A classified image region, built from an ImageRaw plus simple
    geometric heuristics.

    is_likely_logo  : Small, near-square, positioned in a margin zone.
    is_likely_photo : Large, non-square-extreme, positioned in content area.
    source_image_id : ID of the underlying ImageRaw.
    """
    source_image_id: str
    is_likely_logo:  bool = False
    is_likely_photo: bool = False


class WhitespaceRegion(BaseModel):
    """A significant empty rectangular gap between content elements."""
    bbox: BBox


class PageVisual(BaseElement):
    """
    Complete Stage 2 output for a single page.
    """
    margins:     Margins
    columns:     list[ColumnRegion]     = Field(default_factory=list)
    separators:  list[Separator]        = Field(default_factory=list)
    tables:      list[TableRegion]      = Field(default_factory=list)
    images:      list[ImageRegion]      = Field(default_factory=list)
    whitespace:  list[WhitespaceRegion] = Field(default_factory=list)


class DocumentVisual(BaseModel):
    """Complete Stage 2 output for a document — input to Stage 3."""
    source_path: str
    pages:       list[PageVisual] = Field(default_factory=list)