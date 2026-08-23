"""Verify a running demo stack from the outside.

`docker compose --profile demo up` starts the server plus two stand in
sensors, one of them deliberately jittery. This script waits for both to
come online, then checks the running system against the same acceptance
criteria the unit and integration tests use: average absolute divergence
over the last N readings, measured against the specification limit.

It talks HTTP only, so it verifies the container the way a person would,
with no imports from the application.

    python scripts/verify_demo.py
    DEMO_URL=http://localhost:5001 DEMO_TIMEOUT=180 python scripts/verify_demo.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("DEMO_URL", "http://localhost:5001").rstrip("/")
TIMEOUT_SECONDS = int(os.environ.get("DEMO_TIMEOUT", "180"))
POLL_SECONDS = 2


def get(path):
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=5) as response:
        return json.load(response)


def wait_for_a_verdict():
    """Poll the status endpoint until the stack has enough readings."""
    deadline = time.time() + TIMEOUT_SECONDS
    last = None

    while time.time() < deadline:
        try:
            last = get("/api/status")
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            print(f"waiting for the server: {error}")
            time.sleep(POLL_SECONDS)
            continue

        live = last["acceptance"]["live"]
        both_online = last["sensors"]["A"]["online"] and last["sensors"]["B"]["online"]

        print(
            f"sensors online: A={last['sensors']['A']['online']} "
            f"B={last['sensors']['B']['online']} | "
            f"synced {last['synced_count']} | "
            f"readings in window {live['sample_count']}/{live['window']}"
        )

        if both_online and live["verdict"] != "inconclusive":
            return last

        time.sleep(POLL_SECONDS)

    print(f"\nTimed out after {TIMEOUT_SECONDS}s. Last status:")
    print(json.dumps(last, indent=2))
    return None


def main():
    print(f"Verifying the demo stack at {BASE_URL}")

    status = wait_for_a_verdict()
    if status is None:
        return 1

    report = status["acceptance"]
    live = report["live"]
    simulation = report["simulation"]

    print()
    print(f"specification limit : {report['spec_limit_f']}F")
    print(f"window              : {report['window']} readings")
    print(
        f"live A/B            : {live['verdict'].upper()} "
        f"average {live['average_divergence_f']}F, peak {live['peak_divergence_f']}F"
    )
    print(
        f"simulation          : {simulation['verdict'].upper()} "
        f"average {simulation['average_divergence_f']}F"
    )
    print(
        f"synchronizer        : {status['synced_count']} pairs released, "
        f"{status['dropped_count']} unmatched buckets dropped"
    )

    if live["verdict"] != "pass":
        print("\nFAILED: the two simulated devices diverged past the limit.")
        return 1

    print("\nPASSED: the running stack is inside the specification limit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
