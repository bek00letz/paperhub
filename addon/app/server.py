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

def _resolve_data_dir() -> Path:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    default_dir = Path("/data")
    try:
        default_dir.mkdir(parents=True, exist_ok=True)
        return default_dir
    except (PermissionError, OSError):
        local_dir = Path(__file__).parent / "data"
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir


DATA_DIR = _resolve_data_dir()
WEB_DIR = Path(__file__).parent / "web"
HA_BASE = (os.environ.get("HA_BASE") or "http://supervisor/core").rstrip("/")
HA_TOKEN = (os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN") or "").strip()
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
IS_LAN_PANEL = getattr(web, "AppKey", lambda name, t: name)("is_lan_panel", bool)


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

    if "to_json" in expr:
        m_ent = re.search(r"states\('([^']+)'\)", expr)
        if m_ent:
            eid = m_ent.group(1)
            st = states.get(eid) or {}
            if "calendar" in eid:
                return json.dumps({
                    "state": st.get("state", "on"),
                    "message": st.get("message", "Calendar Event"),
                    "start_time": st.get("start_time", "10:00"),
                    "end_time": st.get("end_time", "11:00"),
                    "location": st.get("location", ""),
                    "events": st.get("events", []),
                })
            if "weather" in eid:
                return json.dumps({
                    "temperature": st.get("temperature", 21.5),
                    "condition": st.get("condition") or st.get("state", "partlycloudy"),
                    "forecast": st.get("forecast", []),
                })
            # Tile state & attributes
            name = st.get("friendly_name") or eid.split(".")[-1].replace("_", " ").title()
            return json.dumps({
                "state": st.get("state", "on"),
                "name": name,
                "brightness": st.get("brightness", 255),
                "unit": st.get("unit_of_measurement", ""),
            })

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


_aircraft_cache = {"at": 0.0, "items": []}
# No built-in fallback location: a default would be someone's real home, and wrong for
# everyone else. Home Assistant's zone.home is the only source.
_home_location_cache = {"at": 0.0, "lat": None, "lon": None}
_weather_cache = {}
_calendar_cache = {}
_racing_cache = {}
_sports_match_cache = {}


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def _bearing_calc(lat1, lon1, lat2, lon2):
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(math.radians(lon2 - lon1))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    cardinals = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    idx = int((deg + 22.5) // 45)
    return deg, cardinals[idx]


async def get_home_coordinates(session):
    now = time.time()
    if now - _home_location_cache["at"] < 3600 and _home_location_cache["lat"] is not None:
        return _home_location_cache["lat"], _home_location_cache["lon"]
    if HA_TOKEN and session:
        try:
            zone_state = await ha_json(session, "/states/zone.home")
            attrs = zone_state.get("attributes", {})
            lat = float(attrs.get("latitude"))
            lon = float(attrs.get("longitude"))
            _home_location_cache["at"] = now
            _home_location_cache["lat"] = lat
            _home_location_cache["lon"] = lon
            return lat, lon
        except Exception:
            pass
    return _home_location_cache["lat"], _home_location_cache["lon"]


async def fetch_overhead_aircraft(session, radius_km=35.0):
    now = time.time()
    if now - _aircraft_cache["at"] < 45.0 and _aircraft_cache["items"] is not None:
        return _aircraft_cache["items"]

    lat, lon = await get_home_coordinates(session)
    if lat is None or lon is None:
        return []                   # no home location from Home Assistant: nothing to look around
    radius_km = max(5.0, min(150.0, float(radius_km or 35.0)))
    d_lat = radius_km / 111.0
    cos_lat = max(0.01, math.cos(math.radians(lat)))
    d_lon = radius_km / (111.0 * cos_lat)

    url = (
        f"https://opensky-network.org/api/states/all"
        f"?lamin={lat - d_lat:.4f}&lamax={lat + d_lat:.4f}"
        f"&lomin={lon - d_lon:.4f}&lomax={lon + d_lon:.4f}"
    )
    headers = {"User-Agent": "PaperHub/1.5.0 (HomeAssistant Addon)"}
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        if not session:
            return _aircraft_cache["items"]
        async with session.get(url, headers=headers, timeout=timeout) as r:
            if r.status != 200:
                return _aircraft_cache["items"]
            data = await r.json()
            raw_states = data.get("states") or []
            aircraft = []
            for s in raw_states:
                if not s or len(s) < 12 or s[8] is True:
                    continue
                a_lon, a_lat = s[5], s[6]
                if a_lon is None or a_lat is None:
                    continue
                dist = _haversine_km(lat, lon, a_lat, a_lon)
                if dist > radius_km:
                    continue
                b_deg, cardinal = _bearing_calc(lat, lon, a_lat, a_lon)
                cs = str(s[1]).strip() if s[1] else str(s[0]).upper()
                aircraft.append({
                    "icao24": str(s[0]).upper(),
                    "callsign": cs,
                    "country": str(s[2] or "Commercial"),
                    "latitude": a_lat,
                    "longitude": a_lon,
                    "altitude_m": float(s[7]) if s[7] is not None else 0.0,
                    "velocity_ms": float(s[9]) if s[9] is not None else 0.0,
                    "track_deg": float(s[10]) if s[10] is not None else 0.0,
                    "vertical_rate": float(s[11]) if s[11] is not None else 0.0,
                    "distance_km": round(dist, 1),
                    "bearing_deg": round(b_deg, 1),
                    "bearing_cardinal": cardinal
                })
            aircraft.sort(key=lambda a: a["distance_km"])
            _aircraft_cache["at"] = now
            _aircraft_cache["items"] = aircraft
            return aircraft
    except Exception as exc:
        print(f"fetch_overhead_aircraft error: {exc!r}", flush=True)
        return _aircraft_cache["items"]


async def fetch_weather_forecast(session, entity_id, fallback=None):
    eid = str(entity_id or "weather.home").strip()
    now = time.time()

    base_data = {}
    if isinstance(fallback, dict):
        base_data = dict(fallback)
    elif isinstance(fallback, str) and fallback.strip():
        try:
            base_data = json.loads(fallback)
        except Exception:
            pass

    cached = _weather_cache.get(eid)
    if cached and (now - cached["at"] < 600):
        data = dict(cached["data"])
        if isinstance(base_data, dict):
            for k in ("temperature", "condition"):
                if k in base_data and base_data[k]:
                    data[k] = base_data[k]
        return data

    if HA_TOKEN and session:
        try:
            svc_res = await ha_json(
                session,
                "/services/weather/get_forecasts?return_response=true",
                method="POST",
                json={"entity_id": eid, "type": "daily"}
            )
            forecast_items = []
            if isinstance(svc_res, dict) and eid in svc_res:
                forecast_items = svc_res[eid].get("forecast") or []
            elif isinstance(svc_res, dict) and "response" in svc_res:
                forecast_items = svc_res["response"].get(eid, {}).get("forecast") or []

            if forecast_items:
                base_data["forecast"] = forecast_items
        except Exception:
            pass

    _weather_cache[eid] = {"at": now, "data": base_data}
    return base_data


async def fetch_calendar_events(session, entity_id, days=14, fallback=None):
    raw_eid = str(entity_id or "calendar.personal").strip()
    now = time.time()
    cached = _calendar_cache.get(raw_eid)
    if cached and (now - cached["at"] < 300):
        return cached["data"]

    if not HA_TOKEN or not session:
        return fallback

    eids = [e.strip() for e in raw_eid.split(",") if e.strip()]
    st_iso = datetime.now().isoformat()
    end_iso = (datetime.now() + timedelta(days=days)).isoformat()
    all_events = []

    try:
        for eid in eids:
            try:
                url_path = f"/calendars/{eid}?start={st_iso}&end={end_iso}"
                payload = await ha_json(session, url_path)
                cal_events = payload if isinstance(payload, list) else (payload.get("events") if isinstance(payload, dict) else [])
                short_badge = eid.replace("calendar.", "").upper()[:4]
                for ev in (cal_events or []):
                    ev_copy = dict(ev)
                    ev_copy["calendar"] = eid
                    ev_copy["cal_badge"] = short_badge
                    all_events.append(ev_copy)
            except Exception:
                pass

        def _event_key(ev):
            raw_st = ev.get("start") or ev.get("start_time") or ""
            return str(raw_st)

        all_events.sort(key=_event_key)
        _calendar_cache[raw_eid] = {"at": now, "data": {"events": all_events}}
        return {"events": all_events}
    except Exception as exc:
        print(f"fetch_calendar_events error: {exc!r}", flush=True)
        return fallback


async def fetch_racing_data(session, entity_or_series="f1", fallback=None):
    now = time.time()
    raw_key = str(entity_or_series or "f1").strip().lower()

    # 1. Approach A: Check if fallback is a resolved template from HA entity (e.g. sensor.f1)
    base_data = None
    if isinstance(fallback, dict):
        base_data = fallback
    elif isinstance(fallback, str) and fallback.strip():
        try:
            base_data = json.loads(fallback)
        except Exception:
            pass

    ha_event_name = ""
    ha_status = ""
    ha_circuit = ""
    ha_date = ""
    if isinstance(base_data, dict) and "attributes" in base_data:
        attrs = base_data.get("attributes") or {}
        ha_status = str(base_data.get("state") or "").upper()
        ha_event_name = attrs.get("event_name") or attrs.get("event") or ""
        ha_circuit = attrs.get("venue") or attrs.get("circuit") or ""
        ha_date = attrs.get("date") or ""
        if attrs.get("standings"):
            return {
                "series": "F1",
                "event_name": ha_event_name or "Formula 1 Grand Prix",
                "circuit": ha_circuit or "Grand Prix Circuit",
                "status": ha_status or "IN",
                "lap": attrs.get("lap"),
                "total_laps": attrs.get("total_laps"),
                "clock": attrs.get("clock") or ha_status,
                "standings": attrs.get("standings")
            }

    # 2. Check in-memory cache
    cached = _racing_cache.get(raw_key)
    if cached and (now - cached["at"] < (60.0 if cached.get("is_live") else 600.0)):
        return cached["data"]

    # 3. Approach B: Query ESPN F1 scoreboard
    f1_url = "https://site.api.espn.com/apis/site/v2/sports/racing/f1/scoreboard"
    headers = {"User-Agent": "PaperHub/1.5.0 (HomeAssistant Addon)"}
    timeout = aiohttp.ClientTimeout(total=6)

    event_data = {
        "series": "F1",
        "event_name": ha_event_name or "Formula 1 Grand Prix",
        "circuit": ha_circuit or "Grand Prix Circuit",
        "detail": "Upcoming Grand Prix Session",
        "status": ha_status or "PRE",
        "standings": []
    }
    is_live = False

    try:
        if not session:
            return event_data
        async with session.get(f1_url, headers=headers, timeout=timeout) as r:
            if r.status == 200:
                data = await r.json()
                events = data.get("events") or []
                if events:
                    ev = events[0]
                    ev_name = ev.get("name") or ha_event_name or "Formula 1 Grand Prix"
                    circuit_info = ev.get("circuit") or {}
                    c_name = circuit_info.get("fullName") or ha_circuit or "Grand Prix Circuit"
                    c_addr = circuit_info.get("address", {})
                    c_city = c_addr.get("city") or ""
                    circuit_str = f"{c_name} · {c_city}" if c_city else c_name
                    st_desc = ev.get("status", {}).get("type", {}).get("description") or "Scheduled"
                    st_state = ev.get("status", {}).get("type", {}).get("state") or "pre"
                    is_live = (st_state == "in" or "progress" in st_desc.lower())

                    date_iso = ev.get("date") or ha_date
                    detail_str = f"Status: {st_desc}"
                    if date_iso:
                        try:
                            dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
                            detail_str = dt.strftime("%a %b %d · %H:%M UTC")
                        except Exception:
                            detail_str = f"{st_desc} · {str(date_iso)[:10]}"

                    event_data = {
                        "series": "F1",
                        "event_name": ev_name,
                        "circuit": circuit_str,
                        "detail": detail_str,
                        "status": "IN" if is_live else ("POST" if st_state == "post" else "PRE"),
                        "clock": st_desc,
                        "standings": []
                    }

                    comps = (ev.get("competitions") or [{}])[0].get("competitors") or []
                    if comps:
                        parsed_standings = []
                        for idx, c in enumerate(comps[:10]):
                            ath = c.get("athlete") or {}
                            tm = c.get("team") or {}
                            code = ath.get("abbreviation") or ath.get("shortName") or "DRV"
                            team_name = tm.get("displayName") or tm.get("shortDisplayName") or ""
                            gap_val = c.get("status", {}).get("displayValue") or ("LEADER" if idx == 0 else "")
                            parsed_standings.append({
                                "pos": idx + 1,
                                "driver": str(code)[:3].upper(),
                                "team": team_name,
                                "gap": gap_val,
                                "tyre": "M"
                            })
                        if parsed_standings:
                            event_data["standings"] = parsed_standings

        _racing_cache[raw_key] = {"at": now, "data": event_data, "is_live": is_live}
        return event_data
    except Exception as exc:
        print(f"fetch_racing_data error: {exc!r}", flush=True)
        return _racing_cache.get(raw_key, {}).get("data") or event_data


def _parse_espn_event(ev, league_title="MATCH"):
    comp = (ev.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0] if competitors else {})
    away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})

    st_type = comp.get("status", {}).get("type", {})
    st_state = st_type.get("state") or "pre"
    st_desc = st_type.get("description") or st_type.get("detail") or "Scheduled"
    clock_val = comp.get("status", {}).get("displayClock")
    is_live = (st_state == "in")

    clock_badge = f"{clock_val} · {st_desc}" if (clock_val and clock_val != "0'" and is_live) else st_desc
    venue_title = comp.get("venue", {}).get("fullName") or ""

    home_id = str(home.get("team", {}).get("id") or "")
    events_home = []
    events_away = []
    for dt in comp.get("details", []):
        t_txt = dt.get("type", {}).get("text") or ""
        clk = dt.get("clock", {}).get("displayValue") or ""
        athletes = dt.get("athletesInvolved") or []
        p_name = athletes[0].get("displayName") if athletes else ""
        if p_name and ("Goal" in t_txt or "Point" in t_txt or "Touchdown" in t_txt or "Home Run" in t_txt):
            entry_str = f"{p_name} ({clk})" if clk else p_name
            if str(dt.get("team", {}).get("id") or "") == home_id:
                events_home.append(entry_str)
            else:
                events_away.append(entry_str)

    return {
        "league": league_title,
        "venue": venue_title,
        "clock": clock_badge,
        "status": st_state.upper(),
        "is_live": is_live,
        "home_team": home.get("team", {}).get("displayName") or home.get("team", {}).get("shortDisplayName") or "HOME",
        "home_score": home.get("score") if home.get("score") is not None else "-",
        "home_stats": (home.get("records") or [{}])[0].get("summary", ""),
        "away_team": away.get("team", {}).get("displayName") or away.get("team", {}).get("shortDisplayName") or "AWAY",
        "away_score": away.get("score") if away.get("score") is not None else "-",
        "away_stats": (away.get("records") or [{}])[0].get("summary", ""),
        "events_home": ", ".join(events_home[:3]),
        "events_away": ", ".join(events_away[:3])
    }


