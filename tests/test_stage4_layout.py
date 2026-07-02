"""
Tests for Stage 4 — Layout Analysis.

Builds synthetic DocumentText/DocumentVisual objects directly to test
each classification rule in isolation, plus multi-page tests for
header/footer repetition detection and end-to-end integration.

Run with:
    python -m pytest tests/test_stage4_layout.py -v
"""

import pytest

from document_engine.dom.base import BBox
from document_engine.dom.text import (
    DocumentText, PageTextAnalysis, TextBlock, TextLine, TextSource,
)
from document_engine.dom.visual import DocumentVisual, ImageRegion, Margins, PageVisual
from document_engine.dom.layout import LayoutRole
from document_engine.stages.stage4_layout import LayoutAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_line(
    text, x0=100, y0=100, x1=400, y1=118,
    font_size=12.0, is_bold=False, is_rtl=True,
) -> TextLine:
    return TextLine(
        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
        text=text, source=TextSource.EMBEDDED,
        font_size=font_size, is_bold=is_bold, is_rtl=is_rtl,
    )


def make_page_text(page_number, lines: list[TextLine]) -> PageTextAnalysis:
    return PageTextAnalysis(
        page_number=page_number,
        blocks=[TextBlock(page_number=page_number, lines=lines)],
    )


def make_doc_text(pages: list[PageTextAnalysis]) -> DocumentText:
    return DocumentText(source_path="dummy.pdf", pages=pages)


def make_doc_visual(pages_visual: list[PageVisual]) -> DocumentVisual:
    return DocumentVisual(source_path="dummy.pdf", pages=pages_visual)


def blank_visual(page_number) -> PageVisual:
    return PageVisual(
        page_number=page_number,
        margins=Margins(top=0, bottom=0, left=0, right=0),
    )


# ---------------------------------------------------------------------------
# Body font size baseline
# ---------------------------------------------------------------------------

class TestBodyFontSize:

    def test_median_computed(self):
        lines = [make_line("متن ایک", font_size=12.0), make_line("متن دو", font_size=12.0)]
        doc_text = make_doc_text([make_page_text(1, lines)])
        result = LayoutAnalyzer()._compute_body_font_size(doc_text)
        assert result == pytest.approx(12.0)

    def test_default_when_no_sizes(self):
        doc_text = make_doc_text([])
        result = LayoutAnalyzer()._compute_body_font_size(doc_text)
        assert result == 12.0


# ---------------------------------------------------------------------------
# Heading classification
# ---------------------------------------------------------------------------

class TestHeadingClassification:

    def test_large_font_is_heading(self):
        line = make_line("عنوان", font_size=28.0, y0=300, y1=320)
        role, level, reason = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.HEADING
        assert level == 1

    def test_bold_short_is_heading(self):
        line = make_line("مختصر عنوان", font_size=12.0, is_bold=True, y0=300, y1=320)
        role, level, reason = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.HEADING

    def test_normal_text_is_paragraph(self):
        line = make_line(
            "یہ ایک لمبا جملہ ہے جو عام متن کی طرح نظر آتا ہے",
            font_size=12.0, y0=300, y1=320,
        )
        role, level, reason = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.PARAGRAPH


# ---------------------------------------------------------------------------
# Page number classification
# ---------------------------------------------------------------------------

class TestPageNumberClassification:

    def test_numeric_in_top_margin_is_page_number(self):
        line = make_line("١٢", y0=5, y1=15)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.PAGE_NUMBER

    def test_numeric_not_in_margin_is_not_page_number(self):
        line = make_line("١٢", y0=400, y1=415)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role != LayoutRole.PAGE_NUMBER


# ---------------------------------------------------------------------------
# List item classification
# ---------------------------------------------------------------------------

class TestListClassification:

    def test_bullet_marker(self):
        line = make_line("• پہلا نکتہ", y0=300, y1=320)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.LIST_ITEM

    def test_numbered_marker(self):
        line = make_line("1. پہلا نکتہ", y0=300, y1=320)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.LIST_ITEM


# ---------------------------------------------------------------------------
# Reference classification
# ---------------------------------------------------------------------------

class TestReferenceClassification:

    def test_bracket_number_marker(self):
        line = make_line("[1] حوالہ جات کی تفصیل", y0=300, y1=320)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.REFERENCE


# ---------------------------------------------------------------------------
# Caption classification
# ---------------------------------------------------------------------------

class TestCaptionClassification:

    def test_short_line_below_image_is_caption(self):
        image = ImageRegion(
            bbox=BBox(x0=50, y0=100, x1=400, y1=250),
            source_image_id="img1", is_likely_photo=True,
        )
        line = make_line("تصویر کی وضاحت", x0=60, x1=200, y0=255, y1=270)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[image],
        )
        assert role == LayoutRole.CAPTION

    def test_far_from_image_not_caption(self):
        image = ImageRegion(
            bbox=BBox(x0=50, y0=100, x1=400, y1=250),
            source_image_id="img1", is_likely_photo=True,
        )
        line = make_line("غیر متعلقہ متن", x0=60, x1=200, y0=500, y1=520)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[image],
        )
        assert role != LayoutRole.CAPTION


# ---------------------------------------------------------------------------
# Footnote classification
# ---------------------------------------------------------------------------

class TestFootnoteClassification:

    def test_small_font_bottom_margin_is_footnote(self):
        line = make_line("حاشیہ", font_size=8.0, y0=780, y1=795)
        role, _, _ = LayoutAnalyzer()._classify_line(
            line, body_size=12.0, page_height=800,
            header_pattern=None, footer_pattern=None, image_regions=[],
        )
        assert role == LayoutRole.FOOTNOTE


# ---------------------------------------------------------------------------
# Header / footer repetition detection
# ---------------------------------------------------------------------------

