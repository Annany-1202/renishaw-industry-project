"""Domain vocabulary and approved deterministic rules used by query interpretation.

Everything here is data, kept apart from the parsing logic. The probe table is
an *approved deterministic compatibility rule*: each entry quotes the page of
H-1000-3200 that states which thread the probe uses.
"""
import re
from typing import Dict, List, Set, Tuple

# probe model -> [(thread, source)]
PROBE_THREADS: Dict[str, List[Tuple[str, str]]] = {}


def _probes(thread: str, source: str, names: str) -> None:
    for name in names.split():
        PROBE_THREADS.setdefault(name.upper(), []).append((thread, source))


_probes("M2", "H-1000-3200 p.19", "TP2 TP20 TP200 REVO")
_probes("M3", "H-1000-3200 p.35", "TP1 TP6 REVO SP25M")
_probes("M4", "H-1000-3200 p.43",
        "TP1 TP7 TP7M SP600 MP11 LP2 TS27R OMP40-2 OMP400 RMP60 RP3 RMP40 RLP40 OLP40 OMP60 OTS RMP600 "
        "MP250 HPRA HPPA HPMA OSP60 PRIMO")
_probes("M5", "H-1000-3200 p.61", "SP80")

PROBE_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(p) for p in PROBE_THREADS), key=len, reverse=True)) + r")\b", re.IGNORECASE
)

# Material synonyms -> canonical name. Order matters (longer phrases first).
BALL_MATERIAL_WORDS: List[Tuple[str, str]] = [
    (r"silicon\s+nitride|si3n4", "Silicon nitride"),
    (r"zirconi(?:a|um)(?:\s+oxide)?|zro2", "Zirconia"),
    (r"rub(?:y|ies)", "Ruby"),
]
STEM_MATERIAL_WORDS: List[Tuple[str, str]] = [
    (r"tungsten\s+carbide|carbide|\btc\b", "Tungsten carbide"),
    (r"carbon[\s-]+fib(?:re|er)|\bcf\b|renishaw\s+gf", "Carbon fibre"),
    (r"stainless(?:\s+steel)?", "Stainless steel"),
    (r"silver\s+steel", "Silver steel"),
    (r"ceramic", "Ceramic"),
    (r"titanium", "Titanium"),
    (r"alumini?um", "Aluminium"),
    (r"steel", "Stainless steel"),
]
# Materials that can be either a ball/tip or a stem material depending on the noun that follows.
EITHER_MATERIALS = {"Tungsten carbide", "Ceramic", "Stainless steel", "Silver steel"}

BALL_NOUNS = r"(?:ball|balls|tip|tips|sphere|bead|ball\s+tip|stylus\s+ball)"
STEM_NOUNS = r"(?:stem|stems|shaft|shank|rod|body|stemmed)"

# Product nouns -> (category, stylus_type). Checked in order; first hit wins for the category.
CATEGORY_NOUNS: List[Tuple[str, str, str]] = [
    (r"adapt[oe]r\s+plates?", "adaptor", "adaptor_plate"),
    (r"datum\s+(?:ball|sphere)s?|calibration\s+(?:ball|sphere)s?", "accessory", "datum_ball"),
    (r"extensions?(?:\s+bars?)?", "extension", None),
    (r"adapt[oe]rs?", "adaptor", None),
    (r"knuckles?", "knuckle", None),
    (r"cubes?", "cube", None),
    (r"holders?", "holder", None),
    (r"kits?", "kit", None),
    (r"(?:stylus\s+)?tools?|spanners?|allen\s+keys?", "tool", None),
    (r"washers?|screws?|crash\s+protection(?:\s+devices?)?|star\s+centres?", "accessory", None),
    (r"styl(?:us|i|uses)|probe\s+tips?", "stylus", None),
    # Last, so 'styli and accessories' stays a stylus request.
    (r"accessor(?:y|ies)", "accessory", None),
]
# Answer options for "which kind of product?"; each one parses back to its category through CATEGORY_NOUNS.
CATEGORY_OPTION_LABELS: Dict[str, str] = {
    "stylus": "Stylus", "extension": "Stylus extension", "adaptor": "Thread adaptor", "knuckle": "Knuckle",
    "cube": "Stylus cube", "holder": "Stylus holder", "kit": "Stylus kit", "tool": "Stylus tool",
    "accessory": "Accessory",
}
# Stylus type words (only applied when the category is stylus or unstated).
STYLUS_TYPE_WORDS: List[Tuple[str, str]] = [
    (r"star", "star"), (r"dis[ck]s?", "disc"), (r"cylind(?:er|rical)", "cylinder"), (r"pointer", "pointer"),
    (r"hemispherical", "hemispherical"), (r"cone", "cone"), (r"cranked", "cranked"),
    (r"tool\s+(?:setting|datuming)", "tool_datuming"), (r"swivel(?:ling)?", "swivel"), (r"straight", "straight"),
]
# Words that show the request is about measurement hardware even without a product noun.
DOMAIN_HINTS = (r"probe|probes|probing|cmms?|metrology|renishaw|zeiss|styli|stylus|catalogues?|catalogs?|"
                r"coordinate\s+measuring|touch[\s-]trigger")

