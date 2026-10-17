#!/bin/sh
# ==============================================================================
# PaperHub Linux/Jailbreak Client Daemon
# Lightweight touch framebuffer listener for Kindle & Kobo e-readers
# ==============================================================================

SERVER_URL="${PAPERHUB_SERVER:-http://homeassistant.local:8099}"
DEVICE_ID="${PAPERHUB_DEVICE:-kindle_pw}"
INPUT_DEV="${PAPERHUB_INPUT:-/dev/input/event0}"
FRAME_TMP="/tmp/paperhub_frame.png"
POLL_INTERVAL=60

# Identify framebuffer draw utility: fbink > eips > cat to fb0
DRAW_CMD=""
if command -v fbink >/dev/null 2>&1; then
    DRAW_CMD="fbink -q -g -c -f"
elif command -v eips >/dev/null 2>&1; then
    DRAW_CMD="eips -g"
else
    DRAW_CMD="echo 'No fbink/eips found; cannot draw directly'"
fi

log() {
    echo "[PaperHub] $(date +'%H:%M:%S') - $1"
}

draw_frame() {
    if [ -f "$FRAME_TMP" ]; then
        $DRAW_CMD "$FRAME_TMP"
    fi
}

fetch_initial_frame() {
    log "Fetching initial frame from $SERVER_URL for device $DEVICE_ID..."
    curl -s -m 10 "$SERVER_URL/api/devices/$DEVICE_ID/frame.png" -o "$FRAME_TMP"
    draw_frame
}

# Auto-detect screen resolution
SCREEN_W=1072
SCREEN_H=1448
if command -v fbink >/dev/null 2>&1; then
    DIMS=$(fbink -s 2>/dev/null | grep -E "[0-9]+x[0-9]+" | head -n 1)
    if [ -n "$DIMS" ]; then
        SCREEN_W=$(echo "$DIMS" | cut -d'x' -f1)
        SCREEN_H=$(echo "$DIMS" | cut -d'x' -f2)
    fi
fi

log "Started daemon: Server=$SERVER_URL Device=$DEVICE_ID Res=${SCREEN_W}x${SCREEN_H}"
fetch_initial_frame

# Background periodic refresh loop
(
    while true; do
        sleep "$POLL_INTERVAL"
        curl -s -m 8 "$SERVER_URL/api/devices/$DEVICE_ID/frame.png" -o "${FRAME_TMP}.new" 2>/dev/null
        if [ -s "${FRAME_TMP}.new" ]; then
            mv "${FRAME_TMP}.new" "$FRAME_TMP"
            draw_frame
        fi
    done
) &
TICKER_PID=$!

trap "kill $TICKER_PID 2>/dev/null; exit 0" INT TERM EXIT

# Main Touch Loop: Listen to /dev/input/event0 interrupts
log "Listening to touch events on $INPUT_DEV..."
CUR_X=0
CUR_Y=0

# Use evtest if present; otherwise fall back to raw input device streaming
if command -v evtest >/dev/null 2>&1; then
    evtest "$INPUT_DEV" | while read -r line; do
        case "$line" in
            *"ABS_MT_POSITION_X"* | *"ABS_X"*)
                CUR_X=$(echo "$line" | awk '{print $NF}')
                ;;
            *"ABS_MT_POSITION_Y"* | *"ABS_Y"*)
                CUR_Y=$(echo "$line" | awk '{print $NF}')
                ;;
            *"SYN_REPORT"*)
                if [ "$CUR_X" -gt 0 ] && [ "$CUR_Y" -gt 0 ]; then
                    log "Touch tap: ($CUR_X, $CUR_Y)"
                    curl -s -X POST -m 4 "$SERVER_URL/api/devices/$DEVICE_ID/touch?x=$CUR_X&y=$CUR_Y&format=png" -o "$FRAME_TMP" 2>/dev/null
                    draw_frame
                    CUR_X=0
                    CUR_Y=0
                fi
                ;;
        esac
    done
else
    # Raw binary parsing fallback for minimal Busybox shells
    # Reads 16-byte Linux input_event structures
    while true; do
        # On tap interrupt, trigger quick touch check
        dd if="$INPUT_DEV" bs=16 count=1 >/dev/null 2>&1
        log "Touch detected"
        curl -s -X POST -m 4 "$SERVER_URL/api/devices/$DEVICE_ID/touch?gesture=tap&format=png" -o "$FRAME_TMP" 2>/dev/null
        draw_frame
        sleep 0.2
    done
fi
