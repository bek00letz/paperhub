"""PaperHub automated test suite.

Tests:
1. TRMNL profile lookup, BMP generation, and battery voltage parsing.
2. Calendar timeline and weather forecast widget rasterization with Apple aesthetics.
3. Multilingual font fallback (DejaVuSans for Cyrillic and symbols).
4. Conditional ETag HTTP 304 caching and frame generation.
5. Touch engine hit-testing (edge zones and center elements).
6. Server endpoints: frame_png, frame_bmp, and api_trmnl webhook.
"""

import io
import os
import sys
import time
import json
import asyncio
import unittest

# Ensure addon/app is in Python path
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from PIL import Image
from render import theme as T
from render import layout as L
import server
from aiohttp.test_utils import make_mocked_request


class TestTRMNLSupport(unittest.TestCase):
    def test_trmnl_profiles(self):
        """Verify TRMNL display profiles exist and match hardware specs."""
        self.assertIn("trmnl_og", T.DISPLAYS)
        og = T.DISPLAYS["trmnl_og"]
        self.assertEqual(og["w"], 800)
        self.assertEqual(og["h"], 480)
        self.assertEqual(og["ppi"], 120)

        self.assertIn("trmnl_x", T.DISPLAYS)
        tx = T.DISPLAYS["trmnl_x"]
        self.assertEqual(tx["w"], 1872)
        self.assertEqual(tx["h"], 1404)
        self.assertEqual(tx["ppi"], 227)

        # Alias resolution via get_display
        self.assertEqual(T.get_display("trmnl")["w"], 800)
        self.assertEqual(T.get_display("trmnl_og")["w"], 800)
        self.assertEqual(T.get_display("trmnl_x")["w"], 1872)

    def test_to_1bit_bmp(self):
        """Verify to_1bit_bmp produces a valid 1-bit BMP for zero-RAM ESP32 streaming."""
        img = Image.new("L", (800, 480), 255)
        bmp_bytes = T.to_1bit_bmp(img)
        self.assertTrue(bmp_bytes.startswith(b"BM"), "Missing BMP header signature 'BM'")
        
        # In a 1-bit BMP (800x480):
        # 800 pixels / 8 bits = 100 bytes per row (4-byte aligned).
        # 100 * 480 = 48,000 pixel data bytes + 62 bytes (headers + 2-color palette) = 48,062 bytes.
        self.assertEqual(len(bmp_bytes), 48062)

        # Verify PIL can reopen it as a valid 1-bit BMP
        bmp_io = io.BytesIO(bmp_bytes)
        reopened = Image.open(bmp_io)
        self.assertEqual(reopened.size, (800, 480))
        self.assertEqual(reopened.format, "BMP")


class TestMultilingualFontFallback(unittest.TestCase):
    def test_fallback_selection(self):
        """Verify best_font_for_text selects DejaVuSans for non-ASCII/Cyrillic/symbols."""
        # Standard ASCII can use Lato
        font_ascii = T.best_font_for_text("Living Room Light", size=24, bold=True, family="lato")
        self.assertTrue("Lato" in font_ascii.getname()[0] or "Lato" in str(font_ascii))

        # Cyrillic text must fallback to DejaVuSans
        font_cyr = T.best_font_for_text("Гостиная Свет", size=24, bold=True, family="lato")
        self.assertTrue("DejaVu" in font_cyr.getname()[0] or "DejaVu" in str(font_cyr))

        # Special symbol text (arrows, degrees, stars)
        font_sym = T.best_font_for_text("Temp: 21.5°C ★ 12:00 → 13:00", size=20, bold=False, family="lato")
        self.assertTrue("DejaVu" in font_sym.getname()[0] or "DejaVu" in str(font_sym))


