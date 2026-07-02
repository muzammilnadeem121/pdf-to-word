"""
Stateless Unicode repair utilities, reusable across the entire engine.

Ported from the original extractor/unicode_fixer.py with fixes already
validated in production:
  - Presentation forms handled via NFKC (not a manual NFKD map).
  - BiDi reordering (get_display) is NOT applied here — it belongs only
    where visually-ordered text is joined (pdfplumber-style extraction
    or OCR output), never to already-logical-order PyMuPDF spans.
    Stage 3's OCR merge path applies it explicitly where needed.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

_INVISIBLE_CHARS = (
    "\u200B", "\u200C", "\u200D", "\u200E", "\u200F",
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",
    "\uFEFF", "\u00AD",
)
_INVISIBLE_PATTERN = re.compile("[" + "".join(re.escape(c) for c in _INVISIBLE_CHARS) + "]")


def looks_like_mojibake(text: str) -> bool:
    """UTF-8 Arabic bytes misread as cp1252 produce a glut of Ø/Ù chars."""
    if not text:
        return False
    mojibake_chars = sum(1 for c in text if c in ("\u00D8", "\u00D9"))
    return (mojibake_chars / len(text)) > 0.20


def repair_mojibake(text: str) -> str:
    """Reverse UTF-8-as-cp1252 mojibake."""
    try:
        recovered = text.encode("cp1252").decode("utf-8")
        arabic_chars = sum(
            1 for c in recovered
            if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F"
        )
        if arabic_chars > len(recovered) * 0.3:
            return recovered
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def normalize_presentation_forms(text: str) -> str:
    """NFKC maps all 600+ Arabic Presentation Forms to base characters."""
    return unicodedata.normalize("NFKC", text)


def remove_invisible_chars(text: str) -> str:
    return _INVISIBLE_PATTERN.sub("", text)


def normalize_nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def normalize_whitespace(text: str) -> str:
    text  = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    text  = "\n".join(line for line in lines if line)
    text  = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_rtl_text(text: str, threshold: float = 0.3) -> bool:
    if not text:
        return False
    rtl = sum(1 for c in text if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F")
    return (rtl / len(text)) > threshold


class UnicodeRepairEngine:
    """
    Full repair pipeline, stateless per call.

    Order matters: mojibake -> presentation forms -> invisible chars
    -> NFC -> whitespace.
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
        self.fix_mojibake           = fix_mojibake
        self.fix_presentation_forms = fix_presentation_forms
        self.fix_invisible_chars    = fix_invisible_chars
        self.fix_normalization      = fix_normalization
        self.fix_whitespace         = fix_whitespace
        self.min_text_length        = min_text_length

    def repair(self, text: str) -> str:
        if not text or len(text) < self.min_text_length:
            return text

        steps = [
            (self.fix_mojibake, lambda t: repair_mojibake(t) if looks_like_mojibake(t) else t),
            (self.fix_presentation_forms, normalize_presentation_forms),
            (self.fix_invisible_chars, remove_invisible_chars),
            (self.fix_normalization, normalize_nfc),
            (self.fix_whitespace, normalize_whitespace),
        ]

        for enabled, step in steps:
            if enabled:
                try:
                    text = step(text)
                except Exception as exc:
                    logger.warning("Repair step failed: %s — skipping.", exc)

        return text