async def fetch_sports_match(session, entity_or_league="soccer/eng.1", team=None, fallback=None):
    now = time.time()
    raw_input = str(entity_or_league or "soccer/eng.1").strip()
    cache_key = f"{raw_input}:{str(team or '').lower()}"

    # 1. Approach A: Check if fallback is a resolved HA entity from ha-teamtracker
    base_data = None
    if isinstance(fallback, dict):
        base_data = fallback
    elif isinstance(fallback, str) and fallback.strip():
        try:
            base_data = json.loads(fallback)
        except Exception:
            pass

    if isinstance(base_data, dict) and "attributes" in base_data:
        attrs = base_data.get("attributes") or {}
        home = attrs.get("team_name") or attrs.get("team_abbr") or "HOME"
        away = attrs.get("opponent_name") or attrs.get("opponent_abbr") or "AWAY"
        h_score = attrs.get("team_score")
        a_score = attrs.get("opponent_score")
        st = str(base_data.get("state") or "PRE").upper()
        clock_str = attrs.get("clock") or attrs.get("quarter") or attrs.get("period") or st
        last_play = attrs.get("last_play") or ""
        down_dist = attrs.get("down_distance_text") or ""
        venue = attrs.get("venue") or ""
        league_name = attrs.get("league") or "MATCH"
        return [{
            "league": league_name,
            "venue": venue,
            "clock": clock_str,
            "status": st,
            "home_team": home,
            "home_score": h_score if h_score is not None else "-",
            "home_stats": down_dist,
            "away_team": away,
            "away_score": a_score if a_score is not None else "-",
            "away_stats": "",
            "events_home": last_play,
            "events_away": ""
        }]

    # 2. Check in-memory cache
    cached = _sports_match_cache.get(cache_key)
    if cached and (now - cached["at"] < (30.0 if cached.get("is_live") else 300.0)):
        return cached["data"]

    # 3. Approach B: Map friendly league names to ESPN endpoint
    league_map = {
        "premier_league": "soccer/eng.1",
        "epl": "soccer/eng.1",
        "champions_league": "soccer/uefa.champions",
        "ucl": "soccer/uefa.champions",
        "la_liga": "soccer/esp.1",
        "bundesliga": "soccer/ger.1",
        "serie_a": "soccer/ita.1",
        "mls": "soccer/usa.1",
        "nba": "basketball/nba",
        "wnba": "basketball/wnba",
        "nfl": "football/nfl",
        "college_football": "football/college-football",
        "mlb": "baseball/mlb",
        "nhl": "hockey/nhl"
    }
    slug = raw_input.lower().replace("-", "_").replace(" ", "_")
    endpoint_path = league_map.get(slug, raw_input)
    if "/" not in endpoint_path:
        endpoint_path = f"soccer/{endpoint_path}"

    url = f"https://site.api.espn.com/apis/site/v2/sports/{endpoint_path}/scoreboard"
    headers = {"User-Agent": "PaperHub/1.5.0 (HomeAssistant Addon)"}
    timeout = aiohttp.ClientTimeout(total=6)

    try:
        if not session:
            return cached["data"] if cached else None
        async with session.get(url, headers=headers, timeout=timeout) as r:
            if r.status != 200:
                return cached["data"] if cached else None
            data = await r.json()
            events = data.get("events") or []
            if not events:
                return cached["data"] if cached else None

            league_title = (data.get("leagues") or [{}])[0].get("name") or "MATCH"
            parsed_matches = [_parse_espn_event(ev, league_title) for ev in events]

            if team:
                query = str(team).lower().strip()
                matched, others = [], []
                for m in parsed_matches:
                    if (query in m["home_team"].lower() or query in m["away_team"].lower()):
                        matched.append(m)
                    else:
                        others.append(m)
                parsed_matches = matched + others
            else:
                def _st_sort(m):
                    st = m.get("status", "")
                    if st == "IN": return 0
                    if st == "PRE": return 1
                    return 2
                parsed_matches.sort(key=_st_sort)

            is_any_live = any(m.get("is_live") for m in parsed_matches)
            _sports_match_cache[cache_key] = {"at": now, "data": parsed_matches, "is_live": is_any_live}
            return parsed_matches
    except Exception as exc:
        print(f"fetch_sports_match error: {exc!r}", flush=True)
        return cached["data"] if cached else None


