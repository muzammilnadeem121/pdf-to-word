"""
LayoutDetector
--------------
Full pipeline as of Milestone 9:
  Pass 1 — Compute body font size baseline.
  Pass 2 — Per page:
              a. Detect and extract tables (TableDetector)
              b. Extract images (ImageExtractor)
              c. Classify remaining text blocks
              d. Detect and reorder columns (ColumnDetector)
"""

import logging
import re
import statistics
from pathlib import Path
from typing import Optional

import fitz
import pdfplumber

from extractor.extractor import ExtractionResult, PageResult
from layout.column_detector import detect_columns
from layout.image_extractor import ImageExtractor
from layout.table_detector import TableDetector
from models.layout_block import Alignment, BlockType, LayoutBlock

logger = logging.getLogger(__name__)

_HEADING_SIZE_RATIO   = 1.20
_HEADING_MAX_WORDS    = 8
_PAGE_NUM_MAX_CHARS   = 6
_MARGIN_ZONE_FRACTION = 0.08
_NUMERIC_LINE         = re.compile(r"^\s*[\d\u0660-\u0669\u06F0-\u06F9]+\s*$")


def _detect_alignment(x0: float, x1: float, page_width: float) -> Alignment:
    if page_width <= 0:
        return Alignment.RIGHT
    centre_page  = page_width / 2
    block_centre = (x0 + x1) / 2
    if abs(block_centre - centre_page) < page_width * 0.15:
        return Alignment.CENTER
    if x1 >= page_width * 0.85:
        return Alignment.RIGHT
    if x0 <= page_width * 0.15:
        return Alignment.LEFT
    return Alignment.RIGHT


