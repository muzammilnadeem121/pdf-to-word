"""
Tests for OCR engine components.

EasyOCR itself is not invoked (slow, requires model download).
We test:
  - ImagePreprocessor pipeline steps
  - RTL block sorting
  - BaseOCREngine interface compliance
  - EasyOCREngine graceful failure (mocked)
  - OCRResult and OCRBlock data models

Run with:
    python -m pytest tests/test_ocr_engine.py -v
"""

import numpy as np
import pytest
import fitz
from unittest.mock import patch

from models.ocr_result import OCRBlock, OCRResult
from ocr.base_engine import BaseOCREngine
from ocr.preprocessor import ImagePreprocessor
from ocr.rtl_utils import sort_rtl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def blank_fitz_page(tmp_path) -> fitz.Page:
    doc = fitz.open()
    doc.new_page()
    out = tmp_path / "blank.pdf"
    doc.save(str(out))
    doc.close()
    return fitz.open(str(out))[0]


def rgb_image(h: int = 200, w: int = 400) -> np.ndarray:
    """White RGB image — simulates a clean scanned page."""
    return np.ones((h, w, 3), dtype=np.uint8) * 255


def make_block(x0, y0, x1, y1, text="word", confidence=0.9) -> OCRBlock:
    return OCRBlock(
        text       = text,
        confidence = confidence,
        bbox       = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
    )


# ---------------------------------------------------------------------------
# OCRBlock and OCRResult models
# ---------------------------------------------------------------------------

class TestOCRModels:

    def test_ocr_block_top_y(self):
        block = make_block(50, 100, 150, 120)
        assert block.top_y == 100

    def test_ocr_block_left_x(self):
        block = make_block(50, 100, 150, 120)
        assert block.left_x == 50

    def test_ocr_block_right_x(self):
        block = make_block(50, 100, 150, 120)
        assert block.right_x == 150

    def test_ocr_result_is_empty_true(self):
        result = OCRResult(page_number=1, full_text="", average_confidence=0.0)
        assert result.is_empty is True

    def test_ocr_result_is_empty_whitespace(self):
        result = OCRResult(page_number=1, full_text="   \n ", average_confidence=0.0)
        assert result.is_empty is True

    def test_ocr_result_is_empty_false(self):
        result = OCRResult(page_number=1, full_text="اردو", average_confidence=0.9)
        assert result.is_empty is False

    def test_ocr_result_default_blocks(self):
        result = OCRResult(page_number=1, full_text="text", average_confidence=0.8)
        assert result.blocks == []

    def test_ocr_result_processing_time_default(self):
        result = OCRResult(page_number=1, full_text="", average_confidence=0.0)
        assert result.processing_time_ms == 0.0


# ---------------------------------------------------------------------------
# ImagePreprocessor
# ---------------------------------------------------------------------------

class TestImagePreprocessor:

    def test_render_returns_numpy_array(self, tmp_path):
        page = blank_fitz_page(tmp_path)
        img  = ImagePreprocessor(dpi=72).render(page)
        assert isinstance(img, np.ndarray)
        assert img.ndim == 3
        assert img.dtype == np.uint8

    def test_to_grayscale_reduces_channels(self):
        gray = ImagePreprocessor().to_grayscale(rgb_image())
        assert gray.ndim == 2

    def test_to_grayscale_idempotent(self):
        gray  = ImagePreprocessor().to_grayscale(rgb_image())
        gray2 = ImagePreprocessor().to_grayscale(gray)
        assert gray2.ndim == 2

    def test_binarize_produces_only_0_and_255(self):
        prep   = ImagePreprocessor()
        gray   = prep.to_grayscale(rgb_image())
        binary = prep.binarize_image(gray)
        assert all(v in (0, 255) for v in np.unique(binary))

    def test_remove_noise_preserves_shape(self):
        prep     = ImagePreprocessor()
        gray     = prep.to_grayscale(rgb_image())
        denoised = prep.remove_noise(gray)
        assert denoised.shape == gray.shape

    def test_correct_skew_handles_blank_image(self):
        prep     = ImagePreprocessor()
        gray     = prep.to_grayscale(rgb_image())
        deskewed = prep.correct_skew(gray)
        assert deskewed.shape == gray.shape

    def test_prepare_full_pipeline(self, tmp_path):
        page = blank_fitz_page(tmp_path)
        img  = ImagePreprocessor(dpi=72).prepare(page)
        assert isinstance(img, np.ndarray)
        assert img.dtype == np.uint8

    def test_prepare_with_all_steps_disabled(self, tmp_path):
        page = blank_fitz_page(tmp_path)
        prep = ImagePreprocessor(dpi=72, denoise=False, deskew=False, binarize=False)
        img  = prep.prepare(page)
        assert img.ndim == 2  # still grayscale


# ---------------------------------------------------------------------------
# RTL sorting
# ---------------------------------------------------------------------------

