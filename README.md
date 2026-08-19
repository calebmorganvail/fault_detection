# Temperature Sensor Fault Detection

Real-time dashboard that detects faulty DHT22 temperature readings.

Usecase: 
Testing 1-2 DHT22 sensors for accurate readings

- **Simulation** — compares one sensor against an adjustable simulated
  baseline, so a fault can be triggered on demand without touching the
  hardware.

- **Multiple Live Sensors** — compares two Raspberry Pis against each
  other, using server side synchronization so the two streams are always
  compared at the same moment in time. The idea here is that if both pis are placed in the same room and are supposed to be reading the same temp
the divergence of the two sensors can be deteceted beyond a certain threshold.



## Architecture

```
Pi A ─┐
      ├─ POST /api/reading ─→ Flask server ─→ Synchronizer ─→ SQLite ─→ dashboard polls every 1s
Pi B ─┘
```

```
fault_detection/
├── dashboard/            Frontend (HTML, CSS, JS)
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

Covers the synchronizer, the SQLite layer, and the API end to end.

## Demo walkthrough
