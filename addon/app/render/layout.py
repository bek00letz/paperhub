"""Data-driven page rendering and server-side hit-testing for PaperHub.

Every element carries its own box (x, y, w, h) in canvas pixels.
Supports 16-level grayscale anti-aliasing, concentric geometry, and
millisecond-fast server-side 2D hit-testing for touch interactions.
"""
import json
import math
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import theme as T
from . import binding
from .binding import template_for

_FONTS = Path(__file__).parent.parent / "fonts"
_MDI_TTF = _FONTS / "mdi.ttf"
_MDI_MAP = _FONTS / "mdi-codepoints.json"

_mdi_codepoints = None


def mm_per_px(display=None):
    disp = T.get_display(display)
    return disp["mm_w"] / disp["w"]


@lru_cache(maxsize=256)
def _mdi_font(size: int):
    clamped = max(8, min(480, int(size)))
    return ImageFont.truetype(str(_MDI_TTF), clamped)


def mdi_codepoint(name):
    """Map 'mdi:washing-machine' (or bare 'washing-machine') to a codepoint."""
    global _mdi_codepoints
    if _mdi_codepoints is None:
        try:
            _mdi_codepoints = json.loads(_MDI_MAP.read_text())
        except Exception:
            _mdi_codepoints = {}
    return _mdi_codepoints.get(str(name).removeprefix("mdi:"))


def draw_cat(draw, x=0, y=0, height=200):
    """Sitting cat in profile, facing right, traced at a nominal 200px tall."""
    dx = x - 96
    dy = y
    scale = max(0.1, min(4.0, height / 200.0))

    def P(pts):
        return [(dx + px * scale, dy + py * scale) for px, py in pts]

    draw.polygon(P([(124, 96), (112, 130), (106, 170), (104, 202),
                    (176, 202), (206, 198), (222, 176), (224, 146),
                    (210, 116), (188, 96)]), fill=T.BLACK)
    draw.ellipse(P([(114, 24), (198, 108)]), fill=T.BLACK)          # head
    draw.polygon(P([(122, 44), (112, 4), (152, 30)]), fill=T.BLACK)  # left ear
    draw.polygon(P([(160, 30), (200, 4), (190, 44)]), fill=T.BLACK)  # right ear
    draw.line(P([(202, 196), (248, 188), (268, 166), (272, 136),
                 (262, 112), (246, 102)]),
              fill=T.BLACK, width=max(3, int(14 * scale)), joint="curve")


CUSTOM_ICONS = {
    "cat-sitting": draw_cat,
}


