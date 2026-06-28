"""
ConversionService
-----------------
Orchestrates the full PDF → DOCX pipeline.

Current pipeline (Milestone 4):
    1. Validate the input file exists.
    2. Extract text (PDFExtractor).
    3. Export to DOCX (WordExporter).
    4. Return the output path.

Future milestones will insert steps between 2 and 3:
    - Unicode repair (Milestone 7)
    - OCR for scanned pages (Milestone 6)
    - Layout detection (Milestone 8)

The API layer never calls extractors or exporters directly —
it always goes through this service. That keeps the API thin
and makes the pipeline easy to evolve.
"""

import logging
import uuid
from pathlib import Path

from extractor.extractor import PDFExtractor, ExtractionResult
from exporter.word_export import WordExporter

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("output")


class ConversionService:
    """
    Converts a PDF file to a DOCX file.

    Parameters
    ----------
    extractor : PDFExtractor, optional
        Injected extractor. Defaults to PDFExtractor().
    exporter : WordExporter, optional
        Injected exporter. Defaults to WordExporter().
    output_dir : Path, optional
        Directory where output .docx files are saved.
    """

    def __init__(
        self,
        ocr_engine:  BaseOCREngine | None = None,
        extractor: PDFExtractor | None = None,
        exporter: WordExporter | None = None,
        output_dir: Path = OUTPUT_DIR,
    ) -> None:
        self._ocr_engine = ocr_engine if ocr_engine is not None else EasyOCREngine()
        self._extractor = extractor or PDFExtractor()
        self._exporter = exporter or WordExporter()
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def convert(self, pdf_path: str) -> dict:
        """
        Run the full conversion pipeline on a PDF file.

        Parameters
        ----------
        pdf_path : str
            Path to the source PDF.

        Returns
        -------
        dict with keys:
            - docx_path (str): absolute path to the generated .docx file
            - filename  (str): just the filename (for building download URLs)
            - total_pages (int)
            - digital_pages (int)
            - scanned_pages (int)

        Raises
        ------
        FileNotFoundError, ValueError, IOError — propagated from sub-modules.
        """
        logger.info("Starting conversion: %s", pdf_path)

        # Step 1 — Extract
        extraction: ExtractionResult = self._extractor.extract(pdf_path)

        # Step 2 — (Future: Unicode repair, OCR, layout — inserted here)

        # Step 3 — Export
        output_filename = f"{uuid.uuid4()}.docx"
        output_path = self._output_dir / output_filename
        self._exporter.export(extraction, str(output_path))

        logger.info("Conversion complete → %s", output_path)

        return {
            "docx_path": str(output_path),
            "filename": output_filename,
            "total_pages": extraction.total_pages,
            "digital_pages": extraction.digital_pages,
            "scanned_pages": extraction.scanned_pages,
        }