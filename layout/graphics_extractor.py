"""
GraphicsExtractor
-----------------
Extracts vector graphic elements from PDF pages using PyMuPDF's
get_drawings() API.

get_drawings() returns every path drawn on the page: rectangles,
lines, curves, polygons. For each one we get:
  - fill color  (the box background)
  - stroke color (the border)
  - bounding rect
  - stroke width

We use this to answer: "what colored box does this text block
sit inside?" That lets us reproduce the visual structure of the
PDF in the DOCX without hardcoding anything document-specific.

Supported elements
------------------
- Filled rectangles  → paragraph background shading
- Stroked rectangles → paragraph border
- Horizontal lines   → paragraph top/bottom border
- Filled + stroked   → background + border combined

Ignored elements
----------------
- Curves and complex paths (logos, illustrations) → kept as images
- Very thin lines < 0.5pt → likely PDF artifacts, not visible borders
- White fills on white background → invisible, skip
- Full-page fills → page background, not a content box
"""

import logging
from dataclasses import dataclass
from typing import Optional

import fitz

logger = logging.getLogger(__name__)

# Skip fills that are essentially white (within this distance of 1.0)
_WHITE_THRESHOLD  = 0.95

# Skip fills that cover most of the page (likely a background wash)
_PAGE_FILL_RATIO  = 0.85

# Minimum box area to consider (points²) — filters out hairlines
_MIN_BOX_AREA     = 20 * 4   # 20pt wide × 4pt tall minimum

# Minimum stroke width to register as a visible border
_MIN_STROKE_WIDTH = 0.4


def _rgb_to_255(color: tuple) -> tuple[int, int, int]:
    """Convert PyMuPDF's 0.0–1.0 RGB tuple to 0–255 integers."""
    r, g, b = color
    return (int(r * 255), int(g * 255), int(b * 255))


def _is_white(color: tuple) -> bool:
    """Return True if the color is essentially white."""
    return all(c >= _WHITE_THRESHOLD for c in color)


def _is_black(color: tuple) -> bool:
    """Return True if the color is essentially black."""
    return all(c <= 0.05 for c in color)


@dataclass
class GraphicBox:
    """
    A detected vector graphic element on a PDF page.

    Attributes
    ----------
    rect         : Bounding rectangle in PDF points (x0, y0, x1, y1).
    fill_rgb     : Background fill color in 0–255 RGB. None = transparent.
    stroke_rgb   : Border color in 0–255 RGB. None = no border.
    stroke_width : Border width in points.
    is_line      : True if this is a horizontal/vertical line rather than a box.
    """
    rect:         tuple[float, float, float, float]
    fill_rgb:     Optional[tuple[int, int, int]] = None
    stroke_rgb:   Optional[tuple[int, int, int]] = None
    stroke_width: float = 0.0
    is_line:      bool  = False

    @property
    def x0(self) -> float: return self.rect[0]
    @property
    def y0(self) -> float: return self.rect[1]
    @property
    def x1(self) -> float: return self.rect[2]
    @property
    def y1(self) -> float: return self.rect[3]
    @property
    def width(self) -> float:  return self.x1 - self.x0
    @property
    def height(self) -> float: return self.y1 - self.y0
    @property
    def area(self) -> float:   return self.width * self.height

    def contains_point(self, x: float, y: float, margin: float = 4.0) -> bool:
        """Return True if (x, y) is inside or near this box."""
        return (
            self.x0 - margin <= x <= self.x1 + margin and
            self.y0 - margin <= y <= self.y1 + margin
        )

    def overlaps_rect(
        self,
        x0: float, y0: float, x1: float, y1: float,
        threshold: float = 0.5,
    ) -> bool:
        """
        Return True if this box overlaps the given rect by at least
        `threshold` fraction of the given rect's area.
        """
        ix0 = max(self.x0, x0)
        iy0 = max(self.y0, y0)
        ix1 = min(self.x1, x1)
        iy1 = min(self.y1, y1)

        if ix0 >= ix1 or iy0 >= iy1:
            return False

        intersection = (ix1 - ix0) * (iy1 - iy0)
        text_area    = max((x1 - x0) * (y1 - y0), 1)
        return (intersection / text_area) >= threshold


