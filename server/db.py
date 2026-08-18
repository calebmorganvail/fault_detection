"""SQLite storage for the fault detection server.

v1 and v2 kept every reading in a plain Python list, so restarting the
server threw all of the data away. v3 writes readings to a SQLite file
instead.

Three tables:
  readings            every raw reading, exactly as a sensor sent it
  synced_readings     A/B pairs that the synchronizer matched up
  simulation_readings sensor A paired with the simulated baseline
  settings            small key/value store (currently the baseline temp)
"""

import os
import sqlite3

# Overridable so Docker can point at a mounted volume and the tests can
# point at a temp file.
DB_PATH = os.environ.get("DB_PATH", "readings.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id        INTEGER PRIMARY KEY,
    sensor_id TEXT NOT NULL,
    temp_c    REAL NOT NULL,
    humidity  REAL,
    timestamp TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS synced_readings (
    id         INTEGER PRIMARY KEY,
    timestamp  TEXT NOT NULL,
    temp_a_c   REAL NOT NULL,
    humidity_a REAL,
    temp_b_c   REAL NOT NULL,
    humidity_b REAL
);

CREATE TABLE IF NOT EXISTS simulation_readings (
    id              INTEGER PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    sensor_temp_c   REAL NOT NULL,
    simulated_temp_c REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect():
    """Open a connection to the database file."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Create the tables if they do not exist yet."""
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)

    connection = connect()
    connection.executescript(SCHEMA)
    connection.commit()
    connection.close()


def insert_reading(sensor_id, temp_c, humidity, timestamp):
    """Store one raw reading."""
    connection = connect()
    connection.execute(
        "INSERT INTO readings (sensor_id, temp_c, humidity, timestamp)"
        " VALUES (?, ?, ?, ?)",
        (sensor_id, temp_c, humidity, timestamp),
    )
    connection.commit()
    connection.close()


def insert_synced_pair(timestamp, temp_a_c, humidity_a, temp_b_c, humidity_b):
    """Store one A/B pair that the synchronizer matched up."""
    connection = connect()
    connection.execute(
        "INSERT INTO synced_readings"
        " (timestamp, temp_a_c, humidity_a, temp_b_c, humidity_b)"
        " VALUES (?, ?, ?, ?, ?)",
        (timestamp, temp_a_c, humidity_a, temp_b_c, humidity_b),
    )
    connection.commit()
    connection.close()


def insert_simulation_reading(timestamp, sensor_temp_c, simulated_temp_c):
    """Store sensor A next to whatever the baseline was at that moment."""
    connection = connect()
    connection.execute(
        "INSERT INTO simulation_readings"
        " (timestamp, sensor_temp_c, simulated_temp_c) VALUES (?, ?, ?)",
        (timestamp, sensor_temp_c, simulated_temp_c),
    )
    connection.commit()
    connection.close()


def get_synced_readings(limit=100):
    """Return the most recent synced pairs, oldest first."""
    return _get_recent("synced_readings", limit)


def get_simulation_readings(limit=100):
    """Return the most recent simulation rows, oldest first."""
    return _get_recent("simulation_readings", limit)


def _get_recent(table, limit):
    """Grab the newest rows from a table and flip them back into order.

    The chart wants oldest to newest, but SQLite gives us the newest
    rows most easily, so we reverse the list before returning it.
    """
    connection = connect()
    rows = connection.execute(
        f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    connection.close()

    return [dict(row) for row in reversed(rows)]


def get_last_seen(sensor_id):
    """Return the timestamp of a sensor's most recent reading, or None."""
    connection = connect()
    row = connection.execute(
        "SELECT timestamp FROM readings WHERE sensor_id = ?"
        " ORDER BY id DESC LIMIT 1",
        (sensor_id,),
    ).fetchone()
    connection.close()

    return row["timestamp"] if row else None


def get_setting(key, default):
    """Read a setting, falling back to a default if it was never set."""
    connection = connect()
    row = connection.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    connection.close()

    return row["value"] if row else default


def set_setting(key, value):
    """Write a setting, replacing any existing value."""
    connection = connect()
    connection.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    connection.commit()
    connection.close()
