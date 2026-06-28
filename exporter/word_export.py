"""
WordExporter
------------
Converts a structured ExtractionResult into a Microsoft Word (.docx) file.

Responsibilities:
  - Set document-level RTL direction for Urdu text.
  - Write each page's text as properly formatted paragraphs.
  - Insert page breaks between PDF pages.
  - Insert placeholders for scanned pages (OCR fills these in Milestone 6).
  - Apply correct Urdu font and font size.

This module does NOT perform extraction, OCR, or Unicode repair.
It only takes already-extracted text and writes it to a DOCX.
"""

import logging
from pathlib import Path
from typing import Optional

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from extractor.extractor import ExtractionResult, PageResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — override via constructor if needed
# ---------------------------------------------------------------------------

DEFAULT_FONT = "Jameel Noori Nastaleeq"
FALLBACK_FONT = "Noto Nastaliq Urdu"
DEFAULT_FONT_SIZE = Pt(14)   # Nastaliq needs a bit more size to be readable
PLACEHOLDER_COLOR = RGBColor(0x99, 0x99, 0x99)  # grey for scanned placeholders


# ---------------------------------------------------------------------------
# Low-level OOXML helpers
# ---------------------------------------------------------------------------

def _make_bidi_element() -> OxmlElement:
    """Create a <w:bidi/> element that sets paragraph direction to RTL."""
    return OxmlElement("w:bidi")


def _make_rtl_element() -> OxmlElement:
    """Create a <w:rtl/> element that sets run direction to RTL."""
    return OxmlElement("w:rtl")


def _set_paragraph_rtl(paragraph) -> None:
    """
    Apply RTL direction to a paragraph.

    We must inject raw XML because python-docx does not expose
    paragraph bidi direction as a first-class property.
    """
    pPr = paragraph._p.get_or_add_pPr()
    # Remove any existing bidi element first (avoid duplicates on re-runs)
    for existing in pPr.findall(qn("w:bidi")):
        pPr.remove(existing)
    pPr.append(_make_bidi_element())
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


def _set_run_rtl(run) -> None:
    """Apply RTL direction to a run (inline text span)."""
    rPr = run._r.get_or_add_rPr()
    for existing in rPr.findall(qn("w:rtl")):
        rPr.remove(existing)
    rPr.append(_make_rtl_element())


def _set_document_rtl(doc: Document) -> None:
    """
    Set the document default paragraph style to RTL.

    This ensures that any paragraph that doesn't explicitly set a direction
    still renders correctly in Word's RTL mode.
    """
    # Access the document body's <w:body> → <w:sectPr> → <w:bidi>
    # We set it at the styles level instead, which is cleaner.
    try:
        normal_style = doc.styles["Normal"]
        pPr = normal_style.element.get_or_add_pPr()
        for existing in pPr.findall(qn("w:bidi")):
            pPr.remove(existing)
        pPr.append(_make_bidi_element())
    except Exception as exc:
        logger.warning("Could not set document-level RTL: %s", exc)


# ---------------------------------------------------------------------------
# Main exporter class
# ---------------------------------------------------------------------------

