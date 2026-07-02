"""
Stage 2 — Visual Analysis
--------------------------
Consumes DocumentRaw (Stage 1 output) exclusively. Never touches the
PDF file. Detects margins, columns, separator lines, candidate table
regions, and classifies images — purely geometric analysis, no
semantic interpretation.
"""

import logging
from collections import defaultdict
from pathlib import Path

from document_engine.dom.base import BBox
from document_engine.dom.raw import DocumentRaw, PageRaw, DrawingRaw, ImageRaw
from document_engine.dom.visual import (
    ColumnRegion,
    DocumentVisual,
    ImageRegion,
    Margins,
    Orientation,
    PageVisual,
    Separator,
    TableRegion,
    WhitespaceRegion,
)

logger = logging.getLogger(__name__)

# A horizontal gap between text spans larger than this fraction of
# page width signals a column boundary
_COLUMN_GAP_RATIO = 0.06

# Line intersection tolerance for grid-based table detection (points)
_GRID_TOLERANCE = 4.0

# Minimum row+column lines to call something a table grid
_MIN_TABLE_LINES = 2

# Image classification thresholds
_LOGO_MAX_AREA_RATIO   = 0.03   # logo occupies <3% of page area
_LOGO_ASPECT_TOLERANCE = 0.35   # near-square: |w/h - 1| < this
_MARGIN_ZONE_FRACTION  = 0.12   # top/bottom/side 12% counts as margin


