#!/usr/bin/env sh
set -e

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[TuneBridge] Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

export TUNEBRIDGE_HOST=0.0.0.0
echo "[TuneBridge] Wi-Fi mode: open the printed LAN address on your phone."
exec .venv/bin/python run.py
