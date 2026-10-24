"""Synthetic supply-allocation instances.

An instance is fully determined by (n_warehouses, n_stores, seed), so a load
test can send a tiny request and still get a reproducible, arbitrarily large
problem. This keeps network payload out of the latency we measure.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class Instance:
    n_warehouses: int
    n_stores: int
    seed: int
    supply: list[float]          # units available at each warehouse
    demand: list[float]          # units requested by each store
    cost: list[list[float]]      # cost per unit shipped, warehouse x store
    penalty: list[float]         # cost per unit of unmet demand, per store

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Instance":
        return cls(**d)


def generate_instance(n_warehouses: int, n_stores: int, seed: int = 0,
                      supply_ratio: float = 1.1) -> Instance:
    """Place warehouses and stores on a 100x100 map; cost = distance + handling.

    supply_ratio > 1 means total supply exceeds total base demand, so the base
    case is feasible; demand scenarios can still push it short.
    """
    if n_warehouses < 1 or n_stores < 1:
        raise ValueError("need at least one warehouse and one store")
    rng = np.random.default_rng(seed)

    wh_xy = rng.uniform(0, 100, size=(n_warehouses, 2))
    st_xy = rng.uniform(0, 100, size=(n_stores, 2))
    dist = np.linalg.norm(wh_xy[:, None, :] - st_xy[None, :, :], axis=2)
    handling = rng.uniform(1, 5, size=(n_warehouses, 1))
    cost = 0.5 * dist + handling

    demand = rng.integers(20, 120, size=n_stores).astype(float)
    weights = rng.uniform(0.5, 1.5, size=n_warehouses)
    supply = weights / weights.sum() * demand.sum() * supply_ratio

    # Unmet demand is always dearer than the worst shipping option.
    penalty = np.full(n_stores, float(cost.max()) * 2)

    return Instance(
        n_warehouses=n_warehouses,
        n_stores=n_stores,
        seed=seed,
        supply=np.round(supply, 2).tolist(),
        demand=demand.tolist(),
        cost=np.round(cost, 3).tolist(),
        penalty=penalty.round(3).tolist(),
    )
