from document_engine.stages.stage1_extraction import RawExtractor
from document_engine.stages.stage2_visual import VisualAnalyzer

doc_raw = RawExtractor().extract("uploads/test pdf.pdf")
doc_visual = VisualAnalyzer().extract_and_save(doc_raw, "output/stage2_visual.json")

for page in doc_visual.pages:
    print(f"Page {page.page_number}: "
          f"{len(page.columns)} columns, "
          f"{len(page.separators)} separators, "
          f"{len(page.tables)} table candidates, "
          f"{len(page.images)} images "
          f"({sum(i.is_likely_logo for i in page.images)} logos, "
          f"{sum(i.is_likely_photo for i in page.images)} photos)")