async def enrich_page_values(session, page, vals):
    """Enrich resolved page values with live external/extended data if needed."""
    for i, el in enumerate(page.get("elements", [])):
        t = el.get("type")
        if t == "weather_forecast":
            wdata = await fetch_weather_forecast(session, el.get("entity", "weather.home"), fallback=vals.get(i))
            if wdata:
                vals[i] = wdata
        elif t == "calendar_timeline":
            cal_ent = el.get("entity")
            if cal_ent:
                cal_data = await fetch_calendar_events(session, cal_ent, days=14, fallback=vals.get(i))
                if cal_data:
                    vals[i] = cal_data
        elif t in ("flight_tracker", "flight_radar"):
            radius = float(el.get("radius") or 35)
            fl_data = await fetch_overhead_aircraft(session, radius_km=radius)
            if fl_data is not None:
                vals[i] = fl_data
        elif t == "sports_racing":
            entity_or_series = el.get("entity") or el.get("series") or "f1"
            race_data = await fetch_racing_data(session, entity_or_series, fallback=vals.get(i))
            if race_data:
                vals[i] = race_data
        elif t == "sports_match":
            entity_or_league = el.get("entity") or el.get("league") or "soccer/eng.1"
            team = el.get("team")
            match_data = await fetch_sports_match(session, entity_or_league, team=team, fallback=vals.get(i))
            if match_data:
                vals[i] = match_data


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
        self.last_render_time = float(data.get("last_render_time", 0.0))
        self.version = 1
        self.frame_png = b""
        self.frame_bmp = b""
        self.etag = ""
        self.subscribers: set[asyncio.Queue] = set()

        # Power & Sync Profile
        self.screen_mode = data.get("screen_mode") or "interactive"
        self.refresh_interval = int(data.get("refresh_interval") if data.get("refresh_interval") is not None else 15)
        self.push_on_entity_change = bool(data.get("push_on_entity_change", True))
        self.quiet_hours_enabled = bool(data.get("quiet_hours_enabled", True))
        self.quiet_hours_start = str(data.get("quiet_hours_start") or "23:00")
        self.quiet_hours_end = str(data.get("quiet_hours_end") or "07:00")
        self.quiet_hours_interval = int(data.get("quiet_hours_interval") if data.get("quiet_hours_interval") is not None else 0)
        self.quiet_hours_entity = str(data.get("quiet_hours_entity") or "").strip()

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
            "screen_mode": self.screen_mode,
            "refresh_interval": self.refresh_interval,
            "push_on_entity_change": self.push_on_entity_change,
            "quiet_hours_enabled": self.quiet_hours_enabled,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "quiet_hours_interval": self.quiet_hours_interval,
            "quiet_hours_entity": self.quiet_hours_entity,
        }

    def notify(self):
        self.version += 1
        for q in list(self.subscribers):
            try:
                q.put_nowait({"event": "render", "version": self.version, "page": self.active_page})
            except Exception:
                pass


