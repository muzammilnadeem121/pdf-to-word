"""
EasyOCR implementation of the OCRProvider interface.

Chosen as the initial provider because it has verified Python 3.14
compatibility. Swapping to Tesseract/PaddleOCR/TrOCR later requires
implementing OCRProvider — nothing else in the pipeline changes.
"""

import logging
import time

import numpy as np

from document_engine.dom.base import BBox
from document_engine.ocr.base import OCRPageResult, OCRProvider, OCRWordResult

logger = logging.getLogger(__name__)


class EasyOCRProvider(OCRProvider):
    """
    OCR provider backed by EasyOCR.

    Parameters
    ----------
    languages      : EasyOCR language codes. Default ['ur', 'en'] for Urdu.
    gpu            : Use GPU acceleration if available.
    min_confidence : Discard recognized words below this confidence.
    """

    def __init__(
        self,
        languages:      list[str] = ["ur", "en"],
        gpu:            bool = False,
        min_confidence: float = 0.5,
    ) -> None:
        self._languages      = languages
        self._gpu            = gpu
        self._min_confidence = min_confidence
        self._reader          = None

    @property
    def provider_name(self) -> str:
        return "easyocr"

    def warm_up(self) -> None:
        self._ensure_initialized()

    def recognize(self, image: np.ndarray, page_number: int) -> OCRPageResult:
        start = time.perf_counter()

        try:
            self._ensure_initialized()
            raw_results = self._reader.readtext(image, detail=1, paragraph=False)
        except Exception as exc:
            logger.error("EasyOCR failed on page %d: %s", page_number, exc)
            elapsed = (time.perf_counter() - start) * 1000
            return OCRPageResult(page_number=page_number, processing_time_ms=elapsed)

        words: list[OCRWordResult] = []
        for entry in raw_results:
            bbox_pts, text, confidence = entry
            if confidence < self._min_confidence or not text.strip():
                continue

            xs = [p[0] for p in bbox_pts]
            ys = [p[1] for p in bbox_pts]
            words.append(OCRWordResult(
                text=text.strip(),
                confidence=float(confidence),
                bbox=BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys)),
                language=None,
            ))

        avg_conf = sum(w.confidence for w in words) / len(words) if words else 0.0
        elapsed  = (time.perf_counter() - start) * 1000

        return OCRPageResult(
            page_number=page_number,
            words=words,
            average_confidence=avg_conf,
            processing_time_ms=elapsed,
        )

    def _ensure_initialized(self) -> None:
        if self._reader is not None:
            return
        try:
            import easyocr
            logger.info("Loading EasyOCR (languages=%s, gpu=%s)...", self._languages, self._gpu)
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
            logger.info("EasyOCR ready.")
        except ImportError as exc:
            raise RuntimeError(
                f"EasyOCR is not installed. Run: pip install easyocr\nOriginal error: {exc}"
            ) from exc