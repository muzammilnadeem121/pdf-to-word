"""
Stage 1 — Low-Level Extraction
-------------------------------
Extracts every raw fact from a PDF using PyMuPDF, with zero
interpretation. This is the foundation every later stage builds on.

Design notes
------------
- Uses PyMuPDF exclusively (pdfplumber/pdfminer lag Python 3.14
  wheel support; PyMuPDF covers everything Stage 1 needs).
- One public method: extract(pdf_path) -> DocumentRaw.
- Never raises on a single bad page — logs and continues, so one
  corrupted page doesn't kill extraction of the other 40.
- Every extracted fact keeps its own bbox, so Stage 2+ never needs
  to re-derive position information.
"""

import logging
from pathlib import Path

import fitz

from document_engine.dom.base import BBox
from document_engine.dom.raw import (
    DocumentMetadataRaw,
    DocumentRaw,
    DrawingRaw,
    FontInfo,
    ImageRaw,
    PageRaw,
    TextSpanRaw,
)

logger = logging.getLogger(__name__)

# PyMuPDF span flag bits
_FLAG_ITALIC = 1 << 1
_FLAG_BOLD   = 1 << 4

# Below this size (points²), a drawing is a hairline artifact, not
# a meaningful visual element. Still recorded — Stage 2 decides relevance.
_MIN_DRAWING_DIM = 0.5