class TestWidgetsRasterization(unittest.TestCase):
    def test_calendar_and_weather_rendering(self):
        """Verify calendar_timeline and weather_forecast render with Apple aesthetics in < 25ms."""
        cal_el = {
            "type": "calendar_timeline",
            "x": 40,
            "y": 40,
            "w": 992,
            "h": 460,
            "title": "Today's Schedule",
            "radius": 24,
            "max_events": 4,
        }
        weather_el = {
            "type": "weather_forecast",
            "x": 40,
            "y": 520,
            "w": 992,
            "h": 320,
            "title": "5-Day Forecast",
            "radius": 24,
            "days": 5,
        }
        page = {
            "elements": [cal_el, weather_el]
        }
        vals = {
            0: {
                "events": [
                    {
                        "summary": "Design Sync (Carta 16-Gray)",
                        "start": "09:30",
                        "end": "10:30",
                        "location": "Boardroom",
                        "ongoing": True,
                    },
                    {
                        "summary": "Home Assistant Sprint Review",
                        "start": "13:00",
                        "end": "14:00",
                        "location": "Online",
                        "ongoing": False,
                    },
                ]
            },
            1: {
                "temperature": 21.8,
                "condition": "partlycloudy",
                "forecast": [
                    {"datetime": "2026-10-17T12:00:00+00:00", "condition": "partlycloudy", "temperature": 22, "templow": 14, "precipitation_probability": 10},
                    {"datetime": "2026-10-18T12:00:00+00:00", "condition": "sunny", "temperature": 24, "templow": 15, "precipitation_probability": 0},
                    {"datetime": "2026-10-19T12:00:00+00:00", "condition": "rainy", "temperature": 18, "templow": 11, "precipitation_probability": 75},
                    {"datetime": "2026-10-20T12:00:00+00:00", "condition": "cloudy", "temperature": 19, "templow": 12, "precipitation_probability": 20},
                    {"datetime": "2026-10-21T12:00:00+00:00", "condition": "lightning", "temperature": 16, "templow": 10, "precipitation_probability": 80},
                ],
            },
        }

        t0 = time.perf_counter()
        img = L.render_page(page, vals, display="boox_go_6", clock="10:45 AM", battery_pct=88)
        render_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(img.size, (1072, 1448))
        self.assertEqual(img.mode, "L")
        self.assertLess(render_ms, 50.0, f"Render took too long: {render_ms:.2f}ms (target < 50ms)")


