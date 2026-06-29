"""
TableDetector
-------------
Detects and extracts tables from PDF pages using pdfplumber.

pdfplumber's find_tables() uses line detection to locate table
structures. For each found table, we extract the cell text and
produce a TABLE-type LayoutBlock.

Design decisions
----------------
- Tables with fewer than 2 rows or 2 columns are skipped
  (likely false positives from decorative lines).
- Cell text is stripped and None cells are replaced with "".
- Table position (top-y) is preserved for correct ordering
  relative to surrounding text blocks.
"""

import logging
from typing import Optional

import pdfplumber

from models.layout_block import BlockType, LayoutBlock

logger = logging.getLogger(__name__)

_MIN_ROWS = 2
_MIN_COLS = 2


class TableDetector:
    """
    Finds tables on a PDF page and returns TABLE LayoutBlocks.

    Parameters
    ----------
    min_rows : Minimum rows to treat a detected structure as a table.
    min_cols : Minimum columns to treat a detected structure as a table.
    """

    def __init__(self, min_rows: int = _MIN_ROWS, min_cols: int = _MIN_COLS) -> None:
        self.min_rows = min_rows
        self.min_cols = min_cols

    def extract_page_tables(
        self, plumber_page: pdfplumber.page.Page, page_number: int
    ) -> list[LayoutBlock]:
        """
        Extract all tables from a pdfplumber page.

        Parameters
        ----------
        plumber_page : pdfplumber page object.
        page_number  : 1-based page number.

        Returns
        -------
        list[LayoutBlock]
            One TABLE block per detected table, sorted top-to-bottom.
        """
        table_blocks: list[LayoutBlock] = []

        try:
            tables = plumber_page.find_tables()
        except Exception as exc:
            logger.warning(
                "Table detection failed on page %d: %s", page_number, exc
            )
            return []

        for table in tables:
            block = self._extract_table(table, page_number)
            if block:
                table_blocks.append(block)

        logger.debug(
            "Page %d: found %d valid tables.", page_number, len(table_blocks)
        )
        return table_blocks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_table(
        self,
        table,
        page_number: int,
    ) -> Optional[LayoutBlock]:
        """
        Convert a pdfplumber Table into a LayoutBlock.

        Returns None if the table is too small to be meaningful.
        """
        try:
            rows: list[list[str]] = table.extract()

            if not rows:
                return None

            # Filter out completely empty rows
            rows = [row for row in rows if any(cell for cell in row if cell)]

            if len(rows) < self.min_rows:
                return None

            # Ensure minimum column count
            max_cols = max(len(row) for row in rows)
            if max_cols < self.min_cols:
                return None

            # Normalise: replace None with "", strip whitespace,
            # and pad short rows so all rows have the same width
            cleaned: list[list[str]] = []
            for row in rows:
                cleaned_row = [
                    (cell or "").strip()
                    for cell in row
                ]
                # Pad to max_cols if this row is shorter
                while len(cleaned_row) < max_cols:
                    cleaned_row.append("")
                cleaned.append(cleaned_row)

            # Get table position for ordering with surrounding text
            bbox      = table.bbox   # (x0, top, x1, bottom)
            top_y     = bbox[1] if bbox else 0.0

            logger.debug(
                "Page %d: table %d×%d at y=%.0f",
                page_number, len(cleaned), max_cols, top_y,
            )

            return LayoutBlock(
                text         = "",
                block_type   = BlockType.TABLE,
                page_number  = page_number,
                table_data   = cleaned,
                space_before = top_y,
            )

        except Exception as exc:
            logger.warning(
                "Failed to extract table on page %d: %s", page_number, exc
            )
            return None