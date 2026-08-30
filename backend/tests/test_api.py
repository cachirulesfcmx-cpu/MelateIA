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


def test_genius_engine_full_power(client):
    """Evolutiva uses 15 models + pool optimizer; other strategies carry the
    Genius backbone reinforcement."""
    from app.engine.ensemble import MODEL_KEYS, m_repeat_carry, m_neighbor
    from app.engine.game_config import get_game
    import random as _r

    assert len(MODEL_KEYS) == 15
    cfg = get_game("melate")
    rng = _r.Random(7)
    hist = [sorted(rng.sample(range(1, 57), 6)) for _ in range(120)]
    for fn in (m_repeat_carry, m_neighbor):
        p = fn(hist, cfg)
        assert len(p) == 56 and abs(sum(p.values()) - 1.0) < 1e-6

    uh = auth(client, "demo@melateai.pro", "demo1234")
    r = client.post("/api/predictions/generate", headers=uh, json={"game_type": "melate", "strategy": "evolutiva", "count": 5})
    assert r.status_code == 200, r.text
    combos = r.json()["combos"]
    assert len(combos) == 5
    assert "15 modelos" in combos[0]["explanation"]
    assert "optimizado" in combos[0]["explanation"]
    # pool optimizer returns distinct tickets
    assert len({tuple(c["numbers"]) for c in combos}) == 5
    # backbone note on a classic strategy
    r2 = client.post("/api/predictions/generate", headers=uh, json={"game_type": "melate", "strategy": "conservadora", "count": 2})
    assert r2.status_code == 200
    assert "refuerzo del motor Genius (15 modelos)" in r2.json()["combos"][0]["explanation"]


def test_models_evolve_with_each_added_result(client):
    """Every added official result must move the whole learning system:
    ensemble weights recompute over the larger history, the pending prediction
    gets evaluated, and the meta layer's error memory grows."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")

    before = client.get("/api/ml/probabilities?game_type=melate&source=ensemble", headers=uh).json()
    assert len(before["ensemble_weights"]) == 15

    # a pending prediction that the new draw will evaluate
    sp = client.post("/api/predictions/save", headers=uh, json={"game_type": "melate", "strategy": "evolutiva", "numbers": [3, 9, 21, 27, 44, 50]})
    assert sp.status_code == 200

    cr = client.post("/api/draws", headers=ah, json={"game_type": "melate", "numbers": [3, 9, 14, 30, 41, 53], "draw_number": 96200})
    assert cr.status_code == 200, cr.text
    assert cr.json()["evaluated_predictions"] >= 1  # learning loop fired

    after = client.get("/api/ml/probabilities?game_type=melate&source=ensemble", headers=uh).json()
    # weights were re-evolved over the larger history
    assert after["n_draws"] == before["n_draws"] + 1
    wb = {w["model"]: (w["weight"], w["score"]) for w in before["ensemble_weights"]}
    wa = {w["model"]: (w["weight"], w["score"]) for w in after["ensemble_weights"]}
    assert wb != wa
    # every model was re-scored in the new walk-forward (all 15 present, scores fresh)
    assert set(wa) == set(wb) and len(wa) == 15

    # error memory now feeds the meta layer
    g = client.post("/api/predictions/generate", headers=uh, json={"game_type": "melate", "strategy": "evolutiva", "count": 2})
    assert "memoria de" in g.json()["combos"][0]["explanation"]


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


def test_delete_draw_reverts_predictions(client):
    """Admin can delete a mistaken draw; evaluated predictions revert to pending."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")
    sp = client.post("/api/predictions/save", headers=uh, json={"game_type": "melate", "strategy": "balanceada", "numbers": [5, 9, 14, 20, 31, 48]})
    pred_id = sp.json()["id"]
    cr = client.post("/api/draws", headers=ah, json={"game_type": "melate", "numbers": [5, 9, 14, 50, 51, 52], "draw_number": 96001})
    draw_id = cr.json()["draw"]["id"]
    # non-admin cannot delete
    assert client.delete(f"/api/draws/{draw_id}", headers=uh).status_code == 403
    d = client.delete(f"/api/draws/{draw_id}", headers=ah)
    assert d.status_code == 200, d.text
    assert d.json()["draw_number"] == 96001
    # the draw is gone
    rows = client.get("/api/draws?game_type=melate&limit=200", headers=uh).json()["draws"]
    assert all(r["draw_number"] != 96001 for r in rows)
    # the prediction reverted to pendiente
    hist = client.get("/api/predictions/history?game_type=melate", headers=uh).json()
    mine = next((p for p in hist if p["id"] == pred_id), None)
    assert mine is not None and mine["status"] == "pendiente"
    # deleting a missing draw → 404
    assert client.delete(f"/api/draws/{draw_id}", headers=ah).status_code == 404


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
    assert len(w) == 15
    assert abs(sum(m["weight"] for m in w) - 1.0) < 0.01  # weights form a distribution
    # analytics surfaces the persisted/lazy ensemble block
    an = client.get("/api/ml/analytics?game_type=melate", headers=uh).json()
    assert an["ensemble"] is not None and len(an["ensemble"]["models"]) == 15
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


