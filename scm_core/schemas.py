"""Request bodies shared by every service.

Monolith and microservices accept exactly the same payloads, which keeps
Experiment A fair: only the deployment changes, never the request.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

# Upper bounds stop a single request from using up a container's memory.
MAX_WAREHOUSES = 200
MAX_STORES = 1000


class InstanceSpec(BaseModel):
    """A generated problem: three numbers are enough (used by load tests)."""
    n_warehouses: int = Field(10, ge=1, le=MAX_WAREHOUSES)
    n_stores: int = Field(50, ge=1, le=MAX_STORES)
    seed: int = Field(0, ge=0)


class OptimizeRequest(InstanceSpec):
    include_plan: bool = False


class SimulateRequest(InstanceSpec):
    n_scenarios: int = Field(20, ge=1, le=500)
    demand_cv: float = Field(0.2, ge=0.0, le=1.0)
    scenario_seed: int = Field(0, ge=0)


class CustomProblem(BaseModel):
    """A problem typed in by a user (used by the UI, not by load tests)."""
    supply: list[float] = Field(..., min_length=1, max_length=MAX_WAREHOUSES)
    demand: list[float] = Field(..., min_length=1, max_length=MAX_STORES)
    cost: list[list[float]]
    penalty: float | None = Field(None, gt=0)
    include_plan: bool = True

    @model_validator(mode="after")
    def check_shapes(self):
        W, S = len(self.supply), len(self.demand)
        if len(self.cost) != W or any(len(row) != S for row in self.cost):
            raise ValueError(f"cost must be {W} rows (warehouses) x {S} columns (stores)")
        if min(self.supply) < 0 or min(self.demand) < 0:
            raise ValueError("supply and demand must be non-negative")
        if min(min(row) for row in self.cost) < 0:
            raise ValueError("costs must be non-negative")
        return self