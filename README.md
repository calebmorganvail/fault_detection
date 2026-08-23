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
│   ├── acceptance.py     Sliding window specification limit
│   └── db.py             SQLite storage
├── pi/                   Runs on the Raspberry Pi
│   ├── sensor.py         Reads the real DHT22
│   ├── fake_sensor.py    Stand in sensor for demos without hardware
│   └── pyproject.toml
├── tests/                pytest
│   ├── devices.py        Two simulated devices, one unreliable
│   ├── test_two_device_bench.py  End to end V&V against that fixture
│   └── ...
├── scripts/
│   ├── acceptance_report.py  Writes the CI acceptance summary
│   └── verify_demo.py        Checks a running stack over HTTP
├── .github/workflows/ci.yml  Runs the suite on every push
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
| `/api/status`          | GET    | Sensor liveness, counters, acceptance report|
| `/api/acceptance`      | GET    | Pass/fail against the specification limit  |
| `/api/simulated-temp`  | POST   | Update the simulated baseline              |
| `/api/spec-limit`      | POST   | Update the specification limit             |

### Fault detection

Both tabs use the same rules:

- **Green** — divergence under 2°F
- **Yellow** — divergence over 2°F
- **Red** — the average divergence over the last 30 readings exceeds the
  specification limit

The specification limit and the simulated baseline are editable in real
time.

### Acceptance criteria

The red condition is the acceptance criterion the whole test suite is
built on:

```
average( |stream A − stream B| ) over the last WINDOW readings  ≤  SPEC LIMIT
```

One noisy reading is not a fault. A sensor that has drifted out of
calibration shows up as a sustained divergence, which is what the
sliding window measures. Both numbers are adjustable:

| Setting              | Default | Adjust it by                                  |
| -------------------- | ------- | --------------------------------------------- |
| `FAULT_SPEC_LIMIT_F` | 5.0 °F  | env var, the dashboard field, `/api/spec-limit`|
| `FAULT_WINDOW`       | 30      | env var, `?window=` on `/api/acceptance`       |

The rule lives in `server/acceptance.py` on its own, so the dashboard,
the server and the tests all measure the same way.

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

Covers the synchronizer, the SQLite layer, the acceptance rule, and the
API end to end.

### The two device test fixture

`tests/devices.py` stands in for the bench so nothing has to be plugged
in. Device A behaves. Device B is deliberately unreliable, the way the
second Pi actually behaved:

- a calibration offset, so the two never read identically
- a wider noise band
- dropped readings, when a DHT22 returns `None`
- late readings, when network jitter pushes a POST into the next second

Both devices run off a seeded RNG and a bench clock the test controls,
so a run is reproducible down to the reading. A CI failure means a
regression, not a flaky sensor.

`tests/test_two_device_bench.py` drives that fixture through the real
server and asserts the acceptance criteria:

- two devices that agree stay inside the specification limit
- a device 4 °C out of calibration fails it — the criteria have to be
  able to fail, or they are not measuring anything
- recalibrating that device flips the verdict back to pass once thirty
  good readings are in, which is what makes it a *sliding* window
- readings that lost their partner are discarded, never paired with a
  reading from a different second

Re-run the whole suite at a different specification:

```
FAULT_SPEC_LIMIT_F=2.0 FAULT_WINDOW=30 uv run --group dev pytest
```

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request:

| Job              | What it does                                                     |
| ---------------- | ---------------------------------------------------------------- |
| `test`           | The full suite on Python 3.11, 3.12 and 3.13, JUnit XML uploaded  |
| `demo-stack`     | Builds the image, brings up the demo stack, verifies it over HTTP |

The `test` job also runs `scripts/acceptance_report.py`, which measures
the fixture and writes the result into the run's job summary, so a green
tick comes with the numbers behind it:

| Case                | Stream     | Verdict  | Average °F | Limit °F |
| ------------------- | ---------- | -------- | ---------- | -------- |
| matched devices     | live A/B   | **PASS** | 0.353      | 5.0      |
| device B drifted 4C | live A/B   | **FAIL** | 7.219      | 5.0      |

The `demo-stack` job runs `scripts/verify_demo.py` against the running
containers, so the packaged system is checked the same way a person
would check it, over HTTP, with no imports into the app.

To re-verify at a different specification limit, run the workflow from
the Actions tab with **Run workflow** and set the limit or the window.
No test code changes.

## Demo walkthrough
