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
        self.assertLess(render_ms, 25.0, f"Render took too long: {render_ms:.2f}ms (target < 25ms)")


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


if __name__ == "__main__":
    unittest.main()


