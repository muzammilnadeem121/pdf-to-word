import pytest
import fitz
from layout.graphics_extractor import GraphicsExtractor, GraphicBox

def make_page_with_rect(tmp_path, fill=(0.2, 0.4, 0.8), stroke=None):
    doc  = fitz.open()
    page = doc.new_page(width=595, height=842)
    rect = fitz.Rect(50, 50, 400, 120)
    page.draw_rect(rect, color=stroke, fill=fill, width=1.5)
    out = tmp_path / "rect.pdf"
    doc.save(str(out))
    doc.close()
    return fitz.open(str(out))[0]

class TestGraphicsExtractor:

    def test_extracts_filled_rect(self, tmp_path):
        page      = make_page_with_rect(tmp_path, fill=(0.2, 0.4, 0.8))
        extractor = GraphicsExtractor()
        boxes     = extractor.extract_page_graphics(page)
        assert len(boxes) >= 1
        assert any(b.fill_rgb is not None for b in boxes)

    def test_white_fill_ignored(self, tmp_path):
        doc  = fitz.open()
        page = doc.new_page()
        page.draw_rect(fitz.Rect(50, 50, 400, 120), fill=(1,1,1))
        out = tmp_path / "white.pdf"
        doc.save(str(out)); doc.close()
        page2 = fitz.open(str(out))[0]
        boxes = GraphicsExtractor().extract_page_graphics(page2)
        assert all(b.fill_rgb is None for b in boxes)

    def test_rgb_conversion(self, tmp_path):
        page  = make_page_with_rect(tmp_path, fill=(1.0, 0.0, 0.0))
        boxes = GraphicsExtractor().extract_page_graphics(page)
        filled = [b for b in boxes if b.fill_rgb]
        assert any(b.fill_rgb[0] > 200 for b in filled)

    def test_contains_point(self):
        box = GraphicBox(rect=(50, 50, 400, 120), fill_rgb=(255, 0, 0))
        assert box.contains_point(200, 80) is True
        assert box.contains_point(10, 10)  is False

    def test_overlaps_rect(self):
        box = GraphicBox(rect=(50, 50, 400, 120), fill_rgb=(0, 0, 255))
        assert box.overlaps_rect(60, 55, 300, 110) is True
        assert box.overlaps_rect(500, 500, 600, 600) is False

    def test_find_container(self, tmp_path):
        page  = make_page_with_rect(tmp_path, fill=(0.0, 0.5, 0.5))
        boxes = GraphicsExtractor().extract_page_graphics(page)
        extractor  = GraphicsExtractor()
        container  = extractor.find_container(60, 55, 300, 110, boxes)
        assert container is not None
        assert container.fill_rgb is not None

    def test_blank_page_returns_empty(self, tmp_path):
        doc  = fitz.open()
        doc.new_page()
        out  = tmp_path / "blank.pdf"
        doc.save(str(out)); doc.close()
        page = fitz.open(str(out))[0]
        boxes = GraphicsExtractor().extract_page_graphics(page)
        assert boxes == []

    def test_contrast_text_color_dark_bg(self):
        from exporter.word_export import WordExporter
        from docx.shared import RGBColor
        exp = WordExporter()
        assert exp._contrast_text_color((30, 30, 30))    == RGBColor(255,255,255)
        assert exp._contrast_text_color((220, 220, 220)) == RGBColor(0, 0, 0)