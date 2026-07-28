# fleet-guardian

A Python closed-loop automation agent that polls a fleet of network devices concurrently,
detects unhealthy ones, remediates them, and validates the fix — the
detect / analyze / remediate / validate pattern used in real network and
infrastructure automation platforms.

## What this demonstrates

- **Concurrent I/O with `ThreadPoolExecutor`** — devices are polled and
  remediated in parallel, not sequentially, since each call is network-bound.
- **REST API integration pattern** matching how a real device SDK (F5
  iControl REST, AVI/NSX ALB APIs) would be wrapped: a typed client class
  with `get_status()` / `remediate()` methods over `requests.Session`.
- **Flask control-plane API** exposing the agent over HTTP
  (`/devices`, `/automation/run`, `/automation/history`).
- **SQLite persistence** of every phase of every run, so a cycle can be
  audited after the fact.
- **Automated tests** that spin up the simulated fleet and assert the
  full loop actually detects, fixes, and validates a seeded unhealthy device.

## Honest scope note

The three "devices" this agent talks to are simulated Flask services
(`app/mock_devices.py`) exposing `/api/v1/status` and `/api/v1/remediate`,
not real F5/AVI/NSX appliances — I don't have access to that hardware/licensing.
The client layer (`app/device_client.py`) is written the way a real vendor
integration would be: swap the `base_url` and the JSON shape for the real
API and the orchestrator logic doesn't change. This is presented as a
personal project demonstrating the automation pattern, not as production
network engineering experience.

## Project layout

```
app/
  device_client.py   REST client for a single device (get_status / remediate)
  mock_devices.py     Simulated device REST APIs (Flask), one fleet member seeded unhealthy
  orchestrator.py      Closed-loop agent: detect -> analyze -> remediate -> validate
  db.py                 SQLite persistence for run history
  api.py                 Flask control-plane API wrapping the orchestrator
tests/
  test_orchestrator.py  End-to-end test against the live simulated fleet
scripts/
  run_demo.sh             Starts everything and runs one cycle via curl
```

## Running it

```bash
pip install -r requirements.txt
./scripts/run_demo.sh
```

Or run the test suite directly:

```bash
pytest tests/ -v
# or, if pytest isn't installed:
python3 -m unittest tests.test_orchestrator -v
```

## API

| Method | Path                  | Description                                  |
|--------|-----------------------|-----------------------------------------------|
| GET    | `/devices`             | Current status of every device in the fleet   |
| POST   | `/automation/run`      | Trigger one detect/analyze/remediate/validate cycle |
| GET    | `/automation/history`  | Past run history with full per-device event trail |

## Possible extensions

- Add a FastAPI variant of `api.py` alongside the Flask one (same
  orchestrator underneath) to demonstrate both frameworks.
- Swap `ThreadPoolExecutor` for `asyncio` + `httpx` for a fully async version.
- Add a scheduler (cron / APScheduler) to run cycles continuously rather
  than on-demand.
- Point `device_client.py` at a real lab device (e.g. an F5 BIG-IP VE
  trial or NSX-T lab) if/when available.
