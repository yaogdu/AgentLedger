from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from typing import Any

from .runtime import AgentFunc, Runtime
from .scheduler import RuntimeScheduler

TERMINAL_RUN_STATUSES = {"completed", "failed", "cancelled"}
CLAIMABLE_STEP_STATUSES = {"pending", "retry_scheduled"}


@dataclass(frozen=True)
class WorkerRunSummary:
    worker_id: str
    run_id: str | None
    iterations: int
    attempts: int
    succeeded_attempts: int
    recovered_leases: int
    final_status: str | None
    stopped_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "run_id": self.run_id,
            "iterations": self.iterations,
            "attempts": self.attempts,
            "succeeded_attempts": self.succeeded_attempts,
            "recovered_leases": self.recovered_leases,
            "final_status": self.final_status,
            "stopped_reason": self.stopped_reason,
        }


@dataclass(frozen=True)
class WorkerServiceSummary:
    worker_id: str
    run_id: str | None
    loops: int
    attempts: int
    succeeded_attempts: int
    recovered_leases: int
    idle_polls: int
    stopped_reason: str
    final_status: str | None
    stop_requested: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "run_id": self.run_id,
            "loops": self.loops,
            "attempts": self.attempts,
            "succeeded_attempts": self.succeeded_attempts,
            "recovered_leases": self.recovered_leases,
            "idle_polls": self.idle_polls,
            "stopped_reason": self.stopped_reason,
            "final_status": self.final_status,
            "stop_requested": self.stop_requested,
        }


@dataclass(frozen=True)
class WorkerDeploymentPlan:
    agent_entrypoint: str
    root: str
    backend: str
    replicas: int
    worker_id_prefix: str
    lease_seconds: int
    max_idle_polls: int | None
    idle_sleep_seconds: float
    commands: list[list[str]]
    readiness_checks: list[list[str]]
    shutdown: dict[str, Any]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_entrypoint": self.agent_entrypoint,
            "root": self.root,
            "backend": self.backend,
            "replicas": self.replicas,
            "worker_id_prefix": self.worker_id_prefix,
            "lease_seconds": self.lease_seconds,
            "max_idle_polls": self.max_idle_polls,
            "idle_sleep_seconds": self.idle_sleep_seconds,
            "commands": self.commands,
            "readiness_checks": self.readiness_checks,
            "shutdown": self.shutdown,
            "notes": self.notes,
        }


def build_worker_deployment_plan(
    *,
    agent_entrypoint: str,
    root: str = ".agentledger",
    backend: str = "sqlite",
    replicas: int = 1,
    worker_id_prefix: str = "worker",
    lease_seconds: int = 60,
    max_idle_polls: int | None = None,
    idle_sleep_seconds: float = 0.25,
) -> WorkerDeploymentPlan:
    if replicas < 1:
        raise ValueError("replicas must be >= 1")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be > 0")
    if max_idle_polls is not None and max_idle_polls < 1:
        raise ValueError("max_idle_polls must be >= 1 or omitted")
    if idle_sleep_seconds < 0:
        raise ValueError("idle_sleep_seconds must be >= 0")
    commands = []
    for index in range(replicas):
        worker_id = f"{worker_id_prefix}-{index + 1}"
        command = [
            "agentledger",
            "--root",
            root,
            "worker",
            "serve",
            agent_entrypoint,
            "--worker-id",
            worker_id,
            "--lease-seconds",
            str(lease_seconds),
            "--idle-sleep-seconds",
            str(idle_sleep_seconds),
            "--install-signal-handlers",
        ]
        if max_idle_polls is None:
            command.extend(["--max-idle-polls", "0"])
        else:
            command.extend(["--max-idle-polls", str(max_idle_polls)])
        commands.append(command)
    readiness_checks = [
        ["agentledger", "--root", root, "doctor"],
        ["agentledger", "--root", root, "worker", "conformance", "--backend", backend],
    ]
    if backend == "postgres":
        readiness_checks.append(["agentledger", "--root", root, "migrate", "status", "--dialect", "postgres"])
    else:
        readiness_checks.append(["agentledger", "--root", root, "migrate", "status"])
    return WorkerDeploymentPlan(
        agent_entrypoint=agent_entrypoint,
        root=root,
        backend=backend,
        replicas=replicas,
        worker_id_prefix=worker_id_prefix,
        lease_seconds=lease_seconds,
        max_idle_polls=max_idle_polls,
        idle_sleep_seconds=idle_sleep_seconds,
        commands=commands,
        readiness_checks=readiness_checks,
        shutdown={
            "signal_handling": "SIGINT/SIGTERM request graceful stop",
            "lease_behavior": "uncommitted leased steps become recoverable after lease expiry",
            "safe_restart": "start replacement workers before or after stopping old workers; lease fencing prevents stale commits",
        },
        notes=[
            "run state-store conformance before increasing replicas",
            "lease_seconds should exceed normal step duration or agents should heartbeat",
            "workers are stateless executors; durable run state stays in the StateStore",
            "do not point conformance commands at real application data",
        ],
    )


