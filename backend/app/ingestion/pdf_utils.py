"""Geometry helpers shared by the catalogue extractors.

All extractors work from word positions (`page.get_text("words")`) rather than
from `find_tables()` cell text, because the catalogue tables contain merged
cells and blank cells that table detection collapses or mis-splits.
"""
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

PART_NUMBER_RE = re.compile(r"^[A-Z]-\d{4}-\d{4}$")
PART_NUMBER_SEARCH_RE = re.compile(r"[A-Z]-\d{4}-\d{4}")


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


def page_words(page: "pymupdf.Page", max_height: float = 14.0) -> List[Word]:
    """Words of a page, without rotated margin text (taller than it is a text line)."""
    words = [Word(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
    return [w for w in words if (w.y1 - w.y0) <= max_height or (w.x1 - w.x0) > (w.y1 - w.y0)]


def group_lines(words: Sequence[Word], tolerance: float = 2.5) -> List[List[Word]]:
    """Group words into visual lines (same baseline within `tolerance` points)."""
    lines: List[List[Word]] = []
    for w in sorted(words, key=lambda w: (w.cy, w.x0)):
        if lines and abs(lines[-1][0].cy - w.cy) <= tolerance:
            lines[-1].append(w)
        else:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w.x0)
    return lines


def strip_part_number(text: str) -> Optional[str]:
    """Return the bare part number from a word such as 'A-5000-7800**'."""
    cleaned = text.strip().rstrip("*†‡")
    return cleaned if PART_NUMBER_RE.match(cleaned) else None


def column_anchors(
    rows: Sequence[Sequence[Word]],
    min_share: float = 0.3,
    min_gap: float = 4.0,
    expected: Optional[int] = None,
) -> List[float]:
    """Find the x positions at which left-aligned table columns start.

    A word starts a cell when it is the first word of the row or is separated
    from the previous word by more than an inter-word space. A column start is
    an x0 (rounded to the nearest point) at which at least `min_share` of the
    rows start a cell.
    """
    if not rows:
        return []
    if expected is not None:
        # Retry with other thresholds until the known column count is reached.
        fallback: List[float] = []
        for share in (min_share, 0.5, 0.7, 0.85, 0.15):
            fallback = column_anchors(rows, share, min_gap)
            if len(fallback) == expected:
                return fallback
        return fallback
    counts: Dict[int, int] = {}
    for row in rows:
        seen = set()
        prev: Optional[Word] = None
        for w in row:
            if prev is None or w.x0 - prev.x1 >= min_gap:
                key = int(round(w.x0))
                if key not in seen:
                    seen.add(key)
                    counts[key] = counts.get(key, 0) + 1
            prev = w
    threshold = max(2, int(len(rows) * min_share))
    anchors: List[float] = []
    best: Dict[float, int] = {}
    for k in sorted(counts):
        # Merge sub-point jitter into one column before applying the threshold.
        if anchors and k - anchors[-1] <= 2:
            best[anchors[-1]] += counts[k]
            continue
        anchors.append(float(k))
        best[float(k)] = counts[k]
    return [a for a in anchors if best[a] >= threshold]


def split_row(row: Sequence[Word], anchors: Sequence[float], slack: float = 1.5) -> List[str]:
    """Assign each word of a row to the column whose anchor precedes it."""
    cells: List[List[Word]] = [[] for _ in anchors]
    for w in row:
        idx = 0
        for i, a in enumerate(anchors):
            if w.x0 + slack >= a:
                idx = i
        cells[idx].append(w)
    return [join_cell(c) for c in cells]


def join_cell(words: Sequence[Word]) -> str:
    """Join the words of a cell, repairing numbers typeset as '1. 0' or '8. 0/20. 0'."""
    text = " ".join(w.text for w in sorted(words, key=lambda w: w.x0))
    text = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", text)
    text = re.sub(r"\s*/\s*", "/", text)
    return text.strip()


def ink_ratio(pixmap: "pymupdf.Pixmap") -> float:
    """Share of pixels that are not (near-)white. Used to reject blank crops."""
    samples = pixmap.samples
    n = pixmap.n
    step = max(1, (len(samples) // n) // 20000) * n
    total = 0
    dark = 0
    for i in range(0, len(samples) - n + 1, step):
        total += 1
        if min(samples[i], samples[i + 1 if n > 1 else i], samples[i + 2 if n > 2 else i]) < 235:
            dark += 1
    return dark / total if total else 0.0


def union_rect(rects: Sequence["pymupdf.Rect"]) -> Optional["pymupdf.Rect"]:
    result: Optional[pymupdf.Rect] = None
    for r in rects:
        if r.is_empty or r.is_infinite:
            continue
        result = pymupdf.Rect(r) if result is None else result | r
    return result


def drawing_rects(page: "pymupdf.Page") -> List["pymupdf.Rect"]:
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is not None:
            rects.append(pymupdf.Rect(r))
    for info in page.get_image_info():
        rects.append(pymupdf.Rect(info["bbox"]))
    return rects


def rect_tuple(r: "pymupdf.Rect") -> Tuple[float, float, float, float]:
    return (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))


@dataclass(frozen=True)
class Heading:
    x0: float
    y0: float
    y1: float
    size: float
    text: str


def page_headings(page: "pymupdf.Page", min_size: float = 10.9) -> List[Heading]:
    """Bold display-size text lines, i.e. section headings (not margin section numbers)."""
    found: List[Heading] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            size = max(s["size"] for s in spans)
            if size < min_size or "Bold" not in spans[0].get("font", ""):
                continue
            # Skip rotated margin text.
            if abs(line.get("dir", (1, 0))[0]) < 0.9:
                continue
            text = " ".join("".join(s["text"] for s in spans).split())
            if not text or re.fullmatch(r"[\d.]+", text):
                continue
            x0, y0, _, y1 = line["bbox"]
            found.append(Heading(x0, y0, y1, size, text))
    found.sort(key=lambda h: (h.y0, h.x0))
    # Join headings wrapped over consecutive lines at the same indent.
    merged: List[Heading] = []
    for h in found:
        if merged and abs(merged[-1].x0 - h.x0) < 2 and 0 <= h.y0 - merged[-1].y1 < 6 and merged[-1].size == h.size:
            prev = merged[-1]
            merged[-1] = Heading(prev.x0, prev.y0, h.y1, prev.size, f"{prev.text} {h.text}")
        else:
            merged.append(h)
    return merged


def save_crop(page: "pymupdf.Page", rect: "pymupdf.Rect", path, dpi: int = 150, min_ink: float = 0.004):
    """Render a page region to PNG. Returns (sha256, ink_ratio) or None when the crop is blank."""
    import hashlib

    rect = rect & page.rect
    if rect.is_empty or rect.width < 12 or rect.height < 12:
        return None
    pix = page.get_pixmap(clip=rect, dpi=dpi, alpha=False)
    ratio = ink_ratio(pix)
    if ratio < min_ink:
        return None
    data = pix.tobytes("png")
    with open(path, "wb") as fh:
        fh.write(data)
    return hashlib.sha256(data).hexdigest(), ratio
