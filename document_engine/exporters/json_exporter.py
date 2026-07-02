from pathlib import Path
from document_engine.dom.document import Document

class JsonExporter:
    def export(self, document: Document, output_path: str) -> str:
        Path(output_path).write_text(document.model_dump_json(indent=2), encoding="utf-8")
        return output_path