"""
api.py

Flask control-plane API for the closed-loop automation agent.

Endpoints:
    GET  /devices              -> current status of every device in the fleet
    POST /automation/run       -> trigger one detect/analyze/remediate/validate cycle
    GET  /automation/history   -> past run history from SQLite

This is intentionally a thin HTTP layer over orchestrator.py so the
automation logic stays framework-agnostic and unit-testable without
spinning up Flask at all (see tests/test_orchestrator.py).
"""

from __future__ import annotations

from dataclasses import asdict

from flask import Flask, jsonify
from flask_cors import CORS

from .db import RunStore
from .device_client import DeviceClient, DeviceUnreachableError
from .mock_devices import DEVICE_FLEET
from .orchestrator import ClosedLoopOrchestrator


def create_app(db_path: str = "automation_history.db") -> Flask:
    app = Flask(__name__)

    # Allow the React dev server (Vite, port 5173) to call this API from the browser.
    # Browsers block cross-origin requests unless the server opts in with CORS headers.
    CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])

    clients = [
        DeviceClient(device_id=d["device_id"], base_url=f"http://127.0.0.1:{d['port']}")
        for d in DEVICE_FLEET
    ]
    store = RunStore(db_path=db_path)
    orchestrator = ClosedLoopOrchestrator(clients=clients, store=store)

    @app.get("/devices")
    def list_devices():
        out = []
        for client in clients:
            try:
                status = client.get_status()
                out.append(asdict(status))
            except DeviceUnreachableError as exc:
                out.append({"device_id": client.device_id, "error": str(exc)})
        return jsonify(out)

    @app.post("/automation/run")
    def trigger_run():
        summary = orchestrator.run_cycle()
        return jsonify(
            {
                "run_id": summary.run_id,
                "devices_checked": summary.devices_checked,
                "devices_unhealthy": summary.devices_unhealthy,
                "unreachable": summary.unreachable,
                "remediations": [asdict(r) for r in summary.remediations],
            }
        )

    @app.get("/automation/history")
    def history():
        return jsonify(store.get_history())

    return app


if __name__ == "__main__":
    import time
    from .mock_devices import start_all_devices

    print("Starting simulated device fleet on ports 6001-6003...")
    start_all_devices()
    time.sleep(0.5)  # let the device Flask servers finish binding

    flask_app = create_app()
    flask_app.run(host="127.0.0.1", port=7000, debug=False)
