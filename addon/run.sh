#!/usr/bin/with-contenv bashio
set -e

bashio::config.has_value 'frame_token' && export FRAME_TOKEN="$(bashio::config 'frame_token')" || true
export REFRESH_SECONDS="$(bashio::config 'refresh_seconds')"
export HA_BASE="http://supervisor/core"
export HA_TOKEN="${SUPERVISOR_TOKEN}"
export DATA_DIR="/data"

bashio::log.info "Starting PaperHub (Ambient E-Ink Touch Controller)"
exec python3 -u /opt/paperhub/server.py
