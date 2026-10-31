"""Optimization service: solves one allocation problem per request.

In the microservices deployment this runs in its own container. In the
monolith, the API service calls the same scm_core functions directly.
"""
import os
import socket

from fastapi import FastAPI

from scm_core import generate_instance, make_instance, solve
from scm_core.schemas import CustomProblem, OptimizeRequest

app = FastAPI(title="Optimization Service")

# Azure Container Apps sets this; locally we fall back to the machine name.
# Returned in every response so we can see which replica served a request.
REPLICA = os.getenv("CONTAINER_APP_REPLICA_NAME", socket.gethostname())


@app.get("/health")
def health():
    return {"service": "optimizer", "replica": REPLICA, "status": "ok"}


# These are plain `def`, not `async def`, on purpose: FastAPI then runs them in
# a worker thread, so a slow solve does not freeze the server for other requests.
@app.post("/optimize")
def optimize(req: OptimizeRequest):
    inst = generate_instance(req.n_warehouses, req.n_stores, req.seed)
    result = solve(inst, include_plan=req.include_plan)
    result["served_by"] = {"service": "optimizer", "replica": REPLICA}
    return result


@app.post("/optimize/custom")
def optimize_custom(req: CustomProblem):
    inst = make_instance(req.supply, req.demand, req.cost, req.penalty)
    result = solve(inst, include_plan=req.include_plan)
    result["served_by"] = {"service": "optimizer", "replica": REPLICA}
    return result