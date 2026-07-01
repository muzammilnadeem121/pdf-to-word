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
from bidi.algorithm import get_display
from layout.graphics_extractor import GraphicsExtractor, GraphicBox


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
        self._graphics_extractor = GraphicsExtractor()

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
                self._current_pdf_path = str(path)

                for page_result in extraction.pages:
                    page_idx = page_result.page_number - 1

                    if page_idx >= len(pdf.pages):
                        continue

                    plumber_page = pdf.pages[page_idx]
                    fitz_page    = fitz_doc[page_idx]
                    page_width   = plumber_page.width or 1

                    # ── Graphics ─────────────────────────────────────
                    graphic_boxes = self._graphics_extractor.extract_page_graphics(
                        fitz_page
                    )

                    # ── Tables ───────────────────────────────────────
                    table_blocks = self._table_detector.extract_page_tables(
                        plumber_page, page_result.page_number
                    )

                    # Get bounding boxes of table regions so we can
                    # exclude those words from text classification
                    table_bboxes = self._get_table_bboxes(plumber_page)

                    # ── Images ───────────────────────────────────────
                    image_blocks = self._image_extractor.extract_page_images(
                        fitz_doc,
                        fitz_page,
                        page_result.page_number,
                        char_count=page_result.char_count,   # ← add this
                    )

                    # ── Text blocks ──────────────────────────────────
                    # Pass to digital page detector
                    if page_result.needs_ocr and not page_result.is_mixed:
                        text_blocks = self._detect_scanned_page(page_result, plumber_page)
                    else:
                        text_blocks = self._detect_digital_page(
                            page_result, plumber_page,
                            body_font_size, table_bboxes,
                            graphic_boxes,
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
    
    def _bbox_in_table(
        self,
        bbox:         tuple[float, float, float, float],
        table_bboxes: list[tuple],
    ) -> bool:
        """Return True if this bbox overlaps a table region."""
        bx0, by0, bx1, by1 = bbox
        for (tx0, ttop, tx1, tbottom) in table_bboxes:
            if bx0 >= tx0 and bx1 <= tx1 and by0 >= ttop and by1 <= tbottom:
                return True
        return False

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

    def detect_dominant_font(self, pdf_path: str) -> str:
        """
        Find the most-used font name in the PDF.
        Returns a Word-compatible Urdu font name.
        """
        # Map common PDF font names to installed Word fonts
        FONT_MAP = {
            "jameel":     "Jameel Noori Nastaleeq",
            "nastaleeq":  "Jameel Noori Nastaleeq",
            "nastaliq":   "Jameel Noori Nastaleeq",
            "noorinasta": "Jameel Noori Nastaleeq",
            "nafees":     "Nafees Web Naskh",
            "naskh":      "Noto Naskh Arabic",
            "alvi":       "Alvi Nastaleeq",
            "fajer":      "Fajer Noori Nastalique",
            "urdu":       "Jameel Noori Nastaleeq",
            "arabic":     "Noto Naskh Arabic",
            "tahoma":     "Tahoma",
            "arial":      "Arial Unicode MS",
            "times":      "Times New Roman",
        }
        DEFAULT = "Jameel Noori Nastaleeq"

        from collections import Counter
        font_counts: Counter = Counter()

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages[:5]:
                    for word in (page.extract_words(extra_attrs=["fontname"]) or []):
                        fn = (word.get("fontname") or "").lower()
                        if fn:
                            font_counts[fn] += 1
        except Exception:
            return DEFAULT

        if not font_counts:
            return DEFAULT

        dominant = font_counts.most_common(1)[0][0]

        for key, mapped in FONT_MAP.items():
            if key in dominant:
                return mapped

        return DEFAULT

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
        graphic_boxes: list = None,
    ) -> list[LayoutBlock]:

        blocks:     list[LayoutBlock] = []
        page_height = plumber_page.height or 842
        page_width  = plumber_page.width  or 595

        # ── Use PyMuPDF for text extraction (better Arabic/Urdu support)
        # get_text("dict") returns blocks → lines → spans with direction info.
        try:
            import fitz as _fitz
            # Re-open the page via fitz using the stored pdf_path
            # We get it via page_result indirectly through the fitz_doc
            # passed in detect() — access it via the plumber page index
            fitz_doc = _fitz.open(self._current_pdf_path)
            fitz_page = fitz_doc[page_result.page_number - 1]
            raw_dict  = fitz_page.get_text(
                "dict",
                flags=_fitz.TEXT_PRESERVE_LIGATURES | _fitz.TEXT_PRESERVE_WHITESPACE,
                sort=True,   # sort blocks in reading order
            )
            fitz_doc.close()
        except Exception as exc:
            logger.warning("PyMuPDF dict extraction failed page %d: %s",
                           page_result.page_number, exc)
            return self._fallback_page_text(page_result)

        prev_bottom = 0.0

        for block in raw_dict.get("blocks", []):
            if block.get("type") != 0:   # type 0 = text, type 1 = image
                continue

            # Skip block if it overlaps a detected table region
            bx0, by0, bx1, by1 = block["bbox"]
            if self._bbox_in_table((bx0, by0, bx1, by1), table_bboxes):
                continue

            for line in block.get("lines", []):
                line_text_parts = []
                font_sizes  = []
                is_bold     = False
                is_italic   = False

                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if not span_text:
                        continue
                    line_text_parts.append(span_text)
                    font_sizes.append(span.get("size", body_size))
                    flags = span.get("flags", 0)
                    if flags & 2**4:   # bold flag in PyMuPDF
                        is_bold = True
                    if flags & 2**1:   # italic flag
                        is_italic = True

                    raw_color = span.get("color", 0)
                    if raw_color and raw_color != 0:
                        # Unpack from 0xRRGGBB integer
                        r = (raw_color >> 16) & 0xFF
                        g = (raw_color >> 8)  & 0xFF
                        b =  raw_color        & 0xFF
                        # Only store if it's not plain black
                        if not (r < 10 and g < 10 and b < 10):
                            span_text_color = (r, g, b)
                        else:
                            span_text_color = None

                if not line_text_parts:
                    continue

                # Join spans — for RTL text PyMuPDF with sort=True
                # returns spans in logical order already
                raw_line = " ".join(line_text_parts)

                # Apply BiDi as a safety net for visual-order PDFs
                try:
                    text = get_display(raw_line)
                except Exception:
                    text = raw_line

                if not text.strip():
                    continue

                line_size    = statistics.median(font_sizes) if font_sizes else body_size
                lx0, ly0, lx1, ly1 = line["bbox"]
                space_before = max(0.0, ly0 - prev_bottom)
                prev_bottom  = ly1

                block_type, heading_level = self._classify_line(
                    text=text, font_size=line_size, body_size=body_size,
                    is_bold=is_bold, top=ly0, page_height=page_height,
                )

                blocks.append(LayoutBlock(
                    text          = text,
                    block_type    = block_type,
                    page_number   = page_result.page_number,
                    font_size     = line_size,
                    is_bold       = is_bold,
                    is_italic     = is_italic,
                    alignment     = _detect_alignment(lx0, lx1, page_width),
                    heading_level = heading_level,
                    space_before  = ly0,   # real y0 coordinate
                    is_rtl        = _is_rtl_text(text),
                    text_color    = span_text_color
                ))

                # Decorate immediately with real bbox coords
                self._decorate_block_with_bbox(
                    blocks[-1], lx0, ly0, lx1, ly1,
                    page_width, graphic_boxes or [],
                )

        return blocks if blocks else self._fallback_page_text(page_result)

    def _decorate_block(
        self, block: LayoutBlock, graphic_boxes: list[GraphicBox]
    ) -> None:
        """
        Find the graphic container for a text block and copy its
        colors into the block's decoration fields.

        Modifies block in-place.
        """
        # Reconstruct approximate bbox from what we have
        # space_before is y0; we estimate y1 from font size
        font_h  = (block.font_size or 12) * 1.2
        text_y0 = block.space_before
        text_y1 = text_y0 + font_h

        # Use alignment to estimate x range
        page_w  = 595.0   # A4 default; good enough for overlap detection
        if block.alignment == Alignment.RIGHT:
            text_x0, text_x1 = page_w * 0.3, page_w
        elif block.alignment == Alignment.LEFT:
            text_x0, text_x1 = 0, page_w * 0.7
        else:
            text_x0, text_x1 = page_w * 0.1, page_w * 0.9

        container = self._graphics_extractor.find_container(
            text_x0, text_y0, text_x1, text_y1, graphic_boxes
        )

        if container:
            block.background_color = container.fill_rgb
            block.border_color     = container.stroke_rgb
            block.border_width     = container.stroke_width

        # Check for adjacent lines (dividers above/below)
        top_line, bottom_line = self._graphics_extractor.find_adjacent_lines(
            text_y0, text_y1, graphic_boxes
        )
        if (top_line or bottom_line) and not block.border_color:
            line = top_line or bottom_line
            block.border_color = line.stroke_rgb
            block.border_width = line.stroke_width

    def _decorate_block_with_bbox(
    self,
    block:         LayoutBlock,
    x0: float, y0: float, x1: float, y1: float,
    page_width:    float,
    graphic_boxes: list[GraphicBox],
    ) -> None:
        """Decorate a block using its real PDF bounding box."""
        container = self._graphics_extractor.find_container(
            x0, y0, x1, y1, graphic_boxes
        )
        if container:
            block.background_color = container.fill_rgb
            block.border_color     = container.stroke_rgb
            block.border_width     = container.stroke_width

        top_line, bottom_line = self._graphics_extractor.find_adjacent_lines(
            y0, y1, graphic_boxes
        )
        if (top_line or bottom_line) and not block.border_color:
            line = top_line or bottom_line
            block.border_color = line.stroke_rgb
            block.border_width = line.stroke_width

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

        # Sort top-to-bottom only for line grouping
        sorted_words = sorted(words, key=lambda w: w["top"])

        lines        = []
        current_line = [sorted_words[0]]

        for word in sorted_words[1:]:
            if abs(word["top"] - current_line[0]["top"]) <= tolerance:
                current_line.append(word)
            else:
                lines.append(current_line)
                current_line = [word]
        lines.append(current_line)

        # Within each line sort RIGHT-TO-LEFT (descending x0)
        # so words are joined in Urdu reading order
        for line in lines:
            line.sort(key=lambda w: w["x0"], reverse=True)

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