def compute_device_next_wake_seconds(dev: DeviceSession, ha_states: dict | None = None) -> int:
    """Compute adaptive seconds until next client wake-up considering quiet hours and triggers."""
    now = datetime.now()
    is_quiet = False

    if dev.quiet_hours_enabled:
        # 1. Custom HA entity trigger check (e.g. input_boolean.sleep_mode)
        if dev.quiet_hours_entity:
            states_dict = ha_states
            if states_dict is None:
                if isinstance(_entity_cache, dict) and _entity_cache.get("items"):
                    states_dict = {e["entity_id"]: e for e in _entity_cache["items"]}
                else:
                    states_dict = load_fixture().get("states", {})
            st_obj = states_dict.get(dev.quiet_hours_entity) or {}
            st_val = str(st_obj.get("state") or "").strip().lower()
            if st_val in ("on", "true", "sleep", "sleeping", "active", "night", "not_home"):
                is_quiet = True

        # 2. Configurable time range check
        if not is_quiet and dev.quiet_hours_start and dev.quiet_hours_end:
            try:
                sh, sm = map(int, dev.quiet_hours_start.split(":"))
                eh, em = map(int, dev.quiet_hours_end.split(":"))
                start_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
                if start_dt <= end_dt:
                    is_quiet = start_dt <= now < end_dt
                else:
                    # Overnight range (e.g. 23:00 to 07:00)
                    is_quiet = now >= start_dt or now < end_dt
            except Exception:
                pass

    if is_quiet:
        if dev.quiet_hours_interval > 0:
            return dev.quiet_hours_interval * 60
        # Calculate seconds until end_dt
        try:
            eh, em = map(int, dev.quiet_hours_end.split(":"))
            end_dt = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            if end_dt <= now:
                end_dt += timedelta(days=1)
            secs_until_morning = int((end_dt - now).total_seconds())
            return max(60, min(86400, secs_until_morning))
        except Exception:
            return 28800  # 8 hours default

    # Normal daytime operation
    if dev.refresh_interval <= 0:
        return 86400  # Touch only (sleep up to 24h)
    return max(10, dev.refresh_interval * 60)


