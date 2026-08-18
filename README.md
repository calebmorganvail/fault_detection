# Temperature Sensor Fault Detection

Real-time dashboard that detects faulty DHT22 temperature sensors two
different ways:

- **Simulation** — compares one sensor against an adjustable simulated
  baseline, so a fault can be triggered on demand without touching the
  hardware.
- **Multiple Live Sensors** — compares two Raspberry Pis against each
  other, using server side synchronization so the two streams are always
  compared at the same moment in time.

This is version 3 of a project built across two classes:

| Version           | Class            | What it did                                     |
| ----------------- | ---------------- | ----------------------------------------------- |
| `temp_monitor`    | Operating Systems| Two Pis, live line chart, fault detection       |
| `temp_monitor_v2` | Web Development  | One Pi vs a simulated baseline, redesigned UI   |
| `fault_detection` | —                | Both of the above, plus the synchronization fix |

## The synchronization fix

v1 had a bug that got flagged during the class demo. Each Pi POSTed on
its own schedule and the server appended every reading to one shared
list. The dashboard then took "the last two readings" and treated them
as a pair. The two Pis were never in lockstep, so network jitter meant
the dashboard regularly compared an A reading against a B reading from a
different moment, which showed up as divergence spikes that were not
real.

v3 fixes this in `server/sync.py`. Readings go into a buffer keyed by a
one second time bucket, and a bucket is only released to the dashboard
once both sensors have reported for it. The dashboard never sees a
mismatched pair. A bucket whose partner never arrives is dropped after 3
seconds so one disconnected sensor cannot stall the chart.

The tradeoff: readings that straddle a bucket boundary get dropped
instead of paired. `/api/status` reports `synced_count` and
`dropped_count` so the ratio is visible while it runs.

## Architecture

```
Pi A ─┐
      ├─ POST /api/reading ─→ Flask server ─→ Synchronizer ─→ SQLite ─→ dashboard polls every 1s
Pi B ─┘
```

```
fault_detection/
├── dashboard/            Frontend (HTML, CSS, vanilla JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── server/               Backend (Python, Flask)
│   ├── server.py         Routes
│   ├── sync.py           Timestamp bucket synchronizer
│   └── db.py             SQLite storage
├── pi/                   Runs on the Raspberry Pi
│   ├── sensor.py         Reads the real DHT22
│   ├── fake_sensor.py    Stand in sensor for demos without hardware
│   └── pyproject.toml
├── tests/                pytest
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

### API

| Endpoint               | Method | Purpose                                    |
| ---------------------- | ------ | ------------------------------------------ |
| `/api/reading`         | POST   | A sensor submits one reading               |
| `/api/simulation`      | GET    | Sensor A paired with the simulated baseline|
| `/api/sensors`         | GET    | Synchronized A/B pairs only                |
| `/api/status`          | GET    | Sensor liveness and synchronizer counters  |
| `/api/simulated-temp`  | POST   | Update the simulated baseline              |

### Fault detection

Both tabs use the same rules:

- **Green** — divergence under 2°F
- **Yellow** — divergence over 2°F
- **Red** — the average divergence over the last 30 readings exceeds the
  threshold

The threshold and the simulated baseline are editable in real time.

## Stack

**Dashboard** — HTML, CSS, vanilla JavaScript, Chart.js v4.4.7 (CDN)
**Server** — Python 3, Flask, SQLite
**Sensors** — Python 3, adafruit-circuitpython-dht, requests
**Tooling** — uv, Docker, pytest

**Hardware** — 2x Raspberry Pi 4B, 2x DHT22 sensors, 1x laptop

### What changed from v2

- `pip` → `uv`
- Readings in memory → SQLite
- Runs bare → runs in Docker
- One sensor → tabbed interface with two live sensors
- No synchronization → timestamp bucket synchronizer

## Setup

### Docker (no hardware needed)

```
docker compose --profile demo up --build
```

This starts the server plus two stand in sensors that generate readings,
one of them deliberately jittery so the synchronizer has something to
do. Open <http://localhost:5001>.

To run the server alone and point real Pis at it:

```
docker compose up --build
```

### Without Docker

```
uv sync
uv run python server/server.py
```

Open <http://localhost:5001>.

Stand in sensors, in two more terminals:

```
SENSOR_ID=A uv run python pi/fake_sensor.py
SENSOR_ID=B JITTER=0.4 OFFSET_C=0.5 uv run python pi/fake_sensor.py
```

### Real Raspberry Pis

Everything needs to be on the same network.

Get the laptop IP:

```
ipconfig getifaddr en0
```

On each Pi:

```
sudo apt-get install libgpiod2
cd ~/fault_detection/pi
uv venv && uv pip install -r pyproject.toml
SENSOR_ID=A SERVER_URL=http://<laptop-ip>:5001/api/reading uv run python sensor.py
```

Use `SENSOR_ID=B` on the second Pi.

## Tests

```
uv run --group dev pytest
```

Covers the synchronizer (bucketing, timeouts, the exact mismatch v1 got
wrong), the SQLite layer, and the API end to end.

## Demo walkthrough

<!-- DEMO VIDEO -->

