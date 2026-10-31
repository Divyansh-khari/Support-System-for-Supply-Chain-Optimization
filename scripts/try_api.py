"""Call every route of a running API and print what comes back.

    python scripts/try_api.py                         # API on localhost:8000
    python scripts/try_api.py http://localhost:8000
"""
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

# One client for all calls: the connection is opened once and reused, the way
# a browser or Locust behaves. Only the first call pays the connection set-up.
client = httpx.Client(base_url=BASE, timeout=120)


def call(method, path, body=None):
    t0 = time.perf_counter()
    r = client.request(method, path, json=body)
    ms = (time.perf_counter() - t0) * 1000
    print(f"\n--- {method} {path}  ->  HTTP {r.status_code} in {ms:.0f} ms")
    return r.json()


def show(d, keys):
    for k in keys:
        if k in d:
            v = d[k]
            print(f"  {k:<20}: {round(v, 4) if isinstance(v, float) else v}")


h = call("GET", "/health")
print(f"  mode: {h['mode']}")

s = call("POST", "/instances/summary", {"n_warehouses": 10, "n_stores": 50, "seed": 0})
show(s, ["n_warehouses", "n_stores", "total_supply", "total_demand", "served_by"])

o = call("POST", "/optimize", {"n_warehouses": 40, "n_stores": 200, "seed": 0})
show(o, ["status", "objective", "fill_rate", "n_variables", "total_seconds",
         "network_overhead_ms", "served_by"])

c = call("POST", "/optimize/custom", {
    "supply": [100, 100], "demand": [30, 40, 50],
    "cost": [[1, 2, 9], [5, 6, 1]]})
show(c, ["status", "objective", "unmet_demand", "network_overhead_ms", "served_by"])
print("  plan (rows = warehouses, columns = stores):")
for row in c["plan"]:
    print("   ", row)

m = call("POST", "/simulate", {"n_warehouses": 10, "n_stores": 50, "n_scenarios": 20})
show(m, ["n_scenarios", "cost_mean", "cost_p95", "fill_rate_mean",
         "prob_any_shortage", "total_seconds", "network_overhead_ms", "served_by"])

bad = call("POST", "/optimize/custom", {"supply": [100], "demand": [30, 40],
                                         "cost": [[1]]})
print("  error:", json.dumps(bad["detail"][0]["msg"]))