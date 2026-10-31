"""Service tests. The key one: both API modes return identical results."""
import importlib

import httpx
import pytest
from fastapi.testclient import TestClient

import services.optimizer.main as opt_svc
import services.simulation.main as sim_svc

OPT = {"n_warehouses": 4, "n_stores": 15, "seed": 2}
SIM = {**OPT, "n_scenarios": 5, "scenario_seed": 3}
# 2 warehouses x 3 stores, small enough to check by hand:
# W0 is cheapest for S0 and S1, W1 for S2; supply is ample.
CUSTOM = {"supply": [100, 100], "demand": [30, 40, 50],
          "cost": [[1, 2, 9], [5, 6, 1]]}


def load_api(monkeypatch, mode):
    """Re-import the API module so it picks up the MODE we set."""
    monkeypatch.setenv("MODE", mode)
    import services.api.main as api
    return importlib.reload(api)


def wire_downstream(api):
    """Send the gateway's HTTP calls to the real downstream apps, in-process."""
    api._client = httpx.AsyncClient(mounts={
        api.OPTIMIZER_URL + "/": httpx.ASGITransport(app=opt_svc.app),
        api.SIMULATION_URL + "/": httpx.ASGITransport(app=sim_svc.app),
    })


def test_monolith_routes(monkeypatch):
    api = load_api(monkeypatch, "monolith")
    with TestClient(api.app) as c:
        assert c.get("/health").json()["mode"] == "monolith"
        assert c.post("/instances/summary", json=OPT).status_code == 200
        r = c.post("/optimize", json=OPT).json()
        assert r["status"] == "Optimal"
        assert r["served_by"]["service"] == "api-monolith"


def test_custom_problem_by_hand(monkeypatch):
    api = load_api(monkeypatch, "monolith")
    with TestClient(api.app) as c:
        r = c.post("/optimize/custom", json=CUSTOM).json()
    # Cheapest: S0 and S1 from W0 (30*1 + 40*2), S2 from W1 (50*1) = 160
    assert r["objective"] == pytest.approx(160)
    assert r["plan"] == [[30, 40, 0], [0, 0, 50]]


def test_custom_problem_rejects_wrong_shape(monkeypatch):
    api = load_api(monkeypatch, "monolith")
    bad = {**CUSTOM, "cost": [[1, 2], [5, 6]]}          # 2 columns, need 3
    with TestClient(api.app) as c:
        r = c.post("/optimize/custom", json=bad)
    assert r.status_code == 422
    assert "2 rows" in r.text and "3 columns" in r.text


def test_rejects_oversized_problem(monkeypatch):
    api = load_api(monkeypatch, "monolith")
    with TestClient(api.app) as c:
        assert c.post("/optimize", json={"n_warehouses": 10_000}).status_code == 422


def test_microservices_match_monolith(monkeypatch):
    mono = load_api(monkeypatch, "monolith")
    with TestClient(mono.app) as c:
        m_opt = c.post("/optimize", json=OPT).json()
        m_sim = c.post("/simulate", json=SIM).json()
        m_cus = c.post("/optimize/custom", json=CUSTOM).json()

    micro = load_api(monkeypatch, "microservices")
    with TestClient(micro.app) as c:
        wire_downstream(micro)
        r_opt = c.post("/optimize", json=OPT).json()
        r_sim = c.post("/simulate", json=SIM).json()
        r_cus = c.post("/optimize/custom", json=CUSTOM).json()

    # Served by the separate services, with overhead measured...
    assert r_opt["served_by"]["service"] == "optimizer"
    assert r_sim["served_by"]["service"] == "simulation"
    assert "network_overhead_ms" in r_opt
    # ...and exactly the same answers as the monolith.
    assert r_opt["objective"] == pytest.approx(m_opt["objective"])
    assert r_sim["cost_mean"] == pytest.approx(m_sim["cost_mean"])
    assert r_cus["objective"] == pytest.approx(m_cus["objective"])


def test_downstream_down_gives_502(monkeypatch):
    monkeypatch.setenv("OPTIMIZER_URL", "http://127.0.0.1:9")   # nothing listens here
    api = load_api(monkeypatch, "microservices")
    with TestClient(api.app) as c:
        r = c.post("/optimize", json=OPT)
    assert r.status_code == 502