def test_constitution_endpoint(client):
    """The 10 governance rules are served with their promotion thresholds."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    c = client.get("/api/research/constitution", headers=uh)
    assert c.status_code == 200
    body = c.json()
    assert len(body["rules"]) == 15          # 10 originales + 5 del protocolo v3
    ids = [r["id"] for r in body["rules"]]
    assert ids == list(range(1, 16))
    # rule 10 — the system is allowed to conclude there is no evidence
    assert "no existe evidencia" in body["rules"][9]["rule"].lower()
    th = body["thresholds"]
    assert th["minimum_windows_won"] >= 2 and th["max_weight_delta_per_draw"] > 0


def test_research_agents_do_real_work(client):
    """Agents must compute over the real history, not return canned dicts."""
    from app.engine.agents import (DataAgent, RiskAgent, StatisticianAgent,
                                   BacktestAgent, paired_significance)
    from app.engine.game_config import get_game
    import random as _r

    cfg = get_game("melate")
    rng = _r.Random(3)
    hist = [sorted(rng.sample(range(1, 57), 6)) for _ in range(300)]

    data = DataAgent()
    assert data.validate_draw([1, 2, 3, 4, 5, 6], cfg)
    assert not data.validate_draw([1, 1, 3, 4, 5, 6], cfg)      # repeated
    assert not data.validate_draw([1, 2, 3, 4, 5, 57], cfg)     # out of range
    audit = data.audit([{"numbers": h, "draw_number": i} for i, h in enumerate(hist)], cfg)
    assert audit["ok"] and audit["total"] == 300 and audit["invalid_count"] == 0

    # a uniform random history must NOT be flagged as non-uniform
    stats = StatisticianAgent().analyze(hist, cfg)
    assert stats["uniformity"]["uniform"] is True
    assert stats["uniformity"]["p_value"] > 0.05

    # risk agent rejects calendar-only, long-run, invalid and duplicate tickets
    checked = RiskAgent().validate([
        [30, 31, 32, 33, 45, 52],   # run of 4 (not calendar-only)
        [2, 5, 9, 14, 20, 31],      # all <= 31: birthdays ticket
        [7, 19, 23, 34, 41, 55],    # good
        [7, 19, 23, 34, 41, 55],    # duplicate of the good one
        [7, 19, 23, 34, 41, 99],    # out of range
    ], cfg)
    assert checked["accepted"] == [[7, 19, 23, 34, 41, 55]]
    assert checked["rejected"]["secuencia_larga"] == 1
    assert checked["rejected"]["solo_calendario"] == 1
    assert checked["rejected"]["duplicado"] == 1
    assert checked["rejected"]["invalido"] == 1

    # identical performance to the baseline is never "significant"
    sig = paired_significance([1] * 40, [1] * 40)
    assert sig["significant"] is False
    # noise must not be accepted, no matter the raw edge
    ok, reason = BacktestAgent().accepts({"mean_hits": 0.9}, {"mean_hits": 0.6}, 3,
                                         {"p_value": 0.4})
    assert ok is False and "ruido" in reason


def test_research_cycle_runs_and_is_honest(client):
    """Full cycle: walk-forward vs the random baseline, verdict, and record."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")

    # only an admin may launch it
    assert client.post("/api/research/run?game_type=melate", headers=uh).status_code == 403
    # positional games are out of scope
    assert client.post("/api/research/run?game_type=tris", headers=ah).status_code == 400

    r = client.post("/api/research/run?game_type=melate&windows=2&window_size=12", headers=ah)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "ok"
    assert run["walk_forward"] is True and run["history_mutated"] is False
    assert run["verdict"] in ("evidencia_significativa", "evidencia_debil", "evidencia_insuficiente")
    # the random baseline is always measured and reported (rule 4)
    assert run["baseline"]["mean_hits"] >= 0 and "expected_random" in run["baseline"]
    # every arm carries out-of-sample metrics and a significance test (rules 3, 9)
    assert len(run["experiments"]) == 16   # 15 models + fused ensemble
    for arm in run["experiments"]:
        assert "p_value" in arm["significance"]
        assert arm["metrics"]["n"] > 0
    # accepted arms are ranked first
    accepted_flags = [a["accepted"] for a in run["experiments"]]
    assert accepted_flags == sorted(accepted_flags, reverse=True)
    # the run audits itself against the constitution
    assert run["constitution"]["compliant"] is True
    assert len(run["constitution"]["checks"]) == 15

    # the record is queryable, and rejected hypotheses are kept (rule 7)
    hyps = client.get("/api/research/hypotheses?game_type=melate", headers=uh).json()
    assert len(hyps) > 0
    assert any(h["status"] == "descartada" for h in hyps)
    exps = client.get(f"/api/research/experiments?run_id={run['run_id']}", headers=uh).json()
    assert any(e["model_name"] == "random_baseline" for e in exps)  # baseline recorded

    ch = client.get("/api/research/champion?game_type=melate", headers=uh)
    assert ch.status_code == 200
    body = ch.json()
    # no champion without significant evidence — and that is stated plainly
    if body["champion"] is None:
        assert body["note"] and "azar" in body["note"]


