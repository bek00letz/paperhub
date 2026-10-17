# PaperHub for Linux & Jailbroken E-Readers

This directory contains standalone, lightweight daemons for running PaperHub on jailbroken e-readers (Kindle, Kobo, etc.) without requiring Android or X11.

## Supported Devices

- **Kindle Paperwhite (2, 3, 4, 11th Gen)**
- **Kindle Oasis & Kindle Voyage**
- **Kindle Touch & Kindle Basic**
- **Kobo Clara, Libra, Aura, Forma, Elipsa** (Nickel / Plato / KOReader environment)
- **reMarkable 1 & 2** (Toltec / Linux)

---

## Architecture & Battery Preservation

Unlike running a heavy web browser on an embedded SoC, the PaperHub daemon uses virtually **0% CPU** when idle:
1. It blocks in the Linux kernel on `/dev/input/event0` (touch digitizer interrupt).
2. When a finger taps the screen, the kernel wakes the process.
3. The daemon sends coordinate `(X, Y)` to Home Assistant (`POST /api/devices/{id}/touch`).
4. The server responds with the updated 16-level Carta bitmap in ~20ms.
5. The daemon blits the bitmap directly to the framebuffer (`/dev/fb0`) using `fbink` in Regal mode.
6. The device immediately returns to deep CPU suspend.

---

## Kindle Jailbreak Setup

### Prerequisites
- Jailbroken Kindle with **KUAL** (Kindle Unified Application Launcher) or SSH access.
- **FBInk** installed (comes bundled with Mobileread NiLuJe tools / KUAL helper).
- `curl` installed (standard on modern Kindle firmware).

### Installation
1. Copy `paperhub-daemon.sh` to `/mnt/us/paperhub/paperhub-daemon.sh`:
   ```bash
   mkdir -p /mnt/us/paperhub
   chmod +x /mnt/us/paperhub/paperhub-daemon.sh
   ```

2. Configure your Home Assistant server IP and Device ID:
   ```bash
   export PAPERHUB_SERVER="http://192.168.1.100:8099"
   export PAPERHUB_DEVICE="kindle_pw"
   ```

3. Test running the daemon in foreground:
   ```bash
   /mnt/us/paperhub/paperhub-daemon.sh
   ```

4. Auto-start on boot:
   Add to `/etc/upstart/paperhub.conf` (or `/mnt/us/extensions/onboot` depending on firmware version):
   ```upstart
   start on started lab126_gui
   stop on stopping lab126_gui

   respawn
   exec /mnt/us/paperhub/paperhub-daemon.sh
   ```

---

## Kobo Nickel / Plato Setup

### Prerequisites
- Kobo e-reader with Telnet/SSH enabled or **KFMon** / **NickelMenu**.
- `fbink` installed in `/usr/bin/fbink`.

### Installation
1. Stop the default Kobo Nickel reading interface:
   ```bash
   killall -TERM nickel
   ```

2. Launch `paperhub-daemon.sh`:
   ```bash
   PAPERHUB_SERVER="http://192.168.1.100:8099" PAPERHUB_DEVICE="kobo_clara" ./paperhub-daemon.sh &
   ```

---

## Verifying Touch Coordinates

If your device uses a different input event file, find it by checking:
```bash
cat /proc/bus/input/devices
```
Look for `Handlers=event0` or `event1` next to "touchscreen", then export:
```bash
export PAPERHUB_INPUT="/dev/input/event1"
```