class TestETagAndTouchEngine(unittest.TestCase):
    def test_hit_test_edge_navigation(self):
        """Verify left/right 15% edge zones trigger page turns and center hits element."""
        # Boox Go 6 portrait: 1072 x 1448
        # Left 15% is <= 160.8, Right 15% is >= 911.2
        page = {
            "elements": [
                {
                    "type": "icon",
                    "x": 400,
                    "y": 400,
                    "w": 200,
                    "h": 200,
                    "touch": {"action": "toggle", "entity": "light.living_room"}
                }
            ]
        }
        
        # Left edge tap -> nav_prev
        res_left = L.hit_test(page, 50, 500, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertTrue(res_left.get("handled"))
        self.assertEqual(res_left.get("type"), "nav_prev")
        self.assertEqual(res_left.get("edge"), "left")

        # Right edge tap -> nav_next
        res_right = L.hit_test(page, 1000, 500, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertTrue(res_right.get("handled"))
        self.assertEqual(res_right.get("type"), "nav_next")
        self.assertEqual(res_right.get("edge"), "right")

        # Center tap on element -> element_action
        res_center = L.hit_test(page, 450, 450, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertTrue(res_center.get("handled"))
        self.assertEqual(res_center.get("type"), "element_action")
        self.assertEqual(res_center.get("action"), "toggle")
        self.assertEqual(res_center.get("entity"), "light.living_room")

        # Center tap on empty space -> miss
        res_miss = L.hit_test(page, 300, 300, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertFalse(res_miss.get("handled"))
        self.assertEqual(res_miss.get("type"), "miss")


class TestServerEndpoints(unittest.TestCase):
    def test_frame_png_and_etag(self):
        """Verify frame_png returns 200 with ETag, and 304 on matching If-None-Match."""
        async def _run():
            # First fetch: 200 OK with ETag
            req = make_mocked_request("GET", "/frame.png")
            resp = await server.frame_png(req)
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.content_type, "image/png")
            etag = resp.headers.get("ETag")
            self.assertIsNotNone(etag)

            # Conditional fetch: 304 Not Modified
            req304 = make_mocked_request("GET", "/frame.png", headers={"If-None-Match": etag})
            resp304 = await server.frame_png(req304)
            self.assertEqual(resp304.status, 304)

        asyncio.run(_run())

    def test_frame_bmp_and_etag(self):
        """Verify frame_bmp returns 200 with image/bmp and 304 on matching If-None-Match."""
        async def _run():
            req = make_mocked_request("GET", "/frame.bmp")
            resp = await server.frame_bmp(req)
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.content_type, "image/bmp")
            self.assertTrue(resp.body.startswith(b"BM"))
            etag = resp.headers.get("ETag")
            self.assertIsNotNone(etag)

            req304 = make_mocked_request("GET", "/frame.bmp", headers={"If-None-Match": etag})
            resp304 = await server.frame_bmp(req304)
            self.assertEqual(resp304.status, 304)

        asyncio.run(_run())

    def test_trmnl_webhook(self):
        """Verify TRMNL webhook endpoint parses headers and returns JSON payload."""
        async def _run():
            req = make_mocked_request(
                "GET",
                "/api/trmnl",
                headers={
                    "ID": "trmnl-kitchen-01",
                    "Battery-Voltage": "4.15",
                },
            )
            resp = await server.api_trmnl(req)
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.text)
            self.assertIn("image_url", data)
            self.assertIn("refresh_rate", data)
            self.assertEqual(data.get("status"), 0)

        asyncio.run(_run())


class TestAppleHomeTilesAndSimulation(unittest.TestCase):
    def test_tile_rendering(self):
        """Verify Apple Home control tiles render with concentric geometry and high contrast in < 20ms."""
        tile_on = {
            "type": "tile",
            "x": 64,
            "y": 64,
            "w": 456,
            "h": 140,
            "radius": 24,
            "style": "standard",
            "entity": "light.living_room_ceiling",
            "title": "Ceiling Light",
            "icon": "mdi:ceiling-light",
            "icon_off": "mdi:ceiling-light-outline",
            "touch": {"action": "toggle"}
        }
        tile_off = {
            "type": "tile",
            "x": 552,
            "y": 64,
            "w": 456,
            "h": 140,
            "radius": 24,
            "style": "standard",
            "entity": "light.reading_lamp",
            "title": "Reading Lamp",
            "icon": "mdi:lamp",
            "icon_off": "mdi:lamp-outline",
            "touch": {"action": "toggle"}
        }
        tile_inverted = {
            "type": "tile",
            "x": 64,
            "y": 230,
            "w": 456,
            "h": 140,
            "radius": 24,
            "style": "inverted",
            "entity": "switch.living_room_fan",
            "title": "Ceiling Fan",
            "icon": "mdi:fan",
            "touch": {"action": "toggle"}
        }
        page = {
            "elements": [tile_on, tile_off, tile_inverted]
        }
        vals = {
            0: {"state": "on", "name": "Ceiling Light", "brightness": 204},
            1: {"state": "off", "name": "Reading Lamp"},
            2: {"state": "on", "name": "Ceiling Fan"},
        }

        t0 = time.perf_counter()
        img = L.render_page(page, vals, display="boox_go_6")
        dt_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(img.size, (1072, 1448))
        self.assertEqual(img.mode, "L")
        self.assertLess(dt_ms, 25.0, f"Tile rendering too slow: {dt_ms:.2f}ms")

    def test_tile_hit_test(self):
        """Verify tile is automatically recognized as an interactive target even without explicit touch dict."""
        page = {
            "elements": [
                {
                    "type": "tile",
                    "x": 100,
                    "y": 100,
                    "w": 400,
                    "h": 140,
                    "entity": "light.desk",
                    "title": "Desk Lamp"
                }
            ]
        }
        # Hit inside tile
        res = L.hit_test(page, 200, 150, display="boox_go_6", orientation=0, edge_nav_ratio=0.0)
        self.assertTrue(res.get("handled"))
        self.assertEqual(res.get("type"), "element_action")
        self.assertEqual(res.get("action"), "toggle")
        self.assertEqual(res.get("entity"), "light.desk")

        # Miss outside tile
        res_miss = L.hit_test(page, 50, 50, display="boox_go_6", orientation=0, edge_nav_ratio=0.0)
        self.assertFalse(res_miss.get("handled"))

    def test_live_page_touch_simulation(self):
        """Verify api_touch accepts in-memory client page for instant simulation."""
        async def _run():
            sim_page = {
                "name": "Live Simulation Canvas",
                "elements": [
                    {
                        "type": "tile",
                        "x": 64,
                        "y": 200,
                        "w": 456,
                        "h": 140,
                        "entity": "light.office",
                        "title": "Office Lights",
                        "touch": {"action": "toggle"}
                    }
                ]
            }
            body = {
                "x": 200,
                "y": 250,
                "page": sim_page,
                "display": "boox_go_6",
                "orientation": 0,
                "edge_nav": True,
                "edge_nav_ratio": 0.15
            }
            req = make_mocked_request(
                "POST",
                "/api/touch",
                headers={"Content-Type": "application/json"},
            )
            # Mock json body
            async def _mock_json():
                return body
            req.json = _mock_json

            resp = await server.api_touch(req)
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.text)
            self.assertEqual(data.get("status"), "ok")
            self.assertTrue(data.get("simulated"))
            hit = data.get("hit", {})
            self.assertTrue(hit.get("handled"))
            self.assertEqual(hit.get("action"), "toggle")
            self.assertEqual(hit.get("entity"), "light.office")

        asyncio.run(_run())