def page_has_entity(page: dict, entity_id: str) -> bool:
    """Check if a layout page references a specific Home Assistant entity."""
    if not page or not entity_id:
        return False
    eid = entity_id.strip()
    for el in page.get("elements", []):
        if (el.get("entity") or "").strip() == eid:
            return True
        if el.get("type") == "dynamic_grid":
            for it in el.get("items", []):
                if (it.get("entity") or "").strip() == eid:
                    return True
        val = str(el.get("value") or "")
        sub = str(el.get("subtitle") or "")
        series = str(el.get("series") or "")
        league = str(el.get("league") or "")
        if eid in val or eid in sub or eid in series or eid in league:
            return True
    return False


MAX_DEVICES = 32


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
            if len(self.devices) >= MAX_DEVICES:
                # Return default session to prevent unbounded memory and storage growth
                return self.devices.get("default") or DeviceSession("default")
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
    await enrich_page_values(session, page, vals)

    clock_str = datetime.now().strftime("%-I:%M %p")
    page_info = {
        "current": page_keys.index(dev.active_page) + 1,
        "total": len(page_keys),
    }

    has_multi = len(page_keys) > 1
    edge_active = dev.edge_nav and has_multi

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
        edge_nav=edge_active,
        edge_nav_ratio=dev.edge_nav_ratio,
    )

    if dev.orientation:
        img = T.orient_for_panel(img, dev.orientation)

    png_bytes = _png(img)
    bmp_bytes = T.to_1bit_bmp(img)
    dev.frame_png = png_bytes
    dev.frame_bmp = bmp_bytes
    dev.etag = hashlib.sha256(png_bytes).hexdigest()[:16]
    dev.last_render_time = time.time()
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
        # 2D Hit-Testing on current page (only enable edge nav if multiple pages exist)
        active_page_def = pages[dev.active_page]
        edge_ratio = dev.edge_nav_ratio if (dev.edge_nav and len(page_keys) > 1) else 0.0
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
                elif dev.screen_mode == "view_only":
                    # View-only ambient frame suppresses entity toggles and mutations
                    pass
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

    # 1. Check Bearer Authorization Header
    auth_hdr = request.headers.get("Authorization", "")
    if auth_hdr.lower().startswith("bearer "):
        token = auth_hdr[7:].strip()
        if hmac.compare_digest(token, FRAME_TOKEN):
            return True

    # 2. Check Custom Header
    custom_hdr = request.headers.get("X-PaperHub-Token") or request.headers.get("Access-Token")
    if custom_hdr and hmac.compare_digest(custom_hdr.strip(), FRAME_TOKEN):
        return True

    # 3. Check Query Parameter
    query_token = request.query.get("token", "")
    return bool(query_token and hmac.compare_digest(query_token, FRAME_TOKEN))


async def frame_png(request):
    """Serve crisp 16-level grayscale PNG for e-reader display with ETag caching."""
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")

    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    if not dev.frame_png or request.query.get("force"):
        spec = load_layouts()
        await render_device_frame(SHARED_SESSION, dev, spec)

    next_wake_secs = compute_device_next_wake_seconds(dev)
    headers = {
        "ETag": f'"{dev.etag}"',
        "Cache-Control": "no-cache, must-revalidate",
        "X-PaperHub-Version": str(dev.version),
        "X-PaperHub-Page": dev.active_page,
        "X-PaperHub-Next-Wake": str(next_wake_secs),
        "X-PaperHub-Refresh-Interval": str(dev.refresh_interval),
        "X-PaperHub-Screen-Mode": dev.screen_mode,
        "Refresh": str(next_wake_secs),
    }

    if_none = (request.headers.get("If-None-Match") or "").strip('" ')
    if if_none and if_none == dev.etag:
        return web.Response(status=304, headers=headers)

    return web.Response(
        body=dev.frame_png,
        content_type="image/png",
        headers=headers,
    )


