import numpy as np
import pytest
from scipy.optimize import linprog

from scm_core import generate_instance, run_scenarios, solve


def test_instance_is_reproducible():
    a = generate_instance(5, 20, seed=7)
    b = generate_instance(5, 20, seed=7)
    assert a == b
    assert generate_instance(5, 20, seed=8) != a


def test_base_instance_has_enough_supply():
    inst = generate_instance(8, 40, seed=1)
    assert sum(inst.supply) > sum(inst.demand)


def test_base_solve_meets_all_demand():
    r = solve(generate_instance(5, 20, seed=3), include_plan=True)
    assert r["status"] == "Optimal"
    assert r["unmet_demand"] == pytest.approx(0, abs=1e-6)
    assert r["fill_rate"] == pytest.approx(1.0)


def test_plan_respects_constraints():
    inst = generate_instance(4, 15, seed=2)
    plan = np.array(solve(inst, include_plan=True)["plan"])
    assert (plan >= -1e-6).all()
    assert (plan.sum(axis=1) <= np.array(inst.supply) + 1e-3).all()
    assert plan.sum(axis=0) == pytest.approx(inst.demand, abs=1e-3)


def test_objective_matches_scipy():
    """Cross-check the PuLP model against an independently written LP."""
    inst = generate_instance(4, 12, seed=5)
    W, S = inst.n_warehouses, inst.n_stores
    c = np.concatenate([np.ravel(inst.cost), inst.penalty])
    A_ub = np.zeros((W, W * S + S))
    for i in range(W):
        A_ub[i, i * S:(i + 1) * S] = 1
    A_eq = np.zeros((S, W * S + S))
    for j in range(S):
        A_eq[j, j:W * S:S] = 1
        A_eq[j, W * S + j] = 1
    ref = linprog(c, A_ub=A_ub, b_ub=inst.supply, A_eq=A_eq, b_eq=inst.demand,
                  bounds=(0, None), method="highs")
    assert solve(inst)["objective"] == pytest.approx(ref.fun, rel=1e-6)


def test_shortage_used_when_demand_exceeds_supply():
    inst = generate_instance(3, 10, seed=4)
    total_supply = sum(inst.supply)
    big = [d * 2 for d in inst.demand]
    r = solve(inst, demand=big)
    assert r["status"] == "Optimal"
    assert r["unmet_demand"] == pytest.approx(sum(big) - total_supply, rel=1e-6)


def test_scenarios_summary():
    s = run_scenarios(generate_instance(4, 15, seed=1), n_scenarios=10, seed=1)
    assert s["n_scenarios"] == 10
    assert 0 <= s["fill_rate_mean"] <= 1
    assert s["cost_p95"] >= s["cost_mean"] - s["cost_std"]


def test_zero_variation_reproduces_base():
    inst = generate_instance(4, 15, seed=1)
    s = run_scenarios(inst, n_scenarios=3, demand_cv=0.0)
    assert s["cost_std"] == pytest.approx(0, abs=1e-6)
    assert s["cost_mean"] == pytest.approx(solve(inst)["objective"], rel=1e-6)
