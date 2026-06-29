import logging
import re
import unicodedata
from typing import List, Protocol

# Setup logging
logger = logging.getLogger("urdu_converter.unicode_fixer")


class RepairRule(Protocol):
    """Protocol defining a single, extendable repair strategy."""
    def apply(self, text: str) -> str:
        ...


class NormalizationRule:
    """Applies standard Unicode normalization (NFKC) to unify compositions."""
    def apply(self, text: str) -> str:
        if not text:
            return ""
        return unicodedata.normalize("NFKC", text)


class CharacterSubstitutionRule:
    """Maps incorrect Arabic or font-specific layout glyphs back to semantic Urdu characters."""
    def __init__(self) -> None:
        # Standard replacements for common Persian/Arabic confusion and normalization
        self.mapping = {
            # Arabic Kaf to Urdu Keheh
            "\u0643": "\u06a9",
            # Arabic Yeh variants to Urdu Choti Yeh
            "\u064a": "\u06cc",
            "\u0649": "\u06cc",
            # Arabic Heh to Urdu Goal Heh
            "\u0647": "\u06c1",
            # Incorrect Ta Marbuta conversions to Urdu Te/Goal Heh depending on context 
            # (Keeping simple character unify maps here)
            "\u0642": "\u0642", 
        }

    def apply(self, text: str) -> str:
        for bad_char, good_char in self.mapping.items():
            text = text.replace(bad_char, good_char)
        return text


class PresentationFormsRepairRule:
    """
    Transforms Arabic Presentation Forms A & B back into standard Arabic/Urdu script block ranges.
    PDFs often draw text via these localized glyph blocks rather than semantic codes.
    """
    def __init__(self) -> None:
        # A partial dictionary showing the mapping mechanism.
        # Production versions use a compiled character map coverage for range 0xFB50-0xFDFF and 0xFE70-0xFEFF
        self.presentation_map = {
            "\ufe81": "\u0622",  # Alef with Madda Isolated
            "\ufe8d": "\u0627",  # Alef Isolated
            "\ufe8e": "\u0627",  # Alef Final
            "\ufee7": "\u0645",  # Meem Medial
            "\ufeed": "\u0646",  # Noon Isolated
            "\ufeee": "\u0646",  # Noon Final
            "\ufb92": "\u06a9",  # Keheh Isolated
            "\ufb93": "\u06a9",  # Keheh Initial
            "\ufbfc": "\u06cc",  # Yeh Initial
            "\ufbfe": "\u06cc",  # Yeh Medial
        }

    def apply(self, text: str) -> str:
        # Explicit replace loop for known high-frequency presentation forms
        for glyph, standard in self.presentation_map.items():
            text = text.replace(glyph, standard)
            
        # Fallback mechanism using unicodedata for standard decomposition of presentation forms
        fixed_chars = []
        for char in text:
            cp = ord(char)
            # Check if character lies within Presentation Forms blocks
            if (0xFB50 <= cp <= 0xFDFF) or (0xFE70 <= cp <= 0xFEFF):
                decomp = unicodedata.normalize("NFKD", char)
                # Filter down to base Arabic/Urdu characters
                cleaned_decomp = "".join([c for c in decomp if 0x0600 <= ord(c) <= 0x06FF])
                fixed_chars.append(cleaned_decomp if cleaned_decomp else char)
            else:
                fixed_chars.append(char)
                
        return "".join(fixed_chars)


class CleanInvisibleCharactersRule:
    """Strips rogue control variables and non-printing tags, preserving explicit spaces & ZWNJs."""
    def __init__(self) -> None:
        # Matches control characters except formatting symbols like ZWNJ (\u200c)
        self.control_char_regex = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

    def apply(self, text: str) -> str:
        if not text:
            return ""
        # Remove raw invisible control frames
        text = self.control_char_regex.sub("", text)
        return text


class UnicodeRepairEngine:
    """The orchestration engine running raw text string iterations through the rule engine pipeline."""
    def __init__(self, rules: List[RepairRule] = None) -> None:
        if rules is list or rules is None:
            self.rules: List[RepairRule] = [
                CleanInvisibleCharactersRule(),
                PresentationFormsRepairRule(),
                CharacterSubstitutionRule(),
                NormalizationRule()
            ]
        else:
            self.rules = rules

    def repair(self, text: str) -> str:
        """
        Passes text down the normalization pipeline.
        Handles runtime isolation to ensure no document crashing occurs.
        """
        if not text:
            return ""
        
        try:
            processed_text = text
            for rule in self.rules:
                processed_text = rule.apply(processed_text)
            return processed_text
        except Exception as e:
            logger.error(f"Error occurred during Unicode repair processing sequence: {str(e)}", exc_info=True)
            # Fail-safe gracefully: return original text if the clean engine errors out
            return text