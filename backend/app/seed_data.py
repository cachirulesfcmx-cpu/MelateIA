"""Reusable seeding logic shared by the CLI seed script and the app bootstrap.

Loads the bundled historical CSVs into the database and creates a demo user.
Safe to call repeatedly: it only imports draws/users that don't already exist.
"""
from __future__ import annotations

import os

from sqlalchemy.orm import Session

from .models import User, Draw, CsvUpload
from .auth import hash_password
from .engine.game_config import GAMES
from .engine.data_engine import parse_csv, numbers_to_str

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DEMO_EMAIL = "demo@melateai.pro"
DEMO_PASSWORD = "demo1234"


def ensure_demo_user(db: Session) -> User:
    demo = db.query(User).filter(User.email == DEMO_EMAIL).first()
    if not demo:
        demo = User(name="Demo MelateAI", email=DEMO_EMAIL, password_hash=hash_password(DEMO_PASSWORD))
        db.add(demo)
        db.commit()
        db.refresh(demo)
    return demo


def seed_database(db: Session, log=lambda *_: None) -> dict:
    demo = ensure_demo_user(db)
    summary = {}
    for key, cfg in GAMES.items():
        path = os.path.join(DATA_DIR, cfg.seed_file)
        if not os.path.exists(path):
            log(f"! CSV no encontrado para {key}: {path}")
            continue
        existing = {
            r.draw_number for r in db.query(Draw.draw_number).filter(Draw.game_type == key).all()
        }
        with open(path, "rb") as fh:
            rows = parse_csv(fh.read(), key)
        objs = []
        for r in rows:
            if r["draw_number"] in existing:
                continue
            objs.append(Draw(
                game_type=key,
                draw_number=r["draw_number"],
                draw_date=r["draw_date"],
                numbers=numbers_to_str(r["numbers"]),
                additional=r["additional"],
                source="csv",
                created_by=demo.id,
            ))
            existing.add(r["draw_number"])
        try:
            if objs:
                db.bulk_save_objects(objs)  # fast batch insert
                db.add(CsvUpload(user_id=demo.id, filename=cfg.seed_file, game_type=key, rows_imported=len(objs)))
            db.commit()
        except Exception as e:  # concurrent seeding race, etc.
            db.rollback()
            log(f"! {cfg.label}: seeding skipped ({e})")
        summary[key] = len(objs)
        log(f"✓ {cfg.label}: {len(objs)} sorteos importados ({len(rows)} en CSV)")
    return summary


def seed_if_empty(db: Session) -> bool:
    """Seed only when the database has no draws yet. Returns True if it seeded."""
    try:
        has_draws = db.query(Draw.id).first() is not None
    except Exception:
        has_draws = True  # table may not exist yet; create_all handles it elsewhere
    if has_draws:
        ensure_demo_user(db)
        return False
    seed_database(db)
    return True
