"""
LayoutBlock
-----------
Intermediate representation of a single detected document element.

Milestone 9 additions:
  - BlockType.IMAGE and BlockType.TABLE
  - image_path field for extracted images
  - table_data field for extracted table cells
  - column_index for multi-column ordering
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BlockType(str, Enum):
    HEADING  = "heading"
    BODY     = "body"
    PAGE_NUM = "page_number"
    CAPTION  = "caption"
    IMAGE    = "image"
    TABLE    = "table"
    UNKNOWN  = "unknown"


class Alignment(str, Enum):
    RIGHT  = "right"
    LEFT   = "left"
    CENTER = "center"


@dataclass
class LayoutBlock:
    """
    A single formatted document element ready for DOCX export.

    Attributes
    ----------
    text          : Text content. Empty for IMAGE blocks.
    block_type    : Semantic type of this element.
    page_number   : 1-based source page number.
    font_size     : Detected font size in points. None if unknown.
    is_bold       : Whether the text is bold.
    is_italic     : Whether the text is italic.
    alignment     : Text alignment direction.
    heading_level : 1–3 for headings, None for non-headings.
    space_before  : Vertical spacing above this block in points.
    is_rtl        : True for Urdu/Arabic text.
    column_index  : 0-based column index. 0 = rightmost (Urdu reading order).
    image_path    : Absolute path to extracted image file. IMAGE blocks only.
    image_width   : Image width in points for DOCX sizing.
    image_height  : Image height in points for DOCX sizing.
    table_data    : 2D list of cell strings. TABLE blocks only.
                    table_data[row][col] = cell text.
    """
    text:          str
    block_type:    BlockType
    page_number:   int
    font_size:     Optional[float]          = None
    is_bold:       bool                     = False
    is_italic:     bool                     = False
    alignment:     Alignment                = Alignment.RIGHT
    heading_level: Optional[int]            = None
    space_before:  float                    = 0.0
    is_rtl:        bool                     = True
    column_index:  int                      = 0
    image_path:    Optional[str]            = None
    image_width:   Optional[float]          = None
    image_height:  Optional[float]          = None
    table_data:    list[list[str]]          = field(default_factory=list)
    background_color: Optional[tuple[int,int,int]] = None
    border_color:     Optional[tuple[int,int,int]] = None
    border_width:     float = 0.0
    text_color:       Optional[tuple[int,int,int]] = None


    @property
    def is_heading(self) -> bool:
        return self.block_type == BlockType.HEADING

    @property
    def is_body(self) -> bool:
        return self.block_type == BlockType.BODY

    @property
    def is_page_number(self) -> bool:
        return self.block_type == BlockType.PAGE_NUM

    @property
    def is_image(self) -> bool:
        return self.block_type == BlockType.IMAGE

    @property
    def is_table(self) -> bool:
        return self.block_type == BlockType.TABLE