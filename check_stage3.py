from document_engine.stages.stage1_extraction import RawExtractor
from document_engine.stages.stage2_visual import VisualAnalyzer
from document_engine.stages.stage3_text import TextAnalyzer

pdf_path = "uploads/test pdf.pdf"
doc_raw    = RawExtractor().extract(pdf_path)
doc_visual = VisualAnalyzer().analyze(doc_raw)
doc_text   = TextAnalyzer().extract_and_save(doc_raw, doc_visual, pdf_path, "output/stage3_text.json")

for page in doc_text.pages:
    print(f"Page {page.page_number}: scanned={page.is_scanned} mixed={page.is_mixed} "
          f"blocks={len(page.blocks)} chars={sum(b.char_count for b in page.blocks)}")
    if page.blocks:
        print("  preview:", page.blocks[0].full_text[:60])