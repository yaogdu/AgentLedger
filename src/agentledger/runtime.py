from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .approval import ApprovalRequired
from .blobstore import LocalBlobStore
from .context import AgentContext
from .cost import BudgetController
from .failure import RetryableAgentError, classify_exception
from .policy import PolicyEngine
from .store import SQLiteStore
from .sandbox import SandboxConfig, SandboxExecutor, create_sandbox_executor
from .tools import ToolFunc, ToolGateway, ToolRegistry, ToolSpec, tool as tool_spec

AgentFunc = Callable[[AgentContext, dict[str, Any]], Any]


class SimulatedCrash(RuntimeError):
    """Raised by examples/tests to simulate a worker crash after a side effect."""


class Runtime:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        blobs: LocalBlobStore,
        registry: ToolRegistry | None = None,
        policy: PolicyEngine | None = None,
        budget: BudgetController | None = None,
        sandbox: SandboxExecutor | None = None,
        sandbox_config: SandboxConfig | dict[str, Any] | str | Path | None = None,
    ):
        self.store = store
        self.blobs = blobs
        self.registry = registry or ToolRegistry()
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        if sandbox is None and sandbox_config is not None:
            sandbox = create_sandbox_executor(sandbox_config)
        self.sandbox = sandbox or create_sandbox_executor()
        self.gateway = ToolGateway(store=store, blobs=blobs, registry=self.registry, policy=self.policy, budget=self.budget, sandbox=self.sandbox)

    @classmethod
    def local(cls, root: str | Path = ".agentledger", *, budget: BudgetController | None = None, sandbox: SandboxExecutor | None = None, sandbox_config: SandboxConfig | dict[str, Any] | str | Path | None = None) -> "Runtime":
        root = Path(root)
        store = SQLiteStore(root / "state.db")
        store.init()
        return cls(store=store, blobs=LocalBlobStore(root / "blobs"), budget=budget, sandbox=sandbox, sandbox_config=sandbox_config)

    def run(self, agent: Any, **kwargs: Any) -> Any:
        from .simple import run
        return run(agent, runtime=self, **kwargs)

    async def arun(self, agent: Any, **kwargs: Any) -> Any:
        from .simple import arun
        return await arun(agent, runtime=self, **kwargs)

    def create_run(self, initial_state: dict[str, Any] | None = None, session_id: str | None = None, retry_policy: dict[str, Any] | None = None) -> tuple[str, str]:
        return self.store.create_run(session_id=session_id, initial_state=initial_state, retry_policy=retry_policy)

    def close(self) -> None:
        close = getattr(self.store, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "Runtime":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def register_tool(self, spec: ToolSpec) -> ToolSpec:
        """Register a ToolSpec on this runtime and return it for decorator-style use."""
        return self.registry.register(spec)

    def tool(
        self,
        *,
        name: str,
        description: str = "",
        side_effect: str = "none",
        risk_level: str = "low",
        idempotency: bool = False,
        approval_required: bool = False,
        sandbox_required: bool = False,
        sandbox_executor: str | None = None,
        sandbox_policy: dict[str, Any] | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        version: str = "v1",
    ):
        """Decorate and register a runtime-managed tool with this runtime."""
        def decorate(func: ToolFunc) -> ToolSpec:
            spec = tool_spec(
                name=name,
                description=description,
                side_effect=side_effect,
                risk_level=risk_level,
                idempotency=idempotency,
                approval_required=approval_required,
                sandbox_required=sandbox_required,
                sandbox_executor=sandbox_executor,
                sandbox_policy=sandbox_policy,
                input_schema=input_schema,
                output_schema=output_schema,
                version=version,
            )(func)
            return self.register_tool(spec)

        return decorate

    async def run_once(
        self,
        agent: AgentFunc,
        *,
        run_id: str,
        worker_id: str = "worker-local",
        agent_role: str = "Agent",
        execution_mode: str = "normal",
        source_run_id: str | None = None,
        lease_seconds: int = 60,
    ) -> bool:
        claim = self.store.claim_step(worker_id=worker_id, run_id=run_id, lease_seconds=lease_seconds)
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
            budget=self.budget,
            execution_mode=execution_mode,
            source_run_id=source_run_id,
        )
        self.store.append_event(
            run_id=claim.run_id,
            session_id=session_id,
            step_id=claim.step_id,
            event_type="agent_started",
            payload={"agent_role": agent_role, "attempt": claim.attempt, "execution_mode": execution_mode, "source_run_id": source_run_id},
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
        except ApprovalRequired as exc:
            self.store.mark_waiting_human(run_id=claim.run_id, step_id=claim.step_id, reason=str(exc), approval_id=exc.approval_id)
            return False
        except SimulatedCrash as exc:
            self.store.mark_retry(run_id=claim.run_id, step_id=claim.step_id, error=f"SimulatedCrash: {exc}", error_type="SimulatedCrash")
            return False
        except RetryableAgentError as exc:
            self.store.mark_retry(run_id=claim.run_id, step_id=claim.step_id, error=str(exc), error_type=type(exc).__name__)
            return False
        except Exception as exc:
            failure = classify_exception(exc)
            if failure.retryable:
                self.store.mark_retry(run_id=claim.run_id, step_id=claim.step_id, error=failure.message, error_type=failure.error_type)
                return False
            self.store.mark_failed(run_id=claim.run_id, step_id=claim.step_id, error=repr(exc), error_type=type(exc).__name__)
            raise
