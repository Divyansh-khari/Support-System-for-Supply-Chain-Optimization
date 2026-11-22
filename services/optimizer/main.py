"""Optimization service: solves one allocation problem per request.

In the microservices deployment this runs in its own container. In the
monolith, the API service calls the same scm_core functions directly.
"""
import os
import socket
import uuid
from fastapi import FastAPI

from scm_core import generate_instance, make_instance, solve
from scm_core.schemas import CustomProblem, OptimizeRequest

app = FastAPI(title="Optimization Service")

# A unique ID per running container. Azure's express environment gives every
# container the same hostname, so the Docker start command sets REPLICA_ID to a
# random value once per container (shared by all worker processes inside it).
# Outside Docker we fall back to hostname + a random suffix.
REPLICA = (os.getenv("CONTAINER_APP_REPLICA_NAME") or os.getenv("REPLICA_ID")
           or f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}")


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