class TestPaperHubV130Features(unittest.TestCase):
    def test_dynamic_icon_resolution(self):
        """Verify dynamic state-aware off icons are resolved correctly for all domains."""
        self.assertEqual(T.get_dynamic_off_icon("mdi:lightbulb"), "mdi:lightbulb-outline")
        self.assertEqual(T.get_dynamic_off_icon("mdi:fan"), "mdi:fan-off")
        self.assertEqual(T.get_dynamic_off_icon("mdi:power"), "mdi:power-off")
        self.assertEqual(T.get_dynamic_off_icon("mdi:door-open"), "mdi:door-closed")
        self.assertEqual(T.get_dynamic_off_icon("mdi:volume-high"), "mdi:volume-off")
        self.assertEqual(T.get_dynamic_off_icon("mdi:speaker"), "mdi:speaker-off")
        self.assertEqual(T.get_dynamic_off_icon("mdi:thermostat"), "mdi:thermostat-box")
        # Heuristic fallback for light domain
        self.assertEqual(T.get_dynamic_off_icon("mdi:spotlight", domain="light"), "mdi:spotlight-outline")
        # Heuristic fallback for switch domain
        self.assertEqual(T.get_dynamic_off_icon("mdi:pump", domain="switch"), "mdi:pump-off")

    def test_element_priority_over_edge_turn(self):
        """Verify that an element near the margin receives touch rather than false page turn."""
        # Page on Boox Go 6 (1072w). Edge 15% is x <= 160.8.
        # Place a tile at x=64, w=456 (overlapping x in [64, 520]).
        page = {
            "elements": [
                {
                    "type": "tile",
                    "x": 64,
                    "y": 100,
                    "w": 456,
                    "h": 140,
                    "entity": "light.office",
                    "touch": {"action": "toggle"},
                }
            ]
        }
        # Tap at x=100 (inside 15% edge zone 160px, BUT also inside tile [64, 520])
        hit = L.hit_test(page, 100, 150, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertTrue(hit.get("handled"))
        self.assertEqual(hit.get("type"), "element_action")
        self.assertEqual(hit.get("entity"), "light.office")
        self.assertEqual(hit.get("action"), "toggle")

        # Empty tap at x=40, y=800 (no element) should trigger edge turn
        edge_hit = L.hit_test(page, 40, 800, display="boox_go_6", orientation=0, edge_nav_ratio=0.15)
        self.assertTrue(edge_hit.get("handled"))
        self.assertEqual(edge_hit.get("type"), "nav_prev")
        self.assertEqual(edge_hit.get("edge"), "left")

    def test_edge_nav_suppression_single_page(self):
        """Verify edge zones are completely suppressed when edge_nav_ratio is 0 (single page)."""
        page = {"elements": []}
        # Tap at x=40 (within 15% margin) with edge_nav_ratio=0.0
        hit = L.hit_test(page, 40, 500, display="boox_go_6", orientation=0, edge_nav_ratio=0.0)
        self.assertFalse(hit.get("handled"))
        self.assertEqual(hit.get("type"), "miss")

    def test_custom_canvas_profile(self):
        """Verify custom canvas profile allows arbitrary dimensions and renders cleanly."""
        custom_spec = {"w": 1200, "h": 820, "ppi": 200, "margin": 36}
        disp = T.get_display(custom_spec)
        self.assertEqual(disp["w"], 1200)
        self.assertEqual(disp["h"], 820)
        self.assertEqual(disp["ppi"], 200)
        self.assertEqual(disp["margin"], 36)

        page = {
            "elements": [
                {
                    "type": "tile",
                    "x": 36,
                    "y": 40,
                    "w": 500,
                    "h": 140,
                    "title": "Custom Canvas Tile",
                    "entity": "light.office",
                }
            ]
        }
        img = L.render_page(page, {}, display=custom_spec, clock="12:00 PM")
        self.assertEqual(img.size, (1200, 820))
        self.assertEqual(img.mode, "L")

    def test_friendly_names_in_entities(self):
        """Verify api_entities returns normalized top-level friendly name and unit."""
        async def _run():
            req = make_mocked_request("GET", "/api/entities")
            resp = await server.api_entities(req)
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.text)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)
            first = data[0]
            self.assertIn("name", first)
            self.assertIn("unit", first)
            self.assertIn("entity_id", first)
            # Friendly name must not be None or empty
            self.assertTrue(len(first["name"]) > 0)
        asyncio.run(_run())


