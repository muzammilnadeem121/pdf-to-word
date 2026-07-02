"""
Usage:
    python diagnose.py path/to/urdu.pdf
"""

import sys
import fitz
from extractor.scanner import ScanDetector

if len(sys.argv) < 2:
    print("Usage: python diagnose.py <path_to_pdf>")
    sys.exit(1)

pdf_path = sys.argv[1]
doc      = fitz.open(pdf_path)
detector = ScanDetector()

print(f"\n{'─'*60}")
print(f"  PDF: {pdf_path}")
print(f"  Pages: {doc.page_count}")
print(f"{'─'*60}")
print(f"  {'Page':<6} {'Type':<10} {'Conf':<6} {'Chars':<7} {'Image%':<8} {'Urdu%':<7} Reason")
print(f"{'─'*60}")

for page in doc:
    c = detector.classify(page)
    print(
        f"  {c.page_number:<6} "
        f"{c.page_type.value:<10} "
        f"{c.confidence:<6.2f} "
        f"{c.char_count:<7} "
        f"{c.image_coverage*100:<8.1f} "
        f"{c.urdu_char_ratio*100:<7.1f} "
        f"{c.reason[:55]}"
    )

doc.close()
print(f"{'─'*60}\n")