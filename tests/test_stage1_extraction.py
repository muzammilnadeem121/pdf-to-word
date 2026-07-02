"""
Tests for Stage 1 — Low-Level Extraction.

Verifies RawExtractor produces correct DocumentRaw output for
synthetic PDFs built with PyMuPDF, covering text spans, drawings,
images, metadata, and error resilience.

Run with:
    python -m pytest tests/test_stage1_extraction.py -v
"""

import pytest
import fitz

from document_engine.dom.raw import DocumentRaw, PageRaw
from document_engine.stages.stage1_extraction import RawExtractor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_text_pdf(tmp_path, text="یہ ایک آزمائشی متن ہے") -> str:
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=14)
    out = tmp_path / "text.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


def make_multi_page_pdf(tmp_path, n=3) -> str:
    doc = fitz.open()
    for i in range(n):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), f"Page {i+1} content", fontsize=12)
    out = tmp_path / "multi.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


def make_pdf_with_drawing(tmp_path) -> str:
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.draw_rect(fitz.Rect(50, 50, 300, 120), color=(0, 0, 0), fill=(0.2, 0.4, 0.8), width=1.5)
    out = tmp_path / "drawing.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


def make_blank_pdf(tmp_path) -> str:
    doc = fitz.open()
    doc.new_page()
    out = tmp_path / "blank.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------

class TestRawExtractorBasics:

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            RawExtractor().extract("/nonexistent/file.pdf")

    def test_raises_on_wrong_extension(self, tmp_path):
        fake = tmp_path / "file.txt"
        fake.write_text("hello")
        with pytest.raises(ValueError):
            RawExtractor().extract(str(fake))

    def test_returns_document_raw(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        assert isinstance(result, DocumentRaw)
        assert result.source_path == pdf_path

    def test_correct_page_count(self, tmp_path):
        pdf_path = make_multi_page_pdf(tmp_path, n=3)
        result = RawExtractor().extract(pdf_path)
        assert len(result.pages) == 3
        assert result.metadata.page_count == 3

    def test_page_numbers_are_1_based(self, tmp_path):
        pdf_path = make_multi_page_pdf(tmp_path, n=2)
        result = RawExtractor().extract(pdf_path)
        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

    def test_page_dimensions_captured(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        page = result.pages[0]
        assert page.width == pytest.approx(595, abs=1)
        assert page.height == pytest.approx(842, abs=1)


# ---------------------------------------------------------------------------
# Text span extraction
# ---------------------------------------------------------------------------

class TestTextSpanExtraction:

    def test_extracts_text_spans(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        page = result.pages[0]
        assert len(page.text_spans) > 0

    def test_span_has_bbox(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        span = result.pages[0].text_spans[0]
        assert span.bbox is not None
        assert span.bbox.x1 > span.bbox.x0

    def test_span_has_font_info(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        span = result.pages[0].text_spans[0]
        assert span.font.size > 0
        assert isinstance(span.font.name, str)

    def test_blank_page_has_no_spans(self, tmp_path):
        pdf_path = make_blank_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        assert result.pages[0].text_spans == []

    def test_span_text_not_empty(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        for span in result.pages[0].text_spans:
            assert span.text.strip() != ""


# ---------------------------------------------------------------------------
# Drawing extraction
# ---------------------------------------------------------------------------

class TestDrawingExtraction:

    def test_extracts_rectangle(self, tmp_path):
        pdf_path = make_pdf_with_drawing(tmp_path)
        result = RawExtractor().extract(pdf_path)
        assert len(result.pages[0].drawings) >= 1

    def test_drawing_has_fill_color(self, tmp_path):
        pdf_path = make_pdf_with_drawing(tmp_path)
        result = RawExtractor().extract(pdf_path)
        drawings_with_fill = [d for d in result.pages[0].drawings if d.fill_rgb]
        assert len(drawings_with_fill) >= 1

    def test_drawing_has_bbox(self, tmp_path):
        pdf_path = make_pdf_with_drawing(tmp_path)
        result = RawExtractor().extract(pdf_path)
        drawing = result.pages[0].drawings[0]
        assert drawing.bbox is not None
        assert drawing.bbox.width > 0

    def test_blank_page_has_no_drawings(self, tmp_path):
        pdf_path = make_blank_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        assert result.pages[0].drawings == []


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

class TestMetadataExtraction:

    def test_metadata_present(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        assert result.metadata is not None
        assert result.metadata.page_count == 1

    def test_metadata_handles_missing_fields(self, tmp_path):
        pdf_path = make_blank_pdf(tmp_path)
        result = RawExtractor().extract(pdf_path)
        # Should not raise even if title/author are None
        assert result.metadata.page_count == 1


# ---------------------------------------------------------------------------
# BBox geometry
# ---------------------------------------------------------------------------

class TestBBox:

    def test_width_and_height(self):
        from document_engine.dom.base import BBox
        box = BBox(x0=10, y0=20, x1=110, y1=70)
        assert box.width == 100
        assert box.height == 50

    def test_area(self):
        from document_engine.dom.base import BBox
        box = BBox(x0=0, y0=0, x1=10, y1=10)
        assert box.area == 100

    def test_overlaps_true(self):
        from document_engine.dom.base import BBox
        a = BBox(x0=0, y0=0, x1=100, y1=100)
        b = BBox(x0=50, y0=50, x1=150, y1=150)
        assert a.overlaps(b, threshold=0.1) is True

    def test_overlaps_false(self):
        from document_engine.dom.base import BBox
        a = BBox(x0=0, y0=0, x1=10, y1=10)
        b = BBox(x0=500, y0=500, x1=600, y1=600)
        assert a.overlaps(b) is False


# ---------------------------------------------------------------------------
# JSON serialization (debug export)
# ---------------------------------------------------------------------------

class TestDebugExport:

    def test_extract_and_save_writes_json(self, tmp_path):
        pdf_path   = make_text_pdf(tmp_path)
        debug_path = tmp_path / "stage1_raw.json"
        RawExtractor().extract_and_save(pdf_path, str(debug_path))
        assert debug_path.exists()
        content = debug_path.read_text(encoding="utf-8")
        assert "text_spans" in content

    def test_json_roundtrip(self, tmp_path):
        pdf_path = make_text_pdf(tmp_path)
        result   = RawExtractor().extract(pdf_path)
        json_str = result.model_dump_json()
        restored = DocumentRaw.model_validate_json(json_str)
        assert restored.source_path == result.source_path
        assert len(restored.pages) == len(result.pages)


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

class TestErrorResilience:

    def test_multi_page_one_page_ok(self, tmp_path):
        """Verify normal multi-page extraction doesn't drop any pages."""
        pdf_path = make_multi_page_pdf(tmp_path, n=5)
        result = RawExtractor().extract(pdf_path)
        assert len(result.pages) == 5
        assert all(isinstance(p, PageRaw) for p in result.pages)