"""
ScanDetector
------------
Classifies a PDF page as DIGITAL, SCANNED, or MIXED using
three independent signals combined into a single confidence score.

Signals
-------
1. Character density   — raw non-whitespace char count
2. Image coverage      — raster image area as fraction of page area
3. Urdu character ratio — fraction of chars in Arabic/Urdu Unicode blocks

Design principles
-----------------
- No single signal is decisive on its own.
- Each signal produces a score; scores are weighted and combined.
- The final PageClassification includes the reason, so bugs are debuggable.
- Thresholds are constructor parameters — easy to tune per use case.
"""

import logging
from typing import Sequence

import fitz  # PyMuPDF

from models.page_classification import PageClassification, PageType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unicode ranges for Arabic script (covers Urdu)
# ---------------------------------------------------------------------------
# Arabic block:               U+0600 – U+06FF
# Arabic Supplement:          U+0750 – U+077F
# Arabic Extended-A:          U+08A0 – U+08FF
# Arabic Presentation Forms-A: U+FB50 – U+FDFF  ← common in legacy Urdu PDFs
# Arabic Presentation Forms-B: U+FE70 – U+FEFF

_URDU_RANGES: Sequence[tuple[int, int]] = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)


def _is_urdu_char(ch: str) -> bool:
    """Return True if the character belongs to an Arabic/Urdu Unicode block."""
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _URDU_RANGES)


def _urdu_ratio(text: str) -> float:
    """
    Fraction of non-whitespace characters that are Urdu/Arabic script.

    Returns 0.0 if text is empty.
    """
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    urdu = sum(1 for c in chars if _is_urdu_char(c))
    return urdu / len(chars)