# Product nouns that are never in these catalogues. A hit rejects the request (FR-05).
FOREIGN_TERMS = [
    "laptop", "laptops", "notebook", "computer", "pc", "phone", "smartphone", "iphone", "ipad", "tablet",
    "bicycle", "bike", "motorbike", "car", "cars", "automobile", "truck", "tyre", "tire", "shoe", "shoes",
    "clothing", "shirt", "pizza", "burger", "coffee", "espresso", "desk", "chair", "sofa", "tv", "television",
    "refrigerator", "fridge", "oven", "microwave", "cooking", "kitchen", "appliance", "gaming", "keyboard",
    "monitor", "headphones", "earbuds", "camera", "drone", "watch", "guitar", "piano", "book", "novel",
    "toothbrush", "shampoo", "furniture", "bed", "mattress", "game", "console", "printer", "router",
    "necklace", "ring", "jewellery", "jewelry", "earrings", "perfume", "toy", "doll", "hotel", "flight",
]

HARD_CUES = (
    r"\bmust\b|\bexact(?:ly)?\b|\bonly\b|\brequired?\b|\bmandatory\b|\bnon[\s-]?negotiable\b|\bstrictly\b|"
    r"\bno\s+(?:other|alternatives?|substitutes?)\b|\bhas\s+to\b|\bneeds?\s+to\s+be\b|\bessential\b"
)
FLEXIBLE_CUES = r"\bprefer(?:ably|red)?\b|\bideally\b|\bif\s+possible\b|\bapprox(?:imately|\.)?\b|\baround\b|\babout\b|\broughly\b|\bor\s+similar\b|\bflexible\b|~"

QUALITATIVE = {
    "long": "overall_length_mm", "longer": "overall_length_mm", "short": "overall_length_mm",
    "shorter": "overall_length_mm", "small": "ball_diameter_mm", "smaller": "ball_diameter_mm",
    "tiny": "ball_diameter_mm", "large": "ball_diameter_mm", "big": "ball_diameter_mm",
    "larger": "ball_diameter_mm", "thin": "stem_diameter_mm", "thick": "stem_diameter_mm",
    "micro": "ball_diameter_mm", "mini": "ball_diameter_mm",
}

STOPWORDS: Set[str] = set("""
a an the and or but with without for of to in on at by from is are be been it its this that these those i we you me my
our your need needs needed want wants looking look find finding search show give get please can could would should
have has had do does which what who where when how some any all one two also as so if then than not no yes there here
into onto over under about around approx approximately roughly ideally preferably prefer preferred possible similar
must exact exactly only require required requires mandatory strictly essential non negotiable other alternatives
alternative substitute substitutes take priority both same time
mm millimeter millimeters millimetre millimetres cm inch inches in dia diameter diameters size sized length lengths
long overall total effective working ewl thread threaded threads mount mounting mounted interface fit fits fitting
ball balls tip tips sphere bead stem stems shaft shank rod body material materials made type kind
part number numbers no pn model new use used using measuring measurement measure application applications
compatible compatibility suitable machine system systems range ranges piece pieces pack tall wide high low
""".split())