async def frame_bmp(request):
    """Serve 1-bit monochrome BMP for ESP32/TRMNL e-readers with ETag caching."""
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")

    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    if not dev.frame_bmp or request.query.get("force"):
        spec = load_layouts()
        await render_device_frame(SHARED_SESSION, dev, spec)

    next_wake_secs = compute_device_next_wake_seconds(dev)
    headers = {
        "ETag": f'"{dev.etag}"',
        "Cache-Control": "no-cache, must-revalidate",
        "X-PaperHub-Version": str(dev.version),
        "X-PaperHub-Page": dev.active_page,
        "X-PaperHub-Next-Wake": str(next_wake_secs),
        "X-PaperHub-Refresh-Interval": str(dev.refresh_interval),
        "X-PaperHub-Screen-Mode": dev.screen_mode,
        "Refresh": str(next_wake_secs),
    }

    if_none = (request.headers.get("If-None-Match") or "").strip('" ')
    if if_none and if_none == dev.etag:
        return web.Response(status=304, headers=headers)

    return web.Response(
        body=dev.frame_bmp,
        content_type="image/bmp",
        headers=headers,
    )


async def api_trmnl(request):
    """TRMNL Open Webhook & Display Endpoint.
    
    Compatible with TRMNL native firmware, TRMNL BYOS (Bring Your Own Server),
    and custom ESP32 e-ink polling devices.
    """
    dev_id = (
        request.headers.get("ID")
        or request.headers.get("Mac-Address")
        or request.headers.get("Access-Token")
        or request.match_info.get("device_id")
        or request.query.get("device")
        or "trmnl_default"
    )
    dev_id = re.sub(r"[^a-zA-Z0-9_-]+", "", str(dev_id).strip()) or "trmnl_default"

    if dev_id not in DEVICES.devices:
        dev = DEVICES.get_or_create(dev_id)
        dev.display = "trmnl_og"
        dev.name = f"TRMNL {dev_id[-6:] if len(dev_id) >= 6 else dev_id}"
        DEVICES.save()
    else:
        dev = DEVICES.get_or_create(dev_id)

    bat_volt = request.headers.get("Battery-Voltage")
    if bat_volt:
        try:
            v = float(bat_volt)
            pct = int(round(max(0.0, min(100.0, (v - 3.3) / 0.9 * 100.0))))
            dev.battery_pct = pct
        except (ValueError, TypeError):
            pass

    if not dev.frame_bmp or not dev.frame_png or request.query.get("force"):
        spec = load_layouts()
        await render_device_frame(SHARED_SESSION, dev, spec)

    accept = request.headers.get("Accept", "")
    fmt = request.query.get("format", "")
    if "image/bmp" in accept or fmt == "bmp":
        return await frame_bmp(request)
    if "image/png" in accept or fmt == "png":
        return await frame_png(request)

    host = request.headers.get("Host") or f"127.0.0.1:{FRAME_PORT}"
    proto = request.headers.get("X-Forwarded-Proto") or "http"
    base_url = f"{proto}://{host}"

    refresh_rate = compute_device_next_wake_seconds(dev)
    payload = {
        "status": 0,
        "image_url": f"{base_url}/api/devices/{dev.device_id}/frame.bmp?v={dev.version}",
        "filename": "display.bmp",
        "refresh_rate": refresh_rate,
        "reset_firmware": False,
        "update_firmware": False,
    }
    return web.json_response(payload)


async def api_touch(request):
    """Handle coordinate touch and gestures from e-readers."""
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")

    dev_id = request.match_info.get("device_id") or request.query.get("device", "default")
    dev = DEVICES.get_or_create(dev_id)

    x, y, gesture = None, None, ""
    client_page = None
    body = {}
    if request.method == "POST":
        try:
            body = await request.json()
            x = body.get("x")
            y = body.get("y")
            gesture = body.get("gesture", "")
            client_page = body.get("page")
        except Exception:
            pass

    if x is None:
        try:
            x = float(request.query.get("x", 0))
            y = float(request.query.get("y", 0))
            gesture = request.query.get("gesture", gesture)
        except Exception:
            x, y = 0, 0

    # If the visual editor sent its live in-memory page for simulation:
    if client_page and isinstance(client_page, dict):
        if request.app.get(IS_LAN_PANEL) is True:
            return web.Response(status=403, text="Simulated page actions forbidden on LAN interface.")
        disp_name = body.get("display") or dev.display
        orient = int(body.get("orientation", dev.orientation))
        has_multi = bool(body.get("has_multiple_pages", True))
        edge_ratio = float(body.get("edge_nav_ratio", 0.15)) if (body.get("edge_nav", True) and has_multi) else 0.0
        hit = layout.hit_test(
            client_page,
            x,
            y,
            display=disp_name,
            orientation=orient,
            edge_nav_ratio=edge_ratio,
        )
        if hit.get("handled"):
            hit_type = hit.get("type")
            if hit_type == "element_action":
                act = hit.get("action")
                ent = hit.get("entity")
                srv = hit.get("service")
                data = hit.get("data") or {}
                if dev.screen_mode == "view_only" and act != "navigate_page" and not hit.get("target_page"):
                    pass
                elif act == "toggle" and ent:
                    await call_ha_service(SHARED_SESSION, "homeassistant", "toggle", {"entity_id": ent})
                elif act in ("turn_on", "turn_off") and ent:
                    await call_ha_service(SHARED_SESSION, "homeassistant", act, {"entity_id": ent})
                elif srv:
                    parts = srv.split(".", 1)
                    if len(parts) == 2:
                        d, s = parts
                        if ent and "entity_id" not in data:
                            data["entity_id"] = ent
                        await call_ha_service(SHARED_SESSION, d, s, data)
        return web.json_response({
            "status": "ok",
            "hit": hit,
            "page": dev.active_page,
            "simulated": True,
        })

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
    if not check_token(request):
        return web.Response(status=403, text="Forbidden")
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
        if not isinstance(spec, dict) or not isinstance(spec.get("pages"), dict):
            return web.json_response({"status": "error", "message": "Invalid layout spec: 'pages' must be a dictionary."}, status=400)
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
        await enrich_page_values(SHARED_SESSION, page, vals)

        clock_str = datetime.now().strftime("%-I:%M %p")
        page_info = data.get("page_info")
        edge_nav = bool(data.get("edge_nav", True))
        edge_nav_ratio = float(data.get("edge_nav_ratio", 0.15))
        img = layout.render_page(
            page,
            vals,
            clock=clock_str,
            label=page.get("name", "Preview"),
            battery_pct=95,
            page_info=page_info,
            orientation=orientation,
            display=display,
            grayscale=True,
            edge_nav=edge_nav,
            edge_nav_ratio=edge_nav_ratio,
        )

        return web.Response(body=_png(img), content_type="image/png")
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)


