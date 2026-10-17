#!/usr/bin/env python3
"""PaperHub Linux Evdev Daemon.

Reads touch events directly from Linux /dev/input/event0, scales coordinates
to display dimensions, posts touch to PaperHub server, and draws the returned
16-level grayscale frame using fbink or /dev/fb0.
"""
import os
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import json

SERVER_URL = os.environ.get("PAPERHUB_SERVER", "http://homeassistant.local:8099")
DEVICE_ID = os.environ.get("PAPERHUB_DEVICE", "kindle_pw")
INPUT_DEV = os.environ.get("PAPERHUB_INPUT", "/dev/input/event0")
FRAME_TMP = "/tmp/paperhub_frame.png"

# Detect input_event struct packing (32-bit vs 64-bit / y2038)
is_64bit = sys.maxsize > 2**32
EVENT_FORMAT = "qqHHi" if is_64bit else "IIHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_ABS = 0x03
EV_SYN = 0x00
SYN_REPORT = 0x00
ABS_X = 0x00
ABS_Y = 0x01
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36


_last_etag = ""


def draw_frame(path=FRAME_TMP):
    """Draw frame to e-ink screen using fbink or eips."""
    if subprocess.call(["which", "fbink"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["fbink", "-q", "-g", "-c", "-f", path])
    elif subprocess.call(["which", "eips"], stdout=subprocess.DEVNULL) == 0:
        subprocess.call(["eips", "-g", path])


def fetch_frame():
    global _last_etag
    url = f"{SERVER_URL}/api/devices/{DEVICE_ID}/frame.png"
    headers = {}
    if _last_etag:
        headers["If-None-Match"] = f'"{_last_etag}"'
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            etag = resp.headers.get("ETag", "").strip('" ')
            if etag:
                _last_etag = etag
            data = resp.read()
            if data:
                with open(FRAME_TMP, "wb") as f:
                    f.write(data)
                draw_frame()
    except urllib.error.HTTPError as e:
        if e.code == 304:
            # Content unchanged: preserve battery and skip draw
            return
        print(f"[PaperHub] HTTP error: {e}", file=sys.stderr)
    except Exception as e:
        print(f"[PaperHub] Fetch failed: {e}", file=sys.stderr)


def send_touch(x, y, gesture=""):
    global _last_etag
    url = f"{SERVER_URL}/api/devices/{DEVICE_ID}/touch?format=png"
    data = json.dumps({"x": x, "y": y, "gesture": gesture}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            etag = resp.headers.get("ETag", "").strip('" ')
            if etag:
                _last_etag = etag
            content_type = resp.headers.get("Content-Type", "")
            if "image/png" in content_type:
                data_body = resp.read()
                if data_body:
                    with open(FRAME_TMP, "wb") as f:
                        f.write(data_body)
                    draw_frame()
            else:
                fetch_frame()
    except Exception as e:
        print(f"[PaperHub] Touch post failed: {e}", file=sys.stderr)


def main():
    print(f"[PaperHub] Starting Evdev Daemon for {DEVICE_ID} on {INPUT_DEV}...")
    fetch_frame()

    if not os.path.exists(INPUT_DEV):
        print(f"[PaperHub] Error: Input device {INPUT_DEV} not found.", file=sys.stderr)
        sys.exit(1)

    cur_x, cur_y = 0, 0
    with open(INPUT_DEV, "rb") as ev_file:
        while True:
            data = ev_file.read(EVENT_SIZE)
            if not data or len(data) < EVENT_SIZE:
                continue
            tv_sec, tv_usec, ev_type, ev_code, ev_val = struct.unpack(EVENT_FORMAT, data)

            if ev_type == EV_ABS:
                if ev_code in (ABS_X, ABS_MT_POSITION_X):
                    cur_x = ev_val
                elif ev_code in (ABS_Y, ABS_MT_POSITION_Y):
                    cur_y = ev_val
            elif ev_type == EV_SYN and ev_code == SYN_REPORT:
                if cur_x > 0 and cur_y > 0:
                    print(f"[PaperHub] Tap registered: ({cur_x}, {cur_y})")
                    send_touch(cur_x, cur_y, "tap")
                    cur_x, cur_y = 0, 0


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        pass
