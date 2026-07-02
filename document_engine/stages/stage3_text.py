"""
Stage 3 — Text Analysis
-------------------------
Merges Stage 1 spans into lines and blocks, repairs Unicode, detects
RTL and language, and runs OCR for pages lacking sufficient embedded
text. Consumes DocumentRaw + DocumentVisual; the only PDF file access
in this stage is rendering page bitmaps for OCR, which is unavoidable.
"""

import logging
import statistics
from pathlib import Path
from typing import Optional

import fitz
import numpy as np

from bidi.algorithm import get_display

from document_engine.dom.base import BBox
from document_engine.dom.raw import DocumentRaw, PageRaw, TextSpanRaw
from document_engine.dom.text import (
    DocumentText, PageTextAnalysis, TextBlock, TextLine, TextSource,
)
from document_engine.dom.visual import DocumentVisual, PageVisual
from document_engine.ocr.base import OCRProvider
from document_engine.ocr.easyocr_provider import EasyOCRProvider
from document_engine.text_processing.unicode_repair import (
    UnicodeRepairEngine, is_rtl_text,
)

logger = logging.getLogger(__name__)

_LINE_Y_TOLERANCE   = 3.0
_BLOCK_GAP_MULTIPLE = 2.0
_MIN_CHARS_DIGITAL  = 20
_SCANNED_IMAGE_RATIO = 0.65
_MIXED_IMAGE_RATIO   = 0.30
_RENDER_DPI          = 300


