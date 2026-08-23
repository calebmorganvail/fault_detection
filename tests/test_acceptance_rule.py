"""Unit tests for the acceptance rule itself.

The rule: the average absolute divergence over the last N readings has
to stay at or under the specification limit. Everything here is pure
arithmetic, no server and no database.
"""

import pytest

import acceptance


def test_celsius_converts_to_fahrenheit():
    assert acceptance.to_fahrenheit(0) == 32
    assert acceptance.to_fahrenheit(100) == 212


def test_divergence_is_absolute_and_in_fahrenheit():
    # 1C of difference is 1.8F, whichever sensor is the warmer one.
    assert acceptance.divergence_f(21.0, 22.0) == pytest.approx(1.8)
    assert acceptance.divergence_f(22.0, 21.0) == pytest.approx(1.8)


def test_divergences_are_read_off_paired_rows():
    rows = [
        {"temp_a_c": 21.0, "temp_b_c": 22.0},
        {"temp_a_c": 21.0, "temp_b_c": 21.0},
    ]

    assert acceptance.divergences(rows, "temp_a_c", "temp_b_c") == pytest.approx(
        [1.8, 0.0]
    )


def test_a_run_inside_the_limit_passes():
    result = acceptance.evaluate([1.0] * 30, spec_limit_f=5.0, window=30)

    assert result["verdict"] == "pass"
    assert result["within_spec"] is True
    assert result["average_divergence_f"] == 1.0
    assert result["sample_count"] == 30


def test_a_run_outside_the_limit_fails():
    result = acceptance.evaluate([6.0] * 30, spec_limit_f=5.0, window=30)

    assert result["verdict"] == "fail"
    assert result["within_spec"] is False
    assert result["average_divergence_f"] == 6.0


def test_sitting_exactly_on_the_limit_passes():
    """The limit is inclusive, so a run at spec is a pass, not a fail."""
    result = acceptance.evaluate([5.0] * 30, spec_limit_f=5.0, window=30)

    assert result["verdict"] == "pass"


def test_one_spike_does_not_fail_the_run():
    """A single bad reading is noise. The window is what averages it out."""
    values = [0.0] * 29 + [30.0]

    result = acceptance.evaluate(values, spec_limit_f=5.0, window=30)

    assert result["verdict"] == "pass"
    assert result["average_divergence_f"] == 1.0
    assert result["peak_divergence_f"] == 30.0


def test_only_the_last_window_of_readings_counts():
    """Older readings drop out of the window as new ones arrive."""
    values = [50.0] * 100 + [1.0] * 30

    result = acceptance.evaluate(values, spec_limit_f=5.0, window=30)

    assert result["sample_count"] == 30
    assert result["average_divergence_f"] == 1.0
    assert result["verdict"] == "pass"


def test_the_window_is_adjustable():
    values = [10.0] * 5 + [1.0] * 5

    assert acceptance.evaluate(values, 5.0, window=5)["average_divergence_f"] == 1.0
    assert acceptance.evaluate(values, 5.0, window=10)["average_divergence_f"] == 5.5


def test_the_specification_limit_is_adjustable():
    values = [2.0] * 30

    assert acceptance.evaluate(values, spec_limit_f=5.0)["verdict"] == "pass"
    assert acceptance.evaluate(values, spec_limit_f=1.0)["verdict"] == "fail"


def test_too_few_readings_is_inconclusive_not_a_pass():
    """Two readings that happen to agree do not qualify as verified."""
    result = acceptance.evaluate([0.0, 0.0], spec_limit_f=5.0, window=30)

    assert result["verdict"] == "inconclusive"
    assert result["within_spec"] is False


def test_no_readings_at_all_is_inconclusive():
    result = acceptance.evaluate([], spec_limit_f=5.0, window=30)

    assert result["verdict"] == "inconclusive"
    assert result["sample_count"] == 0


def test_a_half_full_window_is_enough_to_judge():
    result = acceptance.evaluate([1.0] * 15, spec_limit_f=5.0, window=30)

    assert result["verdict"] == "pass"


def test_defaults_come_from_the_environment(monkeypatch):
    """CI re-runs the suite at a different specification this way."""
    monkeypatch.setenv("FAULT_SPEC_LIMIT_F", "1.5")
    monkeypatch.setenv("FAULT_WINDOW", "10")

    assert acceptance.default_spec_limit_f() == 1.5
    assert acceptance.window_size() == 10

    result = acceptance.evaluate([2.0] * 30)

    assert result["spec_limit_f"] == 1.5
    assert result["window"] == 10
    assert result["sample_count"] == 10
    assert result["verdict"] == "fail"


def test_defaults_fall_back_when_the_environment_is_clean(monkeypatch):
    monkeypatch.delenv("FAULT_SPEC_LIMIT_F", raising=False)
    monkeypatch.delenv("FAULT_WINDOW", raising=False)

    assert acceptance.default_spec_limit_f() == acceptance.DEFAULT_SPEC_LIMIT_F
    assert acceptance.window_size() == acceptance.DEFAULT_WINDOW


def test_describe_is_readable_in_a_ci_log():
    result = acceptance.evaluate([6.0] * 30, spec_limit_f=5.0, window=30)

    line = acceptance.describe(result, "live")

    assert "live" in line
    assert "FAIL" in line
    assert "6.0" in line
    assert "5.0" in line