def _fit_glyph(ch, box_w, box_h, start=240):
    """Largest font size at which the glyph's ink fits the box."""
    lo, hi, best = 8, max(8, min(480, int(start))), 8
    while lo <= hi:
        mid = (lo + hi) // 2
        f = _mdi_font(mid)
        l, t, r, b = f.getbbox(ch)
        if (r - l) <= box_w and (b - t) <= box_h:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _anchor_x(align, x, w):
    return {"left": x, "center": x + w // 2, "right": x + w}.get(align, x)


def _clamp_box(el, default_w=200, default_h=60, display=None):
    cw, ch = T.canvas_dims(0, display)
    x = max(0, min(cw - 1, int(el.get("x", 0))))
    y = max(0, min(ch - 1, int(el.get("y", 0))))
    w = max(1, min(cw - x, int(el.get("w", default_w))))
    h = max(1, min(ch - y, int(el.get("h", default_h))))
    return x, y, w, h


def _draw_icon_glyph(draw, name, cx, cy, size, color=T.BLACK):
    """Draw an MDI icon or custom vector icon centered at (cx, cy)."""
    if not name:
        return
    s = str(name).strip()
    if s in CUSTOM_ICONS:
        CUSTOM_ICONS[s](draw, cx - size // 2, cy - size // 2, height=size)
        return
    cp = mdi_codepoint(s)
    if not cp:
        return
    ch = chr(int(cp, 16) if isinstance(cp, str) and not cp.isdigit() else int(cp))
    f = _mdi_font(size)
    l, t, r, b = f.getbbox(ch)
    draw.text((cx - (r + l) // 2, cy - (b + t) // 2), ch, font=f, fill=color)


def _fit_text(text, max_w, f):
    """Truncate text with ellipsis if exceeding max width."""
    s = str(text or "")
    if T.text_width(s, f) <= max_w:
        return s
    ell = "…"
    while s and T.text_width(s + ell, f) > max_w:
        s = s[:-1]
    return s + ell if s else ""


def _draw_text(img, draw, el, val, metrics=None, *, distance_m=3.0, display=None):
    x, y, w, h = _clamp_box(el, default_w=300, default_h=100, display=display)
    val = str(val or "")
    align = el.get("align", "left")
    bold = bool(el.get("bold", True))
    family = el.get("family", "lato")
    color = T.BLACK if el.get("color") != "muted" else T.GRAY_MUTED

    # Support card background styling
    if el.get("card"):
        T.draw_card(draw, [(x, y), (x + w, y + h)], radius=el.get("radius", 18), shadow=el.get("shadow", True))
        # Inset text inside padding
        pad = el.get("padding", 16)
        x += pad
        y += pad
        w -= pad * 2
        h -= pad * 2

    size = el.get("size")
    if not size:
        size = T.fit_size(val, w, h, start=min(h, 240), floor=12, bold=bold, family=family)
    f = T.best_font_for_text(val, size, bold=bold, family=family)

    tx = _anchor_x(align, x, w)
    anchor_mode = {"left": "lt", "center": "mt", "right": "rt"}.get(align, "lt")
    draw.text((tx, y + (h - size) // 2), val, font=f, fill=color, anchor=anchor_mode)


def _draw_icon(img, draw, el, val="", display=None):
    x, y, w, h = _clamp_box(el, default_w=120, default_h=120, display=display)
    active_icon = el.get("icon") or (val if str(val).startswith("mdi:") else "mdi:power")
    domain = el.get("entity", "").split(".")[0] if el.get("entity") else ""

    state_raw = str(val or el.get("state", "on")).strip().lower()
    is_on = state_raw in ("on", "playing", "open", "active", "home", "unlocked") or (
        state_raw.replace(".", "", 1).isdigit() and float(state_raw) > 0
    )
    if not el.get("entity"):
        name = active_icon
    else:
        off_icon = el.get("icon_off") or T.get_dynamic_off_icon(active_icon, domain)
        name = active_icon if is_on else off_icon

    if not name:
        return
    color = T.BLACK if is_on and el.get("color") != "muted" else T.GRAY_MUTED
    sz = min(w, h)
    _draw_icon_glyph(draw, name, x + w // 2, y + h // 2, sz, color=color)


def _draw_line(img, draw, el, val="", display=None):
    x, y, w, h = _clamp_box(el, default_w=200, default_h=4, display=display)
    color = T.GRAY_BORDER if el.get("subtle", True) else T.BLACK
    thickness = max(1, int(el.get("thickness", 1)))
    draw.rectangle([(x, y), (x + w, y + max(1, thickness))], fill=color)


def _draw_curve(img, draw, el, val="", series=None, display=None):
    x, y, w, h = _clamp_box(el, default_w=300, default_h=120, display=display)
    if not series or len(series) < 2:
        return
    pts = []
    min_v, max_v = min(series), max(series)
    span = max(1e-5, max_v - min_v)
    step = w / max(1, len(series) - 1)
    for i, v in enumerate(series):
        px = x + i * step
        py = y + h - ((v - min_v) / span) * h
        pts.append((px, py))
    draw.line(pts, fill=T.BLACK, width=max(2, int(el.get("width", 2))), joint="curve")


def compute_dynamic_grid_boxes(x, y, w, h, n, cols, rows, gap=16):
    """Compute (cx0, cy0, cw, ch) bounding boxes for n items in cols x rows grid."""
    if n <= 0:
        return []
    total_hgap = (cols - 1) * gap
    total_vgap = (rows - 1) * gap
    cw = max(20, (w - total_hgap) // max(1, cols))
    ch = max(20, (h - total_vgap) // max(1, rows))

    boxes = []
    for i in range(n):
        r = i // cols
        c = i % cols
        bx0 = x + c * (cw + gap)
        by0 = y + r * (ch + gap)
        boxes.append((bx0, by0, cw, ch))
    return boxes


def _compute_grid_dimensions(n, is_wide):
    """Determine optimal (cols, rows) for n items."""
    if n <= 1:
        return 1, 1
    if n == 2:
        return (2, 1) if is_wide else (1, 2)
    if n == 3:
        return (3, 1) if is_wide else (1, 3)
    if n == 4:
        return 2, 2
    if n <= 6:
        return (3, 2) if is_wide else (2, 3)
    if n <= 8:
        return (4, 2) if is_wide else (2, 4)
    # n > 8
    if is_wide:
        rows = 3
        cols = math.ceil(n / rows)
        return cols, rows
    cols = 2
    rows = math.ceil(n / cols)
    return cols, rows


def _draw_dynamic_grid(img, draw, el, vals=None, display=None):
    """Render responsive 2D matrix of interactive entity cards."""
    x, y, w, h = _clamp_box(el, default_w=600, default_h=400, display=display)
    raw_items = el.get("items", [])
    if isinstance(vals, str):
        try:
            parsed = json.loads(vals)
            if isinstance(parsed, list):
                items = parsed
            else:
                items = raw_items
        except Exception:
            items = raw_items
    elif isinstance(vals, list):
        items = vals
    else:
        items = raw_items

    # Filter active items
    active_items = []
    for it in items:
        if isinstance(it, dict):
            active_items.append(it)
        elif isinstance(it, str):
            active_items.append({"entity": it, "name": it.split(".")[-1].replace("_", " ").title(), "state": "on"})

    n = len(active_items)
    if n == 0:
        return

    is_wide = w >= h
    cols, rows = _compute_grid_dimensions(n, is_wide)
    gap = int(el.get("gap", 16 if w >= 800 else 12))
    boxes = compute_dynamic_grid_boxes(x, y, w, h, n, cols, rows, gap=gap)

    card_radius = int(el.get("radius", 20 if w >= 800 else 14))

    for it, (cx0, cy0, cw_i, ch_i) in zip(active_items, boxes):
        cx1, cy1 = cx0 + cw_i, cy0 + ch_i
        raw_state = str(it.get("state") or "off").lower()
        is_active = raw_state in ("on", "open", "active", "playing", "home", "unlocked", "heat", "cool", "auto")

        # Card container with concentric geometry and soft depth
        card_fill = T.WHITE
        border_color = T.BLACK if is_active else T.GRAY_BORDER
        border_w = 2 if is_active else 1

        T.draw_card(
            draw,
            [(cx0, cy0), (cx1, cy1)],
            radius=card_radius,
            fill=card_fill,
            outline=border_color,
            width=border_w,
            shadow=True,
        )

        # State Badge (concentric: R_inner = R_card - padding)
        badge_pad = 10
        badge_h = max(24, int(ch_i * 0.18))
        badge_f = T.font(max(11, int(badge_h * 0.58)), bold=True)
        st_text = str(it.get("state") or "ON").upper()
        if len(st_text) > 8:
            st_text = st_text[:8]
        bw = max(42, T.text_width(st_text, badge_f) + 16)
        bx0 = cx1 - bw - badge_pad
        by0 = cy0 + badge_pad

        badge_fill = T.BLACK if is_active else T.GRAY_SURFACE
        badge_txt_color = T.WHITE if is_active else T.GRAY_DARK
        T.draw_concentric_badge(
            draw,
            parent_radius=card_radius,
            padding=badge_pad,
            box=[bx0, by0, bx0 + bw, by0 + badge_h],
            fill=badge_fill,
            text=st_text,
            font=badge_f,
            text_color=badge_txt_color,
        )

        # Icon and Labels layout
        icon_name = it.get("icon") or "mdi:power"
        icon_color = T.BLACK if is_active else T.GRAY_MUTED

        if cw_i >= ch_i * 1.3:
            # Horizontal (wide) card layout
            isz = max(32, min(72, int(ch_i * 0.45)))
            icon_cx = cx0 + 20 + isz // 2
            icon_cy = cy0 + ch_i // 2
            _draw_icon_glyph(draw, icon_name, icon_cx, icon_cy, isz, color=icon_color)

            # Name and secondary text
            text_x = icon_cx + isz // 2 + 16
            avail_w = max(40, bx0 - text_x - 12)
            name_sz = max(14, min(24, int(ch_i * 0.22)))
            f_name = T.font(name_sz, bold=True)
            name_txt = _fit_text(it.get("name", ""), avail_w, f_name)

            sec_txt = it.get("changed") or it.get("secondary", "")
            if sec_txt:
                draw.text((text_x, cy0 + ch_i // 2 - int(name_sz * 0.6)), name_txt, font=f_name, fill=T.BLACK, anchor="lm")
                f_sec = T.font(max(10, int(name_sz * 0.75)), bold=False)
                sec_fitted = _fit_text(sec_txt, avail_w, f_sec)
                draw.text((text_x, cy0 + ch_i // 2 + int(name_sz * 0.7)), sec_fitted, font=f_sec, fill=T.GRAY_MUTED, anchor="lm")
            else:
                draw.text((text_x, cy0 + ch_i // 2), name_txt, font=f_name, fill=T.BLACK, anchor="lm")
        else:
            # Vertical (square/tall) card layout
            mid_x = cx0 + cw_i // 2
            isz = max(36, min(80, int(cw_i * 0.35)))
            icon_cy = cy0 + int(ch_i * 0.38)
            _draw_icon_glyph(draw, icon_name, mid_x, icon_cy, isz, color=icon_color)

            name_sz = max(13, min(22, int(cw_i * 0.12)))
            f_name = T.font(name_sz, bold=True)
            name_txt = _fit_text(it.get("name", ""), cw_i - 24, f_name)
            draw.text((mid_x, cy0 + int(ch_i * 0.72)), name_txt, font=f_name, fill=T.BLACK, anchor="mm")

            sec_txt = it.get("changed") or it.get("secondary", "")
            if sec_txt:
                f_sec = T.font(max(10, int(name_sz * 0.75)), bold=False)
                sec_fitted = _fit_text(sec_txt, cw_i - 24, f_sec)
                draw.text((mid_x, cy0 + int(ch_i * 0.86)), sec_fitted, font=f_sec, fill=T.GRAY_MUTED, anchor="mm")


def _draw_button(img, draw, el, val="", display=None):
    """Draw a dedicated interactive touch button."""
    x, y, w, h = _clamp_box(el, default_w=200, default_h=80, display=display)
    radius = int(el.get("radius", 18))
    is_pressed = bool(el.get("pressed", False))
    fill = T.GRAY_SURFACE if is_pressed else T.WHITE
    outline = T.BLACK if is_pressed else T.GRAY_BORDER

    T.draw_card(draw, [(x, y), (x + w, y + h)], radius=radius, fill=fill, outline=outline, shadow=not is_pressed)

    icon = el.get("icon")
    label = str(el.get("label") or val or "")
    color = T.BLACK

    if icon and label:
        isz = min(40, h - 20)
        _draw_icon_glyph(draw, icon, x + 24 + isz // 2, y + h // 2, isz, color=color)
        f = T.font(max(14, int(h * 0.28)), bold=True)
        draw.text((x + 36 + isz, y + h // 2), label, font=f, fill=color, anchor="lm")
    elif icon:
        _draw_icon_glyph(draw, icon, x + w // 2, y + h // 2, min(w - 20, h - 20), color=color)
    elif label:
        f = T.font(max(14, int(h * 0.3)), bold=True)
        draw.text((x + w // 2, y + h // 2), label, font=f, fill=color, anchor="mm")


def _draw_tile(img, draw, el, val="", display=None):
    """Draw an interactive Apple Home Control Tile.

    Features:
    - Apple concentric squircle card geometry (R_outer = radius, R_inner = radius - padding)
    - True 16-level grayscale Carta anti-aliasing
    - State-aware styling:
      * Standard style: Crisp surface, hairline border, ambient drop shadow.
        When ON: High-contrast solid black circular icon well with inverted white MDI glyph,
                 bold primary title, active status subtitle, top-right active accent pill.
        When OFF: Subtle surface, outline circular icon well with muted dark-gray outline glyph,
                  crisp title, muted secondary subtitle ('Off').
      * Inverted style: Deep Carta black filled card when ON, white card when OFF.
    - Responsive layout:
      * Horizontal (wide): Left circular icon well, right two-line typographic stack.
      * Vertical (square/compact): Top-left icon well, bottom-left typographic stack.
    """
    x, y, w, h = _clamp_box(el, default_w=280, default_h=130, display=display)
    radius = int(el.get("radius", 22))
    style = el.get("style", "standard")
    is_pressed = bool(el.get("pressed", False))

    # Parse state & metadata from template resolution
    data = {}
    if isinstance(val, dict):
        data = val
    elif isinstance(val, str) and val.strip().startswith("{"):
        try:
            data = json.loads(val)
        except Exception:
            pass

    state_raw = str(data.get("state") if "state" in data else val or el.get("state", "off")).strip()
    state_lower = state_raw.lower()
    is_on = state_lower in ("on", "playing", "open", "active", "home", "unlocked") or (
        state_lower.replace(".", "", 1).isdigit() and float(state_lower) > 0
    )

    # Resolve Title
    title = str(el.get("title") or data.get("name") or el.get("name") or "")
    if not title:
        ent = str(el.get("entity") or "")
        title = ent.split(".")[-1].replace("_", " ").title() if ent else "Accessory"

    # Resolve Subtitle
    if "sub" in data:
        subtitle = str(data["sub"])
    elif el.get("subtitle") and "{{" not in el.get("subtitle", ""):
        subtitle = str(el["subtitle"])
    elif state_lower in ("on", "off"):
        if is_on and data.get("brightness"):
            try:
                pct = int(round(int(data["brightness"]) / 255.0 * 100.0))
                subtitle = f"On • {pct}%"
            except (ValueError, TypeError):
                subtitle = "On"
        else:
            subtitle = "On" if is_on else "Off"
    elif state_lower:
        unit = data.get("unit") or el.get("unit", "")
        subtitle = f"{state_raw} {unit}".strip()
    else:
        subtitle = "Off"

    # Resolve Icons
    domain = el.get("entity", "").split(".")[0] if el.get("entity") else ""
    default_icon = "mdi:power"
    if domain == "light":
        default_icon = "mdi:lightbulb"
    elif domain == "switch":
        default_icon = "mdi:power-socket-eu"
    elif domain == "climate":
        default_icon = "mdi:thermostat"
    elif domain == "media_player":
        default_icon = "mdi:speaker"
    elif domain in ("scene", "script"):
        default_icon = "mdi:play-circle"
    elif domain == "sensor":
        default_icon = "mdi:gauge"

    active_icon = el.get("icon") or default_icon
    off_icon = el.get("icon_off") or T.get_dynamic_off_icon(active_icon, domain)
    icon_name = active_icon if is_on else off_icon

    # Color Palette logic
    if style == "inverted":
        card_fill = T.BLACK if is_on else T.WHITE
        card_outline = T.BLACK if is_on else T.GRAY_BORDER
        text_color = T.WHITE if is_on else T.BLACK
        sub_color = T.GRAY_SURFACE if is_on else T.GRAY_MUTED
        well_fill = T.WHITE if is_on else T.GRAY_SURFACE
        well_outline = None if is_on else T.GRAY_BORDER
        icon_color = T.BLACK if is_on else T.GRAY_MID
    else:
        # Standard Apple Home Style
        card_fill = T.GRAY_SURFACE if is_pressed else T.WHITE
        card_outline = T.BLACK if is_on else T.GRAY_BORDER
        text_color = T.BLACK
        sub_color = T.GRAY_DARK if is_on else T.GRAY_MUTED
        if is_on:
            well_fill = T.BLACK
            well_outline = None
            icon_color = T.WHITE
        else:
            well_fill = T.WHITE
            well_outline = T.GRAY_BORDER
            icon_color = T.GRAY_MID

    # Draw Outer Squircle Card
    T.draw_card(draw, (x, y, x + w, y + h), radius=radius, fill=card_fill, outline=card_outline, shadow=not is_pressed)

    # Active Indicator Pill (top-right)
    if is_on and style != "inverted":
        dot_r = 4
        dot_x = x + w - 20
        dot_y = y + 20
        draw.ellipse([(dot_x - dot_r, dot_y - dot_r), (dot_x + dot_r, dot_y + dot_r)], fill=T.BLACK)

    # Optional Custom Badge
    badge_txt = el.get("badge")
    if badge_txt:
        f_b = T.font(11, bold=True)
        bw = T.text_width(badge_txt, f_b) + 12
        bx1 = x + w - 16
        bx0 = bx1 - bw
        T.draw_concentric_badge(draw, radius, 8, (bx0, y + 14, bx1, y + 32), fill=T.GRAY_SURFACE, text=badge_txt, font=f_b, text_color=T.BLACK)

    # Geometry Layout
    is_wide = w >= int(h * 1.25)
    if is_wide:
        # Horizontal Layout: Icon on the left, 2-line text on the right
        well_r = max(18, min(28, int(h * 0.22)))
        well_cx = x + 18 + well_r
        well_cy = y + h // 2

        # Draw Icon Well
        if well_fill or well_outline:
            draw.ellipse(
                [(well_cx - well_r, well_cy - well_r), (well_cx + well_r, well_cy + well_r)],
                fill=well_fill,
                outline=well_outline,
                width=1,
            )
        # Draw Icon Glyph inside Well
        isz = max(18, min(36, int(well_r * 1.25)))
        _draw_icon_glyph(draw, icon_name, well_cx, well_cy, isz, color=icon_color)

        # Typographic Stack
        text_x = well_cx + well_r + 16
        avail_w = max(40, (x + w - 24) - text_x)

        title_sz = max(14, min(24, int(h * 0.18)))
        sub_sz = max(11, min(17, int(title_sz * 0.75)))

        f_title = T.best_font_for_text(title, size=title_sz, bold=True)
        f_sub = T.best_font_for_text(subtitle, size=sub_sz, bold=False)

        fitted_title = _fit_text(title, avail_w, f_title)
        fitted_sub = _fit_text(subtitle, avail_w, f_sub)

        # Align vertically
        draw.text((text_x, well_cy - int(title_sz * 0.58)), fitted_title, font=f_title, fill=text_color, anchor="lm")
        draw.text((text_x, well_cy + int(sub_sz * 0.72)), fitted_sub, font=f_sub, fill=sub_color, anchor="lm")
    else:
        # Square / Compact Tile Layout (Icon Top-Left, Text Bottom)
        well_r = max(18, min(26, int(w * 0.15)))
        well_cx = x + 18 + well_r
        well_cy = y + 18 + well_r

        if well_fill or well_outline:
            draw.ellipse(
                [(well_cx - well_r, well_cy - well_r), (well_cx + well_r, well_cy + well_r)],
                fill=well_fill,
                outline=well_outline,
                width=1,
            )
        isz = max(18, min(32, int(well_r * 1.25)))
        _draw_icon_glyph(draw, icon_name, well_cx, well_cy, isz, color=icon_color)

        avail_w = w - 36
        title_sz = max(13, min(20, int(w * 0.11)))
        sub_sz = max(11, min(15, int(title_sz * 0.78)))

        f_title = T.best_font_for_text(title, size=title_sz, bold=True)
        f_sub = T.best_font_for_text(subtitle, size=sub_sz, bold=False)

        fitted_title = _fit_text(title, avail_w, f_title)
        fitted_sub = _fit_text(subtitle, avail_w, f_sub)

        draw.text((x + 18, y + h - int(sub_sz * 2.2) - 10), fitted_title, font=f_title, fill=text_color, anchor="lm")
        draw.text((x + 18, y + h - int(sub_sz * 0.8) - 10), fitted_sub, font=f_sub, fill=sub_color, anchor="lm")



CONDITION_ICONS = {
    "clear-night": "mdi:weather-night",
    "cloudy": "mdi:weather-cloudy",
    "fog": "mdi:weather-fog",
    "hail": "mdi:weather-hail",
    "lightning": "mdi:weather-lightning",
    "lightning-rainy": "mdi:weather-lightning-rainy",
    "partlycloudy": "mdi:weather-partly-cloudy",
    "pouring": "mdi:weather-pouring",
    "rainy": "mdi:weather-rainy",
    "snowy": "mdi:weather-snowy",
    "snowy-rainy": "mdi:weather-snowy-rainy",
    "sunny": "mdi:weather-sunny",
    "windy": "mdi:weather-windy",
    "windy-variant": "mdi:weather-windy-variant",
    "exceptional": "mdi:alert-circle-outline",
}


def _format_time_str(val):
    if not val:
        return ""
    s = str(val).strip()
    if re.match(r"^\d{1,2}:\d{2}", s):
        return s[:5]
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return s


def _format_day_label(val, idx):
    if not val:
        return "TODAY" if idx == 0 else f"+{idx}D"
    s = str(val).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if dt.date() == now.date():
            return "TODAY"
        return dt.strftime("%a").upper()
    except Exception:
        pass
    if idx == 0:
        return "TODAY"
    return f"+{idx}D"


def _draw_calendar_timeline(img, draw, el, val, display=None):
    """Draw an Apple-standard agenda timeline displaying upcoming events."""
    x, y, w, h = _clamp_box(el, default_w=600, default_h=360, display=display)
    radius = int(el.get("radius", 20))
    title = str(el.get("title") or "Today's Schedule")
    max_events = int(el.get("max_events", 4))

    events = []
    if isinstance(val, str) and val.strip().startswith(("{", "[")):
        try:
            val = json.loads(val)
        except Exception:
            pass

    if isinstance(val, dict):
        if "events" in val and isinstance(val["events"], list):
            events = val["events"]
        else:
            ev_title = val.get("message") or val.get("summary") or val.get("friendly_name")
            if ev_title:
                events.append({
                    "summary": str(ev_title),
                    "start": str(val.get("start_time") or val.get("start") or ""),
                    "end": str(val.get("end_time") or val.get("end") or ""),
                    "location": str(val.get("location") or ""),
                    "ongoing": val.get("state") == "on" or bool(val.get("ongoing")),
                })
    elif isinstance(val, list):
        events = val

    # Concentric Card Outer Container with ambient depth
    T.draw_card(draw, [(x, y), (x + w, y + h)], radius=radius, fill=T.WHITE, outline=T.GRAY_BORDER, shadow=True)

    # Header Bar
    header_h = min(56, max(36, int(h * 0.16)))
    f_hdr = T.best_font_for_text(title, max(14, min(22, int(header_h * 0.45))), bold=True)
    _draw_icon_glyph(draw, "mdi:calendar-blank", x + 24 + 10, y + header_h // 2, 22, color=T.BLACK)
    draw.text((x + 48, y + header_h // 2), title, font=f_hdr, fill=T.BLACK, anchor="lm")

    # Hairline divider
    draw.line([(x + 16, y + header_h), (x + w - 16, y + header_h)], fill=T.GRAY_BORDER, width=1)

    # Empty State
    if not events:
        empty_isz = max(28, min(48, int(h * 0.2)))
        _draw_icon_glyph(draw, "mdi:calendar-check", x + w // 2, y + header_h + (h - header_h) // 2 - 12, empty_isz, color=T.GRAY_MUTED)
        f_empty = T.font(max(13, min(18, int(empty_isz * 0.4))), bold=False)
        draw.text((x + w // 2, y + header_h + (h - header_h) // 2 + empty_isz // 2 + 6), "No upcoming events today", font=f_empty, fill=T.GRAY_MUTED, anchor="mm")
        return

    visible = events[:max_events]
    n = len(visible)
    avail_h = h - header_h - 20
    row_h = avail_h / max(1, n)
    rail_x = x + min(170, max(120, int(w * 0.22)))

    # Continuous vertical timeline rail
    if n > 1:
        rail_top = y + header_h + int(row_h * 0.5)
        rail_bot = y + header_h + int((n - 0.5) * row_h)
        draw.line([(rail_x, rail_top), (rail_x, rail_bot)], fill=T.GRAY_BORDER, width=2)

    for i, ev in enumerate(visible):
        center_y = int(y + header_h + 10 + (i + 0.5) * row_h)
        summary = str(ev.get("summary") or ev.get("title") or "Event")
        start = str(ev.get("start") or ev.get("start_time") or "")
        end = str(ev.get("end") or ev.get("end_time") or "")
        loc = str(ev.get("location") or "")
        is_ongoing = bool(ev.get("ongoing") or ev.get("state") == "on")

        start_fmt = _format_time_str(start)
        end_fmt = _format_time_str(end)

        time_box_w = rail_x - x - 28
        if is_ongoing:
            badge_h = min(28, int(row_h * 0.5))
            badge_y0 = center_y - badge_h // 2
            T.draw_concentric_badge(
                draw,
                parent_radius=10,
                padding=2,
                box=[x + 16, badge_y0, x + 16 + time_box_w, badge_y0 + badge_h],
                fill=T.BLACK,
                text=f"NOW • {start_fmt}" if start_fmt else "NOW",
                font=T.font(max(10, min(13, int(badge_h * 0.48))), bold=True),
                text_color=T.WHITE,
            )
        else:
            f_time_start = T.font(max(12, min(17, int(row_h * 0.3))), bold=True)
            f_time_end = T.font(max(10, min(13, int(row_h * 0.24))), bold=False)
            if end_fmt:
                draw.text((rail_x - 14, center_y - 8), start_fmt, font=f_time_start, fill=T.BLACK, anchor="rm")
                draw.text((rail_x - 14, center_y + 10), end_fmt, font=f_time_end, fill=T.GRAY_MUTED, anchor="rm")
            else:
                draw.text((rail_x - 14, center_y), start_fmt or "--:--", font=f_time_start, fill=T.BLACK, anchor="rm")

        # Timeline Node
        if is_ongoing:
            draw.ellipse([(rail_x - 7, center_y - 7), (rail_x + 7, center_y + 7)], fill=T.WHITE, outline=T.BLACK, width=2)
            draw.ellipse([(rail_x - 4, center_y - 4), (rail_x + 4, center_y + 4)], fill=T.BLACK)
        else:
            draw.ellipse([(rail_x - 5, center_y - 5), (rail_x + 5, center_y + 5)], fill=T.WHITE, outline=T.GRAY_MID, width=2)

        # Event Details
        detail_x = rail_x + 16
        detail_max_w = max(40, x + w - detail_x - 16)
        name_sz = max(13, min(20, int(row_h * 0.32)))
        f_name = T.best_font_for_text(summary, name_sz, bold=True)
        fitted_summary = _fit_text(summary, detail_max_w, f_name)

        if loc:
            draw.text((detail_x, center_y - int(name_sz * 0.55)), fitted_summary, font=f_name, fill=T.BLACK, anchor="lm")
            f_loc = T.font(max(10, int(name_sz * 0.72)), bold=False)
            fitted_loc = _fit_text(f"📍 {loc}", detail_max_w, f_loc)
            draw.text((detail_x, center_y + int(name_sz * 0.65)), fitted_loc, font=f_loc, fill=T.GRAY_MUTED, anchor="lm")
        else:
            draw.text((detail_x, center_y), fitted_summary, font=f_name, fill=T.BLACK, anchor="lm")


def _draw_weather_forecast(img, draw, el, val, display=None):
    """Draw an Apple-standard multi-day weather forecast matrix."""
    x, y, w, h = _clamp_box(el, default_w=600, default_h=260, display=display)
    radius = int(el.get("radius", 20))
    title = str(el.get("title") or "5-Day Forecast")
    max_days = int(el.get("days", 5))

    forecast = []
    current_temp = None
    current_cond = ""
    if isinstance(val, str) and val.strip().startswith(("{", "[")):
        try:
            val = json.loads(val)
        except Exception:
            pass

    if isinstance(val, dict):
        current_temp = val.get("temperature")
        current_cond = str(val.get("condition") or "")
        forecast = val.get("forecast") or []
    elif isinstance(val, list):
        forecast = val

    # Concentric Card Outer Container with ambient depth
    T.draw_card(draw, [(x, y), (x + w, y + h)], radius=radius, fill=T.WHITE, outline=T.GRAY_BORDER, shadow=True)

    # Header Bar
    header_h = min(52, max(34, int(h * 0.18)))
    hdr_icon = CONDITION_ICONS.get(current_cond.lower().replace(" ", "-"), "mdi:weather-partly-cloudy")
    _draw_icon_glyph(draw, hdr_icon, x + 24 + 10, y + header_h // 2, 22, color=T.BLACK)
    f_hdr = T.font(max(14, min(20, int(header_h * 0.45))), bold=True)
    draw.text((x + 48, y + header_h // 2), title, font=f_hdr, fill=T.BLACK, anchor="lm")

    if current_temp is not None:
        cond_label = current_cond.replace("-", " ").title() if current_cond else ""
        cur_str = f"{round(float(current_temp))}° • {cond_label}" if cond_label else f"{round(float(current_temp))}°"
        f_cur = T.font(max(13, min(18, int(header_h * 0.42))), bold=True)
        draw.text((x + w - 20, y + header_h // 2), cur_str, font=f_cur, fill=T.BLACK, anchor="rm")

    draw.line([(x + 16, y + header_h), (x + w - 16, y + header_h)], fill=T.GRAY_BORDER, width=1)

    slots = forecast[:max_days]
    n = len(slots)
    if n == 0:
        f_empty = T.font(14, bold=False)
        draw.text((x + w // 2, y + header_h + (h - header_h) // 2), "No forecast data available", font=f_empty, fill=T.GRAY_MUTED, anchor="mm")
        return

    col_w = (w - 24) / n
    body_h = h - header_h - 12

    for i, day in enumerate(slots):
        cx0 = int(x + 12 + i * col_w)
        mid_x = int(cx0 + col_w * 0.5)

        if i > 0:
            draw.line([(cx0, y + header_h + 10), (cx0, y + h - 16)], fill=T.GRAY_BORDER, width=1)

        dt_str = str(day.get("datetime") or "")
        day_label = _format_day_label(dt_str, i)
        f_day = T.font(max(11, min(16, int(body_h * 0.09))), bold=True)
        draw.text((mid_x, y + header_h + 14), day_label, font=f_day, fill=T.GRAY_DARK if i > 0 else T.BLACK, anchor="mt")

        cond = str(day.get("condition") or "").lower().replace(" ", "-")
        ic_name = CONDITION_ICONS.get(cond, "mdi:weather-cloudy")
        isz = max(28, min(56, int(col_w * 0.36), int(body_h * 0.28)))
        icon_y = y + header_h + int(body_h * 0.36)
        _draw_icon_glyph(draw, ic_name, mid_x, icon_y, isz, color=T.BLACK)

        hi = day.get("temperature")
        lo = day.get("templow")
        hi_sz = max(13, min(24, int(body_h * 0.12)))
        f_hi = T.font(hi_sz, bold=True)
        f_lo = T.font(max(11, int(hi_sz * 0.8)), bold=False)
        temp_y = icon_y + isz // 2 + 12

        if hi is not None and lo is not None:
            hi_str = f"{round(float(hi))}°"
            lo_str = f"{round(float(lo))}°"
            if col_w >= 90:
                draw.text((mid_x - 4, temp_y), hi_str, font=f_hi, fill=T.BLACK, anchor="rm")
                draw.text((mid_x + 4, temp_y), lo_str, font=f_lo, fill=T.GRAY_MUTED, anchor="lm")
            else:
                draw.text((mid_x, temp_y - 6), hi_str, font=f_hi, fill=T.BLACK, anchor="mm")
                draw.text((mid_x, temp_y + 12), lo_str, font=f_lo, fill=T.GRAY_MUTED, anchor="mm")
        elif hi is not None:
            draw.text((mid_x, temp_y), f"{round(float(hi))}°", font=f_hi, fill=T.BLACK, anchor="mm")

        precip = day.get("precipitation_probability")
        if precip is None:
            precip = day.get("precipitation")
        if precip is not None:
            try:
                precip_val = int(round(float(precip)))
            except (ValueError, TypeError):
                precip_val = 0
            if precip_val > 0:
                p_sz = max(10, min(14, int(body_h * 0.08)))
                f_p = T.font(p_sz, bold=False)
                precip_y = y + h - 14
                draw.text((mid_x, precip_y), f"💧{precip_val}%", font=f_p, fill=T.GRAY_MID, anchor="mb")


DRAWERS = {
    "text": _draw_text,
    "number": _draw_text,
    "icon": _draw_icon,
    "line": _draw_line,
    "curve": _draw_curve,
    "dynamic_grid": _draw_dynamic_grid,
    "button": _draw_button,
    "card": _draw_button,
    "tile": _draw_tile,
    "light_tile": _draw_tile,
    "switch_tile": _draw_tile,
    "sensor_tile": _draw_tile,
    "climate_tile": _draw_tile,
    "media_tile": _draw_tile,
    "action_tile": _draw_tile,
    "calendar_timeline": _draw_calendar_timeline,
    "weather_forecast": _draw_weather_forecast,
}


def _fmt_number(val, el):
    if val is None or val == "":
        return "--"
    try:
        fval = float(str(val).strip())
    except (TypeError, ValueError):
        return str(val)
    dec = el.get("decimals", 0)
    try:
        idec = int(dec)
    except (TypeError, ValueError):
        idec = 0
    if idec <= 0:
        s = f"{fval:.0f}"
    else:
        s = f"{fval:.{idec}f}"
    unit = el.get("unit", "")
    prefix = el.get("prefix", "")
    suffix = el.get("suffix", "")
    return f"{prefix}{s}{unit}{suffix}"


def element_text(el, vals, idx):
    """The string an element should display, after template resolution."""
    if el.get("type") == "number":
        return _fmt_number(vals.get(idx, el.get("value", "")), el)
    if el.get("type") in ("text", "button", "card"):
        got = vals.get(idx)
        base = str(got) if got is not None else str(el.get("value", "") or el.get("label", "") or "")
        prefix = el.get("prefix", "")
        suffix = el.get("suffix", "")
        if prefix or suffix:
            return f"{prefix}{base}{suffix}"
        return base
    return ""


def render_page(
    page,
    vals,
    *,
    clock="",
    label="",
    battery_pct=None,
    page_info=None,
    series=None,
    metrics=None,
    orientation=0,
    distance_m=3.0,
    display=None,
    grayscale=True,
    edge_nav=True,
    edge_nav_ratio=0.15,
):
    """Draw a complete page onto a high-DPI 16-level grayscale bitmap canvas."""
    img, d = T.new_canvas(orientation=orientation, display=display)
    elements = page.get("elements", [])

    for i, el in enumerate(elements):
        drawer = DRAWERS.get(el.get("type"))
        if drawer is None:
            continue
        try:
            if el["type"] == "curve":
                drawer(img, d, el, "", (series or {}).get(i), display=display)
            elif el["type"] in ("text", "number"):
                got = []
                drawer(img, d, el, element_text(el, vals, i), got, distance_m=distance_m, display=display)
                if metrics is not None and got:
                    entry = {"i": i, **got[0]}
                    metrics.append(entry)
            elif el["type"] in ("dynamic_grid", "calendar_timeline", "weather_forecast"):
                drawer(img, d, el, vals.get(i), display=display)
            else:
                drawer(img, d, el, element_text(el, vals, i), display=display)
        except Exception:
            # One bad element must never crash the page
            continue

    # Subtle page turn chevrons in edge gutters when multiple pages are configured
    if edge_nav and edge_nav_ratio > 0 and page_info and page_info.get("total", 1) > 1:
        cw, ch = T.canvas_dims(orientation, display)
        mid_y = ch // 2
        f_chevron = T.font(size=44, bold=False, family="lato")
        edge_w = int(cw * float(edge_nav_ratio))
        # Left subtle chevron indicator
        d.text((edge_w // 2, mid_y), "‹", fill=T.GRAY_MUTED, font=f_chevron, anchor="mm")
        # Right subtle chevron indicator
        d.text((cw - edge_w // 2, mid_y), "›", fill=T.GRAY_MUTED, font=f_chevron, anchor="mm")

    # Ambient footer with time, page dots, battery
    T.footer(
        d,
        clock=clock,
        label=label,
        battery_pct=battery_pct,
        page_info=page_info,
        orientation=orientation,
        display=display,
    )

    # Carta 16-level quantization
    if grayscale:
        return T.to_16grayscale(img)
    return img


def hit_test(page, x, y, *, display=None, orientation=0, edge_nav_ratio=0.15):
    """2D Server-Side Hit-Testing for touch events.

    Returns:
        Dict describing hit action:
        - {"type": "element_action", "element_index": ..., "action": ..., "entity": ..., ...}
        - {"type": "nav_prev", "edge": "left", "handled": True}
        - {"type": "nav_next", "edge": "right", "handled": True}
        - {"type": "miss", "handled": False}
    """
    cw, ch = T.canvas_dims(orientation, display)
    x = max(0, min(cw, int(x)))
    y = max(0, min(ch, int(y)))

    # 1. Element Hit-Testing (top layers first)
    # Tapping an interactive element always takes priority over edge turns!
    elements = page.get("elements", [])
    for i in reversed(range(len(elements))):
        el = elements[i]
        ex, ey, ew, eh = _clamp_box(el, display=display)
        if not (ex <= x <= ex + ew and ey <= y <= ey + eh):
            continue

        el_type = el.get("type", "")

        # Dynamic Grid child hit-testing
        if el_type == "dynamic_grid":
            items = el.get("items", [])
            n = len(items)
            if n > 0:
                is_wide = ew >= eh
                cols, rows = _compute_grid_dimensions(n, is_wide)
                gap = int(el.get("gap", 16 if ew >= 800 else 12))
                boxes = compute_dynamic_grid_boxes(ex, ey, ew, eh, n, cols, rows, gap=gap)
                for k, (bx0, by0, bw, bh) in enumerate(boxes):
                    if bx0 <= x <= bx0 + bw and by0 <= y <= by0 + bh:
                        item = items[k] if isinstance(items[k], dict) else {"entity": str(items[k])}
                        ent = item.get("entity", "")
                        return {
                            "type": "element_action",
                            "element_index": i,
                            "element_type": "dynamic_grid",
                            "item_index": k,
                            "entity": ent,
                            "action": item.get("action", "toggle"),
                            "service": item.get("service"),
                            "data": item.get("data"),
                            "target_page": item.get("target_page"),
                            "handled": True,
                            "x": x,
                            "y": y,
                        }

        # Standard element / button / card / tile hit
        touch_cfg = el.get("touch") or {}
        action = touch_cfg.get("action") or el.get("action")
        ent = touch_cfg.get("entity") or el.get("entity")

        # Default action for tile or elements with entities is "toggle"
        if not action and ent:
            domain = ent.split(".")[0]
            action = "turn_on" if domain in ("scene", "script") else "toggle"

        is_tile = el_type in ("tile", "light_tile", "switch_tile", "sensor_tile", "climate_tile", "media_tile", "action_tile")
        if is_tile or action or ent or touch_cfg.get("service") or touch_cfg.get("target_page"):
            return {
                "type": "element_action",
                "element_index": i,
                "element_type": el_type,
                "entity": ent,
                "action": action or "toggle",
                "service": touch_cfg.get("service") or el.get("service"),
                "data": touch_cfg.get("data") or el.get("data"),
                "target_page": touch_cfg.get("target_page") or el.get("target_page"),
                "handled": True,
                "x": x,
                "y": y,
            }

    # 2. Edge Tap Navigation ("Book Metaphor")
    # Only triggered if tap lands in the outer gutter with no interactive element!
    if edge_nav_ratio and edge_nav_ratio > 0:
        edge_w = int(cw * float(edge_nav_ratio))
        if x <= edge_w:
            return {
                "type": "nav_prev",
                "edge": "left",
                "handled": True,
                "x": x,
                "y": y,
            }
        if x >= cw - edge_w:
            return {
                "type": "nav_next",
                "edge": "right",
                "handled": True,
                "x": x,
                "y": y,
            }

    return {"type": "miss", "handled": False, "x": x, "y": y}


def collect_templates(page):
    """Every templated string on a page, as {element_index: template}."""
    out = {}
    for i, el in enumerate(page.get("elements", [])):
        el_type = el.get("type", "")
        if el_type in ("text", "number", "button", "card"):
            tpl = template_for(el)
            if tpl and "{{" in tpl:
                out[i] = tpl
        elif el_type == "icon" and el.get("entity"):
            ent = (el.get("entity") or "").strip()
            if ent:
                out[i] = f"{{{{ states('{binding._quote(ent)}') }}}}"
        elif el_type in ("tile", "light_tile", "switch_tile", "sensor_tile", "climate_tile", "media_tile", "action_tile"):
            ent = (el.get("entity") or "").strip()
            if ent:
                sub_tpl = el.get("subtitle")
                if sub_tpl and "{{" in str(sub_tpl):
                    out[i] = str(sub_tpl)
                else:
                    out[i] = (
                        "{{ {"
                        f"'state': states('{binding._quote(ent)}'), "
                        f"'name': (state_attr('{binding._quote(ent)}', 'friendly_name') or ''), "
                        f"'brightness': state_attr('{binding._quote(ent)}', 'brightness'), "
                        f"'unit': (state_attr('{binding._quote(ent)}', 'unit_of_measurement') or '')"
                        "} | to_json }}"
                    )
        elif el_type == "dynamic_grid":
            items = el.get("items", [])
            ents = [it.get("entity", "").strip() for it in items if isinstance(it, dict) and it.get("entity", "").strip()]
            if ents:
                ents_quoted = ", ".join(f"'{binding._quote(e)}'" for e in ents)
                tpl = (
                    "[{% for e in [" + ents_quoted + "] %}"
                    '{"entity": {{ e | to_json }}, '
                    '"state": {{ states(e) | to_json }}, '
                    '"name": {{ (state_attr(e, "friendly_name") or "") | to_json }}, '
                    '"changed": {{ (relative_time(states[e].last_changed) if (states[e] is defined and states[e] is not none and states[e].last_changed is defined) else "") | to_json }}}'
                    "{% if not loop.last %},{% endif %}{% endfor %}]"
                )
                out[i] = tpl
        elif el.get("type") == "calendar_timeline":
            ent = (el.get("entity") or "calendar.personal").strip()
            raw_val = el.get("value")
            if raw_val and "{{" in str(raw_val):
                out[i] = str(raw_val)
            elif ent:
                out[i] = (
                    "{{ {'state': states('" + binding._quote(ent) + "'), "
                    "'message': state_attr('" + binding._quote(ent) + "', 'message'), "
                    "'start_time': state_attr('" + binding._quote(ent) + "', 'start_time'), "
                    "'end_time': state_attr('" + binding._quote(ent) + "', 'end_time'), "
                    "'location': state_attr('" + binding._quote(ent) + "', 'location')} | to_json }}"
                )
        elif el.get("type") == "weather_forecast":
            ent = (el.get("entity") or "weather.home").strip()
            raw_val = el.get("value")
            if raw_val and "{{" in str(raw_val):
                out[i] = str(raw_val)
            elif ent:
                out[i] = (
                    "{{ {'temperature': state_attr('" + binding._quote(ent) + "', 'temperature'), "
                    "'condition': states('" + binding._quote(ent) + "'), "
                    "'forecast': (state_attr('" + binding._quote(ent) + "', 'forecast') or [])[:7]} | to_json }}"
                )
    return out
