"""
orchestrator.py

Closed-loop automation agent: detect / analyze / remediate / validate.

Polls a fleet of devices CONCURRENTLY using a thread pool (network I/O
bound work, so threads -- not processes -- are the right tool here),
decides which devices are unhealthy, issues a remediation action to
each one in parallel, then re-polls to confirm the fix worked. Every
phase is logged to SQLite so a run can be replayed/audited afterward.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .db import RunStore
from .device_client import DeviceClient, DeviceStatus, DeviceUnreachableError

CPU_LOAD_THRESHOLD = 80.0


@dataclass
class RemediationResult:
    device_id: str
    action_taken: str | None
    healthy_before: bool
    healthy_after: bool | None
    validated: bool


@dataclass
class RunSummary:
    run_id: int
    devices_checked: int
    devices_unhealthy: int
    remediations: list[RemediationResult] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)


class ClosedLoopOrchestrator:
    def __init__(self, clients: list[DeviceClient], store: RunStore, max_workers: int = 8):
        self.clients = clients
        self.store = store
        self.max_workers = max_workers

    # ---------- detect ----------
    def _detect(self, run_id: int) -> dict[str, DeviceStatus]:
        results: dict[str, DeviceStatus] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_client = {pool.submit(c.get_status): c for c in self.clients}
            for future in as_completed(future_to_client):
                client = future_to_client[future]
                try:
                    status = future.result()
                    results[client.device_id] = status
                    self.store.log_event(
                        run_id, client.device_id, "detect",
                        f"cpu_load={status.cpu_load} connections={status.active_connections}",
                        healthy=status.healthy,
                    )
                except DeviceUnreachableError as exc:
                    self.store.log_event(run_id, client.device_id, "detect", str(exc), healthy=None)
        return results

    # ---------- analyze ----------
    def _analyze(self, run_id: int, statuses: dict[str, DeviceStatus]) -> list[str]:
        unhealthy = []
        for device_id, status in statuses.items():
            is_unhealthy = (not status.healthy) or status.cpu_load >= CPU_LOAD_THRESHOLD
            if is_unhealthy:
                unhealthy.append(device_id)
                self.store.log_event(
                    run_id, device_id, "analyze",
                    f"flagged unhealthy: cpu_load={status.cpu_load} >= {CPU_LOAD_THRESHOLD}",
                    healthy=False,
                )
            else:
                self.store.log_event(
                    run_id, device_id, "analyze",
                    f"within threshold: cpu_load={status.cpu_load} < {CPU_LOAD_THRESHOLD}",
                    healthy=True,
                )
        return unhealthy

    # ---------- remediate ----------
    def _remediate(self, run_id: int, unhealthy_ids: list[str]) -> dict[str, dict]:
        clients_by_id = {c.device_id: c for c in self.clients}
        results: dict[str, dict] = {}

        def _fix(device_id: str) -> tuple[str, dict]:
            client = clients_by_id[device_id]
            outcome = client.remediate("drain_connections")
            return device_id, outcome

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(_fix, did): did for did in unhealthy_ids}
            for future in as_completed(futures):
                device_id = futures[future]
                try:
                    _, outcome = future.result()
                    results[device_id] = outcome
                    self.store.log_event(run_id, device_id, "remediate", str(outcome))
                except DeviceUnreachableError as exc:
                    self.store.log_event(run_id, device_id, "remediate", str(exc))
        return results

    # ---------- validate ----------
    def _validate(self, run_id: int, device_ids: list[str]) -> dict[str, bool]:
        clients_by_id = {c.device_id: c for c in self.clients}
        validated: dict[str, bool] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = {pool.submit(clients_by_id[did].get_status): did for did in device_ids}
            for future in as_completed(futures):
                device_id = futures[future]
                try:
                    status = future.result()
                    validated[device_id] = status.healthy
                    self.store.log_event(
                        run_id, device_id, "validate",
                        f"post-remediation cpu_load={status.cpu_load}",
                        healthy=status.healthy,
                    )
                except DeviceUnreachableError as exc:
                    validated[device_id] = False
                    self.store.log_event(run_id, device_id, "validate", str(exc), healthy=False)
        return validated

    # ---------- full cycle ----------
    def run_cycle(self) -> RunSummary:
        run_id = self.store.start_run()

        statuses = self._detect(run_id)
        unhealthy_ids = self._analyze(run_id, statuses)
        unreachable = [c.device_id for c in self.clients if c.device_id not in statuses]

        remediation_outcomes = self._remediate(run_id, unhealthy_ids)
        validated = self._validate(run_id, unhealthy_ids) if unhealthy_ids else {}

        summary = RunSummary(
            run_id=run_id,
            devices_checked=len(statuses),
            devices_unhealthy=len(unhealthy_ids),
            unreachable=unreachable,
        )
        for device_id in unhealthy_ids:
            summary.remediations.append(
                RemediationResult(
                    device_id=device_id,
                    action_taken=remediation_outcomes.get(device_id, {}).get("action"),
                    healthy_before=False,
                    healthy_after=validated.get(device_id),
                    validated=bool(validated.get(device_id)),
                )
            )

        self.store.finish_run(run_id)
        return summary
