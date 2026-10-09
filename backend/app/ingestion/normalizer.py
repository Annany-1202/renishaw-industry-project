"""Normalisation of catalogue values into canonical forms.

Original strings are never overwritten: extractors keep them in
`raw_attributes` and store the outputs of these functions alongside.
"""
import re
from typing import Any, List, Optional, Tuple

MM_PER_INCH = 25.4

EMPTY_MARKERS = {"", "-", "–", "—", "n/a", "na", "none"}

# Canonical material name -> patterns (checked in order; first match wins).
_MATERIAL_PATTERNS: List[Tuple[str, str]] = [
    ("Ruby", r"\bruby\b"),
    ("Silicon nitride", r"\bsilicon\s+nitride\b|\bsi3n4\b"),
    ("Zirconia", r"\bzirconi(a|um)\b|\bzro2\b"),
    ("Tungsten carbide", r"\btungsten\s+carb\w*\b|\bcarbide\b|\btc\b"),
    ("Carbon fibre", r"\bcarbon\s+fib(re|er)\b|\brenishaw\s+gf\b|\bcf\b"),
    ("Ceramic", r"\bceramic\b|\balumina\b"),
    ("Stainless steel", r"\bstainless(\s+steel)?\b"),
    ("Silver steel", r"\bsilver\s+steel\b"),
    ("Carbon steel", r"\bcarbon\s+steel\b"),
    ("Titanium", r"\btitanium\b"),
    ("Aluminium", r"\balumin(i)?um\b"),
    ("Steel", r"\bsteel\b"),
]

BALL_MATERIALS = ["Ruby", "Silicon nitride", "Zirconia", "Tungsten carbide", "Ceramic", "Silver steel", "Steel"]
STEM_MATERIALS = [
    "Tungsten carbide", "Stainless steel", "Ceramic", "Carbon fibre", "Titanium", "Aluminium", "Silver steel", "Steel",
]


def is_empty(value: Any) -> bool:
    return value is None or str(value).strip().lower() in EMPTY_MARKERS


def parse_number(value: Any) -> Optional[float]:
    """Parse the leading metric number of a catalogue cell.

    Handles '1. 0' (typeset with a space), '10.0 (0.40)' (mm with inches in
    brackets) and 'Ø30.0'. Returns None for empty markers and non-numeric text.
    """
    if is_empty(value):
        return None
    s = str(value).strip()
    s = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", s)
    s = s.lstrip("Øø⌀ ")
    m = re.match(r"^(\d+(?:\.\d+)?)(?![\d/])", s)
    if not m:
        return None
    rest = s[m.end():].strip()
    # Reject things like '1/8 in.' or '1 in.' where the number is not millimetres.
    if rest and not rest.startswith("(") and not re.match(r"^(mm|g|°)\b", rest):
        return None
    return float(m.group(1))


def parse_pair(value: Any) -> Tuple[Optional[float], Optional[float]]:
    """Parse 'a/b' cells such as ML1/ML '5.0/10.0'. A single value fills the second slot."""
    if is_empty(value):
        return None, None
    s = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", str(value).strip())
    if "/" in s:
        first, _, second = s.partition("/")
        return parse_number(first), parse_number(second)
    return None, parse_number(s)


def inches_to_mm(inches: float) -> float:
    return inches * MM_PER_INCH


def normalize_thread(value: Any) -> Optional[str]:
    if is_empty(value):
        return None
    m = re.search(r"\bM(\d{1,2})\b", str(value), re.IGNORECASE)
    return f"M{int(m.group(1))}" if m else None


def all_threads(value: Any) -> List[str]:
    if is_empty(value):
        return []
    found = []
    for m in re.finditer(r"\bM(\d{1,2})\b", str(value), re.IGNORECASE):
        t = f"M{int(m.group(1))}"
        if t not in found:
            found.append(t)
    return found


def normalize_material(value: Any) -> Optional[str]:
    """Map catalogue material text to a canonical name; unknown text is returned title-cased."""
    if is_empty(value):
        return None
    s = str(value).strip().lower()
    # 'Carbon steel' must not be read as carbon fibre and 'silver steel' not as stainless.
    for name in ("Silver steel", "Carbon steel"):
        if re.search(dict(_MATERIAL_PATTERNS)[name], s):
            return name
    for name, pattern in _MATERIAL_PATTERNS:
        if re.search(pattern, s):
            return name
    return str(value).strip().capitalize()


