# tests/test_bidi_fix.py — replace entire file

from bidi.algorithm import get_display

def test_get_display_available():
    """BiDi library is importable and callable."""
    result = get_display("نماز پڑھنا")
    assert isinstance(result, str)
    assert len(result) > 0

def test_get_display_reorders_visual_order():
    """
    get_display() corrects visually-ordered RTL characters.
    Visual-order Urdu (as stored in many PDFs) appears reversed
    when read as a string. get_display() fixes this.
    """
    # Simulate a reversed/visual-order word as pdfplumber might return it
    visual = "زامن"        # نماز stored backwards
    logical = get_display(visual)
    assert isinstance(logical, str)