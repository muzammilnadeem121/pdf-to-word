import sys
sys.path.insert(0, '.')

import fitz
from extractor.scanner import ScanDetector

pdf_path = "uploads/d4825c41a6bb4b3cbeb8fd3506bd6136.pdf"  # ← change to actual filename in uploads/
doc      = fitz.open(pdf_path)
detector = ScanDetector()

for page in doc:
    c = detector.classify(page)
    print(
        f"Page {c.page_number}: {c.page_type.value.upper():<8} | "
        f"chars={c.char_count:<6} | "
        f"img={c.image_coverage*100:.0f}% | "
        f"urdu={c.urdu_char_ratio*100:.0f}% | "
        f"{c.reason}"
    )

doc.close()