class LocalWorker:
    """Local worker loop for development and conformance testing.

    The worker is deliberately tiny: scheduling semantics remain in the store and
    scheduler, while agent execution stays behind Runtime.run_once. This provides
    the shape future process pools or distributed worker adapters should follow.
    """

    def __init__(
        self,
        runtime: Runtime,
        agent: AgentFunc,
        *,
        worker_id: str = "worker-local",
        agent_role: str = "Agent",
        lease_seconds: int = 60,
        recover_expired: bool = True,
    ):
        self.runtime = runtime
        self.agent = agent
        self.worker_id = worker_id
        self.agent_role = agent_role
        self.lease_seconds = lease_seconds
        self.recover_expired = recover_expired
        self.scheduler = RuntimeScheduler(runtime.store)

    async def run_until_idle(self, *, run_id: str | None = None, max_iterations: int = 100) -> WorkerRunSummary:
        attempts = 0
        succeeded_attempts = 0
        recovered_leases = 0
        stopped_reason = "max_iterations"
        iterations = 0
        for iterations in range(1, max_iterations + 1):
            if self.recover_expired:
                recovered_leases += self.scheduler.recover_expired_leases().recovered_steps
            if run_id and self._run_status(run_id) in TERMINAL_RUN_STATUSES:
                stopped_reason = "terminal_status"
                break
            if run_id and not self._has_claimable_step(run_id):
                stopped_reason = "idle"
                break
            ok = await self.runtime.run_once(
                self.agent,
                run_id=run_id,
                worker_id=self.worker_id,
                agent_role=self.agent_role,
                lease_seconds=self.lease_seconds,
            )
            if not ok and (run_id is None or not self._has_recent_attempt(run_id, attempts)):
                stopped_reason = "idle"
                break
            attempts += 1
            if ok:
                succeeded_attempts += 1
        else:
            iterations = max_iterations
        final_status = self._run_status(run_id) if run_id else None
        if final_status in TERMINAL_RUN_STATUSES:
            stopped_reason = "terminal_status"
        return WorkerRunSummary(
            worker_id=self.worker_id,
            run_id=run_id,
            iterations=iterations,
            attempts=attempts,
            succeeded_attempts=succeeded_attempts,
            recovered_leases=recovered_leases,
            final_status=final_status,
            stopped_reason=stopped_reason,
        )

    def _run_status(self, run_id: str | None) -> str | None:
        if run_id is None:
            return None
        return self.runtime.store.run(run_id)["status"]

    def _has_claimable_step(self, run_id: str) -> bool:
        return any(row["status"] in CLAIMABLE_STEP_STATUSES for row in self.runtime.store.steps(run_id))

    def _has_recent_attempt(self, run_id: str, previous_attempts: int) -> bool:
        claimed = sum(1 for row in self.runtime.store.events(run_id) if row["type"] == "step_claimed")
        return claimed > previous_attempts


class WorkerService:
    """Long-running worker process shape for deployment adapters.

    The service intentionally keeps correctness in the StateStore: each loop
    recovers expired leases, attempts one claim/execute cycle, then backs off or
    exits according to idle/iteration limits.
    """

    def __init__(
        self,
        runtime: Runtime,
        agent: AgentFunc,
        *,
        worker_id: str = "worker-service",
        agent_role: str = "Agent",
        lease_seconds: int = 60,
        recover_expired: bool = True,
    ):
        self.runtime = runtime
        self.agent = agent
        self.worker_id = worker_id
        self.agent_role = agent_role
        self.lease_seconds = lease_seconds
        self.recover_expired = recover_expired
        self.stop_requested = False
        self.stop_reason = "stop_requested"

    def request_stop(self, reason: str = "stop_requested") -> None:
        self.stop_requested = True
        self.stop_reason = reason

    def install_signal_handlers(self) -> None:
        def handler(signum: int, _frame: Any) -> None:
            name = signal.Signals(signum).name
            self.request_stop(f"signal:{name}")

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    async def serve(
        self,
        *,
        run_id: str | None = None,
        max_loops: int | None = None,
        max_idle_polls: int | None = 1,
        idle_sleep_seconds: float = 0.25,
    ) -> WorkerServiceSummary:
        attempts = 0
        succeeded_attempts = 0
        recovered_leases = 0
        idle_polls = 0
        loops = 0
        stopped_reason = "max_loops"
        while max_loops is None or loops < max_loops:
            if self.stop_requested:
                stopped_reason = self.stop_reason
                break
            loops += 1
            worker = LocalWorker(
                self.runtime,
                self.agent,
                worker_id=self.worker_id,
                agent_role=self.agent_role,
                lease_seconds=self.lease_seconds,
                recover_expired=self.recover_expired,
            )
            summary = await worker.run_until_idle(run_id=run_id, max_iterations=1)
            attempts += summary.attempts
            succeeded_attempts += summary.succeeded_attempts
            recovered_leases += summary.recovered_leases
            if summary.final_status in TERMINAL_RUN_STATUSES:
                stopped_reason = "terminal_status"
                break
            if summary.attempts == 0:
                idle_polls += 1
                if max_idle_polls is not None and idle_polls >= max_idle_polls:
                    stopped_reason = "idle"
                    break
                await asyncio.sleep(idle_sleep_seconds)
                continue
            idle_polls = 0
        else:
            stopped_reason = "max_loops"

        if self.stop_requested and stopped_reason == "max_loops":
            stopped_reason = self.stop_reason
        final_status = self.runtime.store.run(run_id)["status"] if run_id else None
        return WorkerServiceSummary(
            worker_id=self.worker_id,
            run_id=run_id,
            loops=loops,
            attempts=attempts,
            succeeded_attempts=succeeded_attempts,
            recovered_leases=recovered_leases,
            idle_polls=idle_polls,
            stopped_reason=stopped_reason,
            final_status=final_status,
            stop_requested=self.stop_requested,
        )
