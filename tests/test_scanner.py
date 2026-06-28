"""
Tests for the upgraded ScanDetector.

Run with:
    python -m pytest tests/test_scanner.py -v
"""

import pytest
import fitz
from extractor.scanner import ScanDetector
from models.page_classification import PageType


def blank_page(tmp_path) -> fitz.Page:
    """A completely empty page."""
    doc = fitz.open()
    doc.new_page()
    out = tmp_path / "blank.pdf"
    doc.save(str(out))
    doc.close()
    return fitz.open(str(out))[0]


def text_page(tmp_path, text="یہ ایک آزمائشی متن ہے جو کافی لمبا ہے") -> fitz.Page:
    """A page with embedded Urdu text."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=14)
    out = tmp_path / "text.pdf"
    doc.save(str(out))
    doc.close()
    return fitz.open(str(out))[0]


class TestScanDetector:

    def test_blank_page_is_scanned(self, tmp_path):
        page = blank_page(tmp_path)
        result = ScanDetector().classify(page)
        assert result.page_type == PageType.SCANNED
        assert result.confidence >= 0.7

    def test_text_page_is_digital(self, tmp_path):
        page = text_page(tmp_path)
        result = ScanDetector().classify(page)
        assert result.page_type == PageType.DIGITAL
        assert result.confidence >= 0.7
        assert result.char_count > 0

    def test_classification_has_reason(self, tmp_path):
        page = blank_page(tmp_path)
        result = ScanDetector().classify(page)
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    def test_urdu_ratio_on_urdu_text(self, tmp_path):
        page = text_page(tmp_path, text="یہ اردو متن ہے")
        result = ScanDetector().classify(page)
        # PyMuPDF may not embed the chars perfectly in a test PDF,
        # but confidence and type should still be set
        assert result.confidence > 0

    def test_is_scanned_backward_compat(self, tmp_path):
        """The old boolean API must still work."""
        page = blank_page(tmp_path)
        detector = ScanDetector()
        assert detector.is_scanned(page) is True

    def test_needs_ocr_property(self, tmp_path):
        page = blank_page(tmp_path)
        result = ScanDetector().classify(page)
        assert result.needs_ocr is True
        assert result.needs_extraction is False

    def test_custom_min_chars_threshold(self, tmp_path):
        page = text_page(tmp_path, text="Hi")  # only 2 chars
        result = ScanDetector(min_chars=50).classify(page)
        # With a very high threshold, short text is treated as scanned
        assert result.page_type == PageType.SCANNED

    def test_confidence_in_range(self, tmp_path):
        for page in [blank_page(tmp_path), text_page(tmp_path)]:
            result = ScanDetector().classify(page)
            assert 0.0 <= result.confidence <= 1.0