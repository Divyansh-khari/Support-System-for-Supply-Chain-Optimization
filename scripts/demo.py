"""Walk through the core workload and print what each part produces.

    python scripts/demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scm_core import generate_instance, run_scenarios, solve  # noqa: E402


def line(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# 1. A tiny problem we can read by eye
line("1. Generate a small problem: 3 warehouses, 5 stores, seed 42")
inst = generate_instance(3, 5, seed=42)
print("Supply per warehouse :", inst.supply, "  total", round(sum(inst.supply), 1))
print("Demand per store     :", inst.demand, "  total", sum(inst.demand))
print("Cost per unit (rows = warehouses, columns = stores):")
for i, row in enumerate(inst.cost):
    print(f"  W{i}: " + "  ".join(f"{c:6.2f}" for c in row))
print("Penalty per unmet unit:", inst.penalty[0])

# 2. Solve it and show the shipping plan
line("2. Solve: cheapest way to meet demand")
r = solve(inst, include_plan=True)
print(f"Status          : {r['status']}")
print(f"Total cost      : {r['objective']:.2f}")
print(f"Unmet demand    : {r['unmet_demand']:.2f} units")
print(f"Fill rate       : {r['fill_rate']:.1%}")
print(f"Time            : {r['total_seconds']*1000:.1f} ms "
      f"(build {r['build_seconds']*1000:.1f} ms, solve {r['solve_seconds']*1000:.1f} ms)")
print("Shipping plan (units sent, rows = warehouses, columns = stores):")
print("        " + "".join(f"{'S'+str(j):>8}" for j in range(inst.n_stores)) + "    sent / supply")
for i, row in enumerate(r["plan"]):
    print(f"  W{i}:  " + "".join(f"{v:8.1f}" for v in row)
          + f"    {sum(row):6.1f} / {inst.supply[i]:.1f}")

# 3. Same problem when demand spikes
line("3. Demand spike: every store asks for double")
spike = solve(inst, demand=[d * 2 for d in inst.demand])
print(f"Total demand now: {sum(inst.demand) * 2:.0f}, supply only {sum(inst.supply):.1f}")
print(f"Unmet demand    : {spike['unmet_demand']:.1f} units")
print(f"Fill rate       : {spike['fill_rate']:.1%}")
print(f"Total cost      : {spike['objective']:.2f}  (includes shortage penalty)")

# 4. Monte Carlo scenarios
line("4. Simulation: 50 random demand scenarios (+/-20%), 10x50 problem, tight supply")
# supply_ratio=1.0: supply exactly equals average demand, so busy weeks run short
mid = generate_instance(10, 50, seed=1, supply_ratio=1.0)
s = run_scenarios(mid, n_scenarios=50, demand_cv=0.2, seed=1)
print(f"Average cost         : {s['cost_mean']:.2f}")
print(f"95th percentile cost : {s['cost_p95']:.2f}  (a bad-but-realistic week)")
print(f"Average fill rate    : {s['fill_rate_mean']:.2%}")
print(f"Worst 5% fill rate   : {s['fill_rate_p5']:.2%}")
print(f"Chance of a shortage : {s['prob_any_shortage']:.0%} of scenarios")
print(f"Time                 : {s['total_seconds']:.2f} s for 50 solves")

# 5. How compute time grows with size (why this is a good cloud workload)
line("5. Solve time vs problem size")
print(f"{'warehouses x stores':>20}{'variables':>12}{'time (ms)':>12}")
for w, st in [(5, 20), (10, 50), (20, 100), (40, 200), (60, 400)]:
    t = solve(generate_instance(w, st, seed=0))
    print(f"{f'{w} x {st}':>20}{t['n_variables']:>12}{t['total_seconds']*1000:>12.1f}")
