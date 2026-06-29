"""
RTL text ordering utilities.
Shared between all OCR engines — no engine-specific dependencies.
"""

from models.ocr_result import OCRBlock

_LINE_TOLERANCE_PX = 15


def sort_rtl(blocks: list[OCRBlock]) -> list[OCRBlock]:
    """
    Sort OCR blocks into Urdu (RTL) reading order.

    1. Sort top-to-bottom by top_y.
    2. Group blocks within LINE_TOLERANCE_PX into the same line.
    3. Within each line, sort right-to-left (descending right_x).
    """
    if not blocks:
        return blocks

    sorted_by_y = sorted(blocks, key=lambda b: b.top_y)
    lines: list[list[OCRBlock]] = []
    current_line: list[OCRBlock] = [sorted_by_y[0]]

    for block in sorted_by_y[1:]:
        if abs(block.top_y - current_line[0].top_y) <= _LINE_TOLERANCE_PX:
            current_line.append(block)
        else:
            lines.append(current_line)
            current_line = [block]
    lines.append(current_line)

    ordered: list[OCRBlock] = []
    for line in lines:
        ordered.extend(sorted(line, key=lambda b: b.right_x, reverse=True))

    return ordered