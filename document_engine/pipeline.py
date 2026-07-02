"""
Full Document Intelligence Engine pipeline: PDF -> Document -> exporters.
This is what services/converter.py (FastAPI) now calls.
"""

import logging
import uuid
from pathlib import Path

from document_engine.stages.stage1_extraction import RawExtractor
from document_engine.stages.stage2_visual import VisualAnalyzer
from document_engine.stages.stage3_text import TextAnalyzer
from document_engine.stages.stage4_layout import LayoutAnalyzer
from document_engine.stages.stage5_reading_order import ReadingOrderEngine
from document_engine.stages.stage6_semantic import SemanticAnalyzer
from document_engine.stages.stage7_document_model import DocumentModelBuilder
from document_engine.exporters.docx_exporter import DocxExporter
from document_engine.ocr.easyocr_provider import EasyOCRProvider

logger = logging.getLogger(__name__)


class DocumentIntelligencePipeline:
    def __init__(self, output_dir: Path = Path("output")) -> None:
        self._ocr = EasyOCRProvider()
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def warm_up(self) -> None:
        self._ocr.warm_up()

    def convert_to_docx(self, pdf_path: str) -> dict:
        doc_raw      = RawExtractor().extract(pdf_path)
        doc_visual   = VisualAnalyzer().analyze(doc_raw)
        doc_text     = TextAnalyzer(ocr_provider=self._ocr).analyze(doc_raw, doc_visual, pdf_path)
        doc_layout   = LayoutAnalyzer().analyze(doc_text, doc_visual)
        doc_order    = ReadingOrderEngine().analyze(doc_layout, doc_visual)
        doc_semantic = SemanticAnalyzer().analyze(doc_order)
        document     = DocumentModelBuilder().build(doc_raw, doc_semantic)

        output_filename = f"{uuid.uuid4()}.docx"
        output_path = self._output_dir / output_filename
        DocxExporter().export(document, str(output_path))

        try:
            import os
            os.remove(pdf_path)
        except Exception:
            pass

        return {
            "docx_path": str(output_path),
            "filename": output_filename,
            "total_pages": len(document.pages),
            "total_elements": sum(len(p.elements) for p in document.pages),
        }