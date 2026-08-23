"""A test fixture of two simulated devices.

The real bench is two Raspberry Pis with a DHT22 each, sitting in the
same room, POSTing to the server once a second. None of that is
available on a CI runner, so this module stands in for it.

Device A behaves. Device B is deliberately unreliable, the way the
second Pi actually behaved on the bench:

  * a small calibration offset, so its readings are never identical
  * a wider noise band
  * dropped readings, when the DHT22 returns None
  * late readings, when network jitter pushed a POST into the next
    second, which is the exact condition the synchronizer exists to
    handle

Everything is driven from a seeded RNG and a bench clock the test owns,
so a run is byte for byte reproducible. CI failures mean a real
regression, not a coin flip.
"""

import math
from datetime import datetime, timedelta, timezone
from random import Random

# The bench clock starts here and advances one second per cycle.
START = datetime(2026, 8, 18, 12, 0, 0, tzinfo=timezone.utc)


class SimulatedDevice:
    """One stand in Pi. Mirrors the readings pi/fake_sensor.py sends."""

    def __init__(
        self,
        sensor_id,
        base_temp_c=21.1,
        offset_c=0.0,
        noise_c=0.0,
        dropout_rate=0.0,
        late_rate=0.0,
        seed=1,
    ):
        self.sensor_id = sensor_id
        self.base_temp_c = base_temp_c

        # How far this device is out of calibration.
        self.offset_c = offset_c

        # Half width of the per reading noise band.
        self.noise_c = noise_c

        # How often the sensor returns nothing at all.
        self.dropout_rate = dropout_rate

        # How often a reading arrives a second late.
        self.late_rate = late_rate

        self.random = Random(seed)

        self.sent = 0
        self.dropped = 0
        self.delayed = 0

    def read(self, step):
        """Return one reading, or None if the device dropped it."""
        if self.random.random() < self.dropout_rate:
            self.dropped += 1
            return None

        # The same slow sine wave for both devices, because they are
        # supposed to be measuring the same room. The divergence comes
        # from the offset and the noise, not from the signal.
        temp_c = (
            self.base_temp_c
            + self.offset_c
            + math.sin(step / 15)
            + self.random.uniform(-self.noise_c, self.noise_c)
        )

        self.sent += 1
        return {
            "sensor_id": self.sensor_id,
            "temp_c": round(temp_c, 2),
            "humidity": round(50 + math.sin(step / 20) * 5, 2),
        }

    def is_late(self, step):
        """Whether this reading gets held back into the next second."""
        late = self.random.random() < self.late_rate
        if late:
            self.delayed += 1
        return late


def nominal_device(sensor_id="A", **overrides):
    """A device that behaves: no drift, tight noise, nothing dropped."""
    settings = {"noise_c": 0.15, "seed": 11}
    settings.update(overrides)
    return SimulatedDevice(sensor_id, **settings)


def unreliable_device(sensor_id="B", **overrides):
    """The deliberately unreliable device.

    Still inside specification. It is unreliable in the way real
    hardware is unreliable, which is what the system has to tolerate
    without crying fault.
    """
    settings = {
        "offset_c": 0.15,
        "noise_c": 0.3,
        "dropout_rate": 0.15,
        "late_rate": 0.25,
        "seed": 23,
    }
    settings.update(overrides)
    return SimulatedDevice(sensor_id, **settings)


def drifted_device(sensor_id="B", offset_c=4.0, **overrides):
    """An unreliable device that has also drifted out of calibration.

    4C of offset is about 7.2F, comfortably past the default 5F
    specification limit. This is the negative control: it proves the
    acceptance criteria can actually fail.
    """
    return unreliable_device(sensor_id, offset_c=offset_c, **overrides)


class Bench:
    """Runs the two devices against the real server, on a bench clock.

    The server timestamps readings the moment they arrive, so the clock
    has to be under test control for the synchronizer's one second
    buckets to mean anything. `monkeypatch` swaps the server's clock for
    this one, and every cycle of `run` advances it by a second.
    """

    def __init__(self, client, device_a, device_b, monkeypatch, start=START):
        self.client = client
        self.devices = (device_a, device_b)
        self.device_a = device_a
        self.device_b = device_b
        self.now = start
        self.cycles = 0

        # Readings held back by a late device, delivered next cycle.
        self.held = []

        self._install_clock(monkeypatch)

    def _install_clock(self, monkeypatch):
        import server

        bench = self

        class BenchClock(datetime):
            """A datetime whose now() is whatever the bench says it is."""

            @classmethod
            def now(cls, tz=None):
                return bench.now

        monkeypatch.setattr(server, "datetime", BenchClock)

    def tick(self, seconds=1):
        """Advance the bench clock."""
        self.now = self.now + timedelta(seconds=seconds)

    def post(self, reading):
        return self.client.post("/api/reading", json=reading)

    def run(self, cycles=90):
        """Run both devices for `cycles` one second cycles."""
        for step in range(cycles):
            # Anything a device held back last second arrives now, in
            # the wrong bucket.
            due, self.held = self.held, []
            for reading in due:
                self.post(reading)

            for device in self.devices:
                reading = device.read(step)
                if reading is None:
                    continue

                if device.is_late(step):
                    self.held.append(reading)
                else:
                    self.post(reading)

            self.tick()
            self.cycles += 1

        for reading in self.held:
            self.post(reading)
        self.held = []

        return self

    # --- reading the result back through the API --------------------------

    def status(self):
        return self.client.get("/api/status").get_json()

    def acceptance(self, limit=None, window=None):
        """The server's own pass/fail verdict for this run."""
        query = {}
        if limit is not None:
            query["limit"] = limit
        if window is not None:
            query["window"] = window

        return self.client.get("/api/acceptance", query_string=query).get_json()

    def live_pairs(self, limit=100):
        return self.client.get(f"/api/sensors?limit={limit}").get_json()

    def simulation_rows(self, limit=100):
        return self.client.get(f"/api/simulation?limit={limit}").get_json()