def _image_coverage(page: fitz.Page) -> float:
    """
    Fraction of the page area covered by raster images.

    PyMuPDF exposes image bounding boxes via page.get_images(full=True)
    and page.get_image_bbox(). We sum the image areas and divide by the
    total page area.

    Returns a value in [0.0, 1.0].
    """
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return 0.0

    total_image_area = 0.0
    try:
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                bbox = page.get_image_bbox(img)
                w = abs(bbox.x1 - bbox.x0)
                h = abs(bbox.y1 - bbox.y0)
                total_image_area += w * h
            except Exception:
                # Some images can't be located — skip them
                continue
    except Exception as exc:
        logger.debug("Could not enumerate images on page %d: %s", page.number + 1, exc)

    coverage = min(total_image_area / page_area, 1.0)
    return coverage


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class ScanDetector:
    """
    Classifies a PDF page as DIGITAL, SCANNED, or MIXED.

    Parameters
    ----------
    min_chars : int
        Minimum non-whitespace characters to consider a text layer real.
        Below this → strong scanned signal. Default: 20.
    scanned_image_threshold : float
        Image coverage above this → strong scanned signal. Default: 0.85.
    mixed_image_threshold : float
        Image coverage above this but below scanned_image_threshold
        → MIXED signal. Default: 0.40.
    min_urdu_ratio : float
        If text exists but Urdu char ratio is below this, the text layer
        is suspect (ghost text / mojibake). Default: 0.30.
    """

    def __init__(
        self,
        min_chars:               int   = 20,
        scanned_image_threshold: float = 0.85,
        mixed_image_threshold:   float = 0.65,
        min_urdu_ratio:          float = 0.30,
    ) -> None:
        self.min_chars               = min_chars
        self.scanned_image_threshold = scanned_image_threshold
        self.mixed_image_threshold   = mixed_image_threshold
        self.min_urdu_ratio          = min_urdu_ratio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, page: fitz.Page) -> PageClassification:
        """
        Classify a single PDF page.

        Parameters
        ----------
        page : fitz.Page

        Returns
        -------
        PageClassification
        """
        page_num = page.number + 1

        try:
            raw_text   = page.get_text("text")
            char_count = len(raw_text.strip().replace(" ", "").replace("\n", ""))
            img_cover  = _image_coverage(page)
            urdu_ratio = _urdu_ratio(raw_text)
        except Exception as exc:
            logger.warning("Could not read page %d: %s — treating as scanned.", page_num, exc)
            return PageClassification(
                page_number    = page_num,
                page_type      = PageType.SCANNED,
                confidence     = 0.6,
                char_count     = 0,
                image_coverage = 0.0,
                urdu_char_ratio= 0.0,
                reason         = f"Page read error: {exc}",
            )

        page_type, confidence, reason = self._decide(
            char_count, img_cover, urdu_ratio
        )

        classification = PageClassification(
            page_number     = page_num,
            page_type       = page_type,
            confidence      = confidence,
            char_count      = char_count,
            image_coverage  = img_cover,
            urdu_char_ratio = urdu_ratio,
            reason          = reason,
        )

        logger.debug(
            "Page %d → %s (conf=%.2f) | chars=%d img=%.0f%% urdu=%.0f%% | %s",
            page_num,
            page_type.value.upper(),
            confidence,
            char_count,
            img_cover * 100,
            urdu_ratio * 100,
            reason,
        )

        return classification

    # Keep the old boolean API working so Milestone 3 tests don't break
    def is_scanned(self, page: fitz.Page) -> bool:
        """Backward-compatible wrapper. Prefer classify() for new code."""
        return self.classify(page).is_scanned

    # ------------------------------------------------------------------
    # Private decision logic
    # ------------------------------------------------------------------

    def _decide(
        self,
        char_count: int,
        img_cover:  float,
        urdu_ratio: float,
    ) -> tuple[PageType, float, str]:
        """
        Combine the three signals into a single classification.

        Returns (PageType, confidence, reason_string).

        Decision tree
        -------------
        1. Huge image + almost no text → SCANNED (high confidence)
        2. Huge image + some text      → MIXED   (medium confidence)
        3. No text at all              → SCANNED (high confidence)
        4. Text exists but looks like
           mojibake (low urdu ratio)   → SCANNED (medium confidence)
        5. Text exists, image moderate → MIXED   (medium confidence)
        6. Text exists, image small    → DIGITAL (high confidence)
        """

        has_text       = char_count >= self.min_chars
        high_image     = img_cover >= self.scanned_image_threshold
        moderate_image = img_cover >= self.mixed_image_threshold
        good_urdu      = urdu_ratio >= self.min_urdu_ratio or urdu_ratio == 0.0
        # urdu_ratio == 0.0 is allowed for pages with Latin text (headings, etc.)

        # ── Rule 1: Clearly scanned ───────────────────────────────────────
        if high_image and not has_text:
            return (
                PageType.SCANNED,
                0.95,
                f"Image covers {img_cover:.0%} of page and only {char_count} chars found.",
            )

        # ── Rule 2: Ghost-text layer (scanned + fake OCR overlay) ─────────
        if high_image and has_text and not good_urdu:
            return (
                PageType.SCANNED,
                0.80,
                f"Image covers {img_cover:.0%} and text layer has low Urdu ratio "
                f"({urdu_ratio:.0%}) — likely mojibake ghost text.",
            )

        # ── Rule 3: High image + real text → mixed ────────────────────────
        if high_image and has_text and good_urdu:
            return (
                PageType.MIXED,
                0.75,
                f"Image covers {img_cover:.0%} but {char_count} valid Urdu chars found.",
            )

        # ── Rule 4: No text at all ────────────────────────────────────────
        if not has_text and not moderate_image:
            return (
                PageType.SCANNED,
                0.85,
                f"Only {char_count} chars found (threshold: {self.min_chars}). "
                "Page may be blank or fully scanned.",
            )

        # ── Rule 5: Moderate image presence + real text → mixed ───────────
        if moderate_image and has_text and good_urdu:
            return (
                PageType.MIXED,
                0.65,
                f"Image covers {img_cover:.0%} of page alongside "
                f"{char_count} Urdu chars — treating as mixed.",
            )

        # ── Rule 6: Low image, text present, good Urdu ratio → digital ────
        if has_text and good_urdu:
            return (
                PageType.DIGITAL,
                0.92,
                f"{char_count} chars found, {urdu_ratio:.0%} Urdu, "
                f"image only {img_cover:.0%} of page.",
            )

        # ── Fallback ──────────────────────────────────────────────────────
        # Shouldn't reach here with normal PDFs, but never crash.
        return (
            PageType.SCANNED,
            0.50,
            f"Fallback: chars={char_count}, img={img_cover:.0%}, urdu={urdu_ratio:.0%}.",
        )