class GraphicsExtractor:
    """
    Extracts vector graphic decoration from PDF pages.

    Parameters
    ----------
    min_box_area    : Ignore boxes smaller than this (points²).
    min_stroke_width: Ignore strokes thinner than this (points).
    page_fill_ratio : Ignore fills covering more than this fraction of page.
    """

    def __init__(
        self,
        min_box_area:     float = _MIN_BOX_AREA,
        min_stroke_width: float = _MIN_STROKE_WIDTH,
        page_fill_ratio:  float = _PAGE_FILL_RATIO,
    ) -> None:
        self.min_box_area     = min_box_area
        self.min_stroke_width = min_stroke_width
        self.page_fill_ratio  = page_fill_ratio

    def extract_page_graphics(
        self, page: fitz.Page
    ) -> list[GraphicBox]:
        """
        Extract all meaningful graphic boxes from a single PDF page.

        Parameters
        ----------
        page : fitz.Page

        Returns
        -------
        list[GraphicBox], sorted top-to-bottom.
        """
        page_area = page.rect.width * page.rect.height
        boxes: list[GraphicBox] = []

        try:
            drawings = page.get_drawings()
        except Exception as exc:
            logger.warning("get_drawings() failed on page %d: %s",
                           page.number + 1, exc)
            return []

        for drawing in drawings:
            box = self._process_drawing(drawing, page_area)
            if box:
                boxes.append(box)

        # Sort top-to-bottom
        boxes.sort(key=lambda b: b.y0)

        logger.debug(
            "Page %d: %d graphic boxes extracted.",
            page.number + 1, len(boxes),
        )
        return boxes

    def find_container(
        self,
        text_x0: float, text_y0: float,
        text_x1: float, text_y1: float,
        boxes:   list[GraphicBox],
    ) -> Optional[GraphicBox]:
        """
        Find the most specific (smallest area) graphic box that
        contains or significantly overlaps a text block.

        This tells us: "what colored box does this text live inside?"

        Parameters
        ----------
        text_x0, text_y0, text_x1, text_y1 : Text block bounding box.
        boxes : All GraphicBox objects for the page.

        Returns
        -------
        GraphicBox or None.
        """
        candidates = [
            box for box in boxes
            if not box.is_line and
               box.overlaps_rect(text_x0, text_y0, text_x1, text_y1)
        ]

        if not candidates:
            return None

        # Return the smallest matching box — most specific container
        return min(candidates, key=lambda b: b.area)

    def find_adjacent_lines(
        self,
        text_y0: float,
        text_y1: float,
        boxes:   list[GraphicBox],
        margin:  float = 6.0,
    ) -> tuple[Optional[GraphicBox], Optional[GraphicBox]]:
        """
        Find horizontal lines immediately above and below a text block.
        Used to add top/bottom borders to paragraphs that sit between lines.

        Returns (top_line, bottom_line) — either may be None.
        """
        top_line    = None
        bottom_line = None

        for box in boxes:
            if not box.is_line:
                continue
            # Line just above this text block
            if abs(box.y1 - text_y0) <= margin:
                top_line = box
            # Line just below
            if abs(box.y0 - text_y1) <= margin:
                bottom_line = box

        return top_line, bottom_line

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _process_drawing(
        self, drawing: dict, page_area: float
    ) -> Optional[GraphicBox]:
        """
        Convert a PyMuPDF drawing dict into a GraphicBox.
        Returns None if the drawing should be ignored.
        """
        rect = drawing.get("rect")
        if not rect:
            return None

        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
        w = abs(x1 - x0)
        h = abs(y1 - y0)

        # ── Detect horizontal/vertical lines ─────────────────────────
        is_line = h < 3.0 or w < 3.0

        if not is_line:
            # Skip tiny boxes
            if w * h < self.min_box_area:
                return None
            # Skip full-page background fills
            if (w * h) / max(page_area, 1) > self.page_fill_ratio:
                return None

        # ── Fill color ────────────────────────────────────────────────
        fill_rgb  = None
        raw_fill  = drawing.get("fill")
        if raw_fill and len(raw_fill) >= 3 and not _is_white(raw_fill):
            fill_rgb = _rgb_to_255(raw_fill[:3])

        # ── Stroke color ──────────────────────────────────────────────
        stroke_rgb = None
        raw_stroke = drawing.get("color")
        stroke_w   = drawing.get("width") or 0.0

        if (
            raw_stroke and
            len(raw_stroke) >= 3 and
            stroke_w >= self.min_stroke_width and
            not _is_white(raw_stroke)
        ):
            stroke_rgb = _rgb_to_255(raw_stroke[:3])

        # Skip drawings with neither fill nor stroke
        if fill_rgb is None and stroke_rgb is None:
            return None

        return GraphicBox(
            rect         = (x0, y0, x1, y1),
            fill_rgb     = fill_rgb,
            stroke_rgb   = stroke_rgb,
            stroke_width = stroke_w,
            is_line      = is_line,
        )