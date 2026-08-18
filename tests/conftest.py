import os
import sys

# The server modules live in server/ and import each other by plain name,
# so put that folder on the path before the tests import anything.
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server")
)

import pytest

import db


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
