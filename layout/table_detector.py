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

    # layout/table_detector.py — replace _extract_table

    def _extract_table(self, table, page_number: int) -> Optional[LayoutBlock]:
        try:
            rows: list[list[str]] = table.extract()
            if not rows:
                return None

            rows = [row for row in rows if any(cell for cell in row if cell)]
            if len(rows) < self.min_rows:
                return None

            max_cols = max(len(row) for row in rows)
            if max_cols < self.min_cols:
                return None

            cleaned: list[list[str]] = []
            for row in rows:
                cleaned_row = [(cell or "").strip() for cell in row]
                while len(cleaned_row) < max_cols:
                    cleaned_row.append("")
                cleaned.append(cleaned_row)

            # ── NEW: reject false tables ──────────────────────────────
            # Count cells that are empty or very short (≤2 chars).
            # Real tables have content in most cells.
            # News column layouts have mostly empty cells.
            total_cells = len(cleaned) * max_cols
            empty_cells = sum(
                1 for row in cleaned for cell in row
                if len(cell) <= 2
            )
            empty_ratio = empty_cells / total_cells if total_cells > 0 else 1.0

            if empty_ratio > 0.5:
                logger.debug(
                    "Page %d: rejecting false table — %.0f%% empty cells.",
                    page_number, empty_ratio * 100,
                )
                return None
            # ─────────────────────────────────────────────────────────

            bbox  = table.bbox
            top_y = bbox[1] if bbox else 0.0

            return LayoutBlock(
                text         = "",
                block_type   = BlockType.TABLE,
                page_number  = page_number,
                table_data   = cleaned,
                space_before = top_y,
            )

        except Exception as exc:
            logger.warning("Failed to extract table on page %d: %s", page_number, exc)
            return None