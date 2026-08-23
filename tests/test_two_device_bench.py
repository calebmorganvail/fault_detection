"""End to end verification and validation against two simulated devices.

Every test here runs the real Flask server, the real synchronizer and
the real SQLite layer. The only thing standing in for hardware is the
device fixture in devices.py: one well behaved device and one
deliberately unreliable one that drifts, drops readings and arrives
late.

That is what lets this suite run on a CI runner with no Raspberry Pi,
no DHT22 and no network in the loop.

One test, the acceptance gate at the top, measures against whatever
specification limit the environment is configured with, so CI can be
re-run at a tighter limit to find where the system stops passing. The
rest pin their own limit and window, because they are testing what the
rule does rather than where it is currently set.
"""

import acceptance
import devices

# What the rest of the suite measures against, independent of however
# CI happens to be configured for this run.
LIMIT_F = 5.0
WINDOW = 30


# --- the acceptance gate -------------------------------------------------


def test_the_fixture_meets_the_configured_specification_limit(bench):
    """The gate. Reads FAULT_SPEC_LIMIT_F and FAULT_WINDOW.

    Two devices in the same room, one of them unreliable, have to stay
    inside the specification limit over the configured window. Tighten
    the limit in the workflow and this is the test that starts failing.
    """
    run = bench()

    result = run.acceptance()["live"]

    assert result["verdict"] == acceptance.PASS, acceptance.describe(result, "live")
    assert result["spec_limit_f"] == acceptance.default_spec_limit_f()
    assert result["window"] == acceptance.window_size()


# --- verification: the criteria measure what they claim to ---------------


def test_a_clean_run_of_two_devices_passes(bench):
    run = bench()

    result = run.acceptance(limit=LIMIT_F, window=WINDOW)["live"]

    assert result["verdict"] == acceptance.PASS, acceptance.describe(result, "live")
    assert result["sample_count"] == WINDOW
    assert result["average_divergence_f"] <= LIMIT_F


def test_a_drifted_device_fails_the_specification_limit(bench):
    """The negative control: the criteria have to be able to fail."""
    run = bench(device_b=devices.drifted_device("B"))

    result = run.acceptance(limit=LIMIT_F, window=WINDOW)["live"]

    assert result["verdict"] == acceptance.FAIL, acceptance.describe(result, "live")
    # 4C of drift is about 7.2F, so the average should land near there.
    assert result["average_divergence_f"] > 6.0


def test_the_specification_limit_is_adjustable(bench):
    """Same readings, different limit, different verdict."""
    run = bench()

    measured = run.acceptance(window=WINDOW)["live"]["average_divergence_f"]

    tight = run.acceptance(limit=measured / 2, window=WINDOW)["live"]
    loose = run.acceptance(limit=measured * 2, window=WINDOW)["live"]

    assert tight["verdict"] == acceptance.FAIL
    assert loose["verdict"] == acceptance.PASS
    assert tight["average_divergence_f"] == loose["average_divergence_f"]


def test_the_limit_can_be_changed_through_the_api(bench):
    """The dashboard edits the limit live; the server has to honour it."""
    run = bench()

    measured = run.acceptance()["live"]["average_divergence_f"]

    run.client.post("/api/spec-limit", json={"limit_f": measured / 2})
    assert run.status()["spec_limit_f"] == measured / 2
    assert run.acceptance()["live"]["verdict"] == acceptance.FAIL

    run.client.post("/api/spec-limit", json={"limit_f": measured * 2})
    assert run.acceptance()["live"]["verdict"] == acceptance.PASS


def test_the_window_is_adjustable_too(bench):
    run = bench()

    assert run.acceptance(window=10)["live"]["sample_count"] == 10
    assert run.acceptance(window=30)["live"]["sample_count"] == 30


# --- validation: the verdict tracks the state of the hardware ------------


