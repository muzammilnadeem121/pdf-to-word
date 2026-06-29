import pytest
from extractor.unicode_fixer import UnicodeRepairEngine


def test_arabic_to_urdu_substitution():
    engine = UnicodeRepairEngine()
    # Contains Arabic Kaf (\u0643) and Arabic Yeh (\u064a)
    arabic_styled_urdu = "كتاب ہے كيا" 
    repaired = engine.repair(arabic_styled_urdu)
    
    # Target should be converted to Urdu Keheh (\u06a9)
    assert "ك" not in repaired
    assert "کتاب" in repaired


def test_presentation_forms_conversion():
    engine = UnicodeRepairEngine()
    # Mocking string mixing normal chars with Presentation Form elements (e.g., Alef Isolated \ufe8d)
    mixed_text = "\ufe8d" + " اردو"
    repaired = engine.repair(mixed_text)
    
    assert "\ufe8d" not in repaired
    assert repaired.startswith("ا")


def test_invisible_character_stripping():
    engine = UnicodeRepairEngine()
    text_with_control_frames = "Urdu\x02Text\x07With\u200cZWNJ"
    repaired = engine.repair(text_with_control_frames)
    
    assert "\x02" not in repaired
    assert "\x07" not in repaired
    assert "\u200c" in repaired  # ZWNJ must be preserved for script integrity


def test_empty_and_edge_cases():
    engine = UnicodeRepairEngine()
    assert engine.repair("") == ""
    assert engine.repair(None) == ""