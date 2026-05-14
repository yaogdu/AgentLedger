from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .blobstore import LocalBlobStore
from .context import AgentContext
from .policy import PolicyEngine
from .store import SQLiteStore
from .tools import ToolGateway, ToolRegistry

AgentFunc = Callable[[AgentContext, dict[str, Any]], Any]


class SimulatedCrash(RuntimeError):
    """Raised by examples/tests to simulate a worker crash after a side effect."""


class Runtime:
    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore, registry: ToolRegistry | None = None, policy: PolicyEngine | None = None):
        self.store = store
        self.blobs = blobs
        self.registry = registry or ToolRegistry()
        self.policy = policy or PolicyEngine()
        self.gateway = ToolGateway(store=store, blobs=blobs, registry=self.registry, policy=self.policy)

    @classmethod
    def local(cls, root: str | Path = ".agentledger") -> "Runtime":
        root = Path(root)
        store = SQLiteStore(root / "state.db")
        store.init()
        return cls(store=store, blobs=LocalBlobStore(root / "blobs"))

    def create_run(self, initial_state: dict[str, Any] | None = None, session_id: str | None = None) -> tuple[str, str]:
        return self.store.create_run(session_id=session_id, initial_state=initial_state)

    async def run_once(self, agent: AgentFunc, *, run_id: str, worker_id: str = "worker-local", agent_role: str = "Agent") -> bool:
        claim = self.store.claim_step(worker_id=worker_id, run_id=run_id)
        if claim is None:
            return False
        state, state_version, session_id = self.store.load_state(claim.run_id)
        ctx = AgentContext(
            run_id=claim.run_id,
            session_id=session_id,
            step_id=claim.step_id,
            agent_role=agent_role,
            lease_token=claim.lease_token,
            attempt=claim.attempt,
            state_version=state_version,
            store=self.store,
            gateway=self.gateway,
            blobs=self.blobs,
        )
        self.store.append_event(
            run_id=claim.run_id,
            session_id=session_id,
            step_id=claim.step_id,
            event_type="agent_started",
            payload={"agent_role": agent_role, "attempt": claim.attempt},
            agent_role=agent_role,
            state_version=state_version,
        )
        try:
            result = agent(ctx, state)
            if hasattr(result, "__await__"):
                await result
            self.store.commit_state_patch(
                run_id=claim.run_id,
                step_id=claim.step_id,
                lease_token=claim.lease_token,
                base_version=state_version,
                patch=ctx.pending_patch,
                checkpoint_id=f"ckpt:{claim.run_id}:{claim.step_id}:{claim.attempt}",
            )
            return True
        except SimulatedCrash as exc:
            self.store.mark_retry(run_id=claim.run_id, step_id=claim.step_id, error=f"SimulatedCrash: {exc}")
            return False
        except Exception as exc:
            self.store.mark_failed(run_id=claim.run_id, step_id=claim.step_id, error=repr(exc), error_type=type(exc).__name__)
            raise
