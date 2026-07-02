from document_engine.stages.stage1_extraction import RawExtractor
from document_engine.stages.stage2_visual import VisualAnalyzer
from document_engine.stages.stage3_text import TextAnalyzer
from document_engine.stages.stage4_layout import LayoutAnalyzer

pdf_path = "uploads/test pdf.pdf"
doc_raw    = RawExtractor().extract(pdf_path)
doc_visual = VisualAnalyzer().analyze(doc_raw)
doc_text   = TextAnalyzer().analyze(doc_raw, doc_visual, pdf_path)
doc_layout = LayoutAnalyzer().extract_and_save(doc_text, doc_visual, "output/stage4_layout.json")

print(f"Detected header: {doc_layout.detected_header_pattern}")
print(f"Detected footer: {doc_layout.detected_footer_pattern}")

for page in doc_layout.pages:
    print(f"\nPage {page.page_number}:")
    for block in page.blocks[:8]:
        print(f"  [{block.role.value:<11}] {block.text[:50]}  ({block.reason})")