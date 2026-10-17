#!/usr/bin/env python3
"""PaperHub - Ambient E-Ink Touch Controller for Home Assistant.

High-DPI server-side rasterization engine (1448x1072, 1680x1264, 1872x1404)
with 16-level Carta grayscale, instant server-side hit-testing (<20ms),
multi-device session management, and live SSE streaming for zero-latency e-ink touch.
"""
import asyncio
import base64
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp
from aiohttp import web
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import feeds  # noqa: E402
from render import layout, theme as T, binding  # noqa: E402

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
WEB_DIR = Path(__file__).parent / "web"
HA_BASE = (os.environ.get("HA_BASE") or "http://supervisor/core").rstrip("/")
HA_TOKEN = (os.environ.get("HA_TOKEN") or "").strip()
REFRESH = max(10, min(3600, int(os.environ.get("REFRESH_SECONDS", "60") or 60)))
FRAME_TOKEN = (os.environ.get("FRAME_TOKEN") or "").strip()

FRAME_PORT = int(os.environ.get("FRAME_PORT", "8099") or 8099)
INGRESS_PORT = int(os.environ.get("INGRESS_PORT", "8080") or 8080)

def get_layouts_path():
    return DATA_DIR / "layouts.json"


def get_devices_path():
    return DATA_DIR / "devices.json"


DEFAULTS_PATH = Path(__file__).parent / "default_layouts.json"
FIXTURE_PATH = Path(__file__).parent / "render" / "fixture.json"

ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
PAGE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

_entity_cache = {"at": 0.0, "items": []}
_fixture_cache = None
SHARED_SESSION: aiohttp.ClientSession | None = None


def valid_entity_id(eid: str) -> bool:
    return bool(eid and ENTITY_RE.match(str(eid).strip()))


def load_fixture():
    global _fixture_cache
    if _fixture_cache is None:
        try:
            _fixture_cache = json.loads(FIXTURE_PATH.read_text())
        except Exception:
            _fixture_cache = {"states": {}, "pv_curve_w": []}
    return _fixture_cache


def eval_fixture_template(tpl: str) -> str:
    """Evaluate common HA templates against fixture.json when running offline."""
    states = load_fixture().get("states", {})
    s = str(tpl or "").strip()

    if "[{% for e in [" in s and 'states(e) | to_json' in s:
        m_ents = re.search(r"for e in \[([^\]]+)\]", s)
        res = []
        if m_ents:
            for raw_eid in m_ents.group(1).split(","):
                eid = raw_eid.strip(" '\"")
                if not eid:
                    continue
                st = states.get(eid) or {}
                cur_state = st.get("state", "on")
                fname = st.get("friendly_name") or eid.split(".")[-1].replace("_", " ").title()
                res.append({
                    "entity": eid,
                    "state": str(cur_state),
                    "name": fname,
                    "changed": "10m ago",
                })
        return json.dumps(res)

    if s.startswith("{{") and s.endswith("}}"):
        expr = s[2:-2].strip()
    else:
        expr = s

    # Handle `is_state('entity', 'val')`
    m = re.match(r"^is_state\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)$", expr)
    if m:
        eid, target = m.group(1), m.group(2)
        cur = (states.get(eid) or {}).get("state", "")
        return "True" if str(cur) == target else "False"

    # Handle `states('entity') | int(0) > 0`
    m = re.match(r"^states\(\s*'([^']+)'\s*\)\s*\|\s*int\(\d*\)\s*>\s*(\d+)$", expr)
    if m:
        eid, thresh = m.group(1), int(m.group(2))
        try:
            val = int(float((states.get(eid) or {}).get("state", 0)))
        except (TypeError, ValueError):
            val = 0
        return "True" if val > thresh else "False"

    m_state = re.search(r"states\(\s*'([^']+)'\s*\)", expr)
    m_attr = re.search(r"state_attr\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", expr)
    m_prop = re.search(r"states\[\s*'([^']+)'\s*\]\.(last_changed|last_updated)", expr)

    val = ""
    if m_attr:
        val = str((states.get(m_attr.group(1)) or {}).get(m_attr.group(2), ""))
    elif m_state:
        val = str((states.get(m_state.group(1)) or {}).get("state", ""))
    elif m_prop:
        val = "15m ago"

    # Handle strftime
    if "now().strftime" in expr:
        return datetime.now().strftime("%A, %-d %B")

    return val