class WordExporter:
    """
    Converts an ExtractionResult to a .docx file.

    Parameters
    ----------
    font_name : str
        Urdu font to use. Must be installed on the system where Word opens
        the file. Defaults to Jameel Noori Nastaleeq.
    font_size : Pt
        Font size for body text. Default is 14pt (Nastaliq reads better large).
    """

    def __init__(
        self,
        font_name: str = DEFAULT_FONT,
        font_size: Pt = DEFAULT_FONT_SIZE,
    ) -> None:
        self.font_name = font_name
        self.font_size = font_size

    def export(self, extraction: ExtractionResult, output_path: str) -> str:
        """
        Write a .docx file from an ExtractionResult.

        Parameters
        ----------
        extraction : ExtractionResult
            The structured result from PDFExtractor.
        output_path : str
            Full path where the .docx file should be saved.

        Returns
        -------
        str
            The resolved output path (same as input, useful for chaining).

        Raises
        ------
        ValueError
            If the extraction result has no pages.
        IOError
            If the file cannot be written.
        """
        if not extraction.pages:
            raise ValueError("ExtractionResult has no pages — nothing to export.")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        doc = Document()
        _set_document_rtl(doc)

        logger.info(
            "Exporting %d pages to %s", extraction.total_pages, output_path
        )

        for index, page in enumerate(extraction.pages):
            self._write_page(doc, page)

            # Insert a Word page break after every page except the last
            if index < len(extraction.pages) - 1:
                self._add_page_break(doc)

        try:
            doc.save(str(out))
            logger.info("DOCX saved: %s", out)
        except Exception as exc:
            raise IOError(f"Could not save DOCX to {output_path}: {exc}") from exc

        return str(out)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _write_page(self, doc: Document, page: PageResult) -> None:
        """Write a single page's content into the document."""
        if page.error:
            self._write_error_placeholder(doc, page.page_number, page.error)
        elif page.is_scanned:
            self._write_scanned_placeholder(doc, page.page_number)
        elif page.is_mixed:
            # Write whatever text was extracted, then add an OCR-pending note
            if page.raw_text:
                self._write_text(doc, page)
            self._write_mixed_note(doc, page.page_number)
        else:
            self._write_text(doc, page)

    def _write_mixed_note(self, doc: Document, page_number: int) -> None:
        """Small grey note on mixed pages indicating partial OCR is pending."""
        para = doc.add_paragraph()
        run  = para.add_run(
            f"[ Page {page_number} — Contains images. OCR will be added in a future step. ]"
        )
        run.font.name   = "Arial"
        run.font.size   = Pt(9)
        run.font.color.rgb = PLACEHOLDER_COLOR
        run.font.italic = True

    def _write_text(self, doc: Document, page: PageResult) -> None:
        """
        Write the extracted text of a digital page.

        Splits on newlines to create separate paragraphs, which mirrors
        the visual line structure of the original PDF better than dumping
        all text into one paragraph.
        """
        text = page.raw_text or ""
        # Split into non-empty lines
        lines = [line for line in text.splitlines() if line.strip()]

        if not lines:
            # Page had text characters but they were all whitespace — skip
            return

        for line in lines:
            para = doc.add_paragraph()
            _set_paragraph_rtl(para)

            run = para.add_run(line.strip())
            run.font.name = self.font_name
            run.font.size = self.font_size
            _set_run_rtl(run)

    def _write_scanned_placeholder(self, doc: Document, page_number: int) -> None:
        """
        Insert a visible grey placeholder for a scanned page.

        In Milestone 6, the OCR engine will replace this with real text.
        """
        para = doc.add_paragraph()
        run = para.add_run(
            f"[ صفحہ {page_number} — اسکین شدہ، OCR درکار ہے ]"
            f"\n[ Page {page_number} — Scanned. OCR pending. ]"
        )
        run.font.name = self.font_name
        run.font.size = Pt(11)
        run.font.color.rgb = PLACEHOLDER_COLOR
        run.font.italic = True

    def _write_error_placeholder(
        self, doc: Document, page_number: int, error: str
    ) -> None:
        """Insert a visible placeholder when a page failed to extract."""
        para = doc.add_paragraph()
        run = para.add_run(
            f"[ Page {page_number} — Extraction error: {error} ]"
        )
        run.font.name = "Arial"
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0x00, 0x00)  # red
        run.font.italic = True

    def _add_page_break(self, doc: Document) -> None:
        """Insert a hard page break paragraph."""
        para = doc.add_paragraph()
        run = para.add_run()
        run.add_break(
            # WD_BREAK.PAGE = 0  — use the integer to avoid import clutter
            __import__("docx.enum.text", fromlist=["WD_BREAK"]).WD_BREAK.PAGE
        )