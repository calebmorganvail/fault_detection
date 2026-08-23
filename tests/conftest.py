import os
import sys

import db
import devices
import pytest

# The server modules live in server/ and import each other by plain name,
# so put that folder on the path before the tests import anything.
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TESTS_DIR)

sys.path.insert(0, os.path.join(PROJECT_DIR, "server"))

# The device fixture lives next to the tests, so make sure it is
# importable no matter where pytest was started from.
sys.path.insert(0, TESTS_DIR)


@pytest.fixture
def database(tmp_path):
    """Point the db module at a throwaway SQLite file for one test."""
    original = db.DB_PATH
    db.DB_PATH = str(tmp_path / "test.db")
    db.init_db()
    yield db
    db.DB_PATH = original


@pytest.fixture
def client(database):
    """A Flask test client wired up to the throwaway database."""
    import server

    server.synchronizer = server.sync.Synchronizer()
    server.app.config["TESTING"] = True
    return server.app.test_client()


@pytest.fixture
def bench(client, monkeypatch):
    """Build and run a two device bench against the test server.

    Defaults to one well behaved device and one deliberately unreliable
    one, which is the fixture the acceptance criteria are measured
    against in CI.
    """

    def build(device_a=None, device_b=None, cycles=90):
        return devices.Bench(
            client,
            device_a if device_a is not None else devices.nominal_device("A"),
            device_b if device_b is not None else devices.unreliable_device("B"),
            monkeypatch,
        ).run(cycles)

    return build


@pytest.fixture
def make_bench(client, monkeypatch):
    """A bench that has not been run yet, for multi phase tests."""

    def build(device_a, device_b):
        return devices.Bench(client, device_a, device_b, monkeypatch)

    return build
