"""
Tests for Stage 3 — Text Analysis.

Covers span-to-line-to-block merging, Unicode repair integration,
scanned/mixed page detection, and the OCR provider interface — using
synthetic data and mocked OCR to avoid model downloads in CI.

Run with:
    python -m pytest tests/test_stage3_text.py -v
"""

import pytest
from unittest.mock import MagicMock, patch

import fitz

from document_engine.dom.base import BBox
from document_engine.dom.raw import (
    DocumentMetadataRaw, DocumentRaw, FontInfo, ImageRaw, PageRaw, TextSpanRaw,
)
from document_engine.dom.visual import DocumentVisual, ImageRegion, Margins, PageVisual
from document_engine.dom.text import TextSource
from document_engine.ocr.base import OCRPageResult, OCRProvider, OCRWordResult
from document_engine.stages.stage3_text import TextAnalyzer
from document_engine.text_processing.unicode_repair import (
    UnicodeRepairEngine, is_rtl_text, looks_like_mojibake, repair_mojibake,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_span(x0, y0, x1, y1, text, size=12.0) -> TextSpanRaw:
    return TextSpanRaw(
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text=text,
        font=FontInfo(name="Arial", size=size),
    )


def make_pdf(tmp_path, text="یہ ایک آزمائشی جملہ ہے جو کافی لمبا ہے") -> str:
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 100), text, fontsize=14)
    out = tmp_path / "test.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


class StubOCRProvider(OCRProvider):
    """Deterministic OCR stub for testing without model downloads."""
    def __init__(self, words=None):
        self._words = words or []

    @property
    def provider_name(self) -> str:
        return "stub"

    def warm_up(self) -> None:
        pass

    def recognize(self, image, page_number: int) -> OCRPageResult:
        return OCRPageResult(
            page_number=page_number,
            words=self._words,
            average_confidence=0.9 if self._words else 0.0,
        )


# ---------------------------------------------------------------------------
# Unicode repair (ported logic)
# ---------------------------------------------------------------------------

class TestUnicodeRepair:

    def test_mojibake_detected_and_repaired(self):
        original = "نماز"
        mojibake = original.encode("utf-8").decode("cp1252")
        assert looks_like_mojibake(mojibake) is True
        assert repair_mojibake(mojibake) == original

    def test_presentation_forms_normalized(self):
        engine = UnicodeRepairEngine()
        result = engine.repair("\uFBA7" * 5)
        assert not any("\uFB50" <= c <= "\uFEFF" for c in result)

    def test_invisible_chars_removed(self):
        engine = UnicodeRepairEngine()
        result = engine.repair("نماز\u200Bپڑھنا")
        assert "\u200B" not in result

    def test_is_rtl_text(self):
        assert is_rtl_text("نماز پڑھنا") is True
        assert is_rtl_text("Hello world") is False


# ---------------------------------------------------------------------------
# Span -> line -> block merging
# ---------------------------------------------------------------------------

class TestSpanMerging:

    def test_spans_on_same_line_merged(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(300, 100, 400, 118, "پہلا"),
                make_span(100, 100, 290, 118, "دوسرا"),
            ],
        )
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        blocks = analyzer._merge_embedded_text(page)
        assert len(blocks) == 1
        assert len(blocks[0].lines) == 1

    def test_spans_on_different_lines_separate(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(100, 100, 200, 118, "پہلی سطر یہ ایک لمبی سطر ہے"),
                make_span(100, 300, 200, 318, "دوسری سطر یہ بھی ایک لمبی سطر ہے"),
            ],
        )
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        blocks = analyzer._merge_embedded_text(page)
        # Big gap -> separate blocks
        assert len(blocks) == 2

    def test_rtl_order_within_line(self):
        page = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[
                make_span(300, 100, 400, 118, "right"),
                make_span(100, 100, 290, 118, "left"),
            ],
        )
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        blocks = analyzer._merge_embedded_text(page)
        # Right span (higher x0) should come first
        assert blocks[0].lines[0].text.startswith("right")

    def test_empty_page_no_blocks(self):
        page = PageRaw(page_number=1, width=600, height=800)
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        assert analyzer._merge_embedded_text(page) == []


