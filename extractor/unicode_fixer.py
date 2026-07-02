"""
UnicodeRepairEngine
-------------------
Repairs broken Urdu/Arabic text extracted from PDF files.

Each repair rule is a separate method so rules can be:
  - Enabled/disabled individually via constructor flags.
  - Tested independently.
  - Extended without touching other rules.

Pipeline order matters:
  1. Mojibake detection and repair   — must run before Unicode normalization
  2. Presentation forms normalization — convert legacy forms to base codepoints
  3. Invisible character removal      — strip zero-width and control characters
  4. Unicode normalization (NFC)      — canonical composition
  5. Whitespace normalization         — consistent spacing and line breaks
  6. RTL word order repair            — fix words stored in wrong order

Each rule returns a string. The pipeline chains them sequentially.
"""

import logging
import re
import unicodedata
from typing import Callable
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Invisible / zero-width characters
# ---------------------------------------------------------------------------
# These characters are invisible but break text matching and OCR accuracy.

_INVISIBLE_CHARS = (
    "\u200B",  # Zero-width space
    "\u200C",  # Zero-width non-joiner
    "\u200D",  # Zero-width joiner
    "\u200E",  # Left-to-right mark
    "\u200F",  # Right-to-left mark
    "\u202A",  # Left-to-right embedding
    "\u202B",  # Right-to-left embedding
    "\u202C",  # Pop directional formatting
    "\u202D",  # Left-to-right override
    "\u202E",  # Right-to-left override
    "\uFEFF",  # Byte order mark / zero-width no-break space
    "\u00AD",  # Soft hyphen
)

_INVISIBLE_PATTERN = re.compile(
    "[" + "".join(re.escape(c) for c in _INVISIBLE_CHARS) + "]"
)

# ---------------------------------------------------------------------------
# Mojibake detection
# ---------------------------------------------------------------------------
# Mojibake happens when Windows-1256 (Arabic) encoded bytes are
# interpreted as Latin-1 or Windows-1252.
#
# The signature: lots of characters in the range Ù (U+00D9) through
# Ø (U+00D8) and Ã (U+00C3), which are the Latin-1 representations
# of Arabic byte sequences.

_MOJIBAKE_PATTERN = re.compile(r"[\u00D8\u00D9]{1}[\u0080-\u00BF]")


# Replace _looks_like_mojibake and _repair_mojibake

def _looks_like_mojibake(text: str) -> bool:
    """
    Detect UTF-8 Arabic bytes misread as Windows-1252.
    Signature: lots of Ø (U+00D8) and Ù (U+00D9) characters,
    which are the cp1252 representations of the high bytes in
    UTF-8 encoded Arabic (0xD8xx and 0xD9xx sequences).
    """
    if not text:
        return False
    mojibake_chars = sum(1 for c in text if c in ("\u00D8", "\u00D9"))
    return (mojibake_chars / len(text)) > 0.20


