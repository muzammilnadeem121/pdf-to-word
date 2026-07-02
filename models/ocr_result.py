"""
OCR data models.

These are the structured outputs of the OCR engine.
They are separate from PageResult so the OCR engine has no
dependency on the extractor — the data flows one way.
"""

from dataclasses import dataclass, field


@dataclass
class OCRBlock:
    """
    A single recognized text region on the page.

    Attributes
    ----------
    text       : The recognized string for this region.
    confidence : PaddleOCR confidence score (0.0 – 1.0).
    bbox       : Four corner points as [[x0,y0],[x1,y0],[x1,y1],[x0,y1]].
                 Coordinates are in image pixels at the render DPI.
    """
    text:       str
    confidence: float
    bbox:       list[list[float]]

    @property
    def top_y(self) -> float:
        """Top edge of the bounding box (min Y of the four corners)."""
        return min(pt[1] for pt in self.bbox)

    @property
    def left_x(self) -> float:
        """Left edge of the bounding box (min X)."""
        return min(pt[0] for pt in self.bbox)

    @property
    def right_x(self) -> float:
        """Right edge of the bounding box (max X)."""
        return max(pt[0] for pt in self.bbox)


@dataclass
class OCRResult:
    """
    Full OCR result for a single page.

    Attributes
    ----------
    page_number        : 1-based page number.
    full_text          : All recognized text joined in reading order.
    average_confidence : Mean confidence across all blocks.
    blocks             : Individual OCRBlock results, sorted reading order.
    processing_time_ms : Wall-clock time for OCR on this page.
    """
    page_number:         int
    full_text:           str
    average_confidence:  float
    blocks:              list[OCRBlock] = field(default_factory=list)
    processing_time_ms:  float = 0.0

    @property
    def is_empty(self) -> bool:
        return not self.full_text.strip()