class TestRTLSorting:

    def test_same_line_sorted_right_to_left(self):
        left  = make_block(x0=50,  y0=100, x1=150, y1=120, text="left")
        right = make_block(x0=200, y0=100, x1=300, y1=120, text="right")
        result = sort_rtl([left, right])
        assert result[0].text == "right"
        assert result[1].text == "left"

    def test_different_lines_top_to_bottom(self):
        top    = make_block(x0=100, y0=50,  x1=200, y1=70,  text="top")
        bottom = make_block(x0=100, y0=150, x1=200, y1=170, text="bottom")
        result = sort_rtl([bottom, top])
        assert result[0].text == "top"
        assert result[1].text == "bottom"

    def test_empty_list(self):
        assert sort_rtl([]) == []

    def test_single_block_unchanged(self):
        block  = make_block(100, 100, 200, 120, text="only")
        result = sort_rtl([block])
        assert len(result) == 1
        assert result[0].text == "only"

    def test_blocks_within_tolerance_treated_as_same_line(self):
        """Blocks within LINE_TOLERANCE_PX of each other are one line."""
        b1 = make_block(200, 100, 300, 120, text="right")
        b2 = make_block(50,  108, 150, 128, text="left")  # y=108, within 15px of y=100
        result = sort_rtl([b1, b2])
        # Same line → RTL → right first
        assert result[0].text == "right"

    def test_blocks_outside_tolerance_are_separate_lines(self):
        b1 = make_block(50, 100, 150, 120, text="line1")
        b2 = make_block(50, 140, 150, 160, text="line2")  # y=140, >15px from y=100
        result = sort_rtl([b1, b2])
        assert result[0].text == "line1"
        assert result[1].text == "line2"


# ---------------------------------------------------------------------------
# BaseOCREngine interface
# ---------------------------------------------------------------------------

class TestBaseOCREngineInterface:

    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            BaseOCREngine()

    def test_missing_process_page_cannot_instantiate(self):
        class IncompleteEngine(BaseOCREngine):
            def warm_up(self): pass

        with pytest.raises(TypeError):
            IncompleteEngine()

    def test_missing_warm_up_cannot_instantiate(self):
        class IncompleteEngine(BaseOCREngine):
            def process_page(self, page, page_number): pass

        with pytest.raises(TypeError):
            IncompleteEngine()

    def test_minimal_concrete_engine_satisfies_interface(self):
        class StubEngine(BaseOCREngine):
            def process_page(self, page, page_number) -> OCRResult:
                return OCRResult(
                    page_number        = page_number,
                    full_text          = "stub",
                    average_confidence = 1.0,
                )
            def warm_up(self): pass

        engine = StubEngine()
        assert engine is not None


# ---------------------------------------------------------------------------
# EasyOCREngine — graceful failure (mocked, no model download)
# ---------------------------------------------------------------------------

class TestEasyOCREngine:

    def test_returns_empty_result_on_failure(self, tmp_path):
        from ocr.easyocr_engine import EasyOCREngine

        engine = EasyOCREngine()
        page   = blank_fitz_page(tmp_path)

        with patch.object(engine, "_ensure_initialized", side_effect=RuntimeError("not installed")):
            result = engine.process_page(page, page_number=1)

        assert isinstance(result, OCRResult)
        assert result.full_text == ""
        assert result.average_confidence == 0.0
        assert result.page_number == 1
        assert result.blocks == []

    def test_low_confidence_blocks_discarded(self, tmp_path):
        """Blocks below min_confidence threshold must be filtered out."""
        from ocr.easyocr_engine import EasyOCREngine

        engine = EasyOCREngine(min_confidence=0.7)
        assert engine._min_confidence == 0.7
        page   = blank_fitz_page(tmp_path)

        # EasyOCR readtext(detail=1) format: [bbox, text, confidence]
        fake_results = [
            ([[0,0],[100,0],[100,20],[0,20]], "high conf", 0.95),
            ([[0,30],[100,30],[100,50],[0,50]], "low conf", 0.40),
        ]

        with patch.object(engine, "_ensure_initialized"):
            engine._reader = type("R", (), {"readtext": lambda self, img, **kw: fake_results})()
            result = engine.process_page(page, page_number=1)

        assert len(result.blocks) == 1
        assert result.blocks[0].text == "high conf"

    def test_empty_page_returns_empty_result(self, tmp_path):
        """When OCR finds nothing, result is empty — not an error."""
        from ocr.easyocr_engine import EasyOCREngine

        engine = EasyOCREngine()
        page   = blank_fitz_page(tmp_path)

        with patch.object(engine, "_ensure_initialized"):
            engine._reader = type("R", (), {"readtext": lambda self, img, **kw: []})()
            result = engine.process_page(page, page_number=1)

        assert result.is_empty is True
        assert result.average_confidence == 0.0

    def test_processing_time_is_recorded(self, tmp_path):
        from ocr.easyocr_engine import EasyOCREngine

        engine = EasyOCREngine()
        page   = blank_fitz_page(tmp_path)

        with patch.object(engine, "_ensure_initialized"):
            engine._reader = type("R", (), {"readtext": lambda self, img, **kw: []})()
            result = engine.process_page(page, page_number=1)

        assert result.processing_time_ms >= 0.0

    def test_is_instance_of_base_engine(self):
        from ocr.easyocr_engine import EasyOCREngine
        assert isinstance(EasyOCREngine(), BaseOCREngine)