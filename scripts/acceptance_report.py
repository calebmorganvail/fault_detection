"""Run the two device bench once and write a verification summary.

CI calls this after the test suite so the run leaves behind the actual
measurements, not just a green tick. Two cases are measured:

    matched   two devices that agree, expected to pass
    drifted   the same fixture with device B 4C out of calibration,
              expected to fail

If either case comes out the wrong way round the acceptance criteria are
not measuring anything, so this script exits non zero and the CI job
fails with it.

    python scripts/acceptance_report.py
    python scripts/acceptance_report.py >> "$GITHUB_STEP_SUMMARY"
"""

import contextlib
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import acceptance  # noqa: E402
import db  # noqa: E402
import devices  # noqa: E402
import server  # noqa: E402


class Patch:
    """Just enough of pytest's monkeypatch for the bench to run."""

    def setattr(self, obj, name, value):
        setattr(obj, name, value)


def run_case(device_b, cycles=90):
    """Run one bench against a throwaway database and report both streams."""
    db.DB_PATH = os.path.join(tempfile.mkdtemp(), "acceptance.db")
    db.init_db()

    server.synchronizer = server.sync.Synchronizer()
    server.app.config["TESTING"] = True

    # The server logs every reading it accepts, which would bury the
    # summary this script exists to print.
    with contextlib.redirect_stdout(io.StringIO()):
        bench = devices.Bench(
            server.app.test_client(),
            devices.nominal_device("A"),
            device_b,
            Patch(),
        ).run(cycles)

        # The configured limit is what gets reported. The default limit
        # is what the discrimination check below is measured against, so
        # re-running CI at a tighter specification reports a failing
        # fixture without also claiming the criteria are broken.
        report = bench.acceptance()
        baseline = bench.acceptance(limit=acceptance.DEFAULT_SPEC_LIMIT_F)
        status = bench.status()

    return report, baseline, status


def row(case, stream, result):
    return (
        f"| {case} | {stream} | **{result['verdict'].upper()}** | "
        f"{result['average_divergence_f']} | {result['peak_divergence_f']} | "
        f"{result['spec_limit_f']} | {result['sample_count']}/{result['window']} |"
    )


def main():
    matched, matched_baseline, matched_status = run_case(
        devices.unreliable_device("B")
    )
    drifted, drifted_baseline, _ = run_case(devices.drifted_device("B"))

    print("## Acceptance criteria")
    print()
    print(
        f"Average absolute divergence over the last **{matched['window']}** "
        f"readings, against a specification limit of "
        f"**{matched['spec_limit_f']}F**."
    )
    print()
    print("| Case | Stream | Verdict | Average F | Peak F | Limit F | Readings |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    print(row("matched devices", "live A/B", matched["live"]))
    print(row("matched devices", "simulation", matched["simulation"]))
    print(row("device B drifted 4C", "live A/B", drifted["live"]))
    print()
    print("### Fixture")
    print()
    print(
        f"Two simulated devices, no hardware. Device B dropped readings and "
        f"arrived late often enough for the synchronizer to discard "
        f"**{matched_status['dropped_count']}** unmatched buckets while "
        f"releasing **{matched_status['synced_count']}** matched pairs."
    )

    # Discrimination check, always against the default limit: two
    # devices that agree have to pass it, and a device 4C out of
    # calibration has to fail it. If both come out the same way the
    # criteria are not measuring anything.
    failures = []
    if matched_baseline["live"]["verdict"] != acceptance.PASS:
        failures.append(
            "matched devices should pass the default "
            f"{acceptance.DEFAULT_SPEC_LIMIT_F}F limit"
        )
    if drifted_baseline["live"]["verdict"] != acceptance.FAIL:
        failures.append(
            "a device 4C out of calibration should fail the default "
            f"{acceptance.DEFAULT_SPEC_LIMIT_F}F limit"
        )

    if failures:
        print()
        print("**The acceptance criteria are not discriminating:**")
        for failure in failures:
            print(f"- {failure}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
