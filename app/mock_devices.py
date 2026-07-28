"""
mock_devices.py

Simulated network device REST APIs, used as stand-ins for real
F5 / AVI / NSX device endpoints during local development and testing.

Each simulated device exposes:
  GET  /api/v1/status      -> current health snapshot
  POST /api/v1/remediate   -> apply a remediation action, improves health

Run standalone with:
    python -m app.mock_devices
This starts 3 simulated devices on ports 6001, 6002, 6003, one of which
(device-02) starts in an unhealthy state so the orchestrator has
something real to detect and fix.
"""

from __future__ import annotations

import random
import threading

from flask import Flask, jsonify, request


def make_device_app(device_id: str, start_unhealthy: bool = False) -> Flask:
    app = Flask(device_id)

    state = {
        "cpu_load": 92.0 if start_unhealthy else round(random.uniform(20, 50), 1),
        "active_connections": 4800 if start_unhealthy else random.randint(100, 800),
    }

    @app.get("/api/v1/status")
    def status():
        healthy = state["cpu_load"] < 80.0
        return jsonify(
            {
                "device_id": device_id,
                "healthy": healthy,
                "cpu_load": state["cpu_load"],
                "active_connections": state["active_connections"],
            }
        )

    @app.post("/api/v1/remediate")
    def remediate():
        action = request.get_json(force=True).get("action")
        if action == "drain_connections":
            state["active_connections"] = max(0, state["active_connections"] // 4)
            state["cpu_load"] = max(10.0, state["cpu_load"] * 0.4)
        elif action == "restart_pool_member":
            state["cpu_load"] = round(random.uniform(15, 35), 1)
            state["active_connections"] = random.randint(50, 300)
        else:
            return jsonify({"error": f"unknown action '{action}'"}), 400

        return jsonify(
            {
                "device_id": device_id,
                "action": action,
                "result": "applied",
                "cpu_load": state["cpu_load"],
                "active_connections": state["active_connections"],
            }
        )

    return app


def run_device(device_id: str, port: int, start_unhealthy: bool = False):
    app = make_device_app(device_id, start_unhealthy=start_unhealthy)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


DEVICE_FLEET = [
    {"device_id": "device-01", "port": 6001, "start_unhealthy": False},
    {"device_id": "device-02", "port": 6002, "start_unhealthy": True},
    {"device_id": "device-03", "port": 6003, "start_unhealthy": False},
]


def start_all_devices() -> list[threading.Thread]:
    """Start every simulated device in its own thread. Used by demo scripts and tests."""
    threads = []
    for device in DEVICE_FLEET:
        t = threading.Thread(
            target=run_device,
            kwargs=device,
            daemon=True,
        )
        t.start()
        threads.append(t)
    return threads


if __name__ == "__main__":
    import time

    print("Starting simulated device fleet...")
    for d in DEVICE_FLEET:
        print(f"  {d['device_id']} -> http://127.0.0.1:{d['port']}  (unhealthy={d['start_unhealthy']})")
    start_all_devices()
    time.sleep(100000)
