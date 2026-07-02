"""
Stage 4 — Layout Analysis
---------------------------
Consumes DocumentText (Stage 3) + DocumentVisual (Stage 2) exclusively.
Classifies every text line into a semantic role using measurable
signals only: font size relative to body baseline, position on page,
indentation relative to body paragraphs, list-marker patterns, and
repetition across pages (for headers/footers).

Two-pass design
----------------
Pass 1 (document-level):
  - Compute body font size baseline across all pages.
  - Detect repeated top/bottom-zone text -> header/footer candidates.

Pass 2 (per-page):
  - Classify every line using Pass 1's findings.
  - Sub-pass: after initial paragraph classification, measure typical
    body indentation and reclassify over-indented paragraphs as
    quotations.
"""

import logging
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Optional

from document_engine.dom.layout import DocumentLayout, LayoutBlock, LayoutRole, PageLayout
from document_engine.dom.text import DocumentText, PageTextAnalysis, TextLine
from document_engine.dom.visual import DocumentVisual, ImageRegion, PageVisual

logger = logging.getLogger(__name__)

# ── Tunable thresholds ────────────────────────────────────────────────

_HEADING_SIZE_RATIO    = 1.20   # font >= 20% larger than body -> heading
_HEADING_MAX_WORDS     = 8
_MARGIN_ZONE_FRACTION  = 0.08   # top/bottom 8% of page = margin
_FOOTNOTE_SIZE_RATIO   = 0.85   # font <= 85% of body, in bottom margin
_CAPTION_MAX_WORDS     = 15
_CAPTION_PROXIMITY_PT  = 20.0   # line must start within this of image bottom
_QUOTATION_INDENT_PT   = 24.0   # x0 offset beyond median body x0
_HEADER_FOOTER_MIN_RATIO = 0.5  # text must repeat on >= 50% of pages
_MIN_PAGES_FOR_REPEAT  = 3      # don't attempt header/footer detection below this

_NUMERIC_LINE = re.compile(
    r"^\s*[\d\u0660-\u0669\u06F0-\u06F9]+\s*$"
)
_LIST_MARKER = re.compile(
    r"^\s*("
    r"[•\-\*‣●▪]|"                      # bullet chars
    r"\d+[\.\)]|"                       # 1. or 1)
    r"[\u0660-\u0669\u06F0-\u06F9]+[\.\)]|"  # Arabic/Urdu digit lists
    r"[a-zA-Z][\.\)]"                   # a. or a)
    r")\s+"
)
_REFERENCE_MARKER = re.compile(r"^\s*\[\d+\]")


