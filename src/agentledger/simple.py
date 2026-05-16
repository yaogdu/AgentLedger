from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .context import AgentContext
from .evidence import EvidenceExporter
from .runtime import AgentFunc, Runtime

UserAgentFunc = Callable[..., Any]


@dataclass(frozen=True)
class RunResult:
    run_id: str
    session_id: str
    ok: bool
    output: Any
    state: dict[str, Any]
    runtime: Runtime
    evidence_path: Path | None = None

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class SimpleAgent:
    func: UserAgentFunc
    role: str = "Agent"
    name: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or getattr(self.func, "__name__", "agent")

    def as_agent(self) -> AgentFunc:
        async def _agent(ctx: AgentContext, state: dict[str, Any]) -> None:
            result = self._invoke(ctx, state)
            if inspect.isawaitable(result):
                result = await result
            if result is not None:
                ctx.store.append_event(
                    run_id=ctx.run_id,
                    session_id=ctx.session_id,
                    step_id=ctx.step_id,
                    event_type="agent_result_returned",
                    payload={"agent": self.display_name},
                    agent_role=ctx.agent_role,
                    state_version=ctx.state_version,
                )
                ctx.write_state_patch("output", result)
        return _agent

    def _invoke(self, ctx: AgentContext, state: dict[str, Any]) -> Any:
        signature = inspect.signature(self.func)
        positional = [
            param
            for param in signature.parameters.values()
            if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(param.kind == param.VAR_POSITIONAL for param in signature.parameters.values())
        if has_varargs or len(positional) >= 2:
            return self.func(ctx, state)
        if len(positional) == 1:
            return self.func(ctx)
        return self.func()


def agent(func: UserAgentFunc | None = None, *, role: str = "Agent", name: str | None = None):
    """Decorate a plain Python function as an AgentLedger simple agent.

    Supports zero-arg, ctx-only, and ctx/state function signatures.
    """
    def decorate(inner: UserAgentFunc) -> SimpleAgent:
        return SimpleAgent(func=inner, role=role, name=name)

    if func is None:
        return decorate
    return decorate(func)


def _coerce_agent(agent_like: Any, *, agent_role: str | None = None) -> tuple[AgentFunc, str]:
    if isinstance(agent_like, SimpleAgent):
        return agent_like.as_agent(), agent_role or agent_like.role
    if hasattr(agent_like, "as_agent") and callable(agent_like.as_agent):
        role = agent_role or getattr(agent_like, "role", "Agent")
        return agent_like.as_agent(), role
    if callable(agent_like):
        simple = SimpleAgent(agent_like, role=agent_role or "Agent")
        return simple.as_agent(), simple.role
    raise TypeError("agentledger.run() expects a callable, SimpleAgent, or object with as_agent()")


def run(agent_like: Any, **kwargs: Any) -> RunResult:
    """Run one agent step synchronously with durable defaults.

    Use arun() when calling from an existing asyncio event loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(arun(agent_like, **kwargs))
    raise RuntimeError("agentledger.run() cannot be called inside a running event loop; use await agentledger.arun(...)")


async def arun(
    agent_like: Any,
    *,
    runtime: Runtime | None = None,
    root: str | Path = ".agentledger",
    initial_state: dict[str, Any] | None = None,
    session_id: str | None = None,
    agent_role: str | None = None,
    worker_id: str = "worker-simple",
    lease_seconds: int = 60,
    retry_policy: dict[str, Any] | None = None,
    evidence_dir: str | Path | None = None,
) -> RunResult:
    rt = runtime or Runtime.local(root)
    runtime_agent, role = _coerce_agent(agent_like, agent_role=agent_role)
    run_id, _ = rt.create_run(initial_state=initial_state, session_id=session_id, retry_policy=retry_policy)
    ok = await rt.run_once(runtime_agent, run_id=run_id, worker_id=worker_id, agent_role=role, lease_seconds=lease_seconds)
    state = rt.store.final_state(run_id)
    evidence_path: Path | None = None
    if evidence_dir is not None:
        evidence_path = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(Path(evidence_dir) / run_id)
    return RunResult(run_id=run_id, session_id=rt.store.run(run_id)["session_id"], ok=ok, output=state.get("output"), state=state, runtime=rt, evidence_path=evidence_path)
