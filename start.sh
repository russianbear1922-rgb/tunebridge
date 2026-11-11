#!/usr/bin/env sh
set -e

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
    echo "[TuneBridge] Creating virtual environment..."
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

exec .venv/bin/python run.py