def _repair_mojibake(text: str) -> str:
    """
    Recover Arabic text from UTF-8-as-cp1252 mojibake.

    Reversal: encode back to cp1252 bytes (undoing the misread),
    then decode those bytes as UTF-8 (the original encoding).
    """
    try:
        recovered = text.encode("cp1252").decode("utf-8")
        arabic_chars = sum(
            1 for c in recovered
            if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F"
        )
        if arabic_chars > len(recovered) * 0.3:
            logger.debug("Mojibake repair recovered %d Arabic chars.", arabic_chars)
            return recovered
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class UnicodeRepairEngine:
    """
    Repairs broken Urdu/Arabic Unicode text from PDF extraction.

    Parameters
    ----------
    fix_mojibake            : Attempt Windows-1256 mojibake recovery.
    fix_presentation_forms  : Map Arabic Presentation Forms to base chars.
    fix_invisible_chars     : Remove zero-width and directional characters.
    fix_normalization       : Apply NFC Unicode normalization.
    fix_whitespace          : Normalize spaces and line breaks.
    min_text_length         : Strings shorter than this are returned as-is.
    """

    def __init__(
        self,
        fix_mojibake:           bool = True,
        fix_presentation_forms: bool = True,
        fix_invisible_chars:    bool = True,
        fix_normalization:      bool = True,
        fix_whitespace:         bool = True,
        min_text_length:        int  = 3,
    ) -> None:
        self.fix_mojibake            = fix_mojibake
        self.fix_presentation_forms  = fix_presentation_forms
        self.fix_invisible_chars     = fix_invisible_chars
        self.fix_normalization       = fix_normalization
        self.fix_whitespace          = fix_whitespace
        self.min_text_length         = min_text_length

        # Build the pipeline as an ordered list of (flag, method) pairs.
        # Order is critical — see module docstring.
        self._pipeline: list[tuple[bool, Callable[[str], str]]] = [
            (self.fix_mojibake,           self._step_mojibake),
            (self.fix_presentation_forms, self._step_presentation_forms),
            (self.fix_invisible_chars,    self._step_invisible_chars),
            (self.fix_normalization,      self._step_normalization),
            (self.fix_whitespace,         self._step_whitespace),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def repair(self, text: str) -> str:
        """
        Run the full repair pipeline on a string.

        Parameters
        ----------
        text : str
            Raw text from PDF extraction or OCR.

        Returns
        -------
        str
            Repaired text. Returns input unchanged if it is too short
            or if no repairs were applicable.
        """
        if not text or len(text) < self.min_text_length:
            return text

        original = text
        for enabled, step in self._pipeline:
            if enabled:
                try:
                    text = step(text)
                except Exception as exc:
                    logger.warning(
                        "Repair step %s failed: %s — skipping.",
                        step.__name__, exc,
                    )

        if text != original:
            logger.debug(
                "Unicode repair modified text (before=%d chars, after=%d chars).",
                len(original), len(text),
            )

        return text

    def repair_pages(self, pages) -> None:
        """
        Repair text in-place across a list of PageResult objects.

        Modifies raw_text and ocr_result.full_text directly.
        Called by ConversionService between extraction and export.

        Parameters
        ----------
        pages : list[PageResult]
            From ExtractionResult.pages.
        """
        for page in pages:
            # Repair direct extraction text
            if page.raw_text:
                page.raw_text = self.repair(page.raw_text)

            # Repair OCR text
            if page.ocr_result and page.ocr_result.full_text:
                page.ocr_result.full_text = self.repair(page.ocr_result.full_text)
                # Also repair individual blocks for layout use in Milestone 8
                for block in page.ocr_result.blocks:
                    block.text = self.repair(block.text)

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _step_mojibake(self, text: str) -> str:
        """Detect and repair Windows-1256 mojibake."""
        if _looks_like_mojibake(text):
            return _repair_mojibake(text)
        return text

    def _step_presentation_forms(self, text: str) -> str:
        """
        Normalize Arabic Presentation Forms to base Unicode characters
        using NFKC (Compatibility Decomposition + Canonical Composition).

        NFKC is more reliable than manual NFKD mapping because it handles
        all presentation forms in one pass, including edge cases the manual
        map misses. e.g. ﻮﯾﮉﯾو → ویڈیو
        """
        return unicodedata.normalize("NFKC", text)

    def _step_invisible_chars(self, text: str) -> str:
        """Remove zero-width and directional control characters."""
        return _INVISIBLE_PATTERN.sub("", text)
    
    # def _step_bidi_reorder(self, text: str) -> str:
    #     """
    #     Apply the Unicode Bidirectional Algorithm to convert visual-order
    #     RTL text (as stored in the PDF stream) into logical reading order.

    #     PDF text streams for Arabic/Urdu often store glyphs in the order
    #     they're drawn on screen (visual order), not the order a screen
    #     reader or text editor expects (logical order). Without this step,
    #     extracted lines can appear scrambled or interleaved with fragments
    #     from adjacent words.

    #     We process line-by-line because get_display() expects a single
    #     paragraph/line of text, not a multi-line block.
    #     """
    #     lines = text.split("\n")
    #     reordered = []
    #     for line in lines:
    #         if not line.strip():
    #             reordered.append(line)
    #             continue
    #         try:
    #             reordered.append(get_display(line))
    #         except Exception as exc:
    #             logger.warning("BiDi reorder failed on line: %s — using original.", exc)
    #             reordered.append(line)
    #     return "\n".join(reordered)

    def _step_normalization(self, text: str) -> str:
        """
        Apply NFC Unicode normalization.

        NFC (Canonical Decomposition followed by Canonical Composition)
        ensures that characters with combining marks are stored in their
        precomposed form — e.g. Arabic letters with diacritics (tashkeel)
        are stored as single codepoints where possible.
        """
        return unicodedata.normalize("NFC", text)

    def _step_whitespace(self, text: str) -> str:
        """
        Normalize whitespace.

        Rules:
          - Collapse multiple spaces into one.
          - Collapse 3+ newlines into 2 (preserve paragraph breaks).
          - Strip leading/trailing whitespace from each line.
          - Remove lines that are entirely whitespace.
        """
        # Collapse multiple spaces (but not newlines)
        text = re.sub(r"[ \t]+", " ", text)
        # Strip each line
        lines = [line.strip() for line in text.splitlines()]
        # Remove blank lines (keep structure but not empty runs)
        text = "\n".join(line for line in lines if line)
        # Collapse 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()