def load_sources():
    return feeds.load(DATA_DIR) or []


def load_layouts():
    """User layouts, seeded from high-DPI defaults on first run."""
    for src in (get_layouts_path(), DEFAULTS_PATH):
        try:
            return json.loads(src.read_text())
        except Exception:
            continue
    return {"display": "boox_go_6", "orientation": 0, "pages": {}}


def save_layouts(spec):
    lp = get_layouts_path()
    lp.parent.mkdir(parents=True, exist_ok=True)
    tmp = lp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(spec, indent=2))
    tmp.replace(lp)


async def ha_json(session, path, method="GET", **kw):
    url = f"{HA_BASE}/api{path}"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=10)
    async with session.request(method, url, headers=headers, timeout=timeout, **kw) as r:
        r.raise_for_status()
        return await r.json()


async def ha_template(session, tpl) -> str | None:
    if not HA_TOKEN:
        return eval_fixture_template(tpl)
    url = f"{HA_BASE}/api/template"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with session.post(url, headers=headers, json={"template": tpl}, timeout=timeout) as r:
            if r.status != 200:
                return None
            return (await r.text()).strip()
    except Exception:
        return None


async def call_ha_service(session, domain, service, data=None):
    if not HA_TOKEN:
        # Mock action in offline/fixture mode
        if domain == "homeassistant" and service == "toggle" and data and "entity_id" in data:
            eid = data["entity_id"]
            fix = load_fixture()
            cur = (fix.get("states", {}).get(eid, {})).get("state", "off")
            new_st = "off" if cur == "on" else "on"
            if eid not in fix.get("states", {}):
                fix.setdefault("states", {})[eid] = {}
            fix["states"][eid]["state"] = new_st
            print(f"[Offline] Toggled {eid} -> {new_st}", flush=True)
        return True

    safe_domain = re.sub(r"[^a-z0-9_]+", "", str(domain).lower())
    safe_service = re.sub(r"[^a-z0-9_]+", "", str(service).lower())
    try:
        await ha_json(session, f"/services/{safe_domain}/{safe_service}", method="POST", json=data or {})
        return True
    except Exception as exc:
        print(f"service {safe_domain}.{safe_service} failed: {exc!r}", flush=True)
        return False


SEP = "<<<|paperhub|>>>"


async def resolve_templates(session, templates):
    if not templates:
        return {}
    keys = list(templates)
    if not HA_TOKEN:
        return {k: eval_fixture_template(templates[k]) for k in keys}

    joined = f"\n{SEP}\n".join(templates[k] for k in keys)
    out = await ha_template(session, joined)
    if out is not None:
        parts = [p.strip() for p in out.split(SEP)]
        if len(parts) == len(keys):
            return dict(zip(keys, parts))

    results = {}
    for k in keys:
        res = await ha_template(session, templates[k])
        results[k] = res if res is not None else ""
    return results


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


class DeviceSession:
    """State for one connected e-reader client device."""

    def __init__(self, device_id: str, data: dict | None = None):
        data = data or {}
        self.device_id = device_id
        self.name = data.get("name") or f"Device {device_id}"
        self.display = data.get("display") or "boox_go_6"
        self.orientation = int(data.get("orientation") or 0)
        self.active_page = data.get("active_page") or "home"
        self.edge_nav = bool(data.get("edge_nav", True))
        self.edge_nav_ratio = float(data.get("edge_nav_ratio", 0.15))
        self.battery_pct = data.get("battery_pct")
        self.last_seen = time.time()
        self.version = 1
        self.frame_png = b""
        self.etag = ""
        self.subscribers: set[asyncio.Queue] = set()

    def to_dict(self):
        return {
            "device_id": self.device_id,
            "name": self.name,
            "display": self.display,
            "orientation": self.orientation,
            "active_page": self.active_page,
            "edge_nav": self.edge_nav,
            "edge_nav_ratio": self.edge_nav_ratio,
            "battery_pct": self.battery_pct,
            "last_seen": self.last_seen,
            "version": self.version,
        }

    def notify(self):
        self.version += 1
        for q in list(self.subscribers):
            try:
                q.put_nowait({"event": "render", "version": self.version, "page": self.active_page})
            except Exception:
                pass


