"""
ImageExtractor
--------------
Extracts raster images from PDF pages using PyMuPDF and saves them
as temporary PNG files for embedding in the DOCX.

Each extracted image becomes an IMAGE-type LayoutBlock with:
  - image_path  : absolute path to the saved PNG
  - image_width : width in points (for DOCX sizing)
  - image_height: height in points

Design decisions
----------------
- Images are saved to a temp directory under output/.
- We skip very small images (< MIN_IMAGE_AREA points²) to avoid
  extracting decorative icons, bullets, and PDF artifacts.
- CMYK images are converted to RGB before saving.
- Duplicate xrefs on the same page are skipped.
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

import fitz

from models.layout_block import BlockType, LayoutBlock

logger = logging.getLogger(__name__)

# Images smaller than this area (in PDF points²) are skipped
_MIN_IMAGE_AREA = 50 * 50   # 50×50 points ≈ 0.7 × 0.7 inches

# Where extracted images are stored
_IMAGE_CACHE_DIR = Path("output") / "_images"


class ImageExtractor:
    """
    Extracts images from PDF pages into LayoutBlock objects.

    Parameters
    ----------
    min_area   : Minimum image area in points². Smaller images are skipped.
    cache_dir  : Directory to save extracted PNG files.
    """

    def __init__(
        self,
        min_area:  float = _MIN_IMAGE_AREA,
        cache_dir: Path  = _IMAGE_CACHE_DIR,
    ) -> None:
        self.min_area  = min_area
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def extract_page_images(
        self, doc: fitz.Document, page: fitz.Page, page_number: int
    ) -> list[LayoutBlock]:
        """
        Extract all qualifying images from a single PDF page.

        Parameters
        ----------
        doc         : Open fitz.Document (needed to load image by xref).
        page        : fitz.Page to extract from.
        page_number : 1-based page number for LayoutBlock metadata.

        Returns
        -------
        list[LayoutBlock]
            One IMAGE block per extracted image, in top-to-bottom order.
        """
        image_blocks: list[LayoutBlock] = []
        seen_xrefs:   set[int]          = set()

        try:
            images = page.get_images(full=True)
        except Exception as exc:
            logger.warning("Could not enumerate images on page %d: %s", page_number, exc)
            return []

        for img_info in images:
            xref = img_info[0]

            # Skip duplicates (same image referenced multiple times)
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            block = self._extract_image(doc, page, img_info, page_number)
            if block:
                image_blocks.append(block)

        # Sort top-to-bottom by estimated position
        image_blocks.sort(key=lambda b: b.space_before)

        logger.debug(
            "Page %d: extracted %d images.", page_number, len(image_blocks)
        )
        return image_blocks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_image(
        self,
        doc:        fitz.Document,
        page:       fitz.Page,
        img_info:   tuple,
        page_number: int,
    ) -> Optional[LayoutBlock]:
        """
        Extract a single image and save it to disk.

        Returns a LayoutBlock or None if the image should be skipped.
        """
        xref = img_info[0]

        try:
            # Get image bounding box on the page
            bbox = page.get_image_bbox(img_info)
            width_pts  = abs(bbox.x1 - bbox.x0)
            height_pts = abs(bbox.y1 - bbox.y0)

            if width_pts * height_pts < self.min_area:
                logger.debug("Skipping small image (xref=%d, %.0f×%.0f pts).",
                             xref, width_pts, height_pts)
                return None

            # Load pixmap
            pix = fitz.Pixmap(doc, xref)

            # Convert CMYK or unusual colorspaces to RGB
            if pix.n > 4 or pix.colorspace != fitz.csRGB:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # Save as PNG
            filename  = f"page{page_number}_img{xref}_{uuid.uuid4().hex[:6]}.png"
            save_path = self.cache_dir / filename
            pix.save(str(save_path))

            logger.debug(
                "Saved image xref=%d → %s (%.0f×%.0f pts)",
                xref, filename, width_pts, height_pts,
            )

            return LayoutBlock(
                text         = "",
                block_type   = BlockType.IMAGE,
                page_number  = page_number,
                image_path   = str(save_path),
                image_width  = width_pts,
                image_height = height_pts,
                space_before = bbox.y0,   # vertical position on page
            )

        except Exception as exc:
            logger.warning(
                "Failed to extract image (xref=%d, page=%d): %s",
                xref, page_number, exc,
            )
            return None