async def api_devices_list(request):
    return web.json_response([dev.to_dict() for dev in DEVICES.devices.values()])


async def api_devices_get(request):
    if request.app.get(IS_LAN_PANEL) is True and not check_token(request):
        return web.Response(status=403, text="Forbidden")
    dev_id = request.match_info.get("device_id")
    dev = DEVICES.get_or_create(dev_id)
    return web.json_response(dev.to_dict())


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
        if "screen_mode" in body:
            dev.screen_mode = str(body["screen_mode"])
        if "refresh_interval" in body:
            dev.refresh_interval = int(body["refresh_interval"])
        if "push_on_entity_change" in body:
            dev.push_on_entity_change = bool(body["push_on_entity_change"])
        if "quiet_hours_enabled" in body:
            dev.quiet_hours_enabled = bool(body["quiet_hours_enabled"])
        if "quiet_hours_start" in body:
            dev.quiet_hours_start = str(body["quiet_hours_start"])
        if "quiet_hours_end" in body:
            dev.quiet_hours_end = str(body["quiet_hours_end"])
        if "quiet_hours_interval" in body:
            dev.quiet_hours_interval = int(body["quiet_hours_interval"])
        if "quiet_hours_entity" in body:
            dev.quiet_hours_entity = str(body["quiet_hours_entity"]).strip()
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
    if not isinstance(_entity_cache, dict):
        _entity_cache = {"at": 0.0, "items": []}
    now = time.time()
    if _entity_cache.get("items") and (now - _entity_cache.get("at", 0.0)) < 30.0:
        return web.json_response(_entity_cache["items"])

    if not HA_TOKEN:
        states = load_fixture().get("states", {})
        ents = []
        for eid, s in states.items():
            friendly = s.get("friendly_name") or s.get("name") or eid.split(".")[-1].replace("_", " ").title()
            unit = s.get("unit") or s.get("unit_of_measurement", "")
            ents.append({
                "entity_id": eid,
                "state": s.get("state", ""),
                "name": friendly,
                "unit": unit,
                "attributes": dict(s, friendly_name=friendly, unit_of_measurement=unit),
            })
        _entity_cache = {"at": now, "items": ents}
        return web.json_response(ents)

    try:
        raw_ents = await ha_json(SHARED_SESSION, "/states")
        ents = []
        for e in (raw_ents or []):
            if not isinstance(e, dict):
                continue
            attrs = e.get("attributes") or {}
            friendly = attrs.get("friendly_name") or e.get("name") or e.get("entity_id", "")
            unit = attrs.get("unit_of_measurement") or e.get("unit", "")
            ents.append({
                "entity_id": e.get("entity_id", ""),
                "state": e.get("state", ""),
                "name": friendly,
                "unit": unit,
                "attributes": attrs,
            })
        _entity_cache = {"at": now, "items": ents}
        return web.json_response(ents)
    except Exception as exc:
        print(f"Warning: Failed to fetch HA entities ({exc}), falling back to cache/fixture", flush=True)
        if _entity_cache.get("items"):
            return web.json_response(_entity_cache["items"])
        states = load_fixture().get("states", {})
        ents = []
        for eid, s in states.items():
            friendly = s.get("friendly_name") or s.get("name") or eid.split(".")[-1].replace("_", " ").title()
            unit = s.get("unit") or s.get("unit_of_measurement", "")
            ents.append({
                "entity_id": eid,
                "state": s.get("state", ""),
                "name": friendly,
                "unit": unit,
                "attributes": dict(s, friendly_name=friendly, unit_of_measurement=unit),
            })
        _entity_cache = {"at": now, "items": ents}
        return web.json_response(ents)


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


async def api_sources_get(request):
    srcs = load_sources()
    return web.json_response({"sources": feeds.mask_secrets(srcs)})


async def api_sources_put(request):
    try:
        incoming = await request.json()
        items = incoming.get("sources") if isinstance(incoming, dict) else incoming
        existing = load_sources()
        unmasked = feeds.unmask_secrets(items, existing)
        feeds.save(DATA_DIR, unmasked)
        return web.json_response({"status": "ok", "sources": feeds.mask_secrets(unmasked)})
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=400)


async def api_sources_test(request):
    try:
        src = await request.json()
        existing = load_sources()
        unmasked_list = feeds.unmask_secrets([src], existing)
        target = unmasked_list[0] if unmasked_list else src
        ctx = {"session": SHARED_SESSION, "ha_base": HA_BASE, "ha_token": HA_TOKEN}
        res = await feeds.run_all([target], ctx)
        published = [{"entity_id": eid, "state": st, "attributes": attrs} for (eid, st, attrs) in res]
        return web.json_response({"status": "ok", "published": published})
    except Exception as exc:
        return web.json_response({"status": "error", "message": str(exc), "published": []})


async def api_panel_setup(request):
    return web.json_response({
        "status": "ok",
        "config": {
            "ha_host": request.host.split(":")[0],
            "wifi_ssid": "Home",
            "api_key": "",
            "ota_password": ""
        }
    })


async def api_panel_refresh(request):
    return web.json_response({"status": "ok", "ha_updated": False})


