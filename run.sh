#!/usr/bin/env bash
# Portmint Pulse launcher. Just runs the standard-library app — no venv, no pip.
# Usage: ./run.sh [--port 8787] [--no-browser]
cd "$(dirname "$0")" || exit 1
exec python3 app.py "$@"
