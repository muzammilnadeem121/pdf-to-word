"""
BaseElement
-----------
Shared identity and positional fields for every element in the
Document Object Model, from Stage 1 raw extraction through Stage 7's
final semantic model.

Every element in the pipeline — a text span, a paragraph, a table cell —
descends from this so reading-order, parent/child relationships, and
bounding boxes are represented consistently at every stage.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class BBox(BaseModel):
    """
    Axis-aligned bounding box in PDF points.
    Origin (0,0) is top-left, matching PyMuPDF's coordinate system.
    """
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(self.width, 0) * max(self.height, 0)

    def overlaps(self, other: "BBox", threshold: float = 0.5) -> bool:
        """True if this box overlaps `other` by at least `threshold` of other's area."""
        ix0 = max(self.x0, other.x0)
        iy0 = max(self.y0, other.y0)
        ix1 = min(self.x1, other.x1)
        iy1 = min(self.y1, other.y1)
        if ix0 >= ix1 or iy0 >= iy1:
            return False
        intersection = (ix1 - ix0) * (iy1 - iy0)
        return (intersection / max(other.area, 1e-6)) >= threshold


class BaseElement(BaseModel):
    """
    Base identity fields for any DOM element at any stage.

    id           : Unique identifier, auto-generated.
    parent_id    : ID of the containing element, if any.
    page_number  : 1-based source page. None for document-level elements.
    bbox         : Bounding box in PDF points. None for non-visual elements.
    confidence   : 0.0-1.0. How certain the producing stage is. 1.0 for
                   raw extraction facts (they're just facts), lower for
                   inferred semantic classifications in later stages.
    """
    id:          str            = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id:   Optional[str]  = None
    page_number: Optional[int]  = None
    bbox:        Optional[BBox] = None
    confidence:  float          = 1.0