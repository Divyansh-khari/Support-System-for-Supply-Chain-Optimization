"""Monte Carlo demand scenarios over one allocation instance.

Each scenario draws store demand around the base value and re-solves the LP.
Cost grows linearly with n_scenarios, which makes this the CPU-heavy service
that Experiment B scales on its own.
"""
from __future__ import annotations

import time

import numpy as np

from .data import Instance
from .optimizer import solve


def run_scenarios(inst: Instance, n_scenarios: int = 20, demand_cv: float = 0.2,
                  seed: int = 0) -> dict:
    if n_scenarios < 1:
        raise ValueError("n_scenarios must be >= 1")
    t0 = time.perf_counter()
    rng = np.random.default_rng(seed)
    base = np.asarray(inst.demand)

    objectives, fill_rates, unmet = [], [], []
    for _ in range(n_scenarios):
        d = np.clip(rng.normal(base, demand_cv * base), 0, None).round(2)
        r = solve(inst, demand=d.tolist())
        objectives.append(r["objective"])
        fill_rates.append(r["fill_rate"])
        unmet.append(r["unmet_demand"])

    obj = np.asarray(objectives)
    fr = np.asarray(fill_rates)
    return {
        "n_scenarios": n_scenarios,
        "demand_cv": demand_cv,
        "cost_mean": float(obj.mean()),
        "cost_p95": float(np.percentile(obj, 95)),
        "cost_std": float(obj.std()),
        "fill_rate_mean": float(fr.mean()),
        "fill_rate_p5": float(np.percentile(fr, 5)),
        "prob_any_shortage": float(np.mean(np.asarray(unmet) > 1e-6)),
        "total_seconds": time.perf_counter() - t0,
    }
