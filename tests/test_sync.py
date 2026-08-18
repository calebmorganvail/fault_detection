"""Tests for the synchronizer, which is the fix v3 is built around."""

from datetime import datetime, timedelta, timezone

import sync


def reading(sensor_id, timestamp):
    return {
        "sensor_id": sensor_id,
        "temp_c": 21.0,
        "humidity": 50.0,
        "timestamp": timestamp,
    }


def test_one_sensor_alone_does_not_produce_a_pair():
    synchronizer = sync.Synchronizer()

    result = synchronizer.add(reading("A", "2026-08-18T12:00:00.100000+00:00"))

    assert result is None
    assert synchronizer.pending() == 1


def test_both_sensors_in_the_same_second_produce_a_pair():
    synchronizer = sync.Synchronizer()

    synchronizer.add(reading("A", "2026-08-18T12:00:00.100000+00:00"))
    result = synchronizer.add(reading("B", "2026-08-18T12:00:00.900000+00:00"))

    assert result is not None
    assert result["a"]["sensor_id"] == "A"
    assert result["b"]["sensor_id"] == "B"
    assert synchronizer.pending() == 0
    assert synchronizer.synced_count == 1


def test_readings_from_different_seconds_are_not_paired():
    """This is the v1 bug: these two used to get compared to each other."""
    synchronizer = sync.Synchronizer()

    synchronizer.add(reading("A", "2026-08-18T12:00:00.900000+00:00"))
    result = synchronizer.add(reading("B", "2026-08-18T12:00:01.100000+00:00"))

    assert result is None
    assert synchronizer.pending() == 2


def test_stale_buckets_are_dropped_after_the_timeout():
    synchronizer = sync.Synchronizer(timeout_seconds=3)
    start = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)

    synchronizer.add(reading("A", start.isoformat()))

    assert synchronizer.drop_stale(start + timedelta(seconds=2)) == 0
    assert synchronizer.pending() == 1

    assert synchronizer.drop_stale(start + timedelta(seconds=4)) == 1
    assert synchronizer.pending() == 0
    assert synchronizer.dropped_count == 1


def test_a_late_partner_still_pairs_inside_the_timeout():
    synchronizer = sync.Synchronizer(timeout_seconds=3)
    start = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)

    synchronizer.add(reading("A", start.isoformat()))
    synchronizer.drop_stale(start + timedelta(seconds=2))
    result = synchronizer.add(reading("B", start.isoformat()))

    assert result is not None
    assert synchronizer.dropped_count == 0
