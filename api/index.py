"""Vercel serverless entrypoint for the MelateAI Pro FastAPI backend.

Exposes the ASGI ``app`` so Vercel's Python runtime can serve it. All routes
are defined with the ``/api`` prefix inside the FastAPI app, and ``vercel.json``
rewrites ``/api/*`` to this function.
"""
import os
import sys

# Make the backend package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Default to an ephemeral SQLite DB on serverless (auto-seeded at startup from
# the bundled template). Override with a PostgreSQL DATABASE_URL for production.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/melateai.db")

from app.main import app  # noqa: E402

# Vercel's Python runtime serves the ASGI `app` object directly.