class TestHeaderFooterDetection:

    def test_repeated_top_text_detected_as_header(self):
        pages = []
        for i in range(1, 5):
            top_line = make_line("بی بی سی اردو نیوز", y0=5, y1=18)
            body_line = make_line(f"صفحہ {i} کا متن یہ ہے جو کافی لمبا ہے", y0=200, y1=220)
            pages.append(make_page_text(i, [top_line, body_line]))

        doc_text = make_doc_text(pages)
        header, footer = LayoutAnalyzer()._detect_repeated_zones(doc_text)
        assert header is not None

    def test_no_repetition_below_min_pages(self):
        pages = [make_page_text(1, [make_line("متن", y0=5, y1=18)])]
        doc_text = make_doc_text(pages)
        header, footer = LayoutAnalyzer()._detect_repeated_zones(doc_text)
        assert header is None
        assert footer is None

    def test_normalize_strips_digits(self):
        analyzer = LayoutAnalyzer()
        assert analyzer._normalize_for_repeat("صفحہ 3") == analyzer._normalize_for_repeat("صفحہ 4")


# ---------------------------------------------------------------------------
# Quotation reclassification
# ---------------------------------------------------------------------------

class TestQuotationReclassification:

    def test_indented_paragraph_becomes_quotation(self):
        from document_engine.dom.layout import LayoutBlock

        blocks = [
            LayoutBlock(bbox=BBox(x0=100, y0=100, x1=400, y1=120),
                        text="عام پیراگراف ایک", role=LayoutRole.PARAGRAPH),
            LayoutBlock(bbox=BBox(x0=100, y0=140, x1=400, y1=160),
                        text="عام پیراگراف دو", role=LayoutRole.PARAGRAPH),
            LayoutBlock(bbox=BBox(x0=100, y0=180, x1=400, y1=200),
                        text="عام پیراگراف تین", role=LayoutRole.PARAGRAPH),
            LayoutBlock(bbox=BBox(x0=150, y0=220, x1=400, y1=240),
                        text="یہ اقتباس ہے", role=LayoutRole.PARAGRAPH),  # indented +50
        ]
        LayoutAnalyzer()._reclassify_quotations(blocks)
        assert blocks[-1].role == LayoutRole.QUOTATION
        assert blocks[0].role == LayoutRole.PARAGRAPH   # unaffected

    def test_no_reclassification_with_insufficient_data(self):
        from document_engine.dom.layout import LayoutBlock

        blocks = [
            LayoutBlock(bbox=BBox(x0=100, y0=100, x1=400, y1=120),
                        text="صرف ایک پیراگراف", role=LayoutRole.PARAGRAPH),
        ]
        LayoutAnalyzer()._reclassify_quotations(blocks)
        assert blocks[0].role == LayoutRole.PARAGRAPH


# ---------------------------------------------------------------------------
# Full page classification
# ---------------------------------------------------------------------------

class TestPageClassificationIntegration:

    def test_classify_page_produces_blocks(self):
        lines = [
            make_line("بڑا عنوان", font_size=24.0, y0=50, y1=75),
            make_line("یہ ایک عام پیراگراف ہے جو کافی طویل ہے تاکہ ٹیسٹ ہو سکے", y0=100, y1=118),
        ]
        page_text = make_page_text(1, lines)
        page_visual = blank_visual(1)

        result = LayoutAnalyzer()._classify_page(
            page_text, page_visual, body_size=12.0,
            header_pattern=None, footer_pattern=None,
        )
        assert len(result.blocks) == 2
        assert result.blocks[0].role == LayoutRole.HEADING
        assert result.blocks[1].role == LayoutRole.PARAGRAPH

    def test_empty_page_returns_empty_blocks(self):
        page_text = make_page_text(1, [])
        result = LayoutAnalyzer()._classify_page(
            page_text, blank_visual(1), body_size=12.0,
            header_pattern=None, footer_pattern=None,
        )
        assert result.blocks == []


# ---------------------------------------------------------------------------
# End-to-end: Stage 1 -> 2 -> 3 -> 4
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:

    def test_digital_pdf_through_stage4(self, tmp_path):
        import fitz
        from document_engine.stages.stage1_extraction import RawExtractor
        from document_engine.stages.stage2_visual import VisualAnalyzer
        from document_engine.stages.stage3_text import TextAnalyzer
        from document_engine.ocr.base import OCRProvider, OCRPageResult

        class StubOCR(OCRProvider):
            @property
            def provider_name(self): return "stub"
            def warm_up(self): pass
            def recognize(self, image, page_number):
                return OCRPageResult(page_number=page_number)

        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "یہ ایک آزمائشی جملہ ہے جو کافی لمبا ہے", fontsize=14)
        pdf_path = tmp_path / "test.pdf"
        doc.save(str(pdf_path)); doc.close()

        doc_raw    = RawExtractor().extract(str(pdf_path))
        doc_visual = VisualAnalyzer().analyze(doc_raw)
        doc_text   = TextAnalyzer(ocr_provider=StubOCR()).analyze(doc_raw, doc_visual, str(pdf_path))
        doc_layout = LayoutAnalyzer().analyze(doc_text, doc_visual)

        assert len(doc_layout.pages) == 1
        assert len(doc_layout.pages[0].blocks) >= 1

    def test_debug_export(self, tmp_path):
        doc_text   = make_doc_text([make_page_text(1, [make_line("متن")])])
        doc_visual = make_doc_visual([blank_visual(1)])
        debug_path = tmp_path / "stage4_layout.json"
        LayoutAnalyzer().extract_and_save(doc_text, doc_visual, str(debug_path))
        assert debug_path.exists()
        assert "role" in debug_path.read_text(encoding="utf-8")