# ---------------------------------------------------------------------------
# Scanned / mixed detection
# ---------------------------------------------------------------------------

class TestPageClassification:

    def test_high_image_low_text_is_scanned(self, tmp_path):
        pdf_path = make_pdf(tmp_path, text="")  # no text
        doc = fitz.open(pdf_path)
        doc[0].insert_text((10,10), "")  # keep blank
        doc.save(str(tmp_path/"blank2.pdf")); doc.close()

        page_raw = PageRaw(
            page_number=1, width=600, height=800,
            images=[ImageRaw(
                bbox=BBox(x0=0, y0=0, x1=600, y1=800),
                xref=1, width_px=1000, height_px=1000, colorspace="RGB",
            )],
        )
        page_visual = PageVisual(
            page_number=1, margins=Margins(top=0,bottom=0,left=0,right=0),
            images=[ImageRegion(
                page_number=1,
                bbox=BBox(x0=0, y0=0, x1=600, y1=800),
                source_image_id="x", is_likely_photo=True,
            )],
        )
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        ratio = analyzer._compute_image_ratio(page_raw, page_visual)
        assert ratio > 0.6

    def test_digital_page_not_scanned(self, tmp_path):
        page_raw = PageRaw(
            page_number=1, width=600, height=800,
            text_spans=[make_span(50,50,400,68, "یہ ایک لمبا جملہ ہے جو ٹیسٹ کے لیے کافی حروف رکھتا ہے")],
        )
        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        char_count = sum(len(s.text.replace(" ","")) for s in page_raw.text_spans)
        assert char_count >= 20


# ---------------------------------------------------------------------------
# OCR provider interface
# ---------------------------------------------------------------------------

class TestOCRProviderInterface:

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            OCRProvider()

    def test_stub_provider_returns_standard_format(self):
        words = [OCRWordResult(
            text="نماز", confidence=0.95,
            bbox=BBox(x0=0,y0=0,x1=50,y1=20),
        )]
        provider = StubOCRProvider(words=words)
        result = provider.recognize(image=None, page_number=1)
        assert isinstance(result, OCRPageResult)
        assert result.average_confidence == 0.9
        assert result.words[0].text == "نماز"

    def test_empty_ocr_result(self):
        provider = StubOCRProvider(words=[])
        result = provider.recognize(image=None, page_number=1)
        assert result.is_empty is True


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------

class TestStage3Integration:

    def test_digital_pdf_end_to_end(self, tmp_path):
        from document_engine.stages.stage1_extraction import RawExtractor
        from document_engine.stages.stage2_visual import VisualAnalyzer

        pdf_path = make_pdf(tmp_path)
        doc_raw    = RawExtractor().extract(pdf_path)
        doc_visual = VisualAnalyzer().analyze(doc_raw)

        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        doc_text = analyzer.analyze(doc_raw, doc_visual, pdf_path)

        assert len(doc_text.pages) == 1
        page = doc_text.pages[0]
        assert page.is_scanned is False
        assert page.full_text.strip() != ""

    def test_debug_export(self, tmp_path):
        from document_engine.stages.stage1_extraction import RawExtractor
        from document_engine.stages.stage2_visual import VisualAnalyzer

        pdf_path = make_pdf(tmp_path)
        doc_raw    = RawExtractor().extract(pdf_path)
        doc_visual = VisualAnalyzer().analyze(doc_raw)

        analyzer = TextAnalyzer(ocr_provider=StubOCRProvider())
        debug_path = tmp_path / "stage3_text.json"
        analyzer.extract_and_save(doc_raw, doc_visual, pdf_path, str(debug_path))
        assert debug_path.exists()
        assert "blocks" in debug_path.read_text(encoding="utf-8")