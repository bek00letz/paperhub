"""Geometry, typography, and 16-level grayscale styling for PaperHub.

Supports high-DPI consumer e-readers (Onyx Boox, Kindle Paperwhite, Kobo,
reMarkable) with 300 PPI Carta screens and true 4-bit (16-level) grayscale
rendering, concentric geometry, and tactile ambient shadows.
"""
import io
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
    # TRMNL 7.5" (120 PPI) - Low-power ambient e-ink dashboard
    "trmnl_og": {
        "id": "trmnl_og",
        "name": "TRMNL 7.5\" (800×480)",
        "category": "ereader",
        "w": 800,
        "h": 480,
        "ppi": 120,
        "diagonal_in": 7.5,
        "mm_w": 163.2,
        "mm_h": 97.9,
        "margin": 32,
        "touch": False,
        "edge_nav_ratio": 0.0,
    },
    "trmnl_x": {
        "id": "trmnl_x",
        "name": "TRMNL X 10.3\" (1872×1404)",
        "category": "tablet",
        "w": 1872,
        "h": 1404,
        "ppi": 227,
        "diagonal_in": 10.3,
        "mm_w": 209.7,
        "mm_h": 157.2,
        "margin": 64,
        "touch": False,
        "edge_nav_ratio": 0.0,
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
        "trmnl": "trmnl_og",
        "trmnl_og": "trmnl_og",
        "trmnl_x": "trmnl_x",
        "crowpanel": "crowpanel_579",
    }
    target = alias_map.get(k)
    if target and target in DISPLAYS:
        return DISPLAYS[target]
    # Custom Canvas profile
    if k == "custom" or (isinstance(key, dict) and ("w" in key or "custom_w" in key)):
        custom_spec = key if isinstance(key, dict) else {}
        w = int(custom_spec.get("w") or custom_spec.get("custom_w") or 1200)
        h = int(custom_spec.get("h") or custom_spec.get("custom_h") or 820)
        ppi = int(custom_spec.get("ppi") or custom_spec.get("custom_ppi") or 200)
        margin = int(custom_spec.get("margin") or custom_spec.get("custom_margin") or 40)
        ratio = float(custom_spec.get("edge_nav_ratio") or custom_spec.get("custom_edge_nav_ratio") or 0.15)
        return {
            "id": "custom",
            "name": f"Custom Canvas ({w}×{h})",
            "category": "custom",
            "w": w,
            "h": h,
            "ppi": ppi,
            "diagonal_in": round(((w / ppi)**2 + (h / ppi)**2)**0.5, 1) if ppi > 0 else 7.0,
            "mm_w": round(w / ppi * 25.4, 1) if ppi > 0 else 100.0,
            "mm_h": round(h / ppi * 25.4, 1) if ppi > 0 else 100.0,
            "margin": margin,
            "touch": True,
            "edge_nav_ratio": ratio,
        }

    return DISPLAYS[DEFAULT_DISPLAY]