class LayoutAnalyzer:
    """
    Performs Stage 4 analysis: (DocumentText, DocumentVisual) -> DocumentLayout.

    Parameters
    ----------
    heading_size_ratio : Font size ratio above body that signals a heading.
    margin_zone        : Fraction of page height treated as header/footer zone.
    """

    def __init__(
        self,
        heading_size_ratio: float = _HEADING_SIZE_RATIO,
        margin_zone:        float = _MARGIN_ZONE_FRACTION,
    ) -> None:
        self.heading_size_ratio = heading_size_ratio
        self.margin_zone        = margin_zone

    def analyze(
        self, doc_text: DocumentText, doc_visual: DocumentVisual
    ) -> DocumentLayout:
        """
        Run Stage 4 analysis.

        Parameters
        ----------
        doc_text   : Stage 3 output.
        doc_visual : Stage 2 output.

        Returns
        -------
        DocumentLayout
        """
        visual_by_page = {p.page_number: p for p in doc_visual.pages}

        # ── Pass 1: document-level signals ──────────────────────────
        body_size = self._compute_body_font_size(doc_text)
        header_pattern, footer_pattern = self._detect_repeated_zones(doc_text)

        logger.info(
            "Stage 4 Pass 1: body_size=%.1fpt, header=%r, footer=%r",
            body_size, header_pattern, footer_pattern,
        )

        # ── Pass 2: per-page classification ─────────────────────────
        pages: list[PageLayout] = []
        for page_text in doc_text.pages:
            page_visual = visual_by_page.get(page_text.page_number)
            try:
                pages.append(self._classify_page(
                    page_text, page_visual, body_size,
                    header_pattern, footer_pattern,
                ))
            except Exception as exc:
                logger.error(
                    "Stage 4 classification failed on page %d: %s — using UNKNOWN fallback.",
                    page_text.page_number, exc,
                )
                pages.append(self._fallback_page(page_text))

        logger.info("Stage 4 complete: %d pages classified.", len(pages))

        return DocumentLayout(
            source_path=doc_text.source_path,
            pages=pages,
            detected_header_pattern=header_pattern,
            detected_footer_pattern=footer_pattern,
        )

    def extract_and_save(
        self, doc_text: DocumentText, doc_visual: DocumentVisual, debug_output_path: str
    ) -> DocumentLayout:
        result = self.analyze(doc_text, doc_visual)
        Path(debug_output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Stage 4 debug output saved: %s", debug_output_path)
        return result

    # ------------------------------------------------------------------
    # Pass 1a: body font size baseline
    # ------------------------------------------------------------------

    def _compute_body_font_size(self, doc_text: DocumentText) -> float:
        sizes: list[float] = []
        for page in doc_text.pages:
            for block in page.blocks:
                for line in block.lines:
                    if line.font_size:
                        sizes.extend([line.font_size] * max(len(line.text), 1))
        return statistics.median(sizes) if sizes else 12.0

    # ------------------------------------------------------------------
    # Pass 1b: repeated header/footer detection
    # ------------------------------------------------------------------

    def _detect_repeated_zones(
        self, doc_text: DocumentText
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Find text that repeats verbatim (after digit-normalization) in
        the top margin zone or bottom margin zone across a majority of
        pages. Digit-normalization means "Page 3" and "Page 4" both
        become "Page #", so page-numbered headers still match.
        """
        if len(doc_text.pages) < _MIN_PAGES_FOR_REPEAT:
            return None, None

        top_candidates:    list[str] = []
        bottom_candidates: list[str] = []

        for page in doc_text.pages:
            all_lines = [l for b in page.blocks for l in b.lines if l.bbox]
            if not all_lines:
                continue

            page_height = max((l.bbox.y1 for l in all_lines), default=800)
            top_zone_max    = page_height * self.margin_zone
            bottom_zone_min = page_height * (1 - self.margin_zone)

            for line in all_lines:
                normalized = self._normalize_for_repeat(line.text)
                if not normalized:
                    continue
                if line.bbox.y0 <= top_zone_max:
                    top_candidates.append(normalized)
                elif line.bbox.y1 >= bottom_zone_min:
                    bottom_candidates.append(normalized)

        header = self._most_common_if_frequent(top_candidates, len(doc_text.pages))
        footer = self._most_common_if_frequent(bottom_candidates, len(doc_text.pages))
        return header, footer

    def _normalize_for_repeat(self, text: str) -> str:
        """Strip digits so 'Page 3' and 'Page 4' match as the same pattern."""
        normalized = re.sub(r"[\d\u0660-\u0669\u06F0-\u06F9]+", "#", text.strip())
        return normalized if len(normalized) >= 3 else ""

    def _most_common_if_frequent(
        self, candidates: list[str], total_pages: int
    ) -> Optional[str]:
        if not candidates:
            return None
        counts = Counter(candidates)
        text, count = counts.most_common(1)[0]
        if count / total_pages >= _HEADER_FOOTER_MIN_RATIO:
            return text
        return None

    # ------------------------------------------------------------------
    # Pass 2: per-page classification
    # ------------------------------------------------------------------

    def _classify_page(
        self,
        page_text:      PageTextAnalysis,
        page_visual:    Optional[PageVisual],
        body_size:      float,
        header_pattern: Optional[str],
        footer_pattern: Optional[str],
    ) -> PageLayout:

        all_lines = [l for b in page_text.blocks for l in b.lines if l.bbox]
        if not all_lines:
            return PageLayout(page_number=page_text.page_number)

        page_height = max(l.bbox.y1 for l in all_lines)
        image_regions = page_visual.images if page_visual else []

        # First sub-pass: classify everything except quotation
        prelim: list[LayoutBlock] = []
        for line in all_lines:
            role, level, reason = self._classify_line(
                line, body_size, page_height,
                header_pattern, footer_pattern, image_regions,
            )
            prelim.append(LayoutBlock(
                page_number=page_text.page_number,
                bbox=line.bbox,
                text=line.text,
                role=role,
                heading_level=level if role == LayoutRole.HEADING else None,
                list_level=0,
                font_size=line.font_size,
                is_bold=line.is_bold,
                is_italic=line.is_italic,
                is_rtl=line.is_rtl,
                source_line_id=line.id,
                reason=reason,
            ))

        # Second sub-pass: reclassify over-indented PARAGRAPHs as QUOTATION
        self._reclassify_quotations(prelim)

        return PageLayout(page_number=page_text.page_number, blocks=prelim)

    def _classify_line(
        self,
        line:           TextLine,
        body_size:      float,
        page_height:    float,
        header_pattern: Optional[str],
        footer_pattern: Optional[str],
        image_regions:  list[ImageRegion],
    ) -> tuple[LayoutRole, Optional[int], str]:

        text = line.text.strip()
        words = text.split()
        word_count = len(words)
        font_size = line.font_size or body_size

        in_top_margin    = line.bbox.y0 <= page_height * self.margin_zone
        in_bottom_margin = line.bbox.y1 >= page_height * (1 - self.margin_zone)

        # ── Header / Footer (repeated text) ─────────────────────────
        normalized = self._normalize_for_repeat(text)
        if header_pattern and in_top_margin and normalized == header_pattern:
            return LayoutRole.HEADER, None, "Matches repeated top-zone text across pages."
        if footer_pattern and in_bottom_margin and normalized == footer_pattern:
            return LayoutRole.FOOTER, None, "Matches repeated bottom-zone text across pages."

        # ── Page number ───────────────────────────────────────────────
        if (in_top_margin or in_bottom_margin) and _NUMERIC_LINE.match(text):
            return LayoutRole.PAGE_NUMBER, None, "Isolated numeric line in margin zone."

        # ── Reference (explicit [N] marker) ─────────────────────────
        if _REFERENCE_MARKER.match(text):
            return LayoutRole.REFERENCE, None, "Starts with [N] reference marker."

        # ── Caption (short line just below an image) ────────────────
        if word_count <= _CAPTION_MAX_WORDS and image_regions:
            for img in image_regions:
                if not img.bbox:
                    continue
                vertical_gap = line.bbox.y0 - img.bbox.y1
                horizontally_aligned = (
                    line.bbox.x0 < img.bbox.x1 and line.bbox.x1 > img.bbox.x0
                )
                if 0 <= vertical_gap <= _CAPTION_PROXIMITY_PT and horizontally_aligned:
                    return LayoutRole.CAPTION, None, "Short line directly below an image."

        # ── Footnote (small font, bottom margin) ─────────────────────
        if in_bottom_margin and font_size <= body_size * _FOOTNOTE_SIZE_RATIO:
            return LayoutRole.FOOTNOTE, None, "Small font size in bottom margin zone."

        # ── Heading (font size) ───────────────────────────────────────
        if font_size >= body_size * self.heading_size_ratio:
            level = self._heading_level(font_size, body_size)
            return LayoutRole.HEADING, level, (
                f"Font size {font_size:.1f}pt is {font_size/body_size:.1f}x body size."
            )

        # ── Heading (bold + short) ────────────────────────────────────
        if line.is_bold and word_count <= _HEADING_MAX_WORDS:
            return LayoutRole.HEADING, 2, "Bold and short line — likely subheading."

        # ── List item ─────────────────────────────────────────────────
        if _LIST_MARKER.match(text):
            return LayoutRole.LIST_ITEM, None, "Starts with a bullet or numbering marker."

        # ── Default: paragraph ───────────────────────────────────────
        return LayoutRole.PARAGRAPH, None, "Default body text classification."

    def _heading_level(self, font_size: float, body_size: float) -> int:
        ratio = font_size / body_size
        if ratio >= 2.0: return 1
        if ratio >= 1.5: return 2
        return 3

    # ------------------------------------------------------------------
    # Quotation reclassification
    # ------------------------------------------------------------------

    def _reclassify_quotations(self, blocks: list[LayoutBlock]) -> None:
        """
        Measure the median left-edge x0 of PARAGRAPH-role blocks, then
        reclassify any paragraph indented well beyond that median as a
        QUOTATION. Modifies blocks in-place.
        """
        paragraph_x0s = [
            b.bbox.x0 for b in blocks
            if b.role == LayoutRole.PARAGRAPH and b.bbox
        ]
        if len(paragraph_x0s) < 3:
            return   # not enough data to establish a reliable baseline

        median_x0 = statistics.median(paragraph_x0s)

        for block in blocks:
            if block.role != LayoutRole.PARAGRAPH or not block.bbox:
                continue
            if block.bbox.x0 > median_x0 + _QUOTATION_INDENT_PT:
                block.role   = LayoutRole.QUOTATION
                block.reason = (
                    f"Indented {block.bbox.x0 - median_x0:.0f}pt beyond "
                    f"median body paragraph x0 ({median_x0:.0f}pt)."
                )

    def _fallback_page(self, page_text: PageTextAnalysis) -> PageLayout:
        """Every line becomes UNKNOWN — used only if classification crashes."""
        blocks = [
            LayoutBlock(
                page_number=page_text.page_number,
                bbox=line.bbox,
                text=line.text,
                role=LayoutRole.UNKNOWN,
                source_line_id=line.id,
                reason="Fallback: classification failed.",
            )
            for block in page_text.blocks for line in block.lines
        ]
        return PageLayout(page_number=page_text.page_number, blocks=blocks)