class VisualAnalyzer:
    """
    Performs Stage 2 analysis: DocumentRaw -> DocumentVisual.

    Parameters
    ----------
    column_gap_ratio : Fraction of page width that signals a column break.
    margin_zone      : Fraction of page dimension treated as margin, used
                        for logo/stamp heuristics.
    """

    def __init__(
        self,
        column_gap_ratio: float = _COLUMN_GAP_RATIO,
        margin_zone:      float = _MARGIN_ZONE_FRACTION,
    ) -> None:
        self.column_gap_ratio = column_gap_ratio
        self.margin_zone      = margin_zone

    def analyze(self, doc_raw: DocumentRaw) -> DocumentVisual:
        """
        Run Stage 2 analysis on Stage 1 output.

        Parameters
        ----------
        doc_raw : DocumentRaw

        Returns
        -------
        DocumentVisual
        """
        pages: list[PageVisual] = []

        for page_raw in doc_raw.pages:
            try:
                pages.append(self._analyze_page(page_raw))
            except Exception as exc:
                logger.error(
                    "Stage 2 analysis failed on page %d: %s — inserting minimal page.",
                    page_raw.page_number, exc,
                )
                pages.append(PageVisual(
                    page_number=page_raw.page_number,
                    margins=Margins(top=0, bottom=0, left=0, right=0),
                ))

        logger.info("Stage 2 complete: %d pages analyzed.", len(pages))

        return DocumentVisual(source_path=doc_raw.source_path, pages=pages)

    def extract_and_save(
        self, doc_raw: DocumentRaw, debug_output_path: str
    ) -> DocumentVisual:
        """Run analysis and save stage2_visual.json for debugging."""
        result = self.analyze(doc_raw)
        Path(debug_output_path).write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Stage 2 debug output saved: %s", debug_output_path)
        return result

    # ------------------------------------------------------------------
    # Per-page analysis
    # ------------------------------------------------------------------

    def _analyze_page(self, page: PageRaw) -> PageVisual:
        margins    = self._compute_margins(page)
        separators = self._detect_separators(page)
        columns    = self._detect_columns(page)
        tables     = self._detect_table_regions(page, separators)
        images     = self._classify_images(page)
        whitespace = self._detect_whitespace(page, margins)

        return PageVisual(
            page_number=page.page_number,
            bbox=BBox(x0=0, y0=0, x1=page.width, y1=page.height),
            margins=margins,
            columns=columns,
            separators=separators,
            tables=tables,
            images=images,
            whitespace=whitespace,
        )

    # ------------------------------------------------------------------
    # Margins
    # ------------------------------------------------------------------

    def _compute_margins(self, page: PageRaw) -> Margins:
        """
        Estimate margins from the bounding extent of all content
        (text spans + drawings + images).
        """
        all_boxes = (
            [s.bbox for s in page.text_spans if s.bbox]
            + [d.bbox for d in page.drawings if d.bbox]
            + [i.bbox for i in page.images if i.bbox]
        )

        if not all_boxes:
            return Margins(top=0, bottom=0, left=0, right=0)

        min_x0 = min(b.x0 for b in all_boxes)
        min_y0 = min(b.y0 for b in all_boxes)
        max_x1 = max(b.x1 for b in all_boxes)
        max_y1 = max(b.y1 for b in all_boxes)

        return Margins(
            top=max(0.0, min_y0),
            bottom=max(0.0, page.height - max_y1),
            left=max(0.0, min_x0),
            right=max(0.0, page.width - max_x1),
        )

    # ------------------------------------------------------------------
    # Separators
    # ------------------------------------------------------------------

    def _detect_separators(self, page: PageRaw) -> list[Separator]:
        """Classify each DrawingRaw flagged is_line as horizontal or vertical."""
        separators: list[Separator] = []

        for drawing in page.drawings:
            if not drawing.is_line or not drawing.bbox:
                continue

            orientation = (
                Orientation.HORIZONTAL
                if drawing.bbox.width >= drawing.bbox.height
                else Orientation.VERTICAL
            )

            separators.append(Separator(
                page_number=page.page_number,
                bbox=drawing.bbox,
                orientation=orientation,
                source_drawing_id=drawing.id,
            ))

        return separators

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    def _detect_columns(self, page: PageRaw) -> list[ColumnRegion]:
        """
        Detect column boundaries via gap-based clustering of text span
        x-centers. Same algorithm as the old column_detector.py, now
        operating on Stage 1 span data instead of pdfplumber words.
        """
        spans_with_bbox = [s for s in page.text_spans if s.bbox]
        if not spans_with_bbox or page.width <= 0:
            return []

        centers = sorted(
            ((s.bbox.x0 + s.bbox.x1) / 2, s.id) for s in spans_with_bbox
        )
        gap_threshold = page.width * self.column_gap_ratio

        boundaries: list[float] = []
        for i in range(1, len(centers)):
            gap = centers[i][0] - centers[i - 1][0]
            if gap > gap_threshold:
                boundaries.append((centers[i][0] + centers[i - 1][0]) / 2)

        num_columns = len(boundaries) + 1
        if num_columns == 1:
            return []   # single column — nothing meaningful to report

        column_spans: dict[int, list[str]] = defaultdict(list)
        for x_center, span_id in centers:
            col = 0
            for boundary in boundaries:
                if x_center > boundary:
                    col += 1
            column_spans[col].append(span_id)

        columns: list[ColumnRegion] = []
        prev_x = 0.0
        for idx in range(num_columns):
            x_end = boundaries[idx] if idx < len(boundaries) else page.width
            columns.append(ColumnRegion(
                page_number=page.page_number,
                bbox=BBox(x0=prev_x, y0=0, x1=x_end, y1=page.height),
                index=idx,
                span_ids=column_spans.get(idx, []),
            ))
            prev_x = x_end

        logger.debug("Page %d: %d columns detected.", page.page_number, num_columns)
        return columns

    # ------------------------------------------------------------------
    # Table region candidates
    # ------------------------------------------------------------------

    def _detect_table_regions(
        self, page: PageRaw, separators: list[Separator]
    ) -> list[TableRegion]:
        """
        Find grid-like clusters of separator lines: 2+ roughly parallel
        horizontal lines intersected by 2+ roughly parallel vertical
        lines within a bounded region signal a candidate table.

        This is intentionally conservative — a false negative here just
        means Stage 4/6 relies on text-density heuristics instead.
        """
        h_lines = [s for s in separators if s.orientation == Orientation.HORIZONTAL]
        v_lines = [s for s in separators if s.orientation == Orientation.VERTICAL]

        if len(h_lines) < _MIN_TABLE_LINES or len(v_lines) < _MIN_TABLE_LINES:
            return []

        # Cluster h_lines and v_lines that share a bounding region
        # Simple approach: if their combined bbox is reasonably dense
        # (lines close together relative to page size), treat as one table.
        all_x0 = min(s.bbox.x0 for s in h_lines + v_lines if s.bbox)
        all_y0 = min(s.bbox.y0 for s in h_lines + v_lines if s.bbox)
        all_x1 = max(s.bbox.x1 for s in h_lines + v_lines if s.bbox)
        all_y1 = max(s.bbox.y1 for s in h_lines + v_lines if s.bbox)

        region_bbox = BBox(x0=all_x0, y0=all_y0, x1=all_x1, y1=all_y1)

        # Reject if the "table" region covers almost the whole page —
        # likely just a page border, not a data table
        if region_bbox.area / max(page.width * page.height, 1) > 0.9:
            return []

        table = TableRegion(
            page_number=page.page_number,
            bbox=region_bbox,
            row_lines=[s.id for s in h_lines],
            column_lines=[s.id for s in v_lines],
            confidence=0.6,   # geometric candidate only, not confirmed
        )

        logger.debug(
            "Page %d: candidate table region with %d row lines, %d column lines.",
            page.page_number, len(h_lines), len(v_lines),
        )
        return [table]

    # ------------------------------------------------------------------
    # Image classification
    # ------------------------------------------------------------------

    def _classify_images(self, page: PageRaw) -> list[ImageRegion]:
        """
        Classify each ImageRaw as likely logo/stamp vs likely content photo,
        using size, aspect ratio, and position heuristics.
        """
        regions: list[ImageRegion] = []
        page_area = max(page.width * page.height, 1)

        for image in page.images:
            if not image.bbox:
                continue

            area_ratio = image.bbox.area / page_area
            aspect     = image.bbox.width / max(image.bbox.height, 1e-6)
            near_square = abs(aspect - 1.0) < _LOGO_ASPECT_TOLERANCE

            in_margin_zone = (
                image.bbox.y0 < page.height * self.margin_zone or
                image.bbox.y1 > page.height * (1 - self.margin_zone) or
                image.bbox.x0 < page.width  * self.margin_zone or
                image.bbox.x1 > page.width  * (1 - self.margin_zone)
            )

            is_logo = (
                area_ratio < _LOGO_MAX_AREA_RATIO and
                near_square and
                in_margin_zone
            )
            is_photo = not is_logo and area_ratio > _LOGO_MAX_AREA_RATIO

            regions.append(ImageRegion(
                page_number=page.page_number,
                bbox=image.bbox,
                source_image_id=image.id,
                is_likely_logo=is_logo,
                is_likely_photo=is_photo,
            ))

        return regions

    # ------------------------------------------------------------------
    # Whitespace
    # ------------------------------------------------------------------

    def _detect_whitespace(
        self, page: PageRaw, margins: Margins
    ) -> list[WhitespaceRegion]:
        """
        Detect large vertical gaps between consecutive text spans,
        sorted top-to-bottom. A "significant" gap is wider than the
        median line height — likely a section break.
        """
        spans = sorted(
            (s for s in page.text_spans if s.bbox),
            key=lambda s: s.bbox.y0,
        )
        if len(spans) < 2:
            return []

        heights = [s.bbox.height for s in spans if s.bbox.height > 0]
        if not heights:
            return []
        median_height = sorted(heights)[len(heights) // 2]
        gap_threshold = median_height * 2.5

        regions: list[WhitespaceRegion] = []
        for i in range(1, len(spans)):
            prev_bottom = spans[i - 1].bbox.y1
            curr_top    = spans[i].bbox.y0
            gap = curr_top - prev_bottom

            if gap > gap_threshold:
                regions.append(WhitespaceRegion(
                    bbox=BBox(
                        x0=margins.left, y0=prev_bottom,
                        x1=page.width - margins.right, y1=curr_top,
                    )
                ))

        return regions