def test_weight_inertia_rule_six(client):
    """Rule 6: weights keep evolving, but one draw cannot swing them freely."""
    import json
    from app.database import SessionLocal
    from app.models import EnsembleWeight
    from app.engine.constitution import MAX_WEIGHT_DELTA_PER_DRAW
    from app.engine.game_config import get_game
    from app.services import update_ensemble_weights, load_draw_rows

    db = SessionLocal()
    try:
        cfg = get_game("melate")
        history = [r["numbers"] for r in load_draw_rows(db, "melate")]
        first = update_ensemble_weights(db, cfg, history)
        assert first is not None
        before = json.loads(db.query(EnsembleWeight)
                            .filter(EnsembleWeight.game_type == "melate").first().weights)
        # a wildly different history would push the raw weights hard...
        shifted = history[:-40]
        second = update_ensemble_weights(db, cfg, shifted)
        after = json.loads(db.query(EnsembleWeight)
                           .filter(EnsembleWeight.game_type == "melate").first().weights)
        # ...but no single model may move more than the cap
        moved = max(abs(after.get(k, 0.0) - before.get(k, 0.0)) for k in set(after) | set(before))
        assert moved <= MAX_WEIGHT_DELTA_PER_DRAW + 1e-6, f"peso movió {moved}"
        assert abs(sum(after.values()) - 1.0) < 1e-6      # still a distribution
        assert second["n_draws"] == len(shifted)          # and it DID evolve
    finally:
        db.close()


