"""Run a series of load tests and save the results.

For each load level it runs Locust twice:
  1. a warm-up run whose results are thrown away (wakes the apps from zero,
     opens connections, loads code), then
  2. the measured run, saved to results/<experiment>/<label>_u<users>_*.csv

After every measured run, one summary line is appended to
results/<experiment>/summary.csv, so the analysis in Phase 7 reads one file.

Examples
--------
Experiment A, monolith, medium problem, four load levels:
    python loadtest/run.py --experiment A --label mono_medium --host https://scso-mono...
        --profile optimize --warehouses 40 --stores 200 --users 10 50 100 250

Quick local check (API running on 127.0.0.1:8000):
    python loadtest/run.py --experiment local --label test --host http://127.0.0.1:8000
        --users 5 --warmup 5 --duration 15
"""
import argparse
import csv
import os
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCUSTFILE = ROOT / "loadtest" / "locustfile.py"

SUMMARY_FIELDS = [
    "time", "experiment", "label", "profile", "warehouses", "stores", "users",
    "duration_s", "requests", "failures", "error_rate", "rps",
    "p50_ms", "p95_ms", "p99_ms", "avg_ms",
    "server_compute_avg_ms", "server_compute_p95_ms",
    "overhead_avg_ms", "overhead_p95_ms", "replicas_seen",
]


def run_locust(host, users, seconds, env, csv_prefix=None):
    cmd = [sys.executable, "-m", "locust", "-f", str(LOCUSTFILE), "--headless",
           "--host", host, "-u", str(users), "-r", str(min(users, 50)),
           "-t", f"{seconds}s", "--only-summary", "--loglevel", "WARNING"]
    if csv_prefix:
        cmd += ["--csv", str(csv_prefix)]
    # Locust exits with code 1 when any request failed; that is a result, not a crash.
    subprocess.run(cmd, env=env, cwd=ROOT)


def pct(values, q):
    if not values:
        return ""
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q / 100 * len(values)))], 1)


def summarise(stats_csv, server_csv):
    row = {}
    with open(stats_csv, newline="") as f:
        for r in csv.DictReader(f):
            if r["Name"] == "Aggregated":
                req, fail = int(r["Request Count"]), int(r["Failure Count"])
                row.update(requests=req, failures=fail,
                           error_rate=round(fail / req, 4) if req else "",
                           rps=round(float(r["Requests/s"]), 2),
                           p50_ms=r["50%"], p95_ms=r["95%"], p99_ms=r["99%"],
                           avg_ms=round(float(r["Average Response Time"]), 1))
    compute, overhead, replicas = [], [], {}
    if server_csv.exists():
        with open(server_csv, newline="") as f:
            for r in csv.DictReader(f):
                if r["compute_ms"]:
                    compute.append(float(r["compute_ms"]))
                if r["overhead_ms"]:
                    overhead.append(float(r["overhead_ms"]))
                if r["replica"]:
                    replicas.setdefault(r["service"], set()).add(r["replica"])
    row.update(server_compute_avg_ms=round(statistics.mean(compute), 1) if compute else "",
               server_compute_p95_ms=pct(compute, 95),
               overhead_avg_ms=round(statistics.mean(overhead), 1) if overhead else "",
               overhead_p95_ms=pct(overhead, 95),
               replicas_seen=";".join(f"{s}={len(ids)}" for s, ids in sorted(replicas.items())))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", required=True, help="A, B, C or any name (results subfolder)")
    ap.add_argument("--label", required=True, help="e.g. mono_medium, micro_small")
    ap.add_argument("--host", required=True, help="base URL of the API")
    ap.add_argument("--profile", default="optimize", choices=["optimize", "mixed"])
    ap.add_argument("--warehouses", type=int, default=10)
    ap.add_argument("--stores", type=int, default=50)
    ap.add_argument("--users", type=int, nargs="+", default=[10, 50, 100, 250])
    ap.add_argument("--warmup", type=int, default=60, help="seconds, results discarded")
    ap.add_argument("--duration", type=int, default=120, help="seconds measured")
    args = ap.parse_args()

    out = ROOT / "results" / args.experiment
    out.mkdir(parents=True, exist_ok=True)
    summary = out / "summary.csv"
    new_file = not summary.exists()

    for users in args.users:
        env = {**os.environ, "SCSO_PROFILE": args.profile,
               "SCSO_WAREHOUSES": str(args.warehouses), "SCSO_STORES": str(args.stores)}
        print(f"\n=== {args.label}: {users} users  (warm-up {args.warmup}s, then {args.duration}s measured)")
        run_locust(args.host, users, args.warmup, env)

        prefix = out / f"{args.label}_u{users}"
        server_csv = Path(f"{prefix}_server.csv")
        run_locust(args.host, users, args.duration, {**env, "SCSO_SERVER_LOG": str(server_csv)}, prefix)

        row = {"time": datetime.now().isoformat(timespec="seconds"), "experiment": args.experiment,
               "label": args.label, "profile": args.profile, "warehouses": args.warehouses,
               "stores": args.stores, "users": users, "duration_s": args.duration,
               **summarise(Path(f"{prefix}_stats.csv"), server_csv)}
        with open(summary, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
            if new_file:
                w.writeheader()
                new_file = False
            w.writerow(row)
        print(f"    rps={row.get('rps')}  p50={row.get('p50_ms')} ms  p95={row.get('p95_ms')} ms  "
              f"errors={row.get('failures')}  compute={row.get('server_compute_avg_ms')} ms  "
              f"overhead={row.get('overhead_avg_ms')} ms  replicas={row.get('replicas_seen')}")

    print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()