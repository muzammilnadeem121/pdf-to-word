"""
Provider-agnostic OCR interface.

Every OCR engine (EasyOCR, Tesseract, PaddleOCR, TrOCR, custom models)
implements this interface and returns the same standardized result
shape. Stage 3 never knows which engine produced a result.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from document_engine.dom.base import BBox


class OCRWordResult(BaseModel):
    """One recognized text region from an OCR provider."""
    text:        str
    confidence:  float          # 0.0-1.0, standardized across all providers
    bbox:        BBox
    language:    str | None = None


class OCRPageResult(BaseModel):
    """Standardized OCR output for a single rendered page image."""
    page_number:        int
    words:               list[OCRWordResult] = Field(default_factory=list)
    average_confidence:  float = 0.0
    detected_language:   str | None = None
    processing_time_ms:  float = 0.0

    @property
    def full_text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def is_empty(self) -> bool:
        return len(self.words) == 0


class OCRProvider(ABC):
    """
    Abstract interface every OCR engine must implement.

    Implementations must:
      - Lazily load models (don't load in __init__).
      - Never raise — return an empty OCRPageResult on failure.
      - Return confidence as 0.0-1.0 regardless of the underlying
        engine's native scale.
    """

    @abstractmethod
    def recognize(self, image, page_number: int) -> OCRPageResult:
        """
        Run OCR on a rendered page image.

        Parameters
        ----------
        image       : numpy.ndarray (H, W, 3) or (H, W) — preprocessed
                      page bitmap.
        page_number : 1-based page number, for result labeling.

        Returns
        -------
        OCRPageResult — never raises.
        """

    @abstractmethod
    def warm_up(self) -> None:
        """Pre-load models. Optional to call explicitly."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Short identifier, e.g. 'easyocr', 'tesseract'."""