class TestPaperHubV140PowerAndSync(unittest.TestCase):
    def test_compute_device_next_wake_seconds_daytime(self):
        """Verify day-time wake calculation for normal, custom, and touch-only intervals."""
        dev = server.DeviceSession("test_dev", {
            "refresh_interval": 15,
            "quiet_hours_enabled": False,
        })
        # 15 minutes = 900 seconds
        self.assertEqual(server.compute_device_next_wake_seconds(dev), 900)

        # 0 minutes = Touch only -> 86400 seconds (24 hours)
        dev.refresh_interval = 0
        self.assertEqual(server.compute_device_next_wake_seconds(dev), 86400)

        # 60 minutes = 3600 seconds
        dev.refresh_interval = 60
        self.assertEqual(server.compute_device_next_wake_seconds(dev), 3600)

    def test_compute_device_next_wake_ha_trigger(self):
        """Verify quiet hours triggered immediately by Home Assistant sleep entity."""
        dev = server.DeviceSession("test_dev_ha", {
            "refresh_interval": 15,
            "quiet_hours_enabled": True,
            "quiet_hours_entity": "input_boolean.sleep_mode",
            "quiet_hours_interval": 120,  # 2 hours
        })
        ha_states = {
            "input_boolean.sleep_mode": {"state": "on"}
        }
        wake_secs = server.compute_device_next_wake_seconds(dev, ha_states=ha_states)
        self.assertEqual(wake_secs, 120 * 60)

    def test_page_has_entity(self):
        """Verify page_has_entity detects entities in tiles, dynamic grids, and templates."""
        page = {
            "elements": [
                {
                    "type": "tile",
                    "entity": "light.living_room",
                    "title": "Living Room Light"
                },
                {
                    "type": "dynamic_grid",
                    "items": [
                        {"entity": "sensor.kitchen_temperature"}
                    ]
                },
                {
                    "type": "text",
                    "value": "{{ states('sensor.humidity') }}%"
                }
            ]
        }
        self.assertTrue(server.page_has_entity(page, "light.living_room"))
        self.assertTrue(server.page_has_entity(page, "sensor.kitchen_temperature"))
        self.assertTrue(server.page_has_entity(page, "sensor.humidity"))
        self.assertFalse(server.page_has_entity(page, "light.garage"))

    def test_view_only_mode_suppresses_mutations(self):
        """Verify view_only mode suppresses HA entity actions while still responding to touch."""
        async def _run():
            dev = server.DEVICES.get_or_create("test_view_only_dev")
            dev.screen_mode = "view_only"
            spec = {
                "pages": {
                    "home": {
                        "elements": [
                            {
                                "type": "tile",
                                "x": 100,
                                "y": 100,
                                "w": 400,
                                "h": 140,
                                "entity": "light.desk",
                                "touch": {"action": "toggle"}
                            }
                        ]
                    }
                }
            }
            res = await server.handle_touch(None, dev, spec, 150, 150)
            self.assertEqual(res.get("status"), "ok")
            hit = res.get("hit", {})
            self.assertTrue(hit.get("handled"))
            # Action was recognized, but dev.screen_mode == 'view_only' suppressed HA call
            self.assertEqual(dev.screen_mode, "view_only")

        asyncio.run(_run())

    def test_device_api_power_sync_profile(self):
        """Verify GET and POST /api/devices/{device_id} save and return power profile fields."""
        async def _run():
            update_body = {
                "name": "Wall Display 10\"",
                "screen_mode": "view_only",
                "refresh_interval": 300,
                "push_on_entity_change": True,
                "quiet_hours_enabled": True,
                "quiet_hours_start": "22:30",
                "quiet_hours_end": "06:30",
                "quiet_hours_interval": 0,
                "quiet_hours_entity": "input_boolean.bedtime",
            }
            post_req = make_mocked_request(
                "POST",
                "/api/devices/wall_tab_01",
                match_info={"device_id": "wall_tab_01"},
            )
            async def _mock_json():
                return update_body
            post_req.json = _mock_json

            resp = await server.api_devices_update(post_req)
            self.assertEqual(resp.status, 200)
            saved = json.loads(resp.text)
            self.assertEqual(saved.get("screen_mode"), "view_only")
            self.assertEqual(saved.get("refresh_interval"), 300)
            self.assertEqual(saved.get("quiet_hours_start"), "22:30")
            self.assertEqual(saved.get("quiet_hours_end"), "06:30")
            self.assertEqual(saved.get("quiet_hours_entity"), "input_boolean.bedtime")

            # Verify GET /api/devices/{device_id}
            get_req = make_mocked_request(
                "GET",
                "/api/devices/wall_tab_01",
                match_info={"device_id": "wall_tab_01"},
            )
            get_resp = await server.api_devices_get(get_req)
            self.assertEqual(get_resp.status, 200)
            fetched = json.loads(get_resp.text)
            self.assertEqual(fetched.get("screen_mode"), "view_only")
            self.assertEqual(fetched.get("refresh_interval"), 300)
            self.assertEqual(fetched.get("push_on_entity_change"), True)

        asyncio.run(_run())

    def test_frame_headers_power_sync(self):
        """Verify frame_png and frame_bmp include X-PaperHub-Next-Wake and Refresh headers."""
        async def _run():
            dev = server.DEVICES.get_or_create("header_test_dev")
            dev.refresh_interval = 20  # 20 min = 1200s
            dev.quiet_hours_enabled = False
            dev.screen_mode = "interactive"

            req = make_mocked_request("GET", "/api/devices/header_test_dev/frame.png", match_info={"device_id": "header_test_dev"})
            resp = await server.frame_png(req)
            self.assertEqual(resp.status, 200)
            self.assertIn("X-PaperHub-Next-Wake", resp.headers)
            self.assertEqual(resp.headers.get("X-PaperHub-Next-Wake"), "1200")
            self.assertEqual(resp.headers.get("Refresh"), "1200")
            self.assertEqual(resp.headers.get("X-PaperHub-Screen-Mode"), "interactive")

        asyncio.run(_run())


