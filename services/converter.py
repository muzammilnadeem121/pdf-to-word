"""
ConversionService
-----------------
Orchestrates the full PDF → DOCX pipeline.

Pipeline as of Milestone 6:
  1. Extract text (PDFExtractor).
  2. OCR scanned/mixed pages (PaddleOCREngine, injected into extractor).
  3. Export to DOCX (WordExporter).

Future milestones insert between steps 2 and 3:
  - Unicode repair (Milestone 7)
  - Layout detection (Milestone 8)
"""

import logging
import uuid
from pathlib import Path

from extractor.extractor import PDFExtractor, ExtractionResult
from exporter.word_export import WordExporter
from ocr.easyocr_engine import EasyOCREngine
from ocr.base_engine import BaseOCREngine

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


class ConversionService:
    """
    Converts a PDF file to a DOCX file.

    Parameters
    ----------
    ocr_engine  : BaseOCREngine, optional
        Defaults to PaddleOCREngine(). Pass None to disable OCR
        (scanned pages will show placeholders).
    extractor   : PDFExtractor, optional
    exporter    : WordExporter, optional
    output_dir  : Path, optional
    """

    def __init__(
        self,
        ocr_engine:  BaseOCREngine | None = None,
        extractor:   PDFExtractor  | None = None,
        exporter:    WordExporter  | None = None,
        output_dir:  Path                 = OUTPUT_DIR,
    ) -> None:
        self._ocr_engine = ocr_engine if ocr_engine is not None else EasyOCREngine()
        self._extractor  = extractor  or PDFExtractor(ocr_engine=self._ocr_engine)
        self._exporter   = exporter   or WordExporter()
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def warm_up(self) -> None:
        """Pre-load OCR models at startup. Call from FastAPI lifespan."""
        self._ocr_engine.warm_up()

    def convert(self, pdf_path: str) -> dict:
        """
        Run the full conversion pipeline.

        Returns
        -------
        dict with keys: docx_path, filename, total_pages,
                        digital_pages, scanned_pages, mixed_pages.
        """
        logger.info("Starting conversion: %s", pdf_path)

        extraction: ExtractionResult = self._extractor.extract(pdf_path)

        # Future: Unicode repair and layout detection inserted here.

        output_filename = f"{uuid.uuid4()}.docx"
        output_path     = self._output_dir / output_filename
        self._exporter.export(extraction, str(output_path))

        logger.info("Conversion complete → %s", output_path)

        return {
            "docx_path":    str(output_path),
            "filename":     output_filename,
            "total_pages":  extraction.total_pages,
            "digital_pages": extraction.digital_pages,
            "scanned_pages": extraction.scanned_pages,
            "mixed_pages":  extraction.mixed_pages,
        }