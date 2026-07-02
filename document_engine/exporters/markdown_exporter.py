from pathlib import Path
from document_engine.dom.document import Document

class MarkdownExporter:
    def export(self, document: Document, output_path: str) -> str:
        lines = []
        for page in document.pages:
            for el in sorted(page.elements, key=lambda e: e.sequence):
                if el.element_type == "heading":
                    lines.append("#" * (el.heading_level or 2) + " " + el.text)
                elif el.element_type == "paragraph":
                    lines.append(el.text)
                elif el.element_type == "list":
                    lines.extend(f"- {item}" for item in el.list_items)
                elif el.text:
                    lines.append(f"> {el.text}")
                lines.append("")
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        return output_path