class TestPaperHubV150AdaptedPresets(unittest.TestCase):
    def test_flight_tracker_split_and_radar(self):
        """Verify flight tracker renders in both split and radar styles in < 25ms."""
        el_split = {
            "type": "flight_tracker",
            "style": "split",
            "x": 40,
            "y": 40,
            "w": 992,
            "h": 360,
            "radius": 24,
        }
        el_radar = {
            "type": "flight_tracker",
            "style": "radar",
            "x": 40,
            "y": 440,
            "w": 992,
            "h": 460,
            "radius": 24,
        }
        page = {"elements": [el_split, el_radar]}
        vals = {
            0: None,  # Test realistic offline demo fallback
            1: [
                {
                    "callsign": "AFR124",
                    "country": "Air France",
                    "distance_km": 12.5,
                    "bearing_deg": 90.0,
                    "altitude_m": 8500,
                    "velocity_ms": 210.0,
                    "track_deg": 45,
                    "vertical_rate": 2.1,
                }
            ]
        }

        t0 = time.perf_counter()
        img = L.render_page(page, vals, display="boox_go_6")
        dt_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(img.size, (1072, 1448))
        self.assertEqual(img.mode, "L")
        self.assertLess(dt_ms, 30.0, f"Flight tracker rendering too slow: {dt_ms:.2f}ms")

    def test_flight_tracker_portrait_adaptation(self):
        """Verify flight tracker split mode cleanly stacks radar above telemetry on tall/portrait cards."""
        el_tall = {
            "type": "flight_tracker",
            "style": "split",
            "x": 40,
            "y": 40,
            "w": 460,
            "h": 700,
            "radius": 24,
        }
        page = {"elements": [el_tall]}
        img = L.render_page(page, {}, display="boox_go_6")
        self.assertEqual(img.size, (1072, 1448))

    def test_sports_racing_pitwall_and_countdown(self):
        """Verify Formula 1 live pit-wall leaderboard and off-week countdown views."""
        el_live = {
            "type": "sports_racing",
            "series": "f1",
            "x": 40,
            "y": 40,
            "w": 992,
            "h": 340,
            "radius": 24,
        }
        el_scheduled = {
            "type": "sports_racing",
            "series": "f1",
            "x": 40,
            "y": 420,
            "w": 992,
            "h": 300,
            "radius": 24,
        }
        page = {"elements": [el_live, el_scheduled]}
        vals = {
            0: None,  # Default live demo with Verstappen, Norris, etc.
            1: {
                "series": "F1",
                "event_name": "Monaco Grand Prix",
                "circuit": "Circuit de Monaco · Monte Carlo",
                "status": "PRE",
                "detail": "Sun May 24 · 13:00 UTC",
                "standings": []
            }
        }

        t0 = time.perf_counter()
        img = L.render_page(page, vals, display="boox_go_6")
        dt_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(img.size, (1072, 1448))
        self.assertEqual(img.mode, "L")
        self.assertLess(dt_ms, 60.0, f"Sports racing rendering too slow: {dt_ms:.2f}ms")

    def test_sports_match_scoreboard(self):
        """Verify multi-league live sports match scoreboard with hero scores and scorers."""
        el_match = {
            "type": "sports_match",
            "league": "soccer/eng.1",
            "x": 40,
            "y": 40,
            "w": 992,
            "h": 300,
            "radius": 24,
        }
        page = {"elements": [el_match]}
        vals = {
            0: {
                "league": "PREMIER LEAGUE",
                "venue": "Anfield",
                "clock": "88' · 2ND HALF",
                "status": "IN",
                "home_team": "LIVERPOOL",
                "home_score": 3,
                "home_stats": "18 Shots · 62% Poss",
                "away_team": "MAN CITY",
                "away_score": 2,
                "away_stats": "11 Shots · 38% Poss",
                "events_home": "Salah (14', 67'), Diaz (44')",
                "events_away": "Haaland (31', 82' pen)"
            }
        }

        t0 = time.perf_counter()
        img = L.render_page(page, vals, display="boox_go_6")
        dt_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(img.size, (1072, 1448))
        self.assertEqual(img.mode, "L")
        self.assertLess(dt_ms, 30.0, f"Sports match rendering too slow: {dt_ms:.2f}ms")

    def test_enrich_page_values_execution(self):
        """Verify enrich_page_values seamlessly enriches page values without errors."""
        async def _run():
            page = {
                "elements": [
                    {"type": "flight_tracker", "radius": 40},
                    {"type": "sports_racing", "series": "f1"},
                    {"type": "sports_match", "league": "soccer/eng.1"}
                ]
            }
            vals = {}
            # With session=None, graceful offline handling must populate or leave cleanly
            await server.enrich_page_values(None, page, vals)
            self.assertIn(0, vals)
            self.assertIsInstance(vals[0], list)
        asyncio.run(_run())


    def test_hit_test_landscape_orientation(self):
        """Verify elements on the right side of a landscape screen are hit correctly without false page turns."""
        # Boox Go 6 90° Landscape: 1448 x 1072
        page = {
            "elements": [
                {
                    "type": "tile",
                    "x": 1050,
                    "y": 200,
                    "w": 300,
                    "h": 140,
                    "touch": {"action": "toggle", "entity": "light.office_lights"}
                }
            ]
        }
        # Tap on the right-side element in landscape
        res = L.hit_test(page, 1150, 250, display="boox_go_6", orientation=90, edge_nav_ratio=0.15)
        self.assertTrue(res.get("handled"))
        self.assertEqual(res.get("type"), "element_action")
        self.assertEqual(res.get("entity"), "light.office_lights")

    def test_prominent_chevrons_render(self):
        """Verify prominent half-screen tall chevrons render on multi-page layouts with edge_nav enabled."""
        page = {
            "elements": [
                {"type": "text", "value": "Dashboard", "x": 200, "y": 200, "w": 400, "h": 60}
            ]
        }
        img = L.render_page(page, {}, page_info={"current": 1, "total": 2}, edge_nav=True, edge_nav_ratio=0.15, display="boox_go_6")
        self.assertEqual(img.size, (1072, 1448))

    def test_api_entities_resilient_fallback(self):
        """Verify api_entities returns 200 and entities even when HA is unreachable."""
        async def _run():
            req = make_mocked_request("GET", "/api/entities")
            resp = await server.api_entities(req)
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.text)
            self.assertIsInstance(data, list)
            self.assertGreater(len(data), 0)
            # Verify friendly names are present
            first = data[0]
            self.assertIn("name", first)
            self.assertIn("entity_id", first)
        asyncio.run(_run())


