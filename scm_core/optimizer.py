"""Supply allocation as a linear program (transportation problem with shortage).

    minimise   sum_ij cost[i][j] * x[i][j]  +  sum_j penalty[j] * short[j]
    subject to sum_j x[i][j]            <= supply[i]   for every warehouse i
               sum_i x[i][j] + short[j]  = demand[j]   for every store j
               x, short >= 0

The shortage variable keeps every scenario feasible, so the simulation never
has to special-case an infeasible solve.
"""
from __future__ import annotations

import os
import time

import pulp

from .data import Instance


SOLVER = os.getenv("SOLVER", "highs").lower()


def _solver():
    # HiGHS runs in-process (no temp files or subprocess per solve), which keeps
    # container behaviour clean. CBC ships with PuLP and is kept as a fallback.
    if SOLVER == "cbc":
        return pulp.PULP_CBC_CMD(msg=False)
    return pulp.HiGHS(msg=False)


def solve(inst: Instance, demand: list[float] | None = None,
          include_plan: bool = False) -> dict:
    """Solve one allocation. `demand` overrides the instance demand (scenarios)."""
    t0 = time.perf_counter()
    d = demand if demand is not None else inst.demand
    W, S = range(inst.n_warehouses), range(inst.n_stores)

    prob = pulp.LpProblem("allocation", pulp.LpMinimize)
    x = [[pulp.LpVariable(f"x_{i}_{j}", lowBound=0) for j in S] for i in W]
    short = [pulp.LpVariable(f"short_{j}", lowBound=0) for j in S]

    prob += (pulp.lpSum(inst.cost[i][j] * x[i][j] for i in W for j in S)
             + pulp.lpSum(inst.penalty[j] * short[j] for j in S))
    for i in W:
        prob += pulp.lpSum(x[i][j] for j in S) <= inst.supply[i], f"supply_{i}"
    for j in S:
        prob += pulp.lpSum(x[i][j] for i in W) + short[j] == d[j], f"demand_{j}"
    t_build = time.perf_counter() - t0

    status = prob.solve(_solver())
    t_total = time.perf_counter() - t0

    total_demand = float(sum(d))
    unmet = float(sum(v.value() or 0.0 for v in short))
    shipping = float(sum(inst.cost[i][j] * (x[i][j].value() or 0.0)
                         for i in W for j in S))
    result = {
        "status": pulp.LpStatus[status],
        "objective": float(pulp.value(prob.objective) or 0.0),
        "shipping_cost": shipping,
        "unmet_demand": unmet,
        "fill_rate": 1.0 - unmet / total_demand if total_demand else 1.0,
        "n_variables": inst.n_warehouses * inst.n_stores + inst.n_stores,
        "build_seconds": t_build,
        "solve_seconds": t_total - t_build,
        "total_seconds": t_total,
    }
    if include_plan:
        result["plan"] = [[round(x[i][j].value() or 0.0, 3) for j in S] for i in W]
    return result
