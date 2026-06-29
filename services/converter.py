"""
ConversionService
-----------------
Full pipeline as of Milestone 8:
  1. Extract (PDFExtractor — direct text + OCR)
  2. Unicode repair (UnicodeRepairEngine)
  3. Layout detection (LayoutDetector)
  4. Export (WordExporter.export_layout)
"""

import logging
import uuid
from pathlib import Path

from extractor.extractor import PDFExtractor, ExtractionResult
from extractor.unicode_fixer import UnicodeRepairEngine
from exporter.word_export import WordExporter
from layout.detector import LayoutDetector
from ocr.easyocr_engine import EasyOCREngine
from ocr.base_engine import BaseOCREngine

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


class ConversionService:

    def __init__(
        self,
        ocr_engine:     BaseOCREngine       | None = None,
        extractor:      PDFExtractor        | None = None,
        exporter:       WordExporter        | None = None,
        unicode_repair: UnicodeRepairEngine | None = None,
        layout:         LayoutDetector      | None = None,
        output_dir:     Path                       = OUTPUT_DIR,
    ) -> None:
        self._ocr_engine     = ocr_engine if ocr_engine is not None else EasyOCREngine()
        self._extractor      = extractor  or PDFExtractor(ocr_engine=self._ocr_engine)
        self._exporter       = exporter   or WordExporter()
        self._unicode_repair = unicode_repair or UnicodeRepairEngine()
        self._layout         = layout or LayoutDetector()
        self._output_dir     = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def warm_up(self) -> None:
        self._ocr_engine.warm_up()

    def convert(self, pdf_path: str) -> dict:
        """Run the full pipeline and return result metadata."""
        logger.info("Starting conversion: %s", pdf_path)

        # Step 1 — Extract
        extraction = self._extractor.extract(pdf_path)

        # Step 2 — Unicode repair
        self._unicode_repair.repair_pages(extraction.pages)

        # Step 3 — Layout detection
        layout_blocks = self._layout.detect(pdf_path, extraction)

        # Step 4 — Export
        output_filename = f"{uuid.uuid4()}.docx"
        output_path     = self._output_dir / output_filename

        if layout_blocks:
            self._exporter.export_layout(layout_blocks, str(output_path))
        else:
            # Fallback: no layout detected, export plain text
            logger.warning("No layout blocks detected — falling back to plain export.")
            self._exporter.export(extraction, str(output_path))

        logger.info("Conversion complete → %s", output_path)

        return {
            "docx_path":     str(output_path),
            "filename":      output_filename,
            "total_pages":   extraction.total_pages,
            "digital_pages": extraction.digital_pages,
            "scanned_pages": extraction.scanned_pages,
            "mixed_pages":   extraction.mixed_pages,
            "layout_blocks": len(layout_blocks),
        }