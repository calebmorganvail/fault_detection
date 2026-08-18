"""Tests for the SQLite storage layer."""


def test_readings_round_trip(database):
    database.insert_reading("A", 21.0, 50.0, "2026-08-18T12:00:00+00:00")

    assert database.get_last_seen("A") == "2026-08-18T12:00:00+00:00"
    assert database.get_last_seen("B") is None


def test_synced_readings_come_back_oldest_first(database):
    for second in range(3):
        database.insert_synced_pair(
            f"2026-08-18T12:00:0{second}+00:00", 21.0, 50.0, 22.0, 51.0
        )

    rows = database.get_synced_readings(limit=10)

    assert len(rows) == 3
    assert rows[0]["timestamp"] == "2026-08-18T12:00:00+00:00"
    assert rows[-1]["timestamp"] == "2026-08-18T12:00:02+00:00"


def test_limit_keeps_the_newest_rows(database):
    for second in range(5):
        database.insert_simulation_reading(
            f"2026-08-18T12:00:0{second}+00:00", 21.0, 20.0
        )

    rows = database.get_simulation_readings(limit=2)

    assert len(rows) == 2
    assert rows[0]["timestamp"] == "2026-08-18T12:00:03+00:00"
    assert rows[-1]["timestamp"] == "2026-08-18T12:00:04+00:00"


def test_settings_default_and_overwrite(database):
    assert database.get_setting("simulated_temp_c", 21.1) == 21.1

    database.set_setting("simulated_temp_c", 25.0)

    assert float(database.get_setting("simulated_temp_c", 21.1)) == 25.0
