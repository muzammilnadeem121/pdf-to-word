"""
BaseOCREngine
-------------
Abstract interface for all OCR engines.

Any OCR implementation used by PDFExtractor must inherit from this class
and implement process_page(). This keeps the extractor decoupled from
the specific OCR library — swapping engines requires zero changes outside
the ocr/ package.
"""

import logging
from abc import ABC, abstractmethod

import fitz

from models.ocr_result import OCRResult

logger = logging.getLogger(__name__)


class BaseOCREngine(ABC):
    """
    Abstract OCR engine interface.

    Implementations must be:
      - Lazily initialized (don't load models in __init__)
      - Thread-safe for single-threaded sequential use
      - Capable of handling empty/blank images gracefully
    """

    @abstractmethod
    def process_page(self, page: fitz.Page, page_number: int) -> OCRResult:
        """
        Run OCR on a single PDF page.

        Parameters
        ----------
        page        : fitz.Page object from an open PDF.
        page_number : 1-based page number (used to populate OCRResult).

        Returns
        -------
        OCRResult
            Recognized text and metadata. Returns an empty OCRResult
            (not None, not an exception) if the page yields no text.
        """

    @abstractmethod
    def warm_up(self) -> None:
        """
        Pre-load models so the first real call isn't slow.

        Optional to call — engines must lazy-load anyway.
        Useful to call explicitly at server startup.
        """