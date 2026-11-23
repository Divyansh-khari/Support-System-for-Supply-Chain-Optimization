"""Run one spike test (Experiment C) and save the results.

    python loadtest/run_spike.py --label http_min1 --host https://scso-api...

Writes to results/C/:
  <label>_stats.csv, ..._stats_history.csv   Locust's own numbers
  <label>_server.csv                          one row per request (who answered, timings)
  <label>_timeline.csv                        10-second windows: users phase, req/s,
                                              p95 latency, simulation replicas seen
and appends one line to results/C/summary.csv.
"""
import argparse
import csv
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WINDOW = 10   # seconds per timeline row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--host", required=True)
    ap.add_argument("--spike", default="60,240,180", help="quiet,spike,cooldown seconds")
    ap.add_argument("--users", default="10,150", help="low,high users")
    args = ap.parse_args()
    quiet, spike, cool = (int(x) for x in args.spike.split(","))

    out = ROOT / "results" / "C"
    out.mkdir(parents=True, exist_ok=True)
    prefix = out / args.label
    server_csv = Path(f"{prefix}_server.csv")
    env = {**os.environ, "SCSO_PROFILE": "mixed", "SCSO_SERVER_LOG": str(server_csv),
           "SCSO_SPIKE": args.spike, "SCSO_SPIKE_USERS": args.users}

    print(f"\n=== {args.label}: {args.users} users, phases {args.spike} s")
    start = time.time()
    start_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    subprocess.run([sys.executable, "-m", "locust", "-f", str(ROOT / "loadtest" / "spike.py"),
                    "--headless", "--host", args.host, "--csv", str(prefix),
                    "--only-summary", "--loglevel", "WARNING"], env=env, cwd=ROOT)
    end_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")

    s = pd.read_csv(server_csv)
    s["t"] = s["time"] - start
    s["window"] = (s["t"] // WINDOW * WINDOW).astype(int)
    sim = s[s.route == "/simulate"]

    # Timeline in 10-second windows
    tl = s.groupby("window").agg(requests=("route", "size"), p95_ms=("client_ms", lambda x: x.quantile(.95)))
    tl["rps"] = tl.requests / WINDOW
    tl["sim_p95_ms"] = sim.groupby("window")["client_ms"].quantile(.95)
    tl["sim_replicas"] = sim.groupby("window")["replica"].nunique()
    tl["phase"] = ["quiet" if w < quiet else "spike" if w < quiet + spike else "cooldown" for w in tl.index]
    tl.round(1).to_csv(f"{prefix}_timeline.csv")

    # Summary: focus on the spike
    sp = s[(s.t >= quiet) & (s.t < quiet + spike)]
    sp_sim = sp[sp.route == "/simulate"]
    stats = pd.read_csv(f"{prefix}_stats.csv")
    agg = stats[stats.Name == "Aggregated"].iloc[0]
    first_quiet_replicas = sim[sim.t < quiet]["replica"].nunique()
    # Scale-out lag: seconds from spike start until a replica not seen before the spike answers
    before = set(sim[sim.t < quiet]["replica"])
    new = sp_sim[~sp_sim.replica.isin(before)]
    lag = round(new.t.min() - quiet, 1) if len(new) else ""
    row = {
        "time": datetime.now().isoformat(timespec="seconds"), "label": args.label,
        "start_utc": start_utc, "end_utc": end_utc,
        "requests": int(agg["Request Count"]), "failures": int(agg["Failure Count"]),
        "error_rate": round(agg["Failure Count"] / max(agg["Request Count"], 1), 4),
        "spike_rps": round(len(sp) / spike, 2),
        "spike_p95_ms": round(sp.client_ms.quantile(.95), 1) if len(sp) else "",
        "spike_sim_p95_ms": round(sp_sim.client_ms.quantile(.95), 1) if len(sp_sim) else "",
        "quiet_sim_replicas": first_quiet_replicas,
        "max_sim_replicas": int(tl.sim_replicas.max()) if tl.sim_replicas.notna().any() else 0,
        "scale_out_lag_s": lag,
    }
    summary = out / "summary.csv"
    new_file = not summary.exists()
    with open(summary, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if new_file:
            w.writeheader()
        w.writerow(row)
    print("    " + "  ".join(f"{k}={v}" for k, v in row.items() if k not in ("time", "start_utc", "end_utc")))


if __name__ == "__main__":
    main()
