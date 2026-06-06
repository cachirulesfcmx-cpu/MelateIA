#!/usr/bin/env bash
# Run backend (FastAPI) + frontend (Vite) together for local development.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- backend ----
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
  echo "› Creating Python venv…"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
if [ ! -f "melateai.db" ]; then
  echo "› Seeding database from CSVs…"
  python seed.py
fi
echo "› Starting FastAPI on http://127.0.0.1:8000"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# ---- frontend ----
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
  echo "› Installing frontend deps…"
  npm install
fi
echo "› Starting Vite on http://127.0.0.1:5173"
npm run dev &
FRONTEND_PID=$!

trap "echo '› Stopping…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM
wait
