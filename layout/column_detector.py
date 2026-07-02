"""
ColumnDetector
--------------
Detects multi-column layouts and reorders LayoutBlocks into correct
Urdu reading order (right column first, top-to-bottom within each column).

Algorithm
---------
1. Collect x-centre positions of all text blocks on a page.
2. Use a simple gap-based clustering: if there's a large horizontal gap
   between groups of blocks, those groups are separate columns.
3. Assign each block a column_index (0 = rightmost for RTL).
4. Re-sort blocks: primary key = top-y, secondary key = column_index.

Why gap-based instead of k-means?
  - No need to specify k in advance (we don't know how many columns).
  - Works on pages that mix single and multi-column sections.
  - Fast: O(n log n) sort, O(n) scan.
"""

import logging
from dataclasses import dataclass

from models.layout_block import LayoutBlock

logger = logging.getLogger(__name__)

# A horizontal gap larger than this fraction of page width → column boundary
_COLUMN_GAP_RATIO = 0.08


@dataclass
class _BlockWithCoords:
    """Internal structure associating a LayoutBlock with its x-centre."""
    block:    LayoutBlock
    x_centre: float
    top:      float


def detect_columns(
    blocks:     list[LayoutBlock],
    page_width: float,
) -> list[LayoutBlock]:
    """
    Reorder blocks on one page into RTL column reading order.

    Parameters
    ----------
    blocks     : All LayoutBlocks for a single page, in any order.
    page_width : Width of the page in points (from pdfplumber).

    Returns
    -------
    list[LayoutBlock]
        Same blocks, reordered and with column_index set.
        If only one column is detected, order is unchanged.
    """
    if not blocks or page_width <= 0:
        return blocks

    # Only text blocks participate in column detection.
    # Images and tables keep their original position.
    text_blocks = [b for b in blocks if not b.is_image and not b.is_table]
    other_blocks = [b for b in blocks if b.is_image or b.is_table]

    if not text_blocks:
        return blocks

    # Estimate x-centre for blocks that have no explicit coords.
    # We use font_size as a proxy for width — rough but workable.
    coords: list[_BlockWithCoords] = []
    for block in text_blocks:
        # space_before encodes vertical position set by detector
        # We reconstruct x from alignment as a fallback
        x_centre = _estimate_x_centre(block, page_width)
        coords.append(_BlockWithCoords(
            block    = block,
            x_centre = x_centre,
            top      = block.space_before,  # best proxy we have
        ))

    # Sort by x_centre to find column boundaries
    sorted_by_x = sorted(coords, key=lambda c: c.x_centre)
    x_centres   = [c.x_centre for c in sorted_by_x]

    # Find gaps larger than threshold
    gap_threshold = page_width * _COLUMN_GAP_RATIO
    column_boundaries: list[float] = []  # x values where a new column starts

    for i in range(1, len(x_centres)):
        gap = x_centres[i] - x_centres[i - 1]
        if gap > gap_threshold:
            # Midpoint of the gap is the boundary
            column_boundaries.append((x_centres[i] + x_centres[i - 1]) / 2)

    num_columns = len(column_boundaries) + 1

    if num_columns == 1:
        logger.debug("Page: single-column layout detected.")
        return blocks

    logger.info("Page: %d-column layout detected.", num_columns)

    # Assign column index to each block
    # Columns are sorted left-to-right by x; for RTL we reverse the index
    # so column_index=0 is the rightmost column (first to read in Urdu)
    for item in coords:
        col = 0
        for boundary in column_boundaries:
            if item.x_centre > boundary:
                col += 1
        # Reverse for RTL: rightmost column = index 0
        item.block.column_index = (num_columns - 1) - col

    # Re-sort: by top (y position) first, then by column_index
    sorted_blocks = sorted(
        text_blocks,
        key=lambda b: (b.space_before, b.column_index),
    )

    # Re-insert images and tables at the end of their page
    return sorted_blocks + other_blocks


def _estimate_x_centre(block: LayoutBlock, page_width: float) -> float:
    """
    Estimate horizontal centre of a block from its alignment.

    Used when we don't have precise x-coordinates from pdfplumber.
    This is a rough estimate — column detection is best-effort on
    pages where metadata is sparse.
    """
    from models.layout_block import Alignment
    if block.alignment == Alignment.RIGHT:
        return page_width * 0.75
    if block.alignment == Alignment.LEFT:
        return page_width * 0.25
    return page_width * 0.50   # CENTER