"""API service: the single public entry point.

MODE=monolith       all work runs inside this one process
                    (one container = the monolith in Experiment A)
MODE=microservices  heavy work is forwarded over HTTP to the optimizer and
                    simulation services (three containers)

Both modes expose the same routes and accept the same payloads, so the load
test script never changes between experiments; only MODE does.

In microservices mode each response also carries `network_overhead_ms`:
the round-trip time to the downstream service minus the time it spent
computing. That is the service-to-service cost asked about in Q4.
"""
import os
import socket
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool

from scm_core import generate_instance, make_instance, run_scenarios, solve
from scm_core.schemas import CustomProblem, InstanceSpec, OptimizeRequest, SimulateRequest

MODE = os.getenv("MODE", "monolith").lower()
OPTIMIZER_URL = os.getenv("OPTIMIZER_URL", "http://127.0.0.1:8001")
SIMULATION_URL = os.getenv("SIMULATION_URL", "http://127.0.0.1:8002")
TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT_S", "120"))
REPLICA = os.getenv("CONTAINER_APP_REPLICA_NAME", socket.gethostname())

if MODE not in {"monolith", "microservices"}:
    raise RuntimeError(f"MODE must be 'monolith' or 'microservices', got {MODE!r}")

_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one shared HTTP client at start-up and close it at shutdown.

    Reusing one client keeps connections open between calls, as a real
    gateway would; opening a new connection per request would inflate the
    network overhead we are trying to measure.
    """
    global _client
    if MODE == "microservices":
        _client = httpx.AsyncClient(timeout=TIMEOUT)
    yield
    if _client:
        await _client.aclose()


app = FastAPI(title="Supply Chain Decision Support API", lifespan=lifespan)


@app.get("/health")
def health():
    return {"service": "api", "mode": MODE, "replica": REPLICA, "status": "ok"}


@app.post("/instances/summary")
def instance_summary(spec: InstanceSpec):
    """Light request: the 'many cheap calls' half of Experiment B's traffic.
    Always answered by the API itself, in both modes."""
    inst = generate_instance(spec.n_warehouses, spec.n_stores, spec.seed)
    return {
        "n_warehouses": inst.n_warehouses,
        "n_stores": inst.n_stores,
        "total_supply": round(sum(inst.supply), 2),
        "total_demand": round(sum(inst.demand), 2),
        "served_by": {"service": "api", "replica": REPLICA},
    }


async def _forward(url: str, payload: dict) -> dict:
    """Send the request to a downstream service and time the round trip."""
    t0 = time.perf_counter()
    try:
        r = await _client.post(url, json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(502, f"downstream service unreachable: {e}") from e
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.json().get("detail", r.text))
    round_trip = time.perf_counter() - t0
    body = r.json()
    body["network_overhead_ms"] = round((round_trip - body["total_seconds"]) * 1000, 3)
    return body


@app.post("/optimize")
async def optimize(req: OptimizeRequest):
    if MODE == "microservices":
        return await _forward(f"{OPTIMIZER_URL}/optimize", req.model_dump())
    inst = generate_instance(req.n_warehouses, req.n_stores, req.seed)
    result = await run_in_threadpool(solve, inst, None, req.include_plan)
    result["served_by"] = {"service": "api-monolith", "replica": REPLICA}
    return result


@app.post("/optimize/custom")
async def optimize_custom(req: CustomProblem):
    """User-entered supply, demand and costs (for the UI)."""
    if MODE == "microservices":
        return await _forward(f"{OPTIMIZER_URL}/optimize/custom", req.model_dump())
    inst = make_instance(req.supply, req.demand, req.cost, req.penalty)
    result = await run_in_threadpool(solve, inst, None, req.include_plan)
    result["served_by"] = {"service": "api-monolith", "replica": REPLICA}
    return result


@app.post("/simulate")
async def simulate(req: SimulateRequest):
    if MODE == "microservices":
        return await _forward(f"{SIMULATION_URL}/simulate", req.model_dump())
    inst = generate_instance(req.n_warehouses, req.n_stores, req.seed)
    result = await run_in_threadpool(run_scenarios, inst, req.n_scenarios,
                                     req.demand_cv, req.scenario_seed)
    result["served_by"] = {"service": "api-monolith", "replica": REPLICA}
    return result