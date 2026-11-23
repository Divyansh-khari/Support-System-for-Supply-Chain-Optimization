"""Spike load shape for Experiment C (autoscaling policies).

Same users and traffic as locustfile.py (use SCSO_PROFILE=mixed), but the
number of users follows a fixed timeline instead of staying constant:

    quiet  -> spike -> quiet
    10 users for 60 s, 150 users for 240 s, 10 users for 180 s   (default)

Override with SCSO_SPIKE="60,240,180" (seconds) and SCSO_SPIKE_USERS="10,150".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from locust import LoadTestShape  # noqa: E402

from locustfile import ApiUser  # noqa: E402,F401  (Locust finds the user class here)

QUIET_S, SPIKE_S, COOL_S = (int(x) for x in os.getenv("SCSO_SPIKE", "60,240,180").split(","))
LOW, HIGH = (int(x) for x in os.getenv("SCSO_SPIKE_USERS", "10,150").split(","))


class SpikeShape(LoadTestShape):
    def tick(self):
        t = self.get_run_time()
        if t < QUIET_S:
            return LOW, LOW
        if t < QUIET_S + SPIKE_S:
            return HIGH, 50            # reach the spike within ~3 s
        if t < QUIET_S + SPIKE_S + COOL_S:
            return LOW, 50
        return None                    # end of test
