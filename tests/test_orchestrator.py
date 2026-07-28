"""
End-to-end test: starts the simulated device fleet in background threads,
runs a full detect/analyze/remediate/validate cycle against them, and
asserts the unhealthy device (device-02, seeded at 92% CPU) actually
gets flagged, remediated, and comes back healthy.
"""

import time
import unittest

from app.db import RunStore
from app.device_client import DeviceClient
from app.mock_devices import DEVICE_FLEET, start_all_devices
from app.orchestrator import ClosedLoopOrchestrator


class TestClosedLoopOrchestrator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start_all_devices()
        time.sleep(0.5)  # let Flask dev servers bind

    def setUp(self):
        self.clients = [
            DeviceClient(device_id=d["device_id"], base_url=f"http://127.0.0.1:{d['port']}")
            for d in DEVICE_FLEET
        ]
        self.store = RunStore(db_path=":memory:") if False else RunStore(db_path="test_run_history.db")
        self.orchestrator = ClosedLoopOrchestrator(clients=self.clients, store=self.store)

    def test_detect_flags_unhealthy_device(self):
        statuses = self.orchestrator._detect(run_id=self.store.start_run())
        self.assertIn("device-02", statuses)
        self.assertFalse(statuses["device-02"].healthy)
        self.assertTrue(statuses["device-01"].healthy)
        self.assertTrue(statuses["device-03"].healthy)

    def test_full_cycle_remediates_unhealthy_device(self):
        summary = self.orchestrator.run_cycle()

        self.assertEqual(summary.devices_checked, 3)
        self.assertEqual(summary.devices_unhealthy, 1)
        self.assertEqual(len(summary.remediations), 1)

        result = summary.remediations[0]
        self.assertEqual(result.device_id, "device-02")
        self.assertEqual(result.action_taken, "drain_connections")
        self.assertTrue(result.validated)
        self.assertTrue(result.healthy_after)

    def test_history_is_persisted(self):
        self.orchestrator.run_cycle()
        history = self.store.get_history(limit=5)
        self.assertGreaterEqual(len(history), 1)
        latest = history[0]
        self.assertIn("events", latest)
        phases = {e["phase"] for e in latest["events"]}
        self.assertTrue({"detect", "analyze"}.issubset(phases))

    @classmethod
    def tearDownClass(cls):
        import os
        if os.path.exists("test_run_history.db"):
            os.remove("test_run_history.db")


if __name__ == "__main__":
    unittest.main()