def test_research_lab_statistics_v3(client):
    """Protocol v3 statistics: exact baselines, BH correction, splits, hashes."""
    from app.engine import research_lab as rlab

    # point 3 — the exact hypergeometric baseline equals the theoretical mean
    b = rlab.empirical_random_baseline(120, 56, 6)
    assert abs(b["mean_hits"] - rlab.theoretical_random_mean_hits(56, 6)) < 1e-6  # dict redondea a 6 dec
    assert abs(b["mean_hits"] - 36 / 56) < 1e-6
    assert abs(sum(rlab.hypergeometric_pmf(56, 6).values()) - 1.0) < 1e-9
    assert b["ci95_low"] < b["mean_hits"] < b["ci95_high"]
    # Retro has a different N and therefore a different baseline
    assert abs(rlab.empirical_random_baseline(50, 39, 6)["mean_hits"] - 36 / 39) < 1e-6

    # point 6 — Benjamini-Hochberg: monotone q, never below p, alpha respected
    ps = [0.001, 0.02, 0.04, 0.2, 0.5]
    bh = rlab.benjamini_hochberg(ps, alpha=0.05)
    assert [x["p"] for x in bh] == ps
    assert all(bh[i]["q"] >= bh[i]["p"] - 1e-9 for i in range(len(ps)))
    assert all(bh[i]["q"] <= bh[i + 1]["q"] + 1e-9 for i in range(len(ps) - 1))
    assert bh[0]["significant"] and not bh[-1]["significant"]
    assert rlab.benjamini_hochberg([]) == []
    # 16 arms of pure noise must not yield a "winner"
    noisy = rlab.benjamini_hochberg([0.06 + i * 0.05 for i in range(16)])
    assert not any(x["significant"] for x in noisy)

    # permutation p-value is never 0 and reacts to the direction
    assert rlab.permutation_pvalue(1.0, [0.1, 0.2, 0.3]) < rlab.permutation_pvalue(0.0, [0.1, 0.2, 0.3])
    assert rlab.permutation_pvalue(9.9, []) == 1.0

    # point 7 — chronological split keeps the golden holdout at the END
    draws = [[i] for i in range(1000)]
    sp = rlab.chronological_split(draws)
    assert (len(sp.train), len(sp.validation), len(sp.test), len(sp.golden_holdout)) == (650, 150, 100, 100)
    assert len(sp.selection) == 900
    assert sp.golden_holdout[0] == [900] and sp.golden_holdout[-1] == [999]
    assert not set(map(tuple, sp.selection)) & set(map(tuple, sp.golden_holdout))
    assert rlab.hash_draws(sp.golden_holdout) == rlab.hash_draws(sp.golden_holdout)
    assert rlab.hash_draws(sp.golden_holdout) != rlab.hash_draws(sp.test)

    # promotion policy rejects an uncorrected "win"
    bad = rlab.promotion_decision({"improvement_vs_random": 0.30, "q_value": 0.40,
                                   "out_of_sample": True, "windows_won": 3})
    assert bad["promote"] is False and "q-valor" in bad["reason"]
    # ...and rejects a corrected win that died on the golden holdout
    dead = rlab.promotion_decision({"improvement_vs_random": 0.30, "q_value": 0.01,
                                    "out_of_sample": True, "windows_won": 3,
                                    "golden_holdout_passed": False})
    assert dead["promote"] is False and "Golden Holdout" in dead["reason"]
    good = rlab.promotion_decision({"improvement_vs_random": 0.30, "q_value": 0.01,
                                    "out_of_sample": True, "windows_won": 3,
                                    "golden_holdout_passed": True})
    assert good["promote"] is True