class DeviceManager:
    """Manages active e-readers and persistent profiles."""

    def __init__(self):
        self.devices: dict[str, DeviceSession] = {}
        self.load()

    def load(self):
        dp = get_devices_path()
        if dp.exists():
            try:
                raw = json.loads(dp.read_text())
                for dev_id, d in raw.items():
                    self.devices[dev_id] = DeviceSession(dev_id, d)
            except Exception as e:
                print(f"Failed to load devices: {e}", flush=True)

        if "default" not in self.devices:
            self.devices["default"] = DeviceSession("default", {
                "name": "Default E-Reader",
                "display": "boox_go_6",
                "active_page": "home",
            })

    def save(self):
        dp = get_devices_path()
        dp.parent.mkdir(parents=True, exist_ok=True)
        out = {k: dev.to_dict() for k, dev in self.devices.items()}
        dp.write_text(json.dumps(out, indent=2))

    def get_or_create(self, device_id: str) -> DeviceSession:
        dev_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(device_id or "default").strip()) or "default"
        if dev_id not in self.devices:
            self.devices[dev_id] = DeviceSession(dev_id, {"name": f"Device {dev_id}"})
            self.save()
        dev = self.devices[dev_id]
        dev.last_seen = time.time()
        return dev


DEVICES = DeviceManager()


async def render_device_frame(session, dev: DeviceSession, spec: dict) -> bytes:
    """Render the active page of a device in 16-level grayscale."""
    pages = spec.get("pages", {})
    page_keys = list(pages.keys())
    if not page_keys:
        img, _ = T.new_canvas(dev.orientation, dev.display)
        return _png(img)

    if dev.active_page not in pages:
        dev.active_page = page_keys[0]

    page = pages[dev.active_page]
    templates = layout.collect_templates(page)
    vals = await resolve_templates(session, templates) if templates else {}

    clock_str = datetime.now().strftime("%-I:%M %p")
    page_info = {
        "current": page_keys.index(dev.active_page) + 1,
        "total": len(page_keys),
    }

    img = layout.render_page(
        page,
        vals,
        clock=clock_str,
        label=page.get("name", dev.active_page),
        battery_pct=dev.battery_pct,
        page_info=page_info,
        orientation=dev.orientation,
        display=dev.display,
        grayscale=True,
    )

    if dev.orientation:
        img = T.orient_for_panel(img, dev.orientation)

    png_bytes = _png(img)
    dev.frame_png = png_bytes
    dev.etag = hashlib.sha256(png_bytes).hexdigest()[:16]
    return png_bytes


