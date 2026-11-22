"""Locust load test for the supply-chain API.

Usually started by loadtest/run.py, which sets these environment variables:

  SCSO_PROFILE      optimize  -> every user calls /optimize        (Experiment A)
                    mixed     -> 90% light /instances/summary,
                                 10% heavy /simulate               (Experiments B, C)
  SCSO_WAREHOUSES   problem size for /optimize (default 10)
  SCSO_STORES       problem size for /optimize (default 50)
  SCSO_SERVER_LOG   CSV file for per-request server-side timings (optional)

Locust measures what the user sees (end-to-end latency, including the trip
over the internet). The server-side log records what our API reports about
itself: compute time, service-to-service overhead and which replica answered.
That part is not affected by the network between this laptop and Azure.
"""
import csv
import os
import random
import time

from locust import HttpUser, between, events, task

PROFILE = os.getenv("SCSO_PROFILE", "optimize")
WAREHOUSES = int(os.getenv("SCSO_WAREHOUSES", "10"))
STORES = int(os.getenv("SCSO_STORES", "50"))
SERVER_LOG = os.getenv("SCSO_SERVER_LOG")

_log_file = None
_log = None


@events.test_start.add_listener
def _open_log(environment, **kwargs):
    global _log_file, _log
    if SERVER_LOG:
        _log_file = open(SERVER_LOG, "w", newline="")
        _log = csv.writer(_log_file)
        _log.writerow(["time", "route", "status", "client_ms", "compute_ms",
                       "overhead_ms", "service", "replica"])


@events.test_stop.add_listener
def _close_log(environment, **kwargs):
    # Requests still in flight when the test stops may finish afterwards,
    # so flush rather than close; the file closes when Locust exits.
    if _log_file:
        _log_file.flush()


def _record(route, resp, client_ms):
    """Write one server-side row; mark the request failed if the body is wrong."""
    try:
        body = resp.json()
    except ValueError:
        resp.failure(f"HTTP {resp.status_code}, body is not JSON")
        return
    if resp.status_code != 200:
        resp.failure(f"HTTP {resp.status_code}: {str(body)[:120]}")
        return
    if _log:
        served = body.get("served_by", {})
        compute = body.get("total_seconds")
        _log.writerow([round(time.time(), 3), route, resp.status_code, round(client_ms, 1),
                       round(compute * 1000, 1) if compute is not None else "",
                       body.get("network_overhead_ms", ""),
                       served.get("service", ""), served.get("replica", "")])


class ApiUser(HttpUser):
    # Each simulated user waits 0.5-1 s between requests, like a real client.
    wait_time = between(0.5, 1.0)

    def _post(self, route, payload):
        t0 = time.perf_counter()
        with self.client.post(route, json=payload, name=route, catch_response=True) as resp:
            _record(route, resp, (time.perf_counter() - t0) * 1000)

    @task
    def work(self):
        if PROFILE == "optimize":
            # Random seed: a different problem each time, but always the same size.
            self._post("/optimize", {"n_warehouses": WAREHOUSES, "n_stores": STORES,
                                     "seed": random.randint(0, 99)})
        elif random.random() < 0.9:
            self._post("/instances/summary", {"n_warehouses": 10, "n_stores": 50,
                                              "seed": random.randint(0, 99)})
        else:
            self._post("/simulate", {"n_warehouses": 10, "n_stores": 50, "n_scenarios": 10,
                                     "seed": random.randint(0, 99)})