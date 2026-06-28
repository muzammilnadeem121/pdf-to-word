"""
PDFExtractor
------------
Main text extraction class for the Urdu PDF converter.

Milestone 5 update:
  - PageResult now carries a full PageClassification (type, confidence, reason)
    instead of just a boolean is_scanned flag.
  - MIXED pages get text extracted AND are flagged for OCR.
  - The ExtractionResult summary now includes mixed_pages count.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

from extractor.scanner import ScanDetector
from models.page_classification import PageClassification, PageType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PageResult:
    """
    Extraction result for a single PDF page.

    Attributes
    ----------
    page_number     : 1-based page number.
    classification  : Full PageClassification from ScanDetector.
    raw_text        : Extracted text (None if scanned, partial if mixed).
    char_count      : Non-whitespace character count.
    error           : Error message if extraction failed.
    """
    page_number:    int
    classification: PageClassification
    raw_text:       Optional[str] = None
    char_count:     int = 0
    error:          Optional[str] = None

    # Convenience pass-throughs so callers don't need to touch classification
    @property
    def is_scanned(self) -> bool:
        return self.classification.is_scanned

    @property
    def is_digital(self) -> bool:
        return self.classification.is_digital

    @property
    def is_mixed(self) -> bool:
        return self.classification.is_mixed

    @property
    def needs_ocr(self) -> bool:
        return self.classification.needs_ocr

    @property
    def confidence(self) -> float:
        return self.classification.confidence


@dataclass
class ExtractionResult:
    """
    Full extraction result for an entire PDF document.

    Attributes
    ----------
    file_path     : Path to the source PDF.
    total_pages   : Total page count.
    digital_pages : Pages extracted directly.
    scanned_pages : Pages that need OCR.
    mixed_pages   : Pages needing both extraction and OCR.
    pages         : Per-page results in order.
    """
    file_path:     str
    total_pages:   int
    digital_pages: int
    scanned_pages: int
    mixed_pages:   int
    pages:         list[PageResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Extracts text from a PDF, classifying each page via ScanDetector.

    Parameters
    ----------
    scan_detector : ScanDetector, optional
        Injectable detector. Defaults to ScanDetector() with standard settings.
    """

    def __init__(self, scan_detector: Optional[ScanDetector] = None) -> None:
        self._detector = scan_detector or ScanDetector()

    def extract(self, pdf_path: str) -> ExtractionResult:
        """
        Run extraction on an entire PDF file.

        Parameters
        ----------
        pdf_path : str

        Returns
        -------
        ExtractionResult

        Raises
        ------
        FileNotFoundError, ValueError
        """
        path = Path(pdf_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

        logger.info("Opening PDF: %s", pdf_path)

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise ValueError(f"Could not open PDF: {exc}") from exc

        pages:   list[PageResult] = []
        digital  = scanned = mixed = 0

        for page_obj in doc:
            result = self._extract_page(page_obj)
            pages.append(result)

            if result.is_digital:
                digital += 1
            elif result.is_scanned:
                scanned += 1
            elif result.is_mixed:
                mixed += 1

        doc.close()

        extraction = ExtractionResult(
            file_path     = str(path),
            total_pages   = len(pages),
            digital_pages = digital,
            scanned_pages = scanned,
            mixed_pages   = mixed,
            pages         = pages,
        )

        logger.info(
            "Extraction complete: %d pages — %d digital, %d scanned, %d mixed.",
            extraction.total_pages,
            extraction.digital_pages,
            extraction.scanned_pages,
            extraction.mixed_pages,
        )

        return extraction

    def _extract_page(self, page: fitz.Page) -> PageResult:
        """Classify and extract a single page."""
        page_num       = page.number + 1
        classification = self._detector.classify(page)

        try:
            if classification.needs_extraction:
                # DIGITAL or MIXED — pull the text layer
                raw_text  = page.get_text("text")
                char_count = len(
                    raw_text.strip().replace(" ", "").replace("\n", "")
                )
            else:
                # SCANNED — no usable text layer
                raw_text   = None
                char_count = 0

            return PageResult(
                page_number    = page_num,
                classification = classification,
                raw_text       = raw_text,
                char_count     = char_count,
            )

        except Exception as exc:
            logger.error("Failed to process page %d: %s", page_num, exc)
            return PageResult(
                page_number    = page_num,
                classification = classification,
                raw_text       = None,
                char_count     = 0,
                error          = str(exc),
            )