async def periodic_ticker():
    """Background ticker updating devices according to their adaptive power profiles."""
    while True:
        try:
            await asyncio.sleep(30)
            now = time.time()
            spec = load_layouts()
            for dev in list(DEVICES.devices.values()):
                # Only re-render if seen in last 24h
                if now - dev.last_seen < 86400:
                    if dev.refresh_interval <= 0:
                        continue
                    next_wake = compute_device_next_wake_seconds(dev)
                    if (now - dev.last_render_time) >= next_wake:
                        await render_device_frame(SHARED_SESSION, dev, spec)
                        dev.notify()
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Ticker error: {e}", flush=True)


async def ha_websocket_listener():
    """Subscribe to Home Assistant WebSocket state_changed events for instant real-time pushes."""
    token = HA_TOKEN
    if not token:
        return

    ws_base = HA_BASE.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_base}/websocket"
    backoff = 3
    while True:
        try:
            async with SHARED_SESSION.ws_connect(url, timeout=10) as ws:
                msg = await ws.receive_json()
                if msg.get("type") != "auth_required":
                    await asyncio.sleep(backoff)
                    continue
                await ws.send_json({"type": "auth", "access_token": token})
                auth_res = await ws.receive_json()
                if auth_res.get("type") != "auth_ok":
                    print(f"HA WS auth failed: {auth_res}", flush=True)
                    await asyncio.sleep(10)
                    continue

                await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
                await ws.receive_json()
                print("Connected to Home Assistant WebSocket for live state events", flush=True)
                backoff = 3

                last_push = 0.0
                async for ws_msg in ws:
                    if ws_msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(ws_msg.data)
                        if data.get("type") == "event":
                            global _entity_cache
                            _entity_cache = {"at": 0.0, "items": []}

                            now = time.time()
                            if now - last_push < 0.4:
                                continue

                            last_push = now
                            event_data = data.get("event", {}).get("data", {})
                            changed_eid = event_data.get("entity_id", "")

                            spec = load_layouts()
                            pages = spec.get("pages", {})
                            for dev in list(DEVICES.devices.values()):
                                if time.time() - dev.last_seen < 86400:
                                    if not dev.push_on_entity_change:
                                        continue
                                    active_page = pages.get(dev.active_page, {})
                                    if not changed_eid or page_has_entity(active_page, changed_eid) or changed_eid == dev.quiet_hours_entity:
                                        await render_device_frame(SHARED_SESSION, dev, spec)
                                        dev.notify()

                    elif ws_msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

        except asyncio.CancelledError:
            break
        except Exception as e:
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 1.5)


async def start_app(app_runners):
    # LAN E-Reader Port (8099)
    panel = web.Application()
    panel[IS_LAN_PANEL] = True
    panel.add_routes([
        web.get("/frame.png", frame_png),
        web.get("/frame.bmp", frame_bmp),
        web.get("/api/devices/{device_id}/frame.png", frame_png),
        web.get("/api/devices/{device_id}/frame.bmp", frame_bmp),
        web.get("/api/devices/{device_id}/events", api_device_events),
        web.post("/api/touch", api_touch),
        web.post("/api/devices/{device_id}/touch", api_touch),
        web.get("/api/trmnl", api_trmnl),
        web.post("/api/trmnl", api_trmnl),
        web.get("/api/trmnl/display", api_trmnl),
        web.post("/api/trmnl/display", api_trmnl),
        web.get("/api/devices/{device_id}/trmnl", api_trmnl),
        web.post("/api/devices/{device_id}/trmnl", api_trmnl),
        web.get("/api/devices/{device_id}", api_devices_get),
        web.get("/api/panel-setup", api_panel_setup),
        web.post("/api/panel-setup", api_panel_setup),
        web.post("/api/panel-refresh", api_panel_refresh),
        web.get("/kiosk", kiosk_html),
        web.get("/kiosk/{device_id}", kiosk_html),
    ])

    # HA Ingress / Editor Port (8080)
    editor = web.Application(client_max_size=4 * 1024 * 1024)
    editor[IS_LAN_PANEL] = False
    editor.add_routes([
        web.get("/", editor_index),
        web.get("/kiosk", kiosk_html),
        web.get("/kiosk/{device_id}", kiosk_html),
        web.get("/frame.png", frame_png),
        web.get("/frame.bmp", frame_bmp),
        web.get("/api/devices/{device_id}/frame.png", frame_png),
        web.get("/api/devices/{device_id}/frame.bmp", frame_bmp),
        web.get("/api/devices/{device_id}/events", api_device_events),
        web.post("/api/touch", api_touch),
        web.post("/api/devices/{device_id}/touch", api_touch),
        web.get("/api/trmnl", api_trmnl),
        web.post("/api/trmnl", api_trmnl),
        web.get("/api/trmnl/display", api_trmnl),
        web.post("/api/trmnl/display", api_trmnl),
        web.get("/api/devices/{device_id}/trmnl", api_trmnl),
        web.post("/api/devices/{device_id}/trmnl", api_trmnl),
        web.get("/api/status", api_status),
        web.get("/api/displays", api_displays),
        web.get("/api/layouts", api_layouts_get),
        web.put("/api/layouts", api_layouts_put),
        web.post("/api/preview", api_preview),
        web.post("/api/push", api_push),
        web.get("/api/devices", api_devices_list),
        web.get("/api/devices/{device_id}", api_devices_get),
        web.post("/api/devices/{device_id}", api_devices_update),
        web.get("/api/sources", api_sources_get),
        web.put("/api/sources", api_sources_put),
        web.post("/api/sources/test", api_sources_test),
        web.get("/api/panel-setup", api_panel_setup),
        web.post("/api/panel-setup", api_panel_setup),
        web.post("/api/panel-refresh", api_panel_refresh),
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
    ws_task = asyncio.create_task(ha_websocket_listener())

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        ticker_task.cancel()
        ws_task.cancel()
        for r in app_runners:
            await r.cleanup()
        if SHARED_SESSION:
            await SHARED_SESSION.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
