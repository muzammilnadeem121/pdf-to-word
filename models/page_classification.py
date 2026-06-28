"""
PageClassification
------------------
The result of analysing a single PDF page to determine
whether it needs OCR, direct extraction, or both.

This is a pure data model — no logic lives here.
"""

from dataclasses import dataclass
from enum import Enum


class PageType(str, Enum):
    """
    Classification of a PDF page.

    DIGITAL  — Has reliable embedded text. Extract directly.
    SCANNED  — No usable text. Must use OCR.
    MIXED    — Partial text + significant image area. Use both.
    """
    DIGITAL = "digital"
    SCANNED = "scanned"
    MIXED   = "mixed"


@dataclass
class PageClassification:
    """
    Full classification result for one PDF page.

    Attributes
    ----------
    page_number : int
        1-based page number.
    page_type : PageType
        The determined type of this page.
    confidence : float
        0.0 – 1.0. How confident the detector is in this classification.
        1.0 = certain, 0.5 = borderline, 0.0 = unknown.
    char_count : int
        Non-whitespace characters found in the text layer.
    image_coverage : float
        Fraction of page area covered by raster images (0.0 – 1.0).
    urdu_char_ratio : float
        Fraction of characters in valid Urdu/Arabic Unicode ranges.
    reason : str
        Human-readable explanation of why this classification was made.
        Useful for debugging and logging.
    """
    page_number:    int
    page_type:      PageType
    confidence:     float
    char_count:     int
    image_coverage: float
    urdu_char_ratio: float
    reason:         str

    @property
    def is_scanned(self) -> bool:
        return self.page_type == PageType.SCANNED

    @property
    def is_digital(self) -> bool:
        return self.page_type == PageType.DIGITAL

    @property
    def is_mixed(self) -> bool:
        return self.page_type == PageType.MIXED

    @property
    def needs_ocr(self) -> bool:
        """True if OCR should run on this page."""
        return self.page_type in (PageType.SCANNED, PageType.MIXED)

    @property
    def needs_extraction(self) -> bool:
        """True if direct text extraction should run on this page."""
        return self.page_type in (PageType.DIGITAL, PageType.MIXED)