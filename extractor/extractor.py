"""
PDFExtractor
------------
Main text extraction class for the Urdu PDF converter.

Milestone 6 update:
  - Accepts an optional BaseOCREngine.
  - SCANNED pages are processed by OCR.
  - MIXED pages get direct extraction + OCR merged together.
  - OCR results are stored on PageResult for downstream use.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

from extractor.scanner import ScanDetector
from models.page_classification import PageClassification, PageType
from models.ocr_result import OCRResult

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
    page_number    : 1-based page number.
    classification : Full PageClassification from ScanDetector.
    raw_text       : Text from direct extraction (digital/mixed pages).
    ocr_result     : OCRResult if OCR was run on this page, else None.
    char_count     : Non-whitespace character count of the final text.
    error          : Error message if extraction failed.
    """
    page_number:    int
    classification: PageClassification
    raw_text:       Optional[str]       = None
    ocr_result:     Optional[OCRResult] = None
    char_count:     int                 = 0
    error:          Optional[str]       = None

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

    @property
    def final_text(self) -> str:
        """
        The best available text for this page.

        Priority:
          1. For SCANNED pages: OCR text only.
          2. For MIXED pages: direct text + OCR text merged.
          3. For DIGITAL pages: direct text only.
          4. Empty string if nothing was extracted.
        """
        if self.is_scanned:
            return self.ocr_result.full_text if self.ocr_result else ""

        if self.is_mixed:
            parts = []
            if self.raw_text and self.raw_text.strip():
                parts.append(self.raw_text.strip())
            if self.ocr_result and not self.ocr_result.is_empty:
                parts.append(self.ocr_result.full_text.strip())
            return "\n".join(parts)

        return self.raw_text or ""


@dataclass
class ExtractionResult:
    """
    Full extraction result for an entire PDF document.
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
    Extracts text from a PDF, with optional OCR for scanned pages.

    Parameters
    ----------
    scan_detector : ScanDetector, optional
    ocr_engine    : BaseOCREngine, optional
        If provided, SCANNED and MIXED pages are processed by OCR.
        If None, scanned pages will have no text (placeholder in DOCX).
    """

    def __init__(
        self,
        scan_detector=None,
        ocr_engine=None,
    ) -> None:
        self._detector  = scan_detector or ScanDetector()
        self._ocr       = ocr_engine  # None = OCR disabled

    def extract(self, pdf_path: str) -> ExtractionResult:
        """
        Run full extraction on a PDF file.

        Parameters
        ----------
        pdf_path : str

        Returns
        -------
        ExtractionResult
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
        """Classify, extract, and optionally OCR a single page."""
        page_num       = page.number + 1
        classification = self._detector.classify(page)
        raw_text       = None
        ocr_result     = None

        try:
            # ── Direct text extraction ────────────────────────────────
            if classification.needs_extraction:
                raw_text = page.get_text("text")

            # ── OCR ───────────────────────────────────────────────────
            if classification.needs_ocr and self._ocr is not None:
                logger.info("Running OCR on page %d (%s)...", page_num, classification.page_type.value)
                ocr_result = self._ocr.process_page(page, page_num)
            elif classification.needs_ocr and self._ocr is None:
                logger.debug(
                    "Page %d needs OCR but no engine configured — will use placeholder.",
                    page_num,
                )

            # ── Char count from final text ────────────────────────────
            result = PageResult(
                page_number    = page_num,
                classification = classification,
                raw_text       = raw_text,
                ocr_result     = ocr_result,
            )
            result.char_count = len(result.final_text.replace(" ", "").replace("\n", ""))
            return result

        except Exception as exc:
            logger.error("Failed to process page %d: %s", page_num, exc)
            return PageResult(
                page_number    = page_num,
                classification = classification,
                raw_text       = None,
                ocr_result     = None,
                char_count     = 0,
                error          = str(exc),
            )