def test_research_diagnostics_on_random_history(client):
    """Point 4: on a truly random history the diagnostics must report no signal."""
    from app.engine import research_lab as rlab
    import random as _r

    rng = _r.Random(11)
    hist = [sorted(rng.sample(range(1, 57), 6)) for _ in range(600)]
    d = rlab.run_diagnostics(hist, 56)
    assert d["autocorrelation_above_noise"] is False
    assert d["regime_shift_above_noise"] is False
    # the luckiest pair of 1,540 must not survive Bonferroni
    assert d["top_pair_significance"]["tested_pairs"] == 56 * 55 // 2
    assert d["top_pair_significance"]["significant"] is False
    assert "ruido" in d["reading"]

    # permutation test on a memoryless predictor: observed sits inside the null
    def mean_hits(seq):
        from collections import Counter
        c = Counter(n for dd in seq[:-20] for n in dd)
        top = sorted(c, key=c.get, reverse=True)[:6]
        return sum(len(set(top) & set(x)) for x in seq[-20:]) / 20

    perm = rlab.temporal_permutation_test(hist, mean_hits, n_permutations=20, seed=5)
    assert perm["n_permutations"] == 20
    assert 0 < perm["p_value"] <= 1.0
    assert "orden de sorteos aleatorizado" in perm["null_definition"]


def test_research_cycle_v3_protocol(client):
    """The cycle runs the v3 pipeline and reports every one of its guarantees."""
    uh = auth(client, "demo@melateai.pro", "demo1234")
    ah = auth(client, "admin@melateai.pro", "admin1234")

    p = client.get("/api/research/protocol", headers=uh).json()
    assert p["version"] == "v3" and len(p["pre_registered_hypotheses"]) == 7

    c = client.get("/api/research/constitution", headers=uh).json()
    assert len(c["rules"]) == 15                     # 10 originales + 5 de v3
    assert c["thresholds"]["correction"].startswith("Benjamini")

    r = client.post("/api/research/run?game_type=melate&windows=2&window_size=12"
                    "&permutations=5&perm_window=6", headers=ah)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "ok" and run["protocol_version"] == "v3"

    # point 7 — golden holdout is locked and excluded from selection
    gh = run["golden_holdout"]
    assert gh["locked"] is True and gh["selection_allowed"] is False
    assert len(gh["sha256"]) == 64 and gh["rows"] > 0
    assert run["selection_draws"] < run["draws"]
    assert run["selection_draws"] + gh["rows"] == run["draws"]

    # point 3 — the four baseline families are reported apart
    b = run["baselines"]
    assert abs(b["teorico"]["mean_hits"] - 36 / 56) < 1e-6
    assert abs(b["empirico_exacto"]["mean_hits"] - b["teorico"]["mean_hits"]) < 1e-6
    assert "simulado_montecarlo" in b and "de_modelo" in b

    # point 6 — every arm carries a corrected q-value, and q >= p
    assert run["multiple_testing"]["method"].startswith("Benjamini")
    assert run["multiple_testing"]["tests"] == len(run["experiments"])
    for arm in run["experiments"]:
        assert arm["q_value"] >= arm["significance"]["p_value"] - 1e-9

    # pre-registered hypotheses were written before the tests and then resolved
    assert len(run["pre_registered_results"]) == 7
    hyps = client.get("/api/research/hypotheses?game_type=melate&limit=100", headers=uh).json()
    prereg = [h for h in hyps if h["evidence"].get("pre_registered")]
    assert len(prereg) >= 7
    assert all(h["status"] in ("confirmada", "descartada") for h in prereg)
    assert all(h["statement"].startswith("[H0") for h in prereg)

    # point 4 — diagnostics ran
    assert run["diagnostics"]["reading"]
    # point 8 — the pipeline order is reported
    assert run["pipeline"][0].startswith("seguridad")

    # the constitution now audits 15 rules and still passes
    assert len(run["constitution"]["checks"]) == 15
    assert run["constitution"]["compliant"] is True
