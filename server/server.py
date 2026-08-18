"""Flask server for the temperature sensor fault detection dashboard.

Serves the dashboard, accepts readings from the sensors, synchronizes the
two live streams, and stores everything in SQLite.
"""

import os
import threading
from datetime import datetime, timedelta, timezone

from flask import Flask, jsonify, request, send_from_directory

import db
import sync

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard")

# A sensor counts as offline once it has been quiet for this long.
SENSOR_TIMEOUT_SECONDS = 5

DEFAULT_SIMULATED_TEMP_C = 21.1

app = Flask(__name__)

synchronizer = sync.Synchronizer()

# Readings arrive from two sensors at once and Flask handles them on
# separate threads, so guard the buffer and the database with a lock.
lock = threading.Lock()


# --- dashboard ------------------------------------------------------------


@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


# --- sensors --------------------------------------------------------------


@app.route("/api/reading", methods=["POST"])
def post_reading():
    """Accept one reading from a sensor."""
    data = request.get_json()
    sensor_id = data.get("sensor_id", "A")
    temp_c = data["temp_c"]
    humidity = data.get("humidity")

    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    with lock:
        db.insert_reading(sensor_id, temp_c, humidity, timestamp)

        # The simulation tab always compares sensor A against the
        # baseline, the same as it did in v2.
        if sensor_id == "A":
            db.insert_simulation_reading(timestamp, temp_c, simulated_temp_c())

        pair = synchronizer.add(
            {
                "sensor_id": sensor_id,
                "temp_c": temp_c,
                "humidity": humidity,
                "timestamp": timestamp,
            }
        )

        if pair:
            db.insert_synced_pair(
                pair["timestamp"],
                pair["a"]["temp_c"],
                pair["a"]["humidity"],
                pair["b"]["temp_c"],
                pair["b"]["humidity"],
            )

        synchronizer.drop_stale(now)
        buffered = synchronizer.pending()

    print(f"Sensor {sensor_id}: {temp_c}C | synced: {pair is not None} | buffered: {buffered}")
    return jsonify({"status": "ok", "synced": pair is not None, "buffered": buffered})


# --- dashboard data -------------------------------------------------------


@app.route("/api/simulation", methods=["GET"])
def get_simulation():
    """Sensor A paired with the simulated baseline, oldest first."""
    limit = request.args.get("limit", 60, type=int)
    return jsonify(db.get_simulation_readings(limit))


@app.route("/api/sensors", methods=["GET"])
def get_sensors():
    """Synchronized A/B pairs only, oldest first."""
    limit = request.args.get("limit", 100, type=int)
    return jsonify(db.get_synced_readings(limit))


@app.route("/api/status", methods=["GET"])
def get_status():
    """Which sensors are alive, plus what the synchronizer is doing."""
    return jsonify(
        {
            "simulated_temp_c": simulated_temp_c(),
            "sensors": {
                "A": sensor_status("A"),
                "B": sensor_status("B"),
            },
            "buffered": synchronizer.pending(),
            "synced_count": synchronizer.synced_count,
            "dropped_count": synchronizer.dropped_count,
        }
    )


@app.route("/api/simulated-temp", methods=["POST"])
def set_simulated_temp():
    """Update the simulated baseline from the dashboard."""
    data = request.get_json()
    db.set_setting("simulated_temp_c", data["temp_c"])
    print(f"Simulated temp updated to {data['temp_c']}C")
    return jsonify({"status": "ok"})


# --- helpers --------------------------------------------------------------


def simulated_temp_c():
    """The baseline temperature the simulation tab compares against."""
    return float(db.get_setting("simulated_temp_c", DEFAULT_SIMULATED_TEMP_C))


def sensor_status(sensor_id):
    """Report whether a sensor has sent anything recently."""
    last_seen = db.get_last_seen(sensor_id)
    if last_seen is None:
        return {"online": False, "last_seen": None}

    age = datetime.now(timezone.utc) - datetime.fromisoformat(last_seen)
    return {
        "online": age < timedelta(seconds=SENSOR_TIMEOUT_SECONDS),
        "last_seen": last_seen,
    }


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5001)