async def handle_touch(session, dev: DeviceSession, spec: dict, x: float, y: float, gesture: str = ""):
    """Process touch tap or swipe gesture on an e-reader."""
    pages = spec.get("pages", {})
    page_keys = list(pages.keys())
    if not page_keys:
        return {"status": "error", "error": "No pages configured"}

    if dev.active_page not in pages:
        dev.active_page = page_keys[0]

    cur_idx = page_keys.index(dev.active_page)
    hit = None

    # Handle horizontal swipe gestures
    if gesture == "swipe_left":
        next_idx = (cur_idx + 1) % len(page_keys)
        dev.active_page = page_keys[next_idx]
        hit = {"type": "gesture_swipe", "gesture": "swipe_left", "target_page": dev.active_page, "handled": True}
    elif gesture == "swipe_right":
        prev_idx = (cur_idx - 1 + len(page_keys)) % len(page_keys)
        dev.active_page = page_keys[prev_idx]
        hit = {"type": "gesture_swipe", "gesture": "swipe_right", "target_page": dev.active_page, "handled": True}
    else:
        # 2D Hit-Testing on current page
        active_page_def = pages[dev.active_page]
        edge_ratio = dev.edge_nav_ratio if dev.edge_nav else 0.0
        hit = layout.hit_test(
            active_page_def,
            x,
            y,
            display=dev.display,
            orientation=dev.orientation,
            edge_nav_ratio=edge_ratio,
        )

        if hit.get("handled"):
            hit_type = hit.get("type")
            if hit_type == "nav_prev":
                prev_idx = (cur_idx - 1 + len(page_keys)) % len(page_keys)
                dev.active_page = page_keys[prev_idx]
            elif hit_type == "nav_next":
                next_idx = (cur_idx + 1) % len(page_keys)
                dev.active_page = page_keys[next_idx]
            elif hit_type == "element_action":
                act = hit.get("action")
                ent = hit.get("entity")
                srv = hit.get("service")
                data = hit.get("data") or {}

                if act == "navigate_page" or hit.get("target_page"):
                    tgt = hit.get("target_page") or act
                    if tgt in pages:
                        dev.active_page = tgt
                elif act == "toggle" and ent:
                    await call_ha_service(session, "homeassistant", "toggle", {"entity_id": ent})
                elif act in ("turn_on", "turn_off") and ent:
                    await call_ha_service(session, "homeassistant", act, {"entity_id": ent})
                elif srv:
                    parts = srv.split(".", 1)
                    if len(parts) == 2:
                        domain, service_name = parts
                        if ent and "entity_id" not in data:
                            data["entity_id"] = ent
                        await call_ha_service(session, domain, service_name, data)

    # Immediately re-render device frame
    await render_device_frame(session, dev, spec)
    dev.notify()
    DEVICES.save()

    return {
        "status": "ok",
        "hit": hit,
        "page": dev.active_page,
        "version": dev.version,
        "frame_url": f"/api/devices/{dev.device_id}/frame.png?v={dev.version}",
    }


# ==============================================================================
# HTTP Handlers
# ==============================================================================

def check_token(request):
    if not FRAME_TOKEN:
        return True
    return hmac.compare_digest(request.query.get("token", ""), FRAME_TOKEN)


async def frame_png(request):
    """Serve crisp 16-level grayscale PNG for e-reader display."""
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")

    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    if not dev.frame_png or request.query.get("force"):
        spec = load_layouts()
        await render_device_frame(SHARED_SESSION, dev, spec)

    if request.headers.get("If-None-Match") == dev.etag:
        return web.Response(status=304)

    return web.Response(
        body=dev.frame_png,
        content_type="image/png",
        headers={
            "ETag": dev.etag,
            "Cache-Control": "no-cache, must-revalidate",
            "X-PaperHub-Version": str(dev.version),
            "X-PaperHub-Page": dev.active_page,
        },
    )


async def api_touch(request):
    """Handle coordinate touch and gestures from e-readers."""
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")

    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    x, y, gesture = None, None, ""
    if request.method == "POST":
        try:
            body = await request.json()
            x = body.get("x")
            y = body.get("y")
            gesture = body.get("gesture", "")
        except Exception:
            pass

    if x is None:
        try:
            x = float(request.query.get("x", 0))
            y = float(request.query.get("y", 0))
            gesture = request.query.get("gesture", gesture)
        except Exception:
            x, y = 0, 0

    spec = load_layouts()
    result = await handle_touch(SHARED_SESSION, dev, spec, x, y, gesture)

    # If requested image directly, return the updated PNG to save a round-trip
    if request.query.get("format") == "png" or request.headers.get("Accept") == "image/png":
        return web.Response(
            body=dev.frame_png,
            content_type="image/png",
            headers={"X-PaperHub-Version": str(dev.version), "X-PaperHub-Page": dev.active_page},
        )

    return web.json_response(result)