# Comprehensive Dynamic Icon Pairs for active vs inactive entity states
DYNAMIC_ICON_PAIRS = {
    # Lights
    "mdi:lightbulb": "mdi:lightbulb-outline",
    "mdi:lightbulb-on": "mdi:lightbulb-outline",
    "mdi:lightbulb-on-outline": "mdi:lightbulb-outline",
    "mdi:lamp": "mdi:lamp-outline",
    "mdi:ceiling-light": "mdi:ceiling-light-outline",
    "mdi:floor-lamp": "mdi:floor-lamp-outline",
    "mdi:wall-sconce": "mdi:wall-sconce-outline",
    "mdi:led-strip": "mdi:led-strip-variant",
    "mdi:chandelier": "mdi:chandelier",
    # Switches, Sockets & Power
    "mdi:power-socket-eu": "mdi:power-socket-eu",
    "mdi:power-socket-us": "mdi:power-socket-us",
    "mdi:power-socket-uk": "mdi:power-socket-uk",
    "mdi:power-plug": "mdi:power-plug-off",
    "mdi:power": "mdi:power-off",
    "mdi:toggle-switch": "mdi:toggle-switch-off",
    "mdi:lightning-bolt": "mdi:lightning-bolt-outline",
    "mdi:flash": "mdi:flash-outline",
    # Climate, Heating & Fans
    "mdi:thermostat": "mdi:thermostat-box",
    "mdi:radiator": "mdi:radiator-off",
    "mdi:fire": "mdi:fire-off",
    "mdi:snowflake": "mdi:snowflake-off",
    "mdi:hvac": "mdi:hvac-off",
    "mdi:fan": "mdi:fan-off",
    "mdi:air-conditioner": "mdi:air-conditioner-off",
    "mdi:water-boiler": "mdi:water-boiler-off",
    "mdi:heat-wave": "mdi:radiator-off",
    # Doors, Windows & Locks
    "mdi:door-open": "mdi:door-closed",
    "mdi:door": "mdi:door-closed",
    "mdi:lock-open": "mdi:lock",
    "mdi:lock": "mdi:lock-open",
    "mdi:window-open": "mdi:window-closed",
    "mdi:window-shutter-open": "mdi:window-shutter",
    "mdi:garage-open": "mdi:garage",
    "mdi:gate-open": "mdi:gate",
    "mdi:shield-check": "mdi:shield-off",
    "mdi:motion-sensor": "mdi:motion-sensor-off",
    "mdi:cctv": "mdi:cctv-off",
    # Media & Sound
    "mdi:speaker": "mdi:speaker-off",
    "mdi:volume-high": "mdi:volume-off",
    "mdi:volume-medium": "mdi:volume-off",
    "mdi:television": "mdi:television-off",
    "mdi:play-circle": "mdi:pause-circle",
    "mdi:music": "mdi:music-off",
    # Network & Appliances
    "mdi:router-wireless": "mdi:router-wireless-off",
    "mdi:wifi": "mdi:wifi-off",
    "mdi:washing-machine": "mdi:washing-machine-off",
    "mdi:coffee-maker": "mdi:coffee-maker-outline",
}


def get_dynamic_off_icon(active_icon: str, domain: str = "") -> str:
    """Resolve the appropriate inactive/off MDI icon glyph."""
    if not active_icon:
        active_icon = "mdi:power"
    clean = str(active_icon).strip()
    if clean in DYNAMIC_ICON_PAIRS:
        return DYNAMIC_ICON_PAIRS[clean]

    if clean.endswith("-outline") or clean.endswith("-off"):
        return clean
    if clean.endswith("-open"):
        return clean[:-5] + "-closed"
    if domain == "light":
        return clean + "-outline"
    if domain in ("switch", "fan"):
        return clean + "-off"

    return clean + "-outline"


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


def best_font_for_text(text: str, size: int, bold: bool = True, family: str = "lato"):
    """Select the best font for the given text with multilingual fallback.
    
    If text contains characters outside Latin-1 (e.g. Cyrillic, Greek, Ukrainian,
    or special symbols/arrows like →, ★, ●), automatically falls back to DejaVuSans
    which contains over 6,200 glyphs, preventing square missing glyph boxes (□).
    """
    s = str(text or "")
    if any(ord(c) >= 256 for c in s):
        return font(size, bold=bold, family="dejavu")
    return font(size, bold=bold, family=family)


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


def to_1bit_bmp(img):
    """Convert image to 1-bit monochrome BMP bytes for ESP32/TRMNL direct line streaming.
    
    TRMNL and low-memory microcontrollers render 1-bit BMP with zero decompression overhead.
    Uses Floyd-Steinberg dithering on photographic/gradient content or clean thresholding.
    """
    mono = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG if img.mode == "L" else Image.Dither.NONE)
    buf = io.BytesIO()
    mono.save(buf, format="BMP")
    return buf.getvalue()


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
    if len(box) == 2 and isinstance(box[0], (tuple, list)):
        (x0, y0), (x1, y1) = box
    elif len(box) == 4:
        x0, y0, x1, y1 = box
    else:
        raise ValueError(f"Invalid bounding box format: {box!r}")

    if x1 <= x0 or y1 <= y0:
        return

    radius = max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2))

    if shadow and (x1 - x0) > 6 and (y1 - y0) > 6:
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
    if bx1 <= bx0 or by1 <= by0:
        return
    r_inner = min(r_inner, (bx1 - bx0) // 2, (by1 - by0) // 2)
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