def test_the_verdict_follows_the_last_thirty_readings(make_bench):
    """A device that is recalibrated mid run stops failing.

    Phase one runs a device that has drifted 4C out. Phase two is the
    same device after recalibration. Once thirty good readings are in,
    the verdict has to flip back to pass on its own, which is the point
    of measuring over a sliding window instead of over the whole run.
    """
    device_b = devices.drifted_device("B")
    run = make_bench(devices.nominal_device("A"), device_b)

    run.run(60)
    drifted = run.acceptance(limit=LIMIT_F, window=WINDOW)["live"]
    assert drifted["verdict"] == acceptance.FAIL, acceptance.describe(drifted, "drifted")

    # The sensor is recalibrated and the readings come back in line.
    device_b.offset_c = 0.0
    run.run(60)

    recovered = run.acceptance(limit=LIMIT_F, window=WINDOW)["live"]
    assert recovered["verdict"] == acceptance.PASS, acceptance.describe(
        recovered, "recovered"
    )

    # The run still contains the bad readings. They have simply aged out
    # of the window.
    whole_run = acceptance.divergences(
        run.live_pairs(limit=1000), "temp_a_c", "temp_b_c"
    )
    assert len(whole_run) > WINDOW
    assert max(whole_run) > LIMIT_F


def test_a_short_run_is_inconclusive_rather_than_a_pass(bench):
    """Five good readings do not mean the fixture has been verified."""
    run = bench(cycles=5)

    result = run.acceptance(limit=LIMIT_F, window=WINDOW)["live"]

    assert result["verdict"] == acceptance.INCONCLUSIVE
    assert result["within_spec"] is False


# --- the unreliable device is genuinely unreliable -----------------------


def test_the_unreliable_device_really_does_misbehave(bench):
    """Guards the fixture itself: a fixture that behaves proves nothing."""
    run = bench()

    assert run.device_b.dropped > 0, "device B never dropped a reading"
    assert run.device_b.delayed > 0, "device B was never late"
    assert run.device_a.dropped == 0, "device A is supposed to be reliable"


def test_dropped_and_late_readings_never_become_mismatched_pairs(bench):
    """The v1 bug, held down by a test.

    A reading that lost its partner has to be discarded, never paired
    with a reading from a different second.
    """
    run = bench()
    status = run.status()

    assert status["dropped_count"] > 0, "the unreliable device caused no drops"

    pairs = run.live_pairs(limit=1000)
    timestamps = [row["timestamp"] for row in pairs]

    assert len(timestamps) == len(set(timestamps)), "a bucket was released twice"
    assert timestamps == sorted(timestamps), "pairs came back out of order"
    assert len(pairs) == status["synced_count"]
    assert len(pairs) <= run.device_b.sent


def test_a_silent_device_shows_up_in_the_status(bench):
    """One device down means no pairs at all, and the status says why."""
    silent = devices.SimulatedDevice("B", dropout_rate=1.0, seed=5)
    run = bench(device_b=silent)

    status = run.status()

    assert status["sensors"]["A"]["online"] is True
    assert status["sensors"]["B"]["online"] is False
    assert run.live_pairs() == []
    assert run.acceptance()["live"]["verdict"] == acceptance.INCONCLUSIVE


# --- the simulation stream, measured against the same limit --------------


def test_the_simulation_stream_passes_against_a_matching_baseline(bench):
    run = bench()

    result = run.acceptance(limit=LIMIT_F, window=WINDOW)["simulation"]

    assert result["verdict"] == acceptance.PASS, acceptance.describe(
        result, "simulation"
    )
    assert result["sample_count"] == WINDOW


def test_the_simulation_stream_fails_against_a_baseline_it_cannot_meet(
    client, monkeypatch
):
    """Moving the baseline is how a fault gets triggered on demand."""
    client.post("/api/simulated-temp", json={"temp_c": 15.0})

    run = devices.Bench(
        client,
        devices.nominal_device("A"),
        devices.unreliable_device("B"),
        monkeypatch,
    ).run(60)

    result = run.acceptance(limit=LIMIT_F, window=WINDOW)["simulation"]

    assert result["verdict"] == acceptance.FAIL, acceptance.describe(
        result, "simulation"
    )


# --- what CI reads --------------------------------------------------------


def test_status_carries_the_full_acceptance_report(bench):
    run = bench()

    status = run.status()

    assert status["spec_limit_f"] == acceptance.default_spec_limit_f()
    assert status["acceptance"]["window"] == acceptance.window_size()
    assert set(status["acceptance"]) == {
        "spec_limit_f",
        "window",
        "simulation",
        "live",
    }
    for stream in ("simulation", "live"):
        assert status["acceptance"][stream]["verdict"] in {
            acceptance.PASS,
            acceptance.FAIL,
            acceptance.INCONCLUSIVE,
        }
