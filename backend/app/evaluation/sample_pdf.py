"""Builds a small synthetic catalogue PDF (ruled table, optional captioned picture).

Used by the test suite and by the evaluation runner to exercise the
upload -> search -> delete path with a document that is not one of the two
supplied catalogues.
"""
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pymupdf

HEADER = ["Part number", "Description", "Thread", "Ball material", "Ball diameter (mm)", "Stem material", "Length (mm)"]
WIDTHS = [80, 110, 45, 75, 80, 80, 60]


def make_catalogue_pdf(path: Path, rows: Iterable[Sequence], title: str = "Test styli catalogue",
                       image_for: Optional[str] = None, pages: int = 1) -> Path:
    doc = pymupdf.open()
    table = [HEADER] + [list(map(str, r)) for r in rows]
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((50, 60), title, fontsize=14)
        y0, row_h, x0 = 90, 22, 40
        for r, row in enumerate(table):
            x = x0
            for c, text in enumerate(row):
                rect = pymupdf.Rect(x, y0 + r * row_h, x + WIDTHS[c], y0 + (r + 1) * row_h)
                page.draw_rect(rect, color=(0, 0, 0), width=0.6)
                page.insert_text((x + 3, rect.y1 - 7), text, fontsize=7.5)
                x += WIDTHS[c]
        if image_for:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 80), False)
            pix.set_rect(pix.irect, (200, 30, 30))
            pix.set_rect(pymupdf.IRect(20, 30, 100, 50), (40, 40, 40))
            page.insert_image(pymupdf.Rect(60, 420, 240, 540), pixmap=pix)
            page.insert_text((60, 556), f"Figure: {image_for}", fontsize=9)
    doc.save(path)
    doc.close()
    return path
