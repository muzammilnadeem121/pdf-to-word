"""
Tests for Stage 2 — Visual Analysis.

Builds synthetic DocumentRaw objects directly (no PDF needed) to test
margin, column, separator, table, and image classification logic in
isolation, plus end-to-end tests against real synthetic PDFs.

Run with:
    python -m pytest tests/test_stage2_visual.py -v
"""

import pytest
import fitz

from document_engine.dom.base import BBox
from document_engine.dom.raw import (
    DocumentMetadataRaw, DocumentRaw, DrawingRaw, FontInfo,
    ImageRaw, PageRaw, TextSpanRaw,
)
from document_engine.dom.visual import Orientation
from document_engine.stages.stage1_extraction import RawExtractor
from document_engine.stages.stage2_visual import VisualAnalyzer


# ---------------------------------------------------------------------------
# Helpers — build synthetic DocumentRaw without touching PDFs
# ---------------------------------------------------------------------------

def make_span(x0, y0, x1, y1, text="word") -> TextSpanRaw:
    return TextSpanRaw(
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text=text,
        font=FontInfo(name="Arial", size=12.0),
    )


def make_line_drawing(x0, y0, x1, y1) -> DrawingRaw:
    return DrawingRaw(
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        stroke_rgb=(0, 0, 0),
        stroke_width=1.0,
        is_line=True,
    )


def make_image(x0, y0, x1, y1, w=100, h=100) -> ImageRaw:
    return ImageRaw(
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        xref=1, width_px=w, height_px=h, colorspace="RGB",
    )


def make_doc_raw(pages: list[PageRaw]) -> DocumentRaw:
    return DocumentRaw(
        source_path="dummy.pdf",
        metadata=DocumentMetadataRaw(page_count=len(pages)),
        pages=pages,
    )


# ---------------------------------------------------------------------------
# Margins
# ---------------------------------------------------------------------------

class TestMargins:

    def test_margins_from_spans(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[make_span(50, 60, 200, 80)],
        )
        result = VisualAnalyzer()._compute_margins(page)
        assert result.left == pytest.approx(50)
        assert result.top == pytest.approx(60)

    def test_empty_page_zero_margins(self):
        page = PageRaw(page_number=1, width=600, height=800)
        result = VisualAnalyzer()._compute_margins(page)
        assert result.top == 0
        assert result.left == 0


# ---------------------------------------------------------------------------
# Separators
# ---------------------------------------------------------------------------

class TestSeparators:

    def test_horizontal_line_detected(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            drawings=[make_line_drawing(50, 100, 500, 101)],
        )
        result = VisualAnalyzer()._detect_separators(page)
        assert len(result) == 1
        assert result[0].orientation == Orientation.HORIZONTAL

    def test_vertical_line_detected(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            drawings=[make_line_drawing(300, 50, 301, 700)],
        )
        result = VisualAnalyzer()._detect_separators(page)
        assert result[0].orientation == Orientation.VERTICAL

    def test_non_line_drawing_ignored(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            drawings=[DrawingRaw(
                bbox=BBox(x0=50, y0=50, x1=200, y1=150),
                fill_rgb=(200, 0, 0), is_line=False,
            )],
        )
        result = VisualAnalyzer()._detect_separators(page)
        assert result == []


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

class TestColumns:

    def test_single_column_returns_empty(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(250, 100, 350, 120),
                make_span(250, 140, 350, 160),
            ],
        )
        result = VisualAnalyzer()._detect_columns(page)
        assert result == []

    def test_two_columns_detected(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(50, 100, 150, 120),    # left column
                make_span(50, 140, 150, 160),
                make_span(450, 100, 550, 120),   # right column, big gap
                make_span(450, 140, 550, 160),
            ],
        )
        result = VisualAnalyzer()._detect_columns(page)
        assert len(result) == 2

    def test_no_spans_returns_empty(self):
        page = PageRaw(page_number=1, width=600, height=800)
        result = VisualAnalyzer()._detect_columns(page)
        assert result == []


# ---------------------------------------------------------------------------
# Table region detection
# ---------------------------------------------------------------------------

class TestTableRegions:

    def test_grid_of_lines_detected(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            drawings=[
                make_line_drawing(100, 100, 400, 101),
                make_line_drawing(100, 150, 400, 151),
                make_line_drawing(100, 100, 101, 150),
                make_line_drawing(300, 100, 301, 150),
            ],
        )
        separators = VisualAnalyzer()._detect_separators(page)
        result = VisualAnalyzer()._detect_table_regions(page, separators)
        assert len(result) == 1
        assert len(result[0].row_lines) == 2
        assert len(result[0].column_lines) == 2

    def test_too_few_lines_no_table(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            drawings=[make_line_drawing(100, 100, 400, 101)],
        )
        separators = VisualAnalyzer()._detect_separators(page)
        result = VisualAnalyzer()._detect_table_regions(page, separators)
        assert result == []


# ---------------------------------------------------------------------------
# Image classification
# ---------------------------------------------------------------------------

class TestImageClassification:

    def test_small_square_margin_image_is_logo(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            images=[make_image(10, 10, 50, 50)],   # small, square, top-left margin
        )
        result = VisualAnalyzer()._classify_images(page)
        assert result[0].is_likely_logo is True

    def test_large_central_image_is_photo(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            images=[make_image(100, 200, 500, 600)],   # large, central
        )
        result = VisualAnalyzer()._classify_images(page)
        assert result[0].is_likely_photo is True

    def test_no_images_returns_empty(self):
        page = PageRaw(page_number=1, width=600, height=800)
        result = VisualAnalyzer()._classify_images(page)
        assert result == []


# ---------------------------------------------------------------------------
# Whitespace
# ---------------------------------------------------------------------------

class TestWhitespace:

    def test_large_gap_detected(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(50, 100, 200, 115),
                make_span(50, 300, 200, 315),   # big gap from previous
            ],
        )
        margins = VisualAnalyzer()._compute_margins(page)
        result  = VisualAnalyzer()._detect_whitespace(page, margins)
        assert len(result) >= 1

    def test_single_span_no_whitespace(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[make_span(50, 100, 200, 115)],
        )
        margins = VisualAnalyzer()._compute_margins(page)
        result  = VisualAnalyzer()._detect_whitespace(page, margins)
        assert result == []


# ---------------------------------------------------------------------------
# End-to-end: Stage 1 -> Stage 2
# ---------------------------------------------------------------------------

class TestStage1ToStage2Integration:

    def test_full_pipeline_on_synthetic_pdf(self, tmp_path):
        doc  = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "یہ ایک آزمائشی متن ہے", fontsize=14)
        page.draw_rect(fitz.Rect(50, 50, 545, 792), color=(0, 0, 0), width=1.0)
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path))
        doc.close()

        doc_raw    = RawExtractor().extract(str(pdf_path))
        doc_visual = VisualAnalyzer().analyze(doc_raw)

        assert len(doc_visual.pages) == 1
        assert doc_visual.pages[0].margins is not None

    def test_debug_export(self, tmp_path):
        doc  = fitz.open()
        doc.new_page(width=595, height=842)
        pdf_path = tmp_path / "blank.pdf"
        doc.save(str(pdf_path))
        doc.close()

        doc_raw = RawExtractor().extract(str(pdf_path))
        debug_path = tmp_path / "stage2_visual.json"
        VisualAnalyzer().extract_and_save(doc_raw, str(debug_path))
        assert debug_path.exists()
        assert "margins" in debug_path.read_text(encoding="utf-8")