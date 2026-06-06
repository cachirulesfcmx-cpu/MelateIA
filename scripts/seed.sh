#!/usr/bin/env bash
# (Re)seed the database from the bundled historical CSV files.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
[ -d ".venv" ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python seed.py
