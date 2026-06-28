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


@pytest.mark.parametrize("strategy", ["conservadora", "balanceada", "agresiva", "genetica", "anti_popular", "calientes", "frios", "hibrida", "adaptativa", "evolutiva"])
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


def test_grouped_draw_melate_revancha_revanchita(client):
    """One card adds the same physical draw to the 3 games at once."""
    ah = auth(client, "admin@melateai.pro", "admin1234")
    payload = {
        "draw_number": 95500,
        "draw_date": "2026-06-28",
        "melate": {"numbers": [4, 11, 22, 33, 44, 55], "additional": 7},
        "revancha": {"numbers": [1, 2, 3, 50, 51, 52]},
        "revanchita": {"text": "9 18 27 36 45 54"},  # text input also works
    }
    r = client.post("/api/draws/grouped", headers=ah, json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draw_number"] == 95500
    assert len(body["results"]) == 3 and body["errors"] == []
    games = {res["draw"]["game_type"] for res in body["results"]}
    assert games == {"melate", "revancha", "revanchita"}
    # all three share the same concurso number and date
    for res in body["results"]:
        assert res["draw"]["draw_number"] == 95500
        assert res["draw"]["draw_date"] == "2026-06-28"
    # melate kept its bonus
    mel = next(res for res in body["results"] if res["draw"]["game_type"] == "melate")
    assert mel["draw"]["additional"] == 7
    # duplicate submission surfaces per-game errors, not a hard failure
    r2 = client.post("/api/draws/grouped", headers=ah, json=payload)
    assert r2.status_code == 400  # all three already exist
    # non-admin is forbidden
    uh = auth(client, "demo@melateai.pro", "demo1234")
    assert client.post("/api/draws/grouped", headers=uh, json=payload).status_code == 403


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
    assert len(an["strategies"]) == 10
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


def test_score_combo(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    r = client.post("/api/predictions/score", headers=uh, json={"game_type": "melate", "numbers": [1, 2, 3, 4, 5, 6]})
    assert r.status_code == 200
    j = r.json()
    assert 0.0 <= j["score"] <= 1.0 and len(j["tips"]) >= 1 and len(j["number_probs"]) == 6
    assert client.post("/api/predictions/score", headers=uh, json={"game_type": "melate", "numbers": [1, 1, 3, 4, 5, 6]}).status_code == 400


def test_hot_pairs(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    r = client.get("/api/draws/pairs?game_type=melate", headers=uh)
    assert r.status_code == 200
    pairs = r.json()["pairs"]
    assert len(pairs) > 0 and pairs[0]["a"] < pairs[0]["b"] and pairs[0]["count"] >= 1


def test_admin_edit_user(client):
    ah = auth(client, "admin@melateai.pro", "admin1234")
    c = client.post("/api/admin/users", headers=ah, json={"name": "Edit Me", "email": "edit@x.com", "password": "abc123"})
    uid = c.json()["id"]
    r = client.patch(f"/api/admin/users/{uid}", headers=ah, json={"name": "Edited", "is_admin": True})
    assert r.status_code == 200 and r.json()["name"] == "Edited" and r.json()["is_admin"] is True
    client.delete(f"/api/admin/users/{uid}", headers=ah)


def test_account_export_and_delete(client):
    r = client.post("/api/auth/register", json={"name": "Bye", "email": "bye@x.com", "password": "pass1234"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    exp = client.get("/api/auth/export", headers=h)
    assert exp.status_code == 200 and exp.json()["user"]["email"] == "bye@x.com"
    assert client.delete("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"email": "bye@x.com", "password": "pass1234"}).status_code == 401


def test_analytics_contextual_fields(client):
    uh = auth(client, "demo@melateai.pro", "demo1234")
    an = client.get("/api/ml/analytics?game_type=melate", headers=uh).json()
    assert "current_context" in an and "contextual" in an


def test_chispazo_combination_game(client):
    """Chispazo: combination game, 5 unique numbers 1..29."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")
    games = {g["key"] for g in client.get("/api/draws/games").json()}
    assert {"chispazo", "tris"} <= games
    r = client.post("/api/predictions/generate", headers=uh, json={"game_type": "chispazo", "strategy": "hibrida", "count": 3})
    assert r.status_code == 200, r.text
    for c in r.json()["combos"]:
        assert len(c["numbers"]) == 5
        assert len(set(c["numbers"])) == 5
        assert all(1 <= n <= 29 for n in c["numbers"])
    # unique-number rule enforced
    assert client.post("/api/predictions/score", headers=uh, json={"game_type": "chispazo", "numbers": [1, 1, 3, 4, 5]}).status_code == 400
    e = client.post("/api/earnings/estimate", headers=uh, json={"game_type": "chispazo", "combinations": 5, "cost_per_combination": 15})
    assert e.status_code == 200 and e.json()["jackpot_odds_one_in"] == 118755  # C(29,5)
    assert client.post("/api/draws", headers=ah, json={"game_type": "chispazo", "numbers": [1, 2, 3, 4, 5], "draw_number": 95001}).status_code == 200


def test_tris_positional_game(client):
    """Tris: positional, 5 digits 0..9, repeats allowed, per-position matching."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")
    # generate: repeats allowed, digits 0..9, length 5
    r = client.post("/api/predictions/generate", headers=uh, json={"game_type": "tris", "strategy": "calientes", "count": 3})
    assert r.status_code == 200, r.text
    for c in r.json()["combos"]:
        assert len(c["numbers"]) == 5
        assert all(0 <= n <= 9 for n in c["numbers"])
    # repeats are valid in Tris
    assert client.post("/api/predictions/score", headers=uh, json={"game_type": "tris", "numbers": [5, 5, 5, 5, 5]}).status_code == 200
    # wrong length rejected
    assert client.post("/api/predictions/score", headers=uh, json={"game_type": "tris", "numbers": [1, 2, 3]}).status_code == 400
    # order is preserved on save
    sv = client.post("/api/predictions/save", headers=uh, json={"game_type": "tris", "strategy": "balanceada", "numbers": [1, 2, 3, 4, 5]})
    assert sv.status_code == 200 and sv.json()["numbers"] == [1, 2, 3, 4, 5]
    # per-position evaluation: [1,2,3,4,5] vs [5,4,3,2,1] -> only position 3 matches => 1 hit
    res = client.post("/api/draws", headers=ah, json={"game_type": "tris", "numbers": [5, 4, 3, 2, 1], "draw_number": 95500})
    assert res.status_code == 200
    hist = client.get("/api/predictions/history?game_type=tris", headers=uh).json()
    mine = [p for p in hist if p["numbers"] == [1, 2, 3, 4, 5]]
    assert mine and mine[0]["results"][0]["hits"] == 1
    # jackpot odds = 10^5 (each of 5 positions independent, 1/10)
    e = client.post("/api/earnings/estimate", headers=uh, json={"game_type": "tris", "combinations": 5, "cost_per_combination": 6})
    assert e.status_code == 200 and e.json()["jackpot_odds_one_in"] == 100000
    # positional stats + probabilities shape
    st = client.get("/api/draws/stats?game_type=tris", headers=uh).json()
    assert st["kind"] == "positional" and len(st["positions"]) == 5
    pr = client.get("/api/ml/probabilities?game_type=tris", headers=uh).json()
    assert pr["kind"] == "positional" and len(pr["positions"]) == 5


def test_ensemble_probabilities_and_weights(client):
    """Evolutionary ensemble: fused per-number probs + evolved model weights."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    p = client.get("/api/ml/probabilities?game_type=melate&source=ensemble", headers=uh)
    assert p.status_code == 200, p.text
    j = p.json()
    assert j["backend"] == "ensemble"
    assert len(j["numbers"]) == 56
    # normalized distribution (tolerance covers 4-decimal rounding in the response)
    assert abs(sum(n["prob"] for n in j["numbers"]) - 1.0) < 0.01
    w = j["ensemble_weights"]
    assert len(w) == 13
    assert abs(sum(m["weight"] for m in w) - 1.0) < 0.01  # weights form a distribution
    # analytics surfaces the persisted/lazy ensemble block
    an = client.get("/api/ml/analytics?game_type=melate", headers=uh).json()
    assert an["ensemble"] is not None and len(an["ensemble"]["models"]) == 13
    # positional games have no ensemble
    an_t = client.get("/api/ml/analytics?game_type=tris", headers=uh).json()
    assert an_t["ensemble"] is None


def test_existing_games_untouched(client):
    """Guard: existing combination games still sort/dedupe and reject repeats."""
    ah = auth(client, "admin@melateai.pro", "admin1234")
    r = client.post("/api/predictions/score", headers=auth(client, "demo@melateai.pro", "demo1234"),
                    json={"game_type": "melate", "numbers": [6, 5, 4, 3, 2, 1]})
    assert r.status_code == 200 and r.json()["numbers"] == [1, 2, 3, 4, 5, 6]  # sorted
    assert client.post("/api/draws", headers=ah, json={"game_type": "melate", "numbers": [1, 1, 3, 4, 5, 6], "draw_number": 95900}).status_code == 400