def normalize_part_number(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper().rstrip("*")


# --- Category / type classification ---------------------------------------------------------

CATEGORIES = ["stylus", "extension", "adaptor", "knuckle", "cube", "holder", "kit", "tool", "accessory"]

# H-1000-3200 part listing "Component" column -> (category, type)
H1000_COMPONENT_MAP = {
    "ball stylus": ("stylus", "straight"),
    "disc": ("stylus", "disc"),
    "disc stylus": ("stylus", "disc"),
    "star": ("stylus", "star"),
    "hemispherical": ("stylus", "hemispherical"),
    "cone stylus": ("stylus", "cone"),
    "cranked stylus": ("stylus", "cranked"),
    "spherically ended cylinder": ("stylus", "cylinder"),
    "cylinder": ("stylus", "cylinder"),
    "pointer": ("stylus", "pointer"),
    "tool datuming": ("stylus", "tool_datuming"),
    "tool setter": ("stylus", "tool_setting"),
    "extension": ("extension", "extension"),
    "cranked extension": ("extension", "cranked_extension"),
    "adaptor": ("adaptor", "adaptor"),
    "star centre": ("accessory", "star_centre"),
    "crash protection device": ("accessory", "crash_protection"),
}


def classify_h1000(component: str, description: str) -> Tuple[str, str]:
    comp = re.sub(r"\s*×\s*\d+$", "", (component or "").strip().lower())
    if comp in H1000_COMPONENT_MAP:
        return H1000_COMPONENT_MAP[comp]
    desc = (description or "").lower()
    if re.search(r"\bkit\b", desc):
        return "kit", "kit"
    if "datum" in desc and ("ball" in desc or "sphere" in desc):
        return "accessory", "datum_ball"
    if "cube" in desc:
        return "cube", "cube"
    if "knuckle" in desc:
        return "knuckle", "knuckle"
    if re.search(r"\badapt[oe]r\b", desc):
        return "adaptor", "adaptor"
    if re.search(r"\b(tool|spanner|key|crank)\b", desc):
        return "tool", "tool"
    return "accessory", "accessory"


_ZEISS_HEAD_NOUNS = [
    # (pattern, category, type) - the LAST match inside the head phrase is the head noun.
    (r"\bstyl(i|us)\b", "stylus", "straight"),
    (r"\bpointer\b", "stylus", "pointer"),
    (r"\bextensions?\b", "extension", "extension"),
    (r"\badaptor plate\b", "adaptor", "adaptor_plate"),
    (r"\badaptor\b", "adaptor", "adaptor"),
    (r"\bknuckle\b", "knuckle", "knuckle"),
    (r"\bcube\b", "cube", "cube"),
    (r"\bholder\b", "holder", "holder"),
    (r"\btool\b", "tool", "tool"),
    (r"\b(spanner|keys?)\b", "tool", "tool"),
    (r"\b(washer|pin|screw|gauge|sphere|magnet base|angle|disc)\b", "accessory", None),
]


def classify_zeiss_section(title: str, has_tip: bool) -> Tuple[str, str]:
    """Classify a ZEISS catalogue section from its heading.

    English compounds put the head noun last ('Cube extension' is an extension)
    and qualifiers after 'for' / 'with' ('Extension for adaptor plate' is an
    extension), so the head noun is the last known noun before 'for' / 'with'.
    `has_tip` is True when the section table lists a tip diameter with a stem.
    """
    t = " ".join((title or "").lower().split())
    head = re.split(r"\s+(?:for|with)\s+|,|\(", t, maxsplit=1)[0]
    best = None
    for pattern, category, stype in _ZEISS_HEAD_NOUNS:
        for m in re.finditer(pattern, head):
            if best is None or m.end() > best[0] or (m.end() == best[0] and m.start() < best[1]):
                best = (m.end(), m.start(), category, stype, m.group(0))
    if t.startswith("cube star") or (has_tip and best and best[2] in ("cube",)):
        return "stylus", "star"
    if best is None:
        return ("stylus", "straight") if has_tip else ("accessory", "accessory")
    _, _, category, stype, word = best
    if category == "stylus" and stype == "straight":
        if re.match(r"star styl", head):
            return "stylus", "star"
        if "disc" in head:
            return "stylus", "disc"
        if "cylinder" in head:
            return "stylus", "cylinder"
        if "thread measurement" in t:
            return "stylus", "thread_measurement"
        if "swivel" in t:
            return "stylus", "swivel"
        return "stylus", "straight"
    if category == "accessory":
        return "accessory", re.sub(r"[^a-z0-9]+", "_", head).strip("_")[:40] or "accessory"
    return category, stype
