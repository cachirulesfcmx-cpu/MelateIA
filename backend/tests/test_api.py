"""End-to-end API tests for MelateAI Pro (pytest).

Runs against a temporary SQLite database seeded from the bundled CSVs.
"""
import os
import tempfile

import pytest

# isolated temp DB before importing the app
_DB = os.path.join(tempfile.gettempdir(), "melateai_test_ci.db")
if os.path.exists(_DB):
    os.remove(_DB)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # don't throttle tests

from fastapi.testclient import TestClient  # noqa: E402
from app.database import Base, engine, SessionLocal  # noqa: E402
from app.seed_data import seed_database  # noqa: E402
import app.main as main  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_database(db, log=lambda *a: None)
    db.close()
    return TestClient(main.app)


def auth(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_seed_and_auth(client):
    h = auth(client, "demo@melateai.pro", "demo1234")
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200
    assert me.json()["user"]["is_admin"] is False


def test_admin_only_and_roles(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")
    # non-admin cannot add draws or access admin
    assert client.post("/api/draws", headers=uh, json={"game_type": "melate", "numbers": [1, 2, 3, 40, 41, 42], "draw_number": 90001}).status_code == 403
    assert client.get("/api/admin/users", headers=uh).status_code == 403
    # admin can
    assert client.post("/api/draws", headers=ah, json={"game_type": "melate", "numbers": [1, 2, 3, 40, 41, 42], "draw_number": 90001}).status_code == 200
    assert client.get("/api/admin/users", headers=ah).status_code == 200


def test_validation_returns_400(client):
    ah = auth(client, "admin@melateai.pro", "admin1234")
    assert client.post("/api/draws", headers=ah, json={"game_type": "melate", "numbers": [1, 1, 3, 40, 41, 42], "draw_number": 90002}).status_code == 400
    assert client.post("/api/draws", headers=ah, json={"game_type": "melate_retro", "numbers": [1, 2, 3, 40, 41, 42], "draw_number": 90002}).status_code == 400


@pytest.mark.parametrize("strategy", ["conservadora", "balanceada", "agresiva", "genetica", "anti_popular", "calientes", "frios", "hibrida", "adaptativa"])
def test_generate_all_strategies(client, strategy):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    r = client.post("/api/predictions/generate", headers=uh, json={"game_type": "melate", "strategy": strategy, "count": 2})
    assert r.status_code == 200, r.text
    combos = r.json()["combos"]
    assert len(combos) == 2
    for c in combos:
        assert len(c["numbers"]) == 6
        assert len(set(c["numbers"])) == 6
        assert all(1 <= n <= 56 for n in c["numbers"])
        assert 0.0 <= c["score"] <= 1.0
        assert c["features"]["even"] + c["features"]["odd"] == 6


def test_tracker_and_stats(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    for g in ["melate", "revancha", "melate_retro", "revanchita"]:
        assert client.get(f"/api/draws/stats?game_type={g}", headers=uh).status_code == 200
        t = client.get(f"/api/draws/number-tracker?game_type={g}", headers=uh)
        assert t.status_code == 200
        assert len(t.json()["overdue"]) > 0


def test_earnings_and_backtest(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    e = client.post("/api/earnings/estimate", headers=uh, json={"game_type": "melate", "combinations": 5, "cost_per_combination": 21})
    assert e.status_code == 200 and e.json()["jackpot_odds_one_in"] == 32468436
    b = client.post("/api/backtesting", headers=uh, json={"game_type": "melate", "strategy": "balanceada", "last_n": 6, "combos_per_draw": 2, "cost_per_combination": 21})
    assert b.status_code == 200


def test_official_draw_evaluates_all_and_analytics(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")
    client.post("/api/predictions/save", headers=uh, json={"game_type": "revancha", "strategy": "balanceada", "numbers": [2, 3, 12, 16, 20, 42]})
    res = client.post("/api/draws", headers=ah, json={"game_type": "revancha", "numbers": [2, 3, 12, 53, 54, 55], "draw_number": 90100})
    assert res.status_code == 200
    body = res.json()
    assert body["evaluated_predictions"] >= 1
    assert body["retrained"] is not None
    an = client.get("/api/ml/analytics?game_type=revancha", headers=uh).json()
    assert len(an["strategies"]) == 9
    assert an["learning_events"] >= 1


def test_password_flows(client):
    r = client.post("/api/auth/register", json={"name": "T", "email": "t.ci@x.com", "password": "pass1234"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": "pass1234", "new_password": "newp1234"}).status_code == 200
    fr = client.post("/api/auth/forgot-password", json={"email": "t.ci@x.com"}).json()
    assert client.post("/api/auth/reset-password", json={"token": fr["reset_token"], "new_password": "rst12345"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "t.ci@x.com", "password": "rst12345"}).status_code == 200


def test_assistant_status(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    s = client.get("/api/assistant/status", headers=uh)
    assert s.status_code == 200 and "enabled" in s.json()


def test_ml_probabilities(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    p = client.get("/api/ml/probabilities?game_type=melate", headers=uh)
    assert p.status_code == 200
    j = p.json()
    assert len(j["numbers"]) == 56
    assert len(j["top"]) >= 6
    assert all(0.0 <= n["rel"] <= 1.0 for n in j["numbers"])
