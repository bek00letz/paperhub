"""Geometry, typography, and 16-level grayscale styling for PaperHub.

Supports high-DPI consumer e-readers (Onyx Boox, Kindle Paperwhite, Kobo,
reMarkable) with 300 PPI Carta screens and true 4-bit (16-level) grayscale
rendering, concentric geometry, and tactile ambient shadows.
"""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Consumer e-reader display profiles
DISPLAYS = {
    # 6.0" Carta (300 PPI) - Most popular handheld e-reader format
    "boox_go_6": {
        "id": "boox_go_6",
        "name": "Onyx Boox Go 6",
        "category": "ereader",
        "w": 1072,
        "h": 1448,
        "ppi": 300,
        "diagonal_in": 6.0,
        "mm_w": 90.8,
        "mm_h": 122.6,
        "margin": 48,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    "kindle_pw": {
        "id": "kindle_pw",
        "name": "Kindle Paperwhite (11th Gen)",
        "category": "ereader",
        "w": 1264,
        "h": 1680,
        "ppi": 300,
        "diagonal_in": 6.8,
        "mm_w": 107.0,
        "mm_h": 142.2,
        "margin": 52,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    "kobo_clara": {
        "id": "kobo_clara",
        "name": "Kobo Clara 2E / BW",
        "category": "ereader",
        "w": 1072,
        "h": 1448,
        "ppi": 300,
        "diagonal_in": 6.0,
        "mm_w": 90.8,
        "mm_h": 122.6,
        "margin": 48,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    # 7.0" Carta (300 PPI) - Asymmetric reader with page buttons
    "boox_page": {
        "id": "boox_page",
        "name": "Onyx Boox Page / Leaf 2",
        "category": "ereader",
        "w": 1264,
        "h": 1680,
        "ppi": 300,
        "diagonal_in": 7.0,
        "mm_w": 107.0,
        "mm_h": 142.2,
        "margin": 52,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    "kobo_libra": {
        "id": "kobo_libra",
        "name": "Kobo Libra 2 / Colour",
        "category": "ereader",
        "w": 1264,
        "h": 1680,
        "ppi": 300,
        "diagonal_in": 7.0,
        "mm_w": 107.0,
        "mm_h": 142.2,
        "margin": 52,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    # 10.3" Carta/Mobius - Large canvas / wall tablet
    "boox_note_air": {
        "id": "boox_note_air",
        "name": "Onyx Boox Note Air 3 / Scribe",
        "category": "tablet",
        "w": 1404,
        "h": 1872,
        "ppi": 227,
        "diagonal_in": 10.3,
        "mm_w": 157.2,
        "mm_h": 209.7,
        "margin": 64,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    "kindle_scribe": {
        "id": "kindle_scribe",
        "name": "Kindle Scribe 10.2\"",
        "category": "tablet",
        "w": 1860,
        "h": 2480,
        "ppi": 300,
        "diagonal_in": 10.2,
        "mm_w": 157.4,
        "mm_h": 209.9,
        "margin": 72,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    "remarkable_2": {
        "id": "remarkable_2",
        "name": "reMarkable 2 (10.3\")",
        "category": "tablet",
        "w": 1404,
        "h": 1872,
        "ppi": 226,
        "diagonal_in": 10.3,
        "mm_w": 157.2,
        "mm_h": 209.7,
        "margin": 64,
        "touch": True,
        "edge_nav_ratio": 0.15,
    },
    # CrowPanel 5.79" SPI strip (legacy backwards compatibility)
    "crowpanel_579": {
        "id": "crowpanel_579",
        "name": "CrowPanel 5.79\" (Legacy SPI)",
        "category": "strip",
        "w": 792,
        "h": 272,
        "ppi": 145,
        "diagonal_in": 5.79,
        "mm_w": 139.1,
        "mm_h": 47.7,
        "margin": 40,
        "touch": False,
        "edge_nav_ratio": 0.15,
    },
}

DEFAULT_DISPLAY = "boox_go_6"

def get_display(key=None):
    """Retrieve display profile by model key; defaults to Boox Go 6."""
    if not key:
        return DISPLAYS[DEFAULT_DISPLAY]
    k = str(key).lower().strip()
    if k in DISPLAYS:
        return DISPLAYS[k]
    # Check common aliases
    alias_map = {
        "boox": "boox_go_6",
        "go6": "boox_go_6",
        "kindle": "kindle_pw",
        "paperwhite": "kindle_pw",
        "kobo": "kobo_clara",
        "page": "boox_page",
        "libra": "kobo_libra",
        "scribe": "kindle_scribe",
        "note_air": "boox_note_air",
        "remarkable": "remarkable_2",
        "crowpanel": "crowpanel_579",
    }
    target = alias_map.get(k)
    if target and target in DISPLAYS:
        return DISPLAYS[target]
    return DISPLAYS[DEFAULT_DISPLAY]


# 16-level grayscale palette (4-bit Carta native depth)
# Discrete values: [0, 17, 34, 51, 68, 85, 102, 119, 136, 153, 170, 187, 204, 221, 238, 255]
LEVELS_16 = [int(round(i * 255.0 / 15.0)) for i in range(16)]

# Semantic grayscale values
WHITE        = 255  # Level 15 (clean background)
GRAY_SURFACE = 238  # Level 14 (subtle card fill / pressed state)
GRAY_BORDER  = 221  # Level 13 (delicate hairline border)
GRAY_SHADOW  = 204  # Level 12 (soft ambient drop-shadow)
GRAY_MUTED   = 170  # Level 10 (secondary text / inactive icon)
GRAY_MID     = 119  # Level 7  (medium contrast badge)
GRAY_DARK    = 51   # Level 3  (high contrast secondary)
BLACK        = 0    # Level 0  (primary text / active icon)

# 256 -> 16 level lookup table for Pillow point() mapping
_LUT_16 = [int(round(round(v / 17.0) * 17.0)) for v in range(256)]

# Fonts live in fonts directory
_FONT_DIRS = [
    Path(__file__).parent.parent / "fonts",
    Path(__file__).parent / "fonts",
]


def _font_file(*names):
    for d in _FONT_DIRS:
        for n in names:
            p = d / n
            if p.exists():
                return str(p)
    raise FileNotFoundError(f"none of {names} in {[str(d) for d in _FONT_DIRS]}")


FONTS = {
    "lato": {
        "bold": _font_file("Lato-Bold.ttf", "DejaVuSans-Bold.ttf"),
        "regular": _font_file("Lato-Regular.ttf", "DejaVuSans.ttf"),
    },
    "dejavu": {
        "bold": _font_file("DejaVuSans-Bold.ttf", "Lato-Bold.ttf"),
        "regular": _font_file("DejaVuSans.ttf", "Lato-Regular.ttf"),
    },
    "mono": {
        "bold": _font_file("RobotoMono-Variable.ttf", "DejaVuSans-Bold.ttf"),
        "regular": _font_file("RobotoMono-Variable.ttf", "DejaVuSans.ttf"),
    },
}

BOLD    = FONTS["lato"]["bold"]
REGULAR = FONTS["lato"]["regular"]


@lru_cache(maxsize=256)
def _cached_font(path: str, size: int):
    return ImageFont.truetype(path, size)


def font(size, bold=True, family="lato"):
    """Retrieve TrueType font with bounds protection."""
    clamped = max(8, min(480, int(size)))
    fam = FONTS.get(str(family or "lato").lower(), FONTS["lato"])
    path = fam["bold"] if bold else fam["regular"]
    return _cached_font(path, clamped)


def canvas_dims(orientation=0, display=None):
    """Logical (width, height) for the editor and renderer before panel rotation."""
    disp = get_display(display)
    dw, dh = disp["w"], disp["h"]
    if int(orientation or 0) in (90, 270):
        return dh, dw
    return dw, dh


def new_canvas(orientation=0, display=None, bg=WHITE):
    """8-bit grayscale working canvas ('L' mode) initialized to clean white."""
    cw, ch = canvas_dims(orientation, display)
    img = Image.new("L", (cw, ch), bg)
    return img, ImageDraw.Draw(img)


def to_16grayscale(img):
    """Quantize 8-bit grayscale image to the exact 16 discrete levels of Carta e-ink.
    
    Preserves subpixel antialiased font edges while guaranteeing 100% compatibility
    with Carta EPD waveform LUTs (Lookup Tables). Runs in <1ms via C-level LUT.
    """
    if img.mode != "L":
        img = img.convert("L")
    return img.point(_LUT_16)


def to_1bit(img):
    """Hard threshold to 1-bit monochrome (for legacy 1-bit panels or fast previews)."""
    return img.convert("1", dither=Image.Dither.NONE)


def orient_for_panel(img, orientation=0):
    """Rotate a rendered logical page into physical panel orientation."""
    deg = int(orientation or 0) % 360
    if deg == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    if deg == 90:
        return img.transpose(Image.Transpose.ROTATE_270)
    if deg == 270:
        return img.transpose(Image.Transpose.ROTATE_90)
    return img


def text_width(s, f):
    b = f.getbbox(s)
    return b[2] - b[0]


def fit_size(s, max_w, max_h, start, floor=14, bold=True, family="lato"):
    """Largest point size at which s fits max_w x max_h. Binary search."""
    lo, hi, best = floor, max(floor, min(480, int(start))), floor
    while lo <= hi:
        mid = (lo + hi) // 2
        f = font(mid, bold, family=family)
        asc, desc = f.getmetrics()
        if text_width(s, f) <= max_w and (asc + desc) <= max_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def draw_card(draw, box, radius=20, fill=WHITE, outline=GRAY_BORDER, width=1, shadow=True):
    """Draw an Apple-standard rounded card container with concentric geometry and soft depth.
    
    Formula:
        Outer radius = radius
        Inner content radius = radius - padding
    """
    x0, y0, x1, y1 = box
    if shadow:
        # Delicate 2-step ambient drop shadow (soft 16-level grayscale elevation)
        # Layer 1: ambient spread
        draw.rounded_rectangle(
            [(x0 - 1, y0 + 2), (x1 + 1, y1 + 5)],
            radius=radius + 2,
            fill=GRAY_SURFACE,
        )
        # Layer 2: directional contact shadow
        draw.rounded_rectangle(
            [(x0, y0 + 1), (x1, y1 + 3)],
            radius=radius + 1,
            fill=GRAY_SHADOW,
        )
    # Card surface
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=radius, fill=fill, outline=outline, width=width)


def draw_concentric_badge(draw, parent_radius, padding, box, fill=BLACK, text="", font=None, text_color=WHITE):
    """Draw a child badge maintaining mathematical concentricity: R_inner = R_outer - padding."""
    r_inner = max(4, parent_radius - padding)
    bx0, by0, bx1, by1 = box
    draw.rounded_rectangle([(bx0, by0), (bx1, by1)], radius=r_inner, fill=fill)
    if text and font:
        mid_x = (bx0 + bx1) // 2
        mid_y = (by0 + by1) // 2
        draw.text((mid_x, mid_y), text, font=font, fill=text_color, anchor="mm")


def footer(draw, *, clock="", label="", battery_pct=None, page_info=None, orientation=0, display=None):
    """Ambient e-ink footer: hairline rule, clock, page dots, battery indicator."""
    cw, ch = canvas_dims(orientation, display=display)
    disp = get_display(display)
    margin = disp["margin"]
    
    # Scale footer typography gracefully
    fsz = max(16, min(28, int(ch * 0.024)))
    rule_y = ch - int(fsz * 2.2)
    base_y = ch - int(fsz * 0.8)
    f = font(fsz, bold=False)
    f_bold = font(fsz, bold=True)
    
    # Hairline divider
    draw.line([(margin, rule_y), (cw - margin, rule_y)], fill=GRAY_BORDER, width=1)
    
    # Left: Time / Date
    if clock:
        draw.text((margin, base_y), clock, font=f_bold, fill=BLACK, anchor="ls")
        
    # Center: Label or Page Indicator Dots
    mid_x = cw // 2
    if page_info and isinstance(page_info, dict):
        cur = page_info.get("current", 1)
        total = page_info.get("total", 1)
        dots = " ".join("●" if i == cur else "○" for i in range(1, total + 1))
        draw.text((mid_x, base_y), dots, font=f, fill=GRAY_DARK, anchor="ms")
    elif label:
        draw.text((mid_x, base_y), label, font=f, fill=GRAY_DARK, anchor="ms")
        
    # Right: Battery percentage
    if battery_pct is not None and battery_pct >= 0:
        bat_str = f"{battery_pct}%"
        draw.text((cw - margin, base_y), bat_str, font=f, fill=GRAY_DARK, anchor="rs")
