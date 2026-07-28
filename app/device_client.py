"""
device_client.py

A thin REST client for talking to network devices over HTTP APIs.

This mirrors the integration pattern used for real device APIs like
F5 iControl REST or NSX/AVI ALB APIs: authenticate once, poll a status
endpoint, and issue a remediation action when a device reports an
unhealthy state. The concrete devices here are simulated (see
mock_devices.py) because real F5/NSX appliances aren't available in
this environment -- but the client shape (base_url + session + typed
methods) is exactly what you'd swap a real vendor SDK/API into.
"""

from __future__ import annotations

import requests
from dataclasses import dataclass


class DeviceUnreachableError(Exception):
    """Raised when a device does not respond within the timeout window."""


@dataclass
class DeviceStatus:
    device_id: str
    healthy: bool
    cpu_load: float
    active_connections: int
    raw: dict


class DeviceClient:
    """REST client for a single network device / load balancer node."""

    def __init__(self, device_id: str, base_url: str, timeout: float = 2.0):
        self.device_id = device_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def get_status(self) -> DeviceStatus:
        """Poll the device's health/status endpoint (detect phase)."""
        try:
            resp = self.session.get(f"{self.base_url}/api/v1/status", timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DeviceUnreachableError(f"{self.device_id} unreachable: {exc}") from exc

        data = resp.json()
        return DeviceStatus(
            device_id=self.device_id,
            healthy=data["healthy"],
            cpu_load=data["cpu_load"],
            active_connections=data["active_connections"],
            raw=data,
        )

    def remediate(self, action: str) -> dict:
        """Issue a remediation action (e.g. 'drain_connections', 'restart_pool_member')."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/remediate",
                json={"action": action},
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise DeviceUnreachableError(f"{self.device_id} unreachable during remediation: {exc}") from exc
        return resp.json()
