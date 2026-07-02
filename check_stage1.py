from document_engine.stages.stage1_extraction import RawExtractor

extractor = RawExtractor()
result    = extractor.extract_and_save(
    "uploads/test pdf.pdf",
    "output/stage1_raw.json"
)

print(f"Pages: {len(result.pages)}")
for page in result.pages:
    print(f"  Page {page.page_number}: "
          f"{len(page.text_spans)} spans, "
          f"{len(page.drawings)} drawings, "
          f"{len(page.images)} images")