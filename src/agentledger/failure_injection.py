from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .examples import crash_once_agent, recovery_agent, register_fake_github
from .failure import RetryableAgentError
from .ids import new_id
from .runtime import Runtime, SimulatedCrash
from .scheduler import RuntimeScheduler
from .worker import LocalWorker


@dataclass(frozen=True)
class FailureInjectionCheck:
    name: str
    passed: bool
    detail: str
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail, "run_id": self.run_id}


@dataclass(frozen=True)
class FailureInjectionReport:
    passed: bool
    checks: list[FailureInjectionCheck]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [check.to_dict() for check in self.checks]}


class FailureInjectionSuite:
    """Executable reliability probes for crash, retry, lease, and cancellation semantics."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def run(self, scenario: str = "all") -> FailureInjectionReport:
        scenarios: dict[str, Callable[[], FailureInjectionCheck]] = {
            "side_effect_crash": self.side_effect_crash,
            "retry_exhaustion": self.retry_exhaustion,
            "lease_fencing": self.lease_fencing,
            "cancellation_fencing": self.cancellation_fencing,
        }
        selected = scenarios.keys() if scenario == "all" else [scenario]
        checks = [scenarios[name]() for name in selected]
        return FailureInjectionReport(passed=all(check.passed for check in checks), checks=checks)

    def side_effect_crash(self) -> FailureInjectionCheck:
        rt = self._runtime("side-effect-crash")
        external = self.root / "external" / f"{new_id('issues')}.json"
        external.parent.mkdir(parents=True, exist_ok=True)
        external.write_text("[]", encoding="utf-8")
        register_fake_github(rt, external)
        run_id, _ = rt.create_run(initial_state={"crashed_once": False})
        first_ok = asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="FailureInjector"))
        rt.store.apply_system_state_patch(run_id=run_id, patch={"crashed_once": True}, reason="failure injection recovery marker")
        second_ok = asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="FailureInjector"))
        issues = json.loads(external.read_text(encoding="utf-8"))
        final_state = rt.store.final_state(run_id)
        passed = not first_ok and second_ok and len(issues) == 1 and final_state.get("recovered") is True
        detail = f"first_ok={first_ok}, second_ok={second_ok}, external_issue_count={len(issues)}"
        return FailureInjectionCheck("side_effect_crash", passed, detail, run_id)

    def retry_exhaustion(self) -> FailureInjectionCheck:
        rt = self._runtime("retry-exhaustion")
        run_id, _ = rt.create_run(initial_state={}, retry_policy={"max_attempts": 2})

        async def flaky(_ctx: Any, _state: dict[str, Any]) -> None:
            raise RetryableAgentError("injected retryable failure")

        summary = asyncio.run(LocalWorker(rt, flaky, worker_id="failure-injector", agent_role="FailureInjector").run_until_idle(run_id=run_id, max_iterations=3))
        status = rt.store.run(run_id)["status"]
        events = [row["type"] for row in rt.store.events(run_id)]
        passed = status == "failed" and summary.attempts == 2 and "step_failed" in events
        detail = f"status={status}, attempts={summary.attempts}, stopped_reason={summary.stopped_reason}"
        return FailureInjectionCheck("retry_exhaustion", passed, detail, run_id)

    def lease_fencing(self) -> FailureInjectionCheck:
        rt = self._runtime("lease-fencing")
        run_id, step_id = rt.create_run(initial_state={})
        old_claim = rt.store.claim_step(worker_id="stale-worker", run_id=run_id, lease_seconds=0)
        if old_claim is None:
            return FailureInjectionCheck("lease_fencing", False, "failed to claim initial step", run_id)
        recovered = RuntimeScheduler(rt.store).recover_expired_leases()
        stale_rejected = False
        try:
            rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=old_claim.lease_token, base_version=0, patch={"stale": True})
        except RuntimeError:
            stale_rejected = True
        new_claim = rt.store.claim_step(worker_id="fresh-worker", run_id=run_id)
        passed = recovered.recovered_steps == 1 and stale_rejected and new_claim is not None and new_claim.attempt == 2
        detail = f"recovered_steps={recovered.recovered_steps}, stale_rejected={stale_rejected}, new_attempt={getattr(new_claim, 'attempt', None)}"
        return FailureInjectionCheck("lease_fencing", passed, detail, run_id)

    def cancellation_fencing(self) -> FailureInjectionCheck:
        rt = self._runtime("cancellation-fencing")
        run_id, step_id = rt.create_run(initial_state={})
        claim = rt.store.claim_step(worker_id="stale-worker", run_id=run_id)
        if claim is None:
            return FailureInjectionCheck("cancellation_fencing", False, "failed to claim initial step", run_id)
        cancelled_steps = RuntimeScheduler(rt.store).cancel_run(run_id, reason="failure injection cancellation")
        stale_rejected = False
        try:
            rt.store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=claim.lease_token, base_version=0, patch={"late": True})
        except RuntimeError:
            stale_rejected = True
        new_claim = rt.store.claim_step(worker_id="fresh-worker", run_id=run_id)
        passed = cancelled_steps == 1 and stale_rejected and new_claim is None and rt.store.run(run_id)["status"] == "cancelled"
        detail = f"cancelled_steps={cancelled_steps}, stale_rejected={stale_rejected}, new_claim={new_claim is not None}"
        return FailureInjectionCheck("cancellation_fencing", passed, detail, run_id)

    def _runtime(self, name: str) -> Runtime:
        return Runtime.local(self.root / name)