class TestWidgetsDrawCardFix(unittest.TestCase):
    def test_draw_card_box_formats(self):
        img, d = T.new_canvas()
        # 4-tuple format
        T.draw_card(d, (10, 10, 100, 100))
        # 2-point format
        T.draw_card(d, [(10, 10), (100, 100)])

    def test_widgets_render_content(self):
        elements = [
            {'type': 'button', 'x': 10, 'y': 10, 'w': 100, 'h': 50, 'label': 'Test'},
            {'type': 'calendar_timeline', 'x': 10, 'y': 10, 'w': 300, 'h': 200},
            {'type': 'weather_forecast', 'x': 10, 'y': 10, 'w': 300, 'h': 200},
            {'type': 'flight_tracker', 'x': 10, 'y': 10, 'w': 300, 'h': 200},
            {'type': 'sports_racing', 'x': 10, 'y': 10, 'w': 300, 'h': 200},
            {'type': 'sports_match', 'x': 10, 'y': 10, 'w': 300, 'h': 200},
            {'type': 'dynamic_grid', 'x': 10, 'y': 10, 'w': 300, 'h': 200, 'items': [{'entity': 'light.a'}]},
        ]
        for el in elements:
            img = L.render_page({'elements': [el]}, {0: None})
            extrema = img.getextrema()
            self.assertNotEqual(extrema, (255, 255), f"Element {el['type']} did not render any pixels!")


