"""Acceptance criteria for the fault detection system.

Verification and validation both come down to one question: over the last
N readings, is the average absolute divergence between the two
temperature streams inside the specification limit?

    average( |stream_a - stream_b| ) over the last WINDOW readings
        <= SPEC_LIMIT

A single noisy reading is not a fault. A DHT22 that has drifted out of
calibration, or a Pi that is reading a different temperature than its
partner, shows up as a sustained divergence, which is what the sliding
window measures.

Both numbers are adjustable:

    FAULT_SPEC_LIMIT_F   specification limit, in degrees F (default 5.0)
    FAULT_WINDOW         how many readings the average covers (default 30)

The dashboard edits the limit live through /api/spec-limit, and CI can
re-run the whole suite at a different limit by setting the environment
variable, so the acceptance criteria can be tightened without touching
any test code.

This module is deliberately free of Flask and SQLite so the rule can be
tested on its own and reused by anything that has two streams of
readings.
"""

import os

# Matches the sliding window the dashboard has always used.
DEFAULT_WINDOW = 30

# Matches the threshold field the dashboard starts up with.
DEFAULT_SPEC_LIMIT_F = 5.0

PASS = "pass"
FAIL = "fail"

# Not enough readings have arrived yet to judge anything.
INCONCLUSIVE = "inconclusive"

# A verdict needs at least this fraction of the window filled, otherwise
# two readings that happen to agree would count as a passing run.
MINIMUM_FILL = 0.5


def window_size():
    """How many readings the acceptance average covers."""
    return int(os.environ.get("FAULT_WINDOW", DEFAULT_WINDOW))


def default_spec_limit_f():
    """The specification limit to start from, in degrees F."""
    return float(os.environ.get("FAULT_SPEC_LIMIT_F", DEFAULT_SPEC_LIMIT_F))


def to_fahrenheit(temp_c):
    """Convert Celsius to Fahrenheit.

    The sensors report Celsius, the specification limit is written in
    Fahrenheit, so every comparison happens in Fahrenheit.
    """
    return temp_c * 9 / 5 + 32


def divergence_f(temp_a_c, temp_b_c):
    """Absolute divergence between two Celsius readings, in degrees F."""
    return abs(to_fahrenheit(temp_a_c) - to_fahrenheit(temp_b_c))


def divergences(rows, key_a, key_b):
    """Turn rows of paired readings into a list of divergences."""
    return [divergence_f(row[key_a], row[key_b]) for row in rows]


def evaluate(values, spec_limit_f=None, window=None):
    """Measure a run of divergences against the specification limit.

    `values` is oldest first, the same order the API returns rows in.
    Only the last `window` of them count.

    Returns a dict rather than a bare bool so a failing CI run says what
    the measurement actually was:

        {
          "verdict": "pass" | "fail" | "inconclusive",
          "within_spec": bool,
          "average_divergence_f": float,
          "peak_divergence_f": float,
          "spec_limit_f": float,
          "window": int,
          "sample_count": int,
        }
    """
    if spec_limit_f is None:
        spec_limit_f = default_spec_limit_f()
    if window is None:
        window = window_size()

    sample = list(values)[-window:]

    if not sample:
        average = 0.0
        peak = 0.0
    else:
        average = sum(sample) / len(sample)
        peak = max(sample)

    if len(sample) < window * MINIMUM_FILL:
        verdict = INCONCLUSIVE
        within_spec = False
    else:
        within_spec = average <= spec_limit_f
        verdict = PASS if within_spec else FAIL

    return {
        "verdict": verdict,
        "within_spec": within_spec,
        "average_divergence_f": round(average, 3),
        "peak_divergence_f": round(peak, 3),
        "spec_limit_f": spec_limit_f,
        "window": window,
        "sample_count": len(sample),
    }


def describe(result, label):
    """One line summarising a result, for CI logs and assertion messages."""
    return (
        f"{label}: {result['verdict'].upper()} "
        f"average divergence {result['average_divergence_f']}F "
        f"over {result['sample_count']}/{result['window']} readings, "
        f"specification limit {result['spec_limit_f']}F "
        f"(peak {result['peak_divergence_f']}F)"
    )