def _is_rtl_text(text: str) -> bool:
    rtl = sum(1 for c in text if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F")
    return rtl > len(text) * 0.3


class LayoutDetector:

    def __init__(
        self,
        heading_size_ratio: float = _HEADING_SIZE_RATIO,
        heading_max_words:  int   = _HEADING_MAX_WORDS,
        margin_zone:        float = _MARGIN_ZONE_FRACTION,
        image_extractor:    Optional[ImageExtractor]  = None,
        table_detector:     Optional[TableDetector]   = None,
    ) -> None:
        self.heading_size_ratio = heading_size_ratio
        self.heading_max_words  = heading_max_words
        self.margin_zone        = margin_zone
        self._image_extractor   = image_extractor or ImageExtractor()
        self._table_detector    = table_detector  or TableDetector()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, pdf_path: str, extraction: ExtractionResult) -> list[LayoutBlock]:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        all_blocks: list[LayoutBlock] = []

        try:
            fitz_doc = fitz.open(str(path))

            with pdfplumber.open(str(path)) as pdf:
                body_font_size = self._compute_body_font_size(pdf)
                logger.info("Body font size baseline: %.1fpt", body_font_size)

                for page_result in extraction.pages:
                    page_idx = page_result.page_number - 1

                    if page_idx >= len(pdf.pages):
                        continue

                    plumber_page = pdf.pages[page_idx]
                    fitz_page    = fitz_doc[page_idx]
                    page_width   = plumber_page.width or 1

                    # ── Tables ───────────────────────────────────────
                    table_blocks = self._table_detector.extract_page_tables(
                        plumber_page, page_result.page_number
                    )

                    # Get bounding boxes of table regions so we can
                    # exclude those words from text classification
                    table_bboxes = self._get_table_bboxes(plumber_page)

                    # ── Images ───────────────────────────────────────
                    image_blocks = self._image_extractor.extract_page_images(
                        fitz_doc, fitz_page, page_result.page_number
                    )

                    # ── Text blocks ──────────────────────────────────
                    if page_result.needs_ocr and not page_result.is_mixed:
                        text_blocks = self._detect_scanned_page(page_result, plumber_page)
                    else:
                        text_blocks = self._detect_digital_page(
                            page_result, plumber_page,
                            body_font_size, table_bboxes,
                        )

                    # ── Column reordering ────────────────────────────
                    page_blocks = text_blocks + table_blocks + image_blocks
                    page_blocks = detect_columns(page_blocks, page_width)

                    all_blocks.extend(page_blocks)

            fitz_doc.close()

        except Exception as exc:
            logger.error("Layout detection failed: %s — using fallback.", exc)
            all_blocks = self._fallback_plain_text(extraction)

        logger.info("Layout detection complete: %d blocks.", len(all_blocks))
        return all_blocks

    # ------------------------------------------------------------------
    # Table bbox helper
    # ------------------------------------------------------------------

    def _get_table_bboxes(
        self, plumber_page: pdfplumber.page.Page
    ) -> list[tuple[float, float, float, float]]:
        """
        Return bounding boxes of all detected tables.
        Used to exclude table words from text classification.
        """
        try:
            return [t.bbox for t in plumber_page.find_tables()]
        except Exception:
            return []

    def _word_in_table(
        self, word: dict, table_bboxes: list[tuple]
    ) -> bool:
        """Return True if a word's position overlaps any table region."""
        wx0, wx1 = word.get("x0", 0), word.get("x1", 0)
        wtop = word.get("top", 0)
        for (tx0, ttop, tx1, tbottom) in table_bboxes:
            if wx0 >= tx0 and wx1 <= tx1 and wtop >= ttop and wtop <= tbottom:
                return True
        return False

    # ------------------------------------------------------------------
    # Pass 1: Body font size
    # ------------------------------------------------------------------

    def _compute_body_font_size(self, pdf: pdfplumber.PDF) -> float:
        sizes: list[float] = []
        for page in pdf.pages[:10]:
            try:
                for word in page.extract_words(extra_attrs=["size"]):
                    size = word.get("size")
                    if size and 6 <= size <= 72:
                        sizes.extend([size] * len(word.get("text", "")))
            except Exception:
                continue
        return statistics.median(sizes) if sizes else 12.0

    # ------------------------------------------------------------------
    # Pass 2a: Digital page
    # ------------------------------------------------------------------

    def _detect_digital_page(
        self,
        page_result:   PageResult,
        plumber_page:  pdfplumber.page.Page,
        body_size:     float,
        table_bboxes:  list[tuple],
    ) -> list[LayoutBlock]:
        blocks:      list[LayoutBlock] = []
        page_height  = plumber_page.height or 1
        page_width   = plumber_page.width  or 1

        try:
            words = plumber_page.extract_words(
                extra_attrs=["size", "fontname", "upright"]
            )
        except Exception as exc:
            logger.warning("pdfplumber failed on page %d: %s",
                           page_result.page_number, exc)
            return self._fallback_page_text(page_result)

        if not words:
            return self._fallback_page_text(page_result)

        # Exclude words that fall inside detected table regions
        words = [w for w in words if not self._word_in_table(w, table_bboxes)]

        lines       = self._group_words_into_lines(words)
        prev_bottom = 0.0

        for line_words in lines:
            text = " ".join(w["text"] for w in line_words).strip()
            if not text:
                continue

            sizes     = [w.get("size") or body_size for w in line_words]
            fontnames = [w.get("fontname") or "" for w in line_words]
            line_size = statistics.median(sizes)
            is_bold   = any("Bold" in fn or "bold" in fn for fn in fontnames)
            is_italic = any(
                "Italic" in fn or "italic" in fn or "Oblique" in fn
                for fn in fontnames
            )

            x0     = min(w["x0"]  for w in line_words)
            x1     = max(w["x1"]  for w in line_words)
            top    = min(w["top"] for w in line_words)
            bottom = max(w.get("bottom", top + line_size) for w in line_words)

            space_before = max(0.0, top - prev_bottom)
            prev_bottom  = bottom

            block_type, heading_level = self._classify_line(
                text=text, font_size=line_size, body_size=body_size,
                is_bold=is_bold, top=top, page_height=page_height,
            )

            blocks.append(LayoutBlock(
                text          = text,
                block_type    = block_type,
                page_number   = page_result.page_number,
                font_size     = line_size,
                is_bold       = is_bold,
                is_italic     = is_italic,
                alignment     = _detect_alignment(x0, x1, page_width),
                heading_level = heading_level,
                space_before  = space_before,
                is_rtl        = _is_rtl_text(text),
            ))

        return blocks

    # ------------------------------------------------------------------
    # Pass 2b: Scanned page
    # ------------------------------------------------------------------

    def _detect_scanned_page(
        self,
        page_result:  PageResult,
        plumber_page: pdfplumber.page.Page,
    ) -> list[LayoutBlock]:
        text = page_result.final_text
        if not text.strip():
            return []

        blocks      = []
        page_height = plumber_page.height or 1
        lines       = [l.strip() for l in text.splitlines() if l.strip()]

        for i, line in enumerate(lines):
            estimated_top          = (i / max(len(lines), 1)) * page_height
            block_type, heading_level = self._classify_line(
                text=line, font_size=None, body_size=12.0,
                is_bold=False, top=estimated_top, page_height=page_height,
            )
            blocks.append(LayoutBlock(
                text          = line,
                block_type    = block_type,
                page_number   = page_result.page_number,
                alignment     = Alignment.RIGHT,
                heading_level = heading_level,
                space_before  = 6.0,
                is_rtl        = _is_rtl_text(line),
            ))

        return blocks

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_line(
        self, text: str, font_size: Optional[float], body_size: float,
        is_bold: bool, top: float, page_height: float,
    ) -> tuple[BlockType, Optional[int]]:
        words      = text.split()
        word_count = len(words)

        is_in_margin = (
            top < page_height * self.margin_zone or
            top > page_height * (1 - self.margin_zone)
        )
        if is_in_margin and (
            len(text) <= _PAGE_NUM_MAX_CHARS or _NUMERIC_LINE.match(text)
        ):
            return BlockType.PAGE_NUM, None

        if _NUMERIC_LINE.match(text) and word_count == 1:
            return BlockType.PAGE_NUM, None

        if font_size and font_size >= body_size * self.heading_size_ratio:
            return BlockType.HEADING, self._heading_level(font_size, body_size)

        if is_bold and word_count <= self.heading_max_words:
            return BlockType.HEADING, 2

        if (
            top < page_height * 0.20 and
            word_count <= self.heading_max_words and
            not _NUMERIC_LINE.match(text)
        ):
            return BlockType.HEADING, 2

        if word_count <= 3 and not _NUMERIC_LINE.match(text):
            return BlockType.CAPTION, None

        return BlockType.BODY, None

    def _heading_level(self, font_size: float, body_size: float) -> int:
        ratio = font_size / body_size
        if ratio >= 2.0: return 1
        if ratio >= 1.5: return 2
        return 3

    def _group_words_into_lines(
        self, words: list[dict], tolerance: float = 3.0
    ) -> list[list[dict]]:
        if not words:
            return []
        sorted_words = sorted(words, key=lambda w: (w["top"], -w["x0"]))
        lines        = []
        current_line = [sorted_words[0]]
        for word in sorted_words[1:]:
            if abs(word["top"] - current_line[0]["top"]) <= tolerance:
                current_line.append(word)
            else:
                lines.append(current_line)
                current_line = [word]
        lines.append(current_line)
        return lines

    # ------------------------------------------------------------------
    # Fallbacks
    # ------------------------------------------------------------------

    def _fallback_plain_text(self, extraction: ExtractionResult) -> list[LayoutBlock]:
        blocks = []
        for page in extraction.pages:
            blocks.extend(self._fallback_page_text(page))
        return blocks

    def _fallback_page_text(self, page_result: PageResult) -> list[LayoutBlock]:
        text = page_result.final_text
        if not text.strip():
            return []
        return [
            LayoutBlock(
                text        = line.strip(),
                block_type  = BlockType.BODY,
                page_number = page_result.page_number,
                is_rtl      = _is_rtl_text(line),
            )
            for line in text.splitlines()
            if line.strip()
        ]