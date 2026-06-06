"""Seed the database with historical draws from the shipped CSV files and a demo user.

Usage:
    python seed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal
from app.seed_data import seed_database, DEMO_EMAIL, DEMO_PASSWORD


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db, log=print)
        print(f"\n✓ Usuario demo: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print("Seed completado. Inicia el backend con: uvicorn app.main:app --reload")
    finally:
        db.close()


if __name__ == "__main__":
    main()
