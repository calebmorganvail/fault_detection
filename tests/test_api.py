"""End to end tests that go through the Flask routes."""


def post(client, sensor_id, temp_c=21.0, humidity=50.0):
    return client.post(
        "/api/reading",
        json={"sensor_id": sensor_id, "temp_c": temp_c, "humidity": humidity},
    )


def test_sensor_a_feeds_the_simulation_tab(client):
    post(client, "A", temp_c=25.0)

    rows = client.get("/api/simulation").get_json()

    assert len(rows) == 1
    assert rows[0]["sensor_temp_c"] == 25.0
    assert rows[0]["simulated_temp_c"] == 21.1


def test_sensor_b_does_not_feed_the_simulation_tab(client):
    post(client, "B", temp_c=25.0)

    assert client.get("/api/simulation").get_json() == []


def test_live_tab_only_sees_synchronized_pairs(client):
    # A on its own is buffered, nothing to show yet.
    response = post(client, "A", temp_c=21.0)
    assert response.get_json()["synced"] is False
    assert client.get("/api/sensors").get_json() == []

    # B arrives in the same second, so the pair is released.
    response = post(client, "B", temp_c=22.0)
    assert response.get_json()["synced"] is True

    rows = client.get("/api/sensors").get_json()
    assert len(rows) == 1
    assert rows[0]["temp_a_c"] == 21.0
    assert rows[0]["temp_b_c"] == 22.0


def test_simulated_temp_can_be_changed(client):
    client.post("/api/simulated-temp", json={"temp_c": 30.0})
    post(client, "A", temp_c=25.0)

    rows = client.get("/api/simulation").get_json()

    assert rows[0]["simulated_temp_c"] == 30.0


def test_status_reports_which_sensors_are_online(client):
    post(client, "A")

    status = client.get("/api/status").get_json()

    assert status["sensors"]["A"]["online"] is True
    assert status["sensors"]["B"]["online"] is False
    assert status["buffered"] == 1


def test_dashboard_is_served(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Temperature Sensor Fault Detection" in response.data
