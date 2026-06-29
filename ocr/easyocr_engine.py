import fitz
import easyocr
import numpy as np
from models.ocr_result import OCRBlock, OCRResult
from ocr.base_engine import BaseOCREngine
from ocr.preprocessor import ImagePreprocessor

class EasyOCREngine(BaseOCREngine):
    def __init__(
        self,
        languages:      list[str]                   = ["ur", "en"],
        gpu:            bool                        = False,
        min_confidence: float                       = 0.5,
        preprocessor:   Optional[ImagePreprocessor] = None,
    ) -> None:
        self._languages      = languages
        self._gpu            = gpu
        self._min_confidence = min_confidence
        self._prep           = preprocessor or ImagePreprocessor()
        self._reader         = None

    def warm_up(self):
        self._ensure_initialized()

    # ocr/easyocr_engine.py — replace process_page

    def process_page(self, page: fitz.Page, page_number: int) -> OCRResult:
        import time
        start = time.perf_counter()
        try:
            self._ensure_initialized()
            img     = self._prep.prepare(page)
            results = self._reader.readtext(img, detail=1, paragraph=False)
            blocks = [
                OCRBlock(text=r[1], confidence=r[2], bbox=r[0])
                for r in results
                if r[2] >= self._min_confidence
            ]
            elapsed = (time.perf_counter() - start) * 1000
            return OCRResult(
                page_number        = page_number,
                full_text          = "\n".join(b.text for b in blocks),
                average_confidence = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0,
                blocks             = blocks,
                processing_time_ms = elapsed,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("EasyOCR failed on page %d: %s", page_number, exc)
            elapsed = (time.perf_counter() - start) * 1000
            return OCRResult(
                page_number        = page_number,
                full_text          = "",
                average_confidence = 0.0,
                blocks             = [],
                processing_time_ms = elapsed,
            )

    def _ensure_initialized(self):
        if self._reader is None:
            self._reader = easyocr.Reader(["ur", "en"], gpu=False)