"""Simulation service: Monte Carlo demand scenarios (the heavy service).

One request = n_scenarios solves, so this is the service Experiment B scales
on its own while the light API stays at one replica.
"""
import os
import uuid
from fastapi import FastAPI

from scm_core import generate_instance, run_scenarios
from scm_core.schemas import SimulateRequest

app = FastAPI(title="Simulation Service")
# A unique ID per running container. Azure's express environment gives every
# container the same hostname, so the Docker start command sets REPLICA_ID to a
# random value once per container (shared by all worker processes inside it).
# Outside Docker we use "local-" + a random suffix
REPLICA = (os.getenv("CONTAINER_APP_REPLICA_NAME") or os.getenv("REPLICA_ID")
           or f"local-{uuid.uuid4().hex[:6]}")


@app.get("/health")
def health():
    return {"service": "simulation", "replica": REPLICA, "status": "ok"}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    inst = generate_instance(req.n_warehouses, req.n_stores, req.seed)
    result = run_scenarios(inst, req.n_scenarios, req.demand_cv, req.scenario_seed)
    result["served_by"] = {"service": "simulation", "replica": REPLICA}
    return result