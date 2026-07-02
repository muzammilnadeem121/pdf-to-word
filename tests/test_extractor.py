"""
Tests for PDFExtractor and ScanDetector.

To run:
    python -m pytest tests/test_extractor.py -v
"""

import pytest
from pathlib import Path
from extractor.extractor import PDFExtractor, ExtractionResult
from extractor.scanner import ScanDetector


# ── Helper: create a minimal real PDF in memory ──────────────────────────────

# tests/test_extractor.py  — replace make_test_pdf and test_digital_pdf_extraction only

def make_test_pdf(tmp_path: Path, text: str = "This is a test page with enough text to pass the digital threshold check.") -> str:
    """
    Creates a single-page PDF with embedded text.

    We use plain ASCII here because PyMuPDF's built-in fonts don't
    fully embed Urdu glyphs — the char count after extraction ends up
    below the default min_chars=20 threshold, causing a false SCANNED
    classification. The extractor's job is page classification and
    text extraction; language correctness is tested in test_scanner.py.
    """
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    out = tmp_path / "test.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


# ── ScanDetector tests ────────────────────────────────────────────────────────

class TestScanDetector:
    def test_digital_page_not_scanned(self, tmp_path):
        import fitz
        pdf_path = make_test_pdf(tmp_path)
        doc = fitz.open(pdf_path)
        detector = ScanDetector(min_chars=5)
        assert detector.is_scanned(doc[0]) is False
        doc.close()

    def test_empty_page_is_scanned(self, tmp_path):
        import fitz
        doc = fitz.open()
        doc.new_page()  # blank page, no text
        out = tmp_path / "blank.pdf"
        doc.save(str(out))
        doc.close()

        doc2 = fitz.open(str(out))
        detector = ScanDetector(min_chars=20)
        assert detector.is_scanned(doc2[0]) is True
        doc2.close()

    def test_custom_threshold(self, tmp_path):
        pdf_path = make_test_pdf(tmp_path, text="Hi")
        import fitz
        doc = fitz.open(pdf_path)
        # "Hi" = 2 chars, threshold = 5 → scanned
        assert ScanDetector(min_chars=5).is_scanned(doc[0]) is True
        # "Hi" = 2 chars, threshold = 1 → digital
        assert ScanDetector(min_chars=1).is_scanned(doc[0]) is False
        doc.close()


# ── PDFExtractor tests ────────────────────────────────────────────────────────

class TestPDFExtractor:
    def test_raises_on_missing_file(self):
        extractor = PDFExtractor()
        with pytest.raises(FileNotFoundError):
            extractor.extract("/nonexistent/path/file.pdf")

    def test_raises_on_wrong_extension(self, tmp_path):
        fake = tmp_path / "file.txt"
        fake.write_text("hello")
        with pytest.raises(ValueError):
            PDFExtractor().extract(str(fake))

    def test_digital_pdf_extraction(self, tmp_path):
        pdf_path = make_test_pdf(tmp_path)
        result: ExtractionResult = PDFExtractor().extract(pdf_path)

        assert result.total_pages == 1
        assert result.digital_pages == 1
        assert result.scanned_pages == 0
        assert result.pages[0].is_scanned is False
        assert result.pages[0].raw_text is not None
        assert result.pages[0].char_count > 0

    def test_page_numbers_are_1_based(self, tmp_path):
        pdf_path = make_test_pdf(tmp_path)
        result = PDFExtractor().extract(pdf_path)
        assert result.pages[0].page_number == 1