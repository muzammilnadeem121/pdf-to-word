"""
Tests for UnicodeRepairEngine.

Every repair rule is tested in isolation and as part of the full pipeline.
No PDF files or external dependencies required.

Run with:
    python -m pytest tests/test_unicode_fixer.py -v
"""

import pytest
from extractor.unicode_fixer import (
    UnicodeRepairEngine,
    _looks_like_mojibake,
    _repair_mojibake,
    _INVISIBLE_CHARS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def engine(**kwargs) -> UnicodeRepairEngine:
    """Create an engine with all steps disabled except the ones under test."""
    defaults = dict(
        fix_mojibake           = False,
        fix_presentation_forms = False,
        fix_invisible_chars    = False,
        fix_normalization      = False,
        fix_whitespace         = False,
    )
    defaults.update(kwargs)
    return UnicodeRepairEngine(**defaults)


# ---------------------------------------------------------------------------
# Mojibake detection
# ---------------------------------------------------------------------------

# Replace TestMojibakeDetection and TestMojibakeRepair

class TestMojibakeDetection:

    def test_detects_utf8_as_cp1252_mojibake(self):
        # Build real mojibake: UTF-8 Arabic bytes misread as cp1252
        mojibake = "نماز".encode("utf-8").decode("cp1252")
        assert _looks_like_mojibake(mojibake) is True

    def test_clean_urdu_not_flagged(self):
        assert _looks_like_mojibake("نماز پڑھنا") is False

    def test_clean_english_not_flagged(self):
        assert _looks_like_mojibake("Hello world") is False

    def test_empty_string_not_flagged(self):
        assert _looks_like_mojibake("") is False

    def test_high_ratio_of_mojibake_chars_flagged(self):
        # Manually construct text with >20% Ø/Ù characters
        text = "Ø" * 5 + "abc"
        assert _looks_like_mojibake(text) is True


class TestMojibakeRepair:

    def test_repairs_utf8_as_cp1252_mojibake(self):
        original = "نماز"
        mojibake = original.encode("utf-8").decode("cp1252")
        repaired = _repair_mojibake(mojibake)
        arabic_count = sum(1 for c in repaired if "\u0600" <= c <= "\u06FF")
        assert arabic_count > 0

    def test_repaired_text_matches_original(self):
        original = "نماز"
        mojibake = original.encode("utf-8").decode("cp1252")
        repaired = _repair_mojibake(mojibake)
        assert repaired == original

    def test_non_mojibake_returned_unchanged(self):
        text = "Hello world"
        assert _repair_mojibake(text) == text

    def test_repair_step_in_pipeline(self):
        eng      = engine(fix_mojibake=True)
        mojibake = "نماز".encode("utf-8").decode("cp1252")
        result   = eng.repair(mojibake)
        arabic   = sum(1 for c in result if "\u0600" <= c <= "\u06FF")
        assert arabic > 0

# ---------------------------------------------------------------------------
# Presentation forms
# ---------------------------------------------------------------------------

class TestPresentationForms:

    def test_presentation_form_mapped_to_base(self):
        # ﻧ (U+FBA7, Noon presentation form) → ن (U+0646, base Noon)
        presentation = "\uFBA7"
        eng          = engine(fix_presentation_forms=True)
        result       = eng.repair(presentation * 5)  # needs min_text_length
        # Result should not contain presentation form characters
        has_pres = any("\uFB50" <= c <= "\uFEFF" for c in result)
        assert has_pres is False

    def test_normal_arabic_unchanged(self):
        text   = "نماز پڑھنا"
        eng    = engine(fix_presentation_forms=True)
        result = eng.repair(text)
        # Base Arabic chars should be preserved
        assert "ن" in result

    def test_mixed_presentation_and_base(self):
        # A mix of presentation forms and normal Arabic
        mixed  = "ن\uFBA7ماز"
        eng    = engine(fix_presentation_forms=True)
        result = eng.repair(mixed)
        assert "\uFBA7" not in result


# ---------------------------------------------------------------------------
# Invisible characters
# ---------------------------------------------------------------------------

class TestInvisibleChars:

    def test_removes_zero_width_space(self):
        text   = "ن\u200Bم\u200Bاز"
        eng    = engine(fix_invisible_chars=True)
        result = eng.repair(text)
        assert "\u200B" not in result
        assert "ن" in result

    def test_removes_all_invisible_chars(self):
        for char in _INVISIBLE_CHARS:
            text   = f"اردو{char}متن"
            eng    = engine(fix_invisible_chars=True)
            result = eng.repair(text)
            assert char not in result

    def test_visible_chars_preserved(self):
        text   = "نماز\u200Bپڑھنا"
        eng    = engine(fix_invisible_chars=True)
        result = eng.repair(text)
        assert "نماز" in result
        assert "پڑھنا" in result


# ---------------------------------------------------------------------------
# Unicode normalization
# ---------------------------------------------------------------------------

class TestNormalization:

    def test_nfc_normalization_applied(self):
        import unicodedata
        # Create NFD form (decomposed) of Arabic text
        nfd_text = unicodedata.normalize("NFD", "نماز")
        eng      = engine(fix_normalization=True)
        result   = eng.repair(nfd_text)
        assert unicodedata.is_normalized("NFC", result)

    def test_already_nfc_unchanged(self):
        text   = "نماز پڑھنا"
        eng    = engine(fix_normalization=True)
        result = eng.repair(text)
        assert result == text


# ---------------------------------------------------------------------------
# Whitespace normalization
# ---------------------------------------------------------------------------

class TestWhitespaceNormalization:

    def test_collapses_multiple_spaces(self):
        text   = "نماز    پڑھنا"
        eng    = engine(fix_whitespace=True)
        result = eng.repair(text)
        assert "  " not in result

    def test_strips_line_whitespace(self):
        text   = "  نماز  \n  پڑھنا  "
        eng    = engine(fix_whitespace=True)
        result = eng.repair(text)
        assert not any(line != line.strip() for line in result.splitlines())

    def test_collapses_excessive_newlines(self):
        text   = "نماز\n\n\n\n\nپڑھنا"
        eng    = engine(fix_whitespace=True)
        result = eng.repair(text)
        assert "\n\n\n" not in result

    def test_removes_blank_lines(self):
        text   = "نماز\n\nپڑھنا"
        eng    = engine(fix_whitespace=True)
        result = eng.repair(text)
        lines  = result.splitlines()
        assert all(line.strip() for line in lines)

    def test_collapses_tabs(self):
        text   = "نماز\t\tپڑھنا"
        eng    = engine(fix_whitespace=True)
        result = eng.repair(text)
        assert "\t" not in result


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:

    def test_short_text_returned_unchanged(self):
        eng    = UnicodeRepairEngine(min_text_length=10)
        short  = "نم"
        assert eng.repair(short) == short

    def test_empty_string_returned_unchanged(self):
        assert UnicodeRepairEngine().repair("") == ""

    def test_clean_urdu_passes_through_cleanly(self):
        text   = "یہ ایک آزمائشی جملہ ہے"
        result = UnicodeRepairEngine().repair(text)
        # All original Urdu chars must still be present
        assert "یہ" in result
        assert "جملہ" in result

    def test_pipeline_step_failure_does_not_crash(self, monkeypatch):
        """If one step raises, repair() must continue and return something."""
        eng = UnicodeRepairEngine()
        # Patch one step to always raise
        monkeypatch.setattr(eng, "_step_whitespace", lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
        result = eng.repair("نماز پڑھنا")
        assert isinstance(result, str)

    def test_repair_pages_modifies_raw_text(self):
        from extractor.extractor import PageResult
        from extractor.scanner import ScanDetector
        from models.page_classification import PageClassification, PageType

        classification = PageClassification(
            page_number     = 1,
            page_type       = PageType.DIGITAL,
            confidence      = 0.9,
            char_count      = 20,
            image_coverage  = 0.0,
            urdu_char_ratio = 0.8,
            reason          = "test",
        )
        page = PageResult(
            page_number    = 1,
            classification = classification,
            raw_text       = "نماز\u200Bپڑھنا",  # has invisible char
            char_count     = 10,
        )
        eng = UnicodeRepairEngine()
        eng.repair_pages([page])
        assert "\u200B" not in page.raw_text

    def test_repair_pages_modifies_ocr_text(self):
        from extractor.extractor import PageResult
        from models.page_classification import PageClassification, PageType
        from models.ocr_result import OCRResult, OCRBlock

        classification = PageClassification(
            page_number     = 1,
            page_type       = PageType.SCANNED,
            confidence      = 0.9,
            char_count      = 0,
            image_coverage  = 0.95,
            urdu_char_ratio = 0.0,
            reason          = "test",
        )
        ocr = OCRResult(
            page_number        = 1,
            full_text          = "نماز\u200Bپڑھنا",
            average_confidence = 0.9,
            blocks             = [
                OCRBlock(
                    text       = "نماز\u200B",
                    confidence = 0.9,
                    bbox       = [[0,0],[100,0],[100,20],[0,20]],
                )
            ],
        )
        page = PageResult(
            page_number    = 1,
            classification = classification,
            ocr_result     = ocr,
            char_count     = 5,
        )
        UnicodeRepairEngine().repair_pages([page])
        assert "\u200B" not in page.ocr_result.full_text
        assert "\u200B" not in page.ocr_result.blocks[0].text