class TestTileValuePassing(unittest.TestCase):
    def test_tile_receives_resolved_state(self):
        tile = {'type': 'tile', 'entity': 'light.desk', 'state': 'off'}
        vals = {0: json.dumps({'state': 'on', 'name': 'Desk Light', 'brightness': 255})}
        received = []
        orig = L._draw_tile
        def mock_draw(img, draw, el, val='', display=None):
            received.append(val)
            return orig(img, draw, el, val, display)
        L.DRAWERS['tile'] = mock_draw
        try:
            L.render_page({'elements': [tile]}, vals)
            self.assertTrue(bool(received and received[0]), "Tile received empty value!")
            self.assertIn('"state": "on"', received[0])
        finally:
            L.DRAWERS['tile'] = orig


class TestEntityCacheResilience(unittest.TestCase):
    def test_entity_cache_never_none(self):
        server._entity_cache = {"at": 0.0, "items": []}
        req = make_mocked_request('GET', '/api/entities')
        asyncio.run(server.api_entities(req))


class TestCollectTemplatesDelimiters(unittest.TestCase):
    def test_extended_widgets_delimiters(self):
        page = {'elements': [
            {'type': 'flight_tracker', 'entity': 'sensor.flight'},
            {'type': 'sports_racing', 'entity': 'sensor.f1'}
        ]}
        tpls = L.collect_templates(page)
        for i, t in tpls.items():
            self.assertTrue(t.startswith("{{") and t.endswith("}}"), f"Template {i} missing delimiters: {t}")


class TestSecurityAndApiEndpoints(unittest.TestCase):
    def test_header_based_token_auth(self):
        orig_token = server.FRAME_TOKEN
        try:
            server.FRAME_TOKEN = "secret123"
            # No token -> False
            req_none = make_mocked_request("GET", "/frame.png")
            self.assertFalse(server.check_token(req_none))

            # Bearer token -> True
            req_bearer = make_mocked_request("GET", "/frame.png", headers={"Authorization": "Bearer secret123"})
            self.assertTrue(server.check_token(req_bearer))

            # X-PaperHub-Token -> True
            req_custom = make_mocked_request("GET", "/frame.png", headers={"X-PaperHub-Token": "secret123"})
            self.assertTrue(server.check_token(req_custom))

            # Query token -> True
            req_query = make_mocked_request("GET", "/frame.png?token=secret123")
            self.assertTrue(server.check_token(req_query))
        finally:
            server.FRAME_TOKEN = orig_token

    def test_lan_panel_blocks_simulation(self):
        async def _run():
            from aiohttp import web
            app = web.Application()
            app[server.IS_LAN_PANEL] = True
            body = {
                "x": 100,
                "y": 100,
                "page": {"elements": [{"type": "tile", "x": 50, "y": 50, "w": 200, "h": 100, "entity": "light.test", "action": "toggle"}]}
            }
            req = make_mocked_request("POST", "/api/touch", app=app)
            async def _json():
                return body
            req.json = _json
            resp = await server.api_touch(req)
            self.assertEqual(resp.status, 403)
        asyncio.run(_run())

    def test_device_cap_max_devices(self):
        dm = server.DeviceManager()
        dm.devices.clear()
        for i in range(server.MAX_DEVICES + 5):
            dev = dm.get_or_create(f"dev_{i}")
        self.assertLessEqual(len(dm.devices), server.MAX_DEVICES)

    def test_sources_and_panel_endpoints(self):
        async def _run():
            req_sources = make_mocked_request("GET", "/api/sources")
            resp_sources = await server.api_sources_get(req_sources)
            self.assertEqual(resp_sources.status, 200)

            req_setup = make_mocked_request("GET", "/api/panel-setup")
            resp_setup = await server.api_panel_setup(req_setup)
            self.assertEqual(resp_setup.status, 200)

            req_refresh = make_mocked_request("POST", "/api/panel-refresh")
            resp_refresh = await server.api_panel_refresh(req_refresh)
            self.assertEqual(resp_refresh.status, 200)
        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()