async def api_device_events(request):
    """Server-Sent Events (SSE) stream for zero-latency screen refresh pushes."""
    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await resp.prepare(request)

    q = asyncio.Queue()
    dev.subscribers.add(q)

    # Initial frame notice
    init_msg = json.dumps({"event": "init", "version": dev.version, "page": dev.active_page})
    await resp.write(f"data: {init_msg}\n\n".encode("utf-8"))

    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=25.0)
                payload = json.dumps(msg)
                await resp.write(f"data: {payload}\n\n".encode("utf-8"))
            except asyncio.TimeoutError:
                # SSE Heartbeat
                await resp.write(b": heartbeat\n\n")
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        dev.subscribers.discard(q)

    return resp


async def kiosk_html(request):
    """Serve the Universal Kiosk PWA."""
    kiosk_path = WEB_DIR / "kiosk.html"
    if not kiosk_path.exists():
        return web.Response(text="Kiosk not found.", status=404)
    return web.FileResponse(kiosk_path, headers={"Cache-Control": "no-cache, must-revalidate"})


async def editor_index(request):
    index = WEB_DIR / "index.html"
    if not index.exists():
        return web.Response(text="Editor not found.", status=404)
    return web.FileResponse(index, headers={"Cache-Control": "no-cache, must-revalidate"})


async def api_status(request):
    return web.json_response({
        "status": "ok",
        "devices": len(DEVICES.devices),
        "uptime": time.time(),
        "ha_connected": bool(HA_TOKEN),
    })


async def api_displays(request):
    return web.json_response(T.DISPLAYS)


async def api_layouts_get(request):
    return web.json_response(load_layouts())


async def api_layouts_put(request):
    try:
        spec = await request.json()
        save_layouts(spec)
        # Notify all devices
        for dev in DEVICES.devices.values():
            await render_device_frame(SHARED_SESSION, dev, spec)
            dev.notify()
        return web.json_response({"status": "ok"})
    except Exception as exc:
        return web.json_response({"status": "error", "message": str(exc)}, status=400)


async def api_preview(request):
    """Render on-demand preview PNG for the visual editor."""
    try:
        data = await request.json()
        page = data.get("page") or {}
        display = data.get("display") or "boox_go_6"
        orientation = int(data.get("orientation") or 0)

        templates = layout.collect_templates(page)
        vals = await resolve_templates(SHARED_SESSION, templates) if templates else {}

        clock_str = datetime.now().strftime("%-I:%M %p")
        img = layout.render_page(
            page,
            vals,
            clock=clock_str,
            label=page.get("name", "Preview"),
            battery_pct=95,
            orientation=orientation,
            display=display,
            grayscale=True,
        )

        return web.Response(body=_png(img), content_type="image/png")
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def api_devices_list(request):
    return web.json_response([dev.to_dict() for dev in DEVICES.devices.values()])


async def api_devices_update(request):
    dev_id = request.match_info.get("device_id")
    dev = DEVICES.get_or_create(dev_id)
    try:
        body = await request.json()
        if "name" in body:
            dev.name = str(body["name"])
        if "display" in body:
            dev.display = str(body["display"])
        if "orientation" in body:
            dev.orientation = int(body["orientation"])
        if "active_page" in body:
            dev.active_page = str(body["active_page"])
        if "edge_nav" in body:
            dev.edge_nav = bool(body["edge_nav"])
        if "edge_nav_ratio" in body:
            dev.edge_nav_ratio = float(body["edge_nav_ratio"])
        DEVICES.save()
        spec = load_layouts()
        await render_device_frame(SHARED_SESSION, dev, spec)
        dev.notify()
        return web.json_response(dev.to_dict())
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


async def api_push(request):
    spec = load_layouts()
    for dev in DEVICES.devices.values():
        await render_device_frame(SHARED_SESSION, dev, spec)
        dev.notify()
    return web.json_response({"status": "ok", "devices": len(DEVICES.devices)})


