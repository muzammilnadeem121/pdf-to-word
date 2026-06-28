import fitz
import easyocr
import numpy as np
from models.ocr_result import OCRBlock, OCRResult
from ocr.base_engine import BaseOCREngine
from ocr.preprocessor import ImagePreprocessor

class EasyOCREngine(BaseOCREngine):
    def __init__(self):
        self._reader = None
        self._prep   = ImagePreprocessor()

    def warm_up(self):
        self._ensure_initialized()

    def process_page(self, page: fitz.Page, page_number: int) -> OCRResult:
        self._ensure_initialized()
        img     = self._prep.prepare(page)
        results = self._reader.readtext(img, detail=1, paragraph=False)
        blocks  = [
            OCRBlock(text=r[1], confidence=r[2], bbox=r[0])
            for r in results if r[2] >= 0.5
        ]
        return OCRResult(
            page_number        = page_number,
            full_text          = "\n".join(b.text for b in blocks),
            average_confidence = sum(b.confidence for b in blocks) / len(blocks) if blocks else 0.0,
            blocks             = blocks,
        )

    def _ensure_initialized(self):
        if self._reader is None:
            self._reader = easyocr.Reader(["ur", "en"], gpu=False)