class RawExtractor:
    """
    Performs Stage 1 extraction: PDF file -> DocumentRaw.

    No configuration needed — this stage makes no judgment calls,
    so there's nothing to tune. Filtering and thresholds belong to
    Stage 2 onward.
    """

    def extract(self, pdf_path: str) -> DocumentRaw:
        """
        Extract every raw fact from a PDF file.

        Parameters
        ----------
        pdf_path : str

        Returns
        -------
        DocumentRaw

        Raises
        ------
        FileNotFoundError, ValueError
        """
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            raise ValueError(f"Could not open PDF: {exc}") from exc

        metadata = self._extract_metadata(doc)
        pages: list[PageRaw] = []

        for page in doc:
            try:
                pages.append(self._extract_page(page))
            except Exception as exc:
                logger.error(
                    "Stage 1 extraction failed on page %d: %s — inserting empty page.",
                    page.number + 1, exc,
                )
                pages.append(PageRaw(
                    page_number=page.number + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                ))

        doc.close()

        logger.info(
            "Stage 1 complete: %d pages, %d total spans, %d total drawings, %d total images.",
            len(pages),
            sum(len(p.text_spans) for p in pages),
            sum(len(p.drawings)   for p in pages),
            sum(len(p.images)     for p in pages),
        )

        return DocumentRaw(
            source_path=str(path),
            metadata=metadata,
            pages=pages,
        )

    # ------------------------------------------------------------------
    # Private extraction methods
    # ------------------------------------------------------------------

    def _extract_metadata(self, doc: fitz.Document) -> DocumentMetadataRaw:
        meta = doc.metadata or {}
        return DocumentMetadataRaw(
            title=meta.get("title") or None,
            author=meta.get("author") or None,
            subject=meta.get("subject") or None,
            creator=meta.get("creator") or None,
            producer=meta.get("producer") or None,
            creation_date=meta.get("creationDate") or None,
            page_count=doc.page_count,
        )

    def _extract_page(self, page: fitz.Page) -> PageRaw:
        page_num = page.number + 1

        text_spans = self._extract_text_spans(page, page_num)
        drawings   = self._extract_drawings(page, page_num)
        images     = self._extract_images(page, page_num)

        return PageRaw(
            page_number=page_num,
            width=page.rect.width,
            height=page.rect.height,
            rotation=page.rotation,
            bbox=BBox(x0=0, y0=0, x1=page.rect.width, y1=page.rect.height),
            text_spans=text_spans,
            drawings=drawings,
            images=images,
        )

    def _extract_text_spans(self, page: fitz.Page, page_num: int) -> list[TextSpanRaw]:
        """
        Extract every text span with full font metadata.
        A span is PyMuPDF's smallest text unit sharing one font/size/color —
        finer-grained than a word, coarser than a character.
        """
        spans: list[TextSpanRaw] = []

        try:
            raw = page.get_text("dict")
        except Exception as exc:
            logger.warning("get_text('dict') failed on page %d: %s", page_num, exc)
            return spans

        for block in raw.get("blocks", []):
            if block.get("type") != 0:   # 0 = text block, 1 = image block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue

                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    flags = span.get("flags", 0)
                    color_int = span.get("color", 0)

                    color_rgb = None
                    if color_int:
                        r = (color_int >> 16) & 0xFF
                        g = (color_int >> 8)  & 0xFF
                        b = color_int & 0xFF
                        color_rgb = (r, g, b)

                    spans.append(TextSpanRaw(
                        page_number=page_num,
                        bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                        text=text,
                        font=FontInfo(
                            name=span.get("font", ""),
                            size=span.get("size", 0.0),
                            color_rgb=color_rgb,
                            is_bold=bool(flags & _FLAG_BOLD),
                            is_italic=bool(flags & _FLAG_ITALIC),
                        ),
                    ))

        return spans

    def _extract_drawings(self, page: fitz.Page, page_num: int) -> list[DrawingRaw]:
        """Extract every vector graphic path on the page."""
        drawings: list[DrawingRaw] = []

        try:
            raw_drawings = page.get_drawings()
        except Exception as exc:
            logger.warning("get_drawings() failed on page %d: %s", page_num, exc)
            return drawings

        for d in raw_drawings:
            rect = d.get("rect")
            if not rect:
                continue

            w = abs(rect.x1 - rect.x0)
            h = abs(rect.y1 - rect.y0)
            if w < _MIN_DRAWING_DIM and h < _MIN_DRAWING_DIM:
                continue   # zero-size artifact, not a real drawing

            fill_rgb = None
            raw_fill = d.get("fill")
            if raw_fill and len(raw_fill) >= 3:
                fill_rgb = tuple(int(c * 255) for c in raw_fill[:3])

            stroke_rgb = None
            raw_stroke = d.get("color")
            if raw_stroke and len(raw_stroke) >= 3:
                stroke_rgb = tuple(int(c * 255) for c in raw_stroke[:3])

            drawings.append(DrawingRaw(
                page_number=page_num,
                bbox=BBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1),
                fill_rgb=fill_rgb,
                stroke_rgb=stroke_rgb,
                stroke_width=d.get("width") or 0.0,
                is_line=(h < 3.0 or w < 3.0),
            ))

        return drawings

    def _extract_images(self, page: fitz.Page, page_num: int) -> list[ImageRaw]:
        """Extract every embedded raster image's metadata and position."""
        images: list[ImageRaw] = []
        seen_xrefs: set[int] = set()

        try:
            raw_images = page.get_images(full=True)
        except Exception as exc:
            logger.warning("get_images() failed on page %d: %s", page_num, exc)
            return images

        for img_info in raw_images:
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            try:
                bbox = page.get_image_bbox(img_info)
                pix  = fitz.Pixmap(page.parent, xref)

                images.append(ImageRaw(
                    page_number=page_num,
                    bbox=BBox(x0=bbox.x0, y0=bbox.y0, x1=bbox.x1, y1=bbox.y1),
                    xref=xref,
                    width_px=pix.width,
                    height_px=pix.height,
                    colorspace=pix.colorspace.name if pix.colorspace else "unknown",
                ))
            except Exception as exc:
                logger.warning(
                    "Could not extract image xref=%d on page %d: %s",
                    xref, page_num, exc,
                )
                continue

        return images

    def extract_and_save(self, pdf_path: str, debug_output_path: str) -> "DocumentRaw":
        """
        Run extraction and save the result as stage1_raw.json for debugging.

        Parameters
        ----------
        pdf_path          : Source PDF.
        debug_output_path : Where to write the JSON dump.

        Returns
        -------
        DocumentRaw (same as extract())
        """
        result = self.extract(pdf_path)
        Path(debug_output_path).write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
        logger.info("Stage 1 debug output saved: %s", debug_output_path)
        return result