async def api_entities(request):
    global _entity_cache
    now = time.time()
    if _entity_cache["items"] and (now - _entity_cache["at"]) < 30.0:
        return web.json_response(_entity_cache["items"])

    if not HA_TOKEN:
        states = load_fixture().get("states", {})
        ents = []
        for eid, s in states.items():
            ents.append({
                "entity_id": eid,
                "state": s.get("state", ""),
                "attributes": {"friendly_name": s.get("friendly_name", eid)},
            })
        _entity_cache = {"at": now, "items": ents}
        return web.json_response(ents)

    try:
        ents = await ha_json(SHARED_SESSION, "/states")
        _entity_cache = {"at": now, "items": ents}
        return web.json_response(ents)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def api_mdi_all(request):
    map_file = Path(__file__).parent / "fonts" / "mdi-codepoints.json"
    if not map_file.exists():
        return web.json_response({})
    return web.FileResponse(map_file, headers={"Cache-Control": "public, max-age=86400"})


async def api_mdi_font(request):
    font_file = Path(__file__).parent / "fonts" / "mdi.ttf"
    if not font_file.exists():
        return web.Response(status=404)
    return web.FileResponse(font_file, headers={"Cache-Control": "public, max-age=86400"})


async def periodic_ticker():
    """Background ticker updating devices every REFRESH seconds."""
    while True:
        try:
            await asyncio.sleep(REFRESH)
            spec = load_layouts()
            for dev in list(DEVICES.devices.values()):
                # Only re-render if seen in last 24h
                if time.time() - dev.last_seen < 86400:
                    await render_device_frame(SHARED_SESSION, dev, spec)
                    dev.notify()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Ticker error: {e}", flush=True)


async def start_app(app_runners):
    # LAN E-Reader Port (8099)
    panel = web.Application()
    panel.add_routes([
        web.get("/frame.png", frame_png),
        web.get("/api/devices/{device_id}/frame.png", frame_png),
        web.get("/api/devices/{device_id}/events", api_device_events),
        web.post("/api/touch", api_touch),
        web.get("/api/touch", api_touch),
        web.post("/api/devices/{device_id}/touch", api_touch),
        web.get("/api/devices/{device_id}/touch", api_touch),
        web.get("/kiosk", kiosk_html),
        web.get("/kiosk/{device_id}", kiosk_html),
    ])

    # HA Ingress / Editor Port (8080)
    editor = web.Application(client_max_size=4 * 1024 * 1024)
    editor.add_routes([
        web.get("/", editor_index),
        web.get("/kiosk", kiosk_html),
        web.get("/kiosk/{device_id}", kiosk_html),
        web.get("/frame.png", frame_png),
        web.get("/api/devices/{device_id}/frame.png", frame_png),
        web.get("/api/devices/{device_id}/events", api_device_events),
        web.post("/api/touch", api_touch),
        web.get("/api/touch", api_touch),
        web.post("/api/devices/{device_id}/touch", api_touch),
        web.get("/api/devices/{device_id}/touch", api_touch),
        web.get("/api/status", api_status),
        web.get("/api/displays", api_displays),
        web.get("/api/layouts", api_layouts_get),
        web.put("/api/layouts", api_layouts_put),
        web.post("/api/preview", api_preview),
        web.post("/api/push", api_push),
        web.get("/api/devices", api_devices_list),
        web.post("/api/devices/{device_id}", api_devices_update),
        web.get("/api/entities", api_entities),
        web.get("/api/mdi/all", api_mdi_all),
        web.get("/api/mdi/font", api_mdi_font),
    ])

    if WEB_DIR.exists():
        editor.router.add_static("/static/", WEB_DIR)
        panel.router.add_static("/static/", WEB_DIR)

    for app, port in ((panel, FRAME_PORT), (editor, INGRESS_PORT)):
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", port).start()
        app_runners.append(runner)
        print(f"PaperHub listening on :{port}", flush=True)


async def main():
    global SHARED_SESSION
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_SESSION = aiohttp.ClientSession()

    app_runners = []
    await start_app(app_runners)

    # Pre-render default device
    spec = load_layouts()
    def_dev = DEVICES.get_or_create("default")
    await render_device_frame(SHARED_SESSION, def_dev, spec)

    ticker_task = asyncio.create_task(periodic_ticker())

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        ticker_task.cancel()
        for r in app_runners:
            await r.cleanup()
        if SHARED_SESSION:
            await SHARED_SESSION.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