class TextAnalyzer:
    """
    Performs Stage 3 analysis: (DocumentRaw, DocumentVisual, pdf_path)
    -> DocumentText.

    Parameters
    ----------
    ocr_provider    : OCRProvider implementation. Defaults to EasyOCRProvider.
    unicode_repair  : UnicodeRepairEngine instance.
    """

    def __init__(
        self,
        ocr_provider:   Optional[OCRProvider] = None,
        unicode_repair: Optional[UnicodeRepairEngine] = None,
    ) -> None:
        self._ocr     = ocr_provider or EasyOCRProvider()
        self._repair  = unicode_repair or UnicodeRepairEngine()

    def warm_up(self) -> None:
        self._ocr.warm_up()

    def analyze(
        self,
        doc_raw:    DocumentRaw,
        doc_visual: DocumentVisual,
        pdf_path:   str,
    ) -> DocumentText:
        """
        Run Stage 3 analysis.

        Parameters
        ----------
        doc_raw    : Stage 1 output.
        doc_visual : Stage 2 output.
        pdf_path   : Source PDF — needed only to rasterize pages for OCR.
        """
        fitz_doc = fitz.open(pdf_path)
        pages: list[PageTextAnalysis] = []

        visual_by_page = {p.page_number: p for p in doc_visual.pages}

        for page_raw in doc_raw.pages:
            page_visual = visual_by_page.get(page_raw.page_number)
            try:
                pages.append(self._analyze_page(page_raw, page_visual, fitz_doc))
            except Exception as exc:
                logger.error(
                    "Stage 3 analysis failed on page %d: %s — inserting empty page.",
                    page_raw.page_number, exc,
                )
                pages.append(PageTextAnalysis(page_number=page_raw.page_number))

        fitz_doc.close()

        logger.info(
            "Stage 3 complete: %d pages, %d scanned, %d mixed.",
            len(pages),
            sum(p.is_scanned for p in pages),
            sum(p.is_mixed for p in pages),
        )

        return DocumentText(source_path=doc_raw.source_path, pages=pages)

    def extract_and_save(
        self,
        doc_raw:    DocumentRaw,
        doc_visual: DocumentVisual,
        pdf_path:   str,
        debug_output_path: str,
    ) -> DocumentText:
        result = self.analyze(doc_raw, doc_visual, pdf_path)
        Path(debug_output_path).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Stage 3 debug output saved: %s", debug_output_path)
        return result

    # ------------------------------------------------------------------
    # Per-page
    # ------------------------------------------------------------------

    def _analyze_page(
        self,
        page_raw:    PageRaw,
        page_visual: Optional[PageVisual],
        fitz_doc:    fitz.Document,
    ) -> PageTextAnalysis:

        char_count   = sum(len(s.text.replace(" ", "")) for s in page_raw.text_spans)
        image_ratio  = self._compute_image_ratio(page_raw, page_visual)

        is_scanned = image_ratio >= _SCANNED_IMAGE_RATIO and char_count < _MIN_CHARS_DIGITAL
        is_mixed   = (not is_scanned) and image_ratio >= _MIXED_IMAGE_RATIO and char_count >= _MIN_CHARS_DIGITAL
        needs_ocr  = is_scanned or (char_count < _MIN_CHARS_DIGITAL)

        blocks: list[TextBlock] = []

        if char_count >= _MIN_CHARS_DIGITAL:
            blocks.extend(self._merge_embedded_text(page_raw))

        if needs_ocr:
            ocr_blocks = self._run_ocr(page_raw, fitz_doc)
            blocks.extend(ocr_blocks)

        for block in blocks:
            for line in block.lines:
                line.text = self._repair.repair(line.text)

        return PageTextAnalysis(
            page_number=page_raw.page_number,
            is_scanned=is_scanned,
            is_mixed=is_mixed,
            blocks=blocks,
        )

    def _compute_image_ratio(
        self, page_raw: PageRaw, page_visual: Optional[PageVisual]
    ) -> float:
        page_area = max(page_raw.width * page_raw.height, 1)
        if page_visual and page_visual.images:
            total = sum(img.bbox.area for img in page_visual.images if img.bbox)
            return min(total / page_area, 1.0)
        total = sum(img.bbox.area for img in page_raw.images if img.bbox)
        return min(total / page_area, 1.0)

    # ------------------------------------------------------------------
    # Embedded text merging: spans -> lines -> blocks
    # ------------------------------------------------------------------

    def _merge_embedded_text(self, page_raw: PageRaw) -> list[TextBlock]:
        spans = [s for s in page_raw.text_spans if s.bbox and s.text.strip()]
        if not spans:
            return []

        lines = self._group_spans_into_lines(spans)
        text_lines = [self._build_text_line(line) for line in lines]
        return self._group_lines_into_blocks(text_lines, page_raw.page_number)

    def _group_spans_into_lines(self, spans: list[TextSpanRaw]) -> list[list[TextSpanRaw]]:
        sorted_spans = sorted(spans, key=lambda s: s.bbox.y0)
        lines: list[list[TextSpanRaw]] = []
        current = [sorted_spans[0]]

        for span in sorted_spans[1:]:
            if abs(span.bbox.y0 - current[0].bbox.y0) <= _LINE_Y_TOLERANCE:
                current.append(span)
            else:
                lines.append(current)
                current = [span]
        lines.append(current)

        for line in lines:
            line.sort(key=lambda s: s.bbox.x0, reverse=True)  # RTL default

        return lines

    def _build_text_line(self, spans: list[TextSpanRaw]) -> TextLine:
        raw_text = " ".join(s.text for s in spans).strip()
        rtl = is_rtl_text(raw_text)

        # Text from PyMuPDF spans (sort=True style extraction) is already
        # in logical order; apply BiDi only as a safety net if the joined
        # text looks reversed relative to expected script direction.
        text = raw_text

        sizes = [s.font.size for s in spans if s.font.size]
        x0 = min(s.bbox.x0 for s in spans)
        y0 = min(s.bbox.y0 for s in spans)
        x1 = max(s.bbox.x1 for s in spans)
        y1 = max(s.bbox.y1 for s in spans)

        return TextLine(
            page_number=spans[0].page_number,
            bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            text=text,
            source=TextSource.EMBEDDED,
            is_rtl=rtl,
            language="ur" if rtl else "en",
            font_size=statistics.median(sizes) if sizes else None,
            is_bold=any(s.font.is_bold for s in spans),
            is_italic=any(s.font.is_italic for s in spans),
            source_span_ids=[s.id for s in spans],
        )

    def _group_lines_into_blocks(
        self, lines: list[TextLine], page_number: int
    ) -> list[TextBlock]:
        if not lines:
            return []

        sorted_lines = sorted(lines, key=lambda l: l.bbox.y0)
        heights = [l.bbox.height for l in sorted_lines if l.bbox]
        median_h = statistics.median(heights) if heights else 12.0
        gap_threshold = median_h * _BLOCK_GAP_MULTIPLE

        blocks: list[TextBlock] = []
        current: list[TextLine] = [sorted_lines[0]]

        for prev, line in zip(sorted_lines, sorted_lines[1:]):
            gap = line.bbox.y0 - prev.bbox.y1
            if gap > gap_threshold:
                blocks.append(self._finalize_block(current, page_number))
                current = [line]
            else:
                current.append(line)
        blocks.append(self._finalize_block(current, page_number))

        return blocks

    def _finalize_block(self, lines: list[TextLine], page_number: int) -> TextBlock:
        x0 = min(l.bbox.x0 for l in lines if l.bbox)
        y0 = min(l.bbox.y0 for l in lines if l.bbox)
        x1 = max(l.bbox.x1 for l in lines if l.bbox)
        y1 = max(l.bbox.y1 for l in lines if l.bbox)
        langs = [l.language for l in lines if l.language]
        dominant = max(set(langs), key=langs.count) if langs else None

        return TextBlock(
            page_number=page_number,
            bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
            lines=lines,
            dominant_language=dominant,
        )

    # ------------------------------------------------------------------
    # OCR path
    # ------------------------------------------------------------------

    def _run_ocr(self, page_raw: PageRaw, fitz_doc: fitz.Document) -> list[TextBlock]:
        fitz_page = fitz_doc[page_raw.page_number - 1]
        image = self._render_page(fitz_page)

        ocr_result = self._ocr.recognize(image, page_raw.page_number)
        if ocr_result.is_empty:
            return []

        lines: list[TextLine] = []
        for word in ocr_result.words:
            # OCR words are visually ordered — BiDi-correct on join later
            text = word.text
            lines.append(TextLine(
                page_number=page_raw.page_number,
                bbox=word.bbox,
                text=text,
                source=TextSource.OCR,
                is_rtl=is_rtl_text(text),
                language="ur",
                ocr_confidence=word.confidence,
            ))

        # Merge OCR words into lines by y-proximity, then apply BiDi
        # to fix visual-order character sequences within each line.
        merged_lines = self._merge_ocr_words_into_lines(lines, page_raw.page_number)
        return self._group_lines_into_blocks(merged_lines, page_raw.page_number)

    def _merge_ocr_words_into_lines(
        self, word_lines: list[TextLine], page_number: int
    ) -> list[TextLine]:
        if not word_lines:
            return []

        sorted_words = sorted(word_lines, key=lambda l: l.bbox.y0)
        groups: list[list[TextLine]] = []
        current = [sorted_words[0]]

        for w in sorted_words[1:]:
            if abs(w.bbox.y0 - current[0].bbox.y0) <= _LINE_Y_TOLERANCE * 2:
                current.append(w)
            else:
                groups.append(current)
                current = [w]
        groups.append(current)

        merged: list[TextLine] = []
        for group in groups:
            group.sort(key=lambda l: l.bbox.x0, reverse=True)
            raw_text = " ".join(l.text for l in group)
            try:
                text = get_display(raw_text)
            except Exception:
                text = raw_text

            x0 = min(l.bbox.x0 for l in group)
            y0 = min(l.bbox.y0 for l in group)
            x1 = max(l.bbox.x1 for l in group)
            y1 = max(l.bbox.y1 for l in group)
            confidences = [l.ocr_confidence for l in group if l.ocr_confidence]

            merged.append(TextLine(
                page_number=page_number,
                bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                text=text,
                source=TextSource.OCR,
                is_rtl=is_rtl_text(text),
                language="ur",
                ocr_confidence=statistics.mean(confidences) if confidences else None,
            ))

        return merged

    def _render_page(self, page: fitz.Page) -> np.ndarray:
        scale = _RENDER_DPI / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        return img