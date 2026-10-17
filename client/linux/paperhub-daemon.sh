#!/bin/sh
# ==============================================================================
# PaperHub Linux/Jailbreak Client Daemon
# Lightweight touch framebuffer listener for Kindle & Kobo e-readers
# ==============================================================================

SERVER_URL="${PAPERHUB_SERVER:-http://homeassistant.local:8099}"
DEVICE_ID="${PAPERHUB_DEVICE:-kindle_pw}"
INPUT_DEV="${PAPERHUB_INPUT:-/dev/input/event0}"
FRAME_TMP="/tmp/paperhub_frame.png"
ETAG_FILE="/tmp/paperhub.etag"
HEADERS_FILE="/tmp/paperhub_headers.txt"
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

fetch_frame() {
    PREV_ETAG=""
    if [ -f "$ETAG_FILE" ]; then
        PREV_ETAG=$(cat "$ETAG_FILE" 2>/dev/null | tr -d '\r\n"')
    fi

    if [ -n "$PREV_ETAG" ]; then
        HTTP_STATUS=$(curl -s -m 10 -D "$HEADERS_FILE" -H "If-None-Match: \"$PREV_ETAG\"" "$SERVER_URL/api/devices/$DEVICE_ID/frame.png" -o "${FRAME_TMP}.new" -w "%{http_code}")
    else
        HTTP_STATUS=$(curl -s -m 10 -D "$HEADERS_FILE" "$SERVER_URL/api/devices/$DEVICE_ID/frame.png" -o "${FRAME_TMP}.new" -w "%{http_code}")
    fi
    
    if [ "$HTTP_STATUS" = "304" ]; then
        # Content unchanged: skip disk write and e-ink refresh to preserve battery
        rm -f "${FRAME_TMP}.new"
        return 0
    elif [ "$HTTP_STATUS" = "200" ] && [ -s "${FRAME_TMP}.new" ]; then
        mv "${FRAME_TMP}.new" "$FRAME_TMP"
        NEW_ETAG=$(grep -i '^etag:' "$HEADERS_FILE" 2>/dev/null | awk '{print $2}' | tr -d '\r\n"')
        if [ -n "$NEW_ETAG" ]; then
            echo "$NEW_ETAG" > "$ETAG_FILE"
        fi
        log "Frame updated (ETag=$NEW_ETAG); drawing to e-ink screen."
        draw_frame
        return 0
    else
        log "Frame fetch returned HTTP $HTTP_STATUS"
        rm -f "${FRAME_TMP}.new"
        return 1
    fi
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
fetch_frame

# Background periodic refresh loop (checks conditional ETag every 60s)
(
    while true; do
        sleep "$POLL_INTERVAL"
        fetch_frame
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
                    if curl -s -X POST -m 4 "$SERVER_URL/api/devices/$DEVICE_ID/touch?x=$CUR_X&y=$CUR_Y&format=png" -o "${FRAME_TMP}.touch" 2>/dev/null && [ -s "${FRAME_TMP}.touch" ]; then
                        mv "${FRAME_TMP}.touch" "$FRAME_TMP"
                        draw_frame
                    else
                        rm -f "${FRAME_TMP}.touch"
                    fi
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
        if curl -s -X POST -m 4 "$SERVER_URL/api/devices/$DEVICE_ID/touch?gesture=tap&format=png" -o "${FRAME_TMP}.touch" 2>/dev/null && [ -s "${FRAME_TMP}.touch" ]; then
            mv "${FRAME_TMP}.touch" "$FRAME_TMP"
            draw_frame
        else
            rm -f "${FRAME_TMP}.touch"
        fi
        sleep 0.2
    done
fi
