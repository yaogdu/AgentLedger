from __future__ import annotations

import inspect
from typing import Any, Callable

from .adapters import AgentCallable, FrameworkAdapter
from .adapters_omp import (
    ExecutionArtifact,
    ExecutionEvidenceBridge,
    ExecutionFailure,
    ExecutionModelCall,
    ExecutionSession,
    ExecutionStateChange,
    ExecutionToolExecution,
    ExecutionToolProposal,
    ExecutionTurn,
)
from .context import AgentContext

InputMapper = Callable[[AgentContext, dict[str, Any]], Any]


def default_input_mapper(_ctx: AgentContext, state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


class MethodFrameworkAdapter(FrameworkAdapter):
    """Dependency-free facade for framework objects with conventional methods."""

    name = "method-framework"

    def __init__(
        self,
        target: Any,
        *,
        role: str = "FrameworkAgent",
        method_candidates: tuple[str, ...],
        input_mapper: InputMapper | None = None,
        output_key: str | None = "output",
    ):
        self.target = target
        self.role = role
        self.method_candidates = method_candidates
        self.input_mapper = input_mapper or default_input_mapper
        self.output_key = output_key

    def map_run_spec(self, framework_run: Any = None) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "role": self.role,
            "target": type(self.target).__name__,
            "methods": list(self.method_candidates),
        }

    def as_agent(self) -> AgentCallable:
        async def wrapped(ctx: AgentContext, state: dict[str, Any]) -> Any:
            payload = self.input_mapper(ctx, state)
            result = await self._invoke(payload)
            if self.output_key is not None:
                ctx.write_state_patch(self.output_key, result)
            return result

        return wrapped

    async def _invoke(self, payload: Any) -> Any:
        for name in self.method_candidates:
            method = getattr(self.target, name, None)
            if method is None:
                continue
            result = method(payload)
            if inspect.isawaitable(result):
                return await result
            return result
        if callable(self.target):
            result = self.target(payload)
            if inspect.isawaitable(result):
                return await result
            return result
        raise AttributeError(f"{type(self.target).__name__} does not expose any of {self.method_candidates!r}")


class LangChainRunnableAdapter(MethodFrameworkAdapter):
    """Wrap a LangChain-style Runnable without importing LangChain."""

    name = "langchain-runnable"

    def __init__(self, runnable: Any, *, role: str = "LangChainAgent", input_mapper: InputMapper | None = None, output_key: str | None = "langchain_output"):
        super().__init__(runnable, role=role, method_candidates=("ainvoke", "invoke"), input_mapper=input_mapper, output_key=output_key)


class CrewAIAdapter(MethodFrameworkAdapter):
    """Wrap a CrewAI-style Crew/Task object without importing CrewAI."""

    name = "crewai"

    def __init__(self, crew_or_task: Any, *, role: str = "CrewAIAgent", input_mapper: InputMapper | None = None, output_key: str | None = "crewai_output"):
        super().__init__(crew_or_task, role=role, method_candidates=("akickoff", "kickoff", "arun", "run"), input_mapper=input_mapper, output_key=output_key)


class AutoGenAdapter(MethodFrameworkAdapter):
    """Wrap an AutoGen-style agent object without importing AutoGen."""

    name = "autogen"

    def __init__(self, agent: Any, *, role: str = "AutoGenAgent", input_mapper: InputMapper | None = None, output_key: str | None = "autogen_output"):
        super().__init__(
            agent,
            role=role,
            method_candidates=("a_generate_reply", "generate_reply", "a_run", "run", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class OpenAIAgentsSDKAdapter(MethodFrameworkAdapter):
    """Wrap an OpenAI Agents SDK-style runner without importing the SDK."""

    name = "openai-agents-sdk"

    def __init__(self, agent_or_runner: Any, *, role: str = "OpenAIAgent", input_mapper: InputMapper | None = None, output_key: str | None = "openai_agent_output"):
        super().__init__(
            agent_or_runner,
            role=role,
            method_candidates=("arun", "run", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class LlamaIndexAdapter(MethodFrameworkAdapter):
    """Wrap a LlamaIndex-style query/chat/retriever object without importing LlamaIndex."""

    name = "llamaindex"

    def __init__(self, query_engine_or_agent: Any, *, role: str = "LlamaIndexAgent", input_mapper: InputMapper | None = None, output_key: str | None = "llamaindex_output"):
        super().__init__(
            query_engine_or_agent,
            role=role,
            method_candidates=("aquery", "query", "achat", "chat", "aretrieve", "retrieve", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class SemanticKernelAdapter(MethodFrameworkAdapter):
    """Wrap a Semantic Kernel-style kernel/function object without importing it."""

    name = "semantic-kernel"

    def __init__(self, kernel_or_function: Any, *, role: str = "SemanticKernelAgent", input_mapper: InputMapper | None = None, output_key: str | None = "semantic_kernel_output"):
        super().__init__(
            kernel_or_function,
            role=role,
            method_candidates=("ainvoke", "invoke", "invoke_prompt", "run_async", "run"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


FRAMEWORK_OBSERVER_SCHEMA_VERSION = "agentledger.framework.observer.v1"


class FrameworkEvidenceObserver:
    """Observe normalized framework node, checkpoint, and tool events."""

    name = "framework-evidence-observer"

    def __init__(self, runtime: Any, *, app_name: str, source: str = "framework", run_id: str | None = None):
        if not isinstance(source, str) or not source.strip():
            raise ValueError("framework observer source must not be empty")
        self.bridge = ExecutionEvidenceBridge(runtime, app_name=app_name, source=source.strip())
        self.run_id = run_id

    def observe(self, event: dict[str, Any]) -> Any:
        if not isinstance(event, dict):
            raise TypeError("framework evidence event must be a dictionary")
        event_type = self._event_type(event)
        session_id = self._session_id(event)
        self._ensure_bound_session(event, session_id)
        if event_type in {"session_started", "run_started", "graph_started", "agent_started"}:
            return self.bridge.record_session_started(
                ExecutionSession(
                    session_id=session_id,
                    initial_state=self._dict(event, "initial_state"),
                    metadata=self._metadata(event),
                    run_id=self._runtime_run_id(event),
                )
            )
        if event_type in {"node_started", "step_started", "turn_started"}:
            return self.bridge.record_turn_started(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    agent_role=str(event.get("agent_role") or event.get("node_name") or "FrameworkAgent"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"model_call", "model_call_completed"}:
            return self.bridge.record_model_call(
                ExecutionModelCall(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    provider=self._required(event, "provider"),
                    model=self._required(event, "model"),
                    request=self._dict(event, "request"),
                    response=self._dict(event, "response"),
                    usage=self._dict(event, "usage"),
                    total_usd=float(event.get("total_usd", 0.0) or 0.0),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"tool_proposal", "tool_call_proposed", "tool_call_requested"}:
            return self.bridge.record_tool_proposal(
                ExecutionToolProposal(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    tool_name=self._required(event, "tool_name", "tool"),
                    arguments=self._dict(event, "arguments", "args"),
                    provider=self._optional(event, "provider"),
                    model=self._optional(event, "model"),
                    model_call_ref=self._optional(event, "model_call_ref"),
                    confidence=event.get("confidence"),
                    reason=self._optional(event, "reason"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"tool_execution", "tool_call_completed", "tool_call_failed"}:
            return self.bridge.record_tool_execution(
                ExecutionToolExecution(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    tool_name=self._required(event, "tool_name", "tool"),
                    arguments=self._dict(event, "arguments", "args"),
                    result=event.get("result"),
                    tool_call_id=self._optional(event, "tool_call_id"),
                    tool_version=str(event.get("tool_version") or "external"),
                    idempotency_key=self._optional(event, "idempotency_key"),
                    ledger_status=self._optional(event, "ledger_status", "status"),
                    error_type=self._optional(event, "error_type"),
                    error_message=self._optional(event, "error_message", "error"),
                    external_id=self._optional(event, "external_id"),
                    causal_token=self._optional(event, "causal_token"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"state_change", "state_change_recorded"}:
            return self.bridge.record_state_change(
                ExecutionStateChange(
                    session_id=session_id,
                    turn_id=self._optional(event, "node_id", "step_id", "turn_id"),
                    reason=self._required(event, "reason"),
                    patch=self._dict(event, "patch"),
                    label=str(event.get("label") or "state"),
                    commit_status=str(event.get("commit_status") or "committed"),
                    before_snapshot=event.get("before_snapshot"),
                    after_snapshot=event.get("after_snapshot"),
                    diff=event.get("diff"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"artifact_recorded", "artifact_created", "media_artifact_recorded"}:
            return self.bridge.record_artifact(
                ExecutionArtifact(
                    session_id=session_id,
                    turn_id=self._optional(event, "node_id", "step_id", "turn_id"),
                    name=self._required(event, "name", "artifact_name"),
                    kind=str(event.get("kind") or "artifact"),
                    uri=self._optional(event, "uri"),
                    content_ref=self._optional(event, "content_ref"),
                    external_id=self._optional(event, "external_id", "artifact_id"),
                    metadata=self._metadata(event),
                    lineage=self._dict(event, "lineage"),
                    derived_outputs=self._dict(event, "derived_outputs"),
                )
            )
        if event_type in {
            "checkpoint_saved",
            "checkpoint_recorded",
            "handoff_requested",
            "handoff_completed",
        }:
            return self.bridge.record_execution_event(
                session_id=session_id,
                turn_id=self._optional(event, "node_id", "step_id", "turn_id"),
                event_name="task_receipt_recorded",
                causal_token=self._optional(event, "causal_token", "checkpoint_id", "handoff_id"),
                payload={
                    "receipt_type": event_type,
                    "checkpoint_id": self._optional(event, "checkpoint_id"),
                    "checkpoint_ns": self._optional(event, "checkpoint_ns"),
                    "parent_checkpoint_id": self._optional(event, "parent_checkpoint_id"),
                    "thread_id": self._optional(event, "thread_id"),
                    "handoff_id": self._optional(event, "handoff_id"),
                    "from_agent": self._optional(event, "from_agent"),
                    "to_agent": self._optional(event, "to_agent"),
                    "artifact_refs": event.get("artifact_refs", event.get("artifacts")),
                    "status": self._optional(event, "status", "state"),
                    "metadata": self._metadata(event),
                },
            )
        if event_type in {"node_completed", "step_completed", "turn_completed"}:
            return self.bridge.record_turn_completed(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    state_patch=self._dict(event, "state_patch"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"run_completed", "graph_completed", "agent_completed"}:
            return self.bridge.record_execution_event(
                session_id=session_id,
                event_name="task_receipt_recorded",
                causal_token=self._optional(event, "causal_token", "run_id", "thread_id"),
                payload={
                    "receipt_type": event_type,
                    "status": self._optional(event, "status", "state") or "completed",
                    "metadata": self._metadata(event),
                },
            )
        if event_type in {"node_failed", "step_failed", "turn_failed"}:
            return self.bridge.record_failure(
                ExecutionFailure(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    error_type=str(event.get("error_type") or "FrameworkStepFailure"),
                    message=self._required(event, "message", "error"),
                    retryable=event.get("retryable"),
                    status=str(event.get("status") or ("retry_scheduled" if event.get("retryable") else "failed")),
                    terminal=bool(event.get("terminal", True)),
                    category=str(event.get("category") or "runtime"),
                    provider=self._optional(event, "provider"),
                    model=self._optional(event, "model"),
                    request=self._dict(event, "request"),
                    usage=self._dict(event, "usage"),
                    total_usd=float(event.get("total_usd", 0.0) or 0.0),
                    metadata=self._metadata(event),
                    approval_id=self._optional(event, "approval_id"),
                )
            )
        raise ValueError(f"unsupported framework evidence event type: {event_type}")

    def _ensure_bound_session(self, event: dict[str, Any], session_id: str) -> None:
        run_id = self._runtime_run_id(event)
        if run_id is None:
            return
        self.bridge.record_session_started(
            ExecutionSession(
                session_id=session_id,
                initial_state=self._dict(event, "initial_state"),
                metadata=self._metadata(event),
                run_id=run_id,
            )
        )

    def _runtime_run_id(self, event: dict[str, Any]) -> str | None:
        return self._optional(event, "runtime_run_id", "agentledger_run_id") or self.run_id

    @staticmethod
    def _event_type(event: dict[str, Any]) -> str:
        value = event.get("type") or event.get("event_type")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("framework evidence event requires type")
        return value.strip().lower().replace(".", "_")

    @classmethod
    def _session_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "session_id", "thread_id", "run_id")

    @classmethod
    def _turn_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "turn_id", "node_id", "step_id")

    @staticmethod
    def _metadata(event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("framework evidence metadata must be a dictionary")
        result = dict(metadata)
        for key in (
            "session_id",
            "thread_id",
            "run_id",
            "turn_id",
            "node_id",
            "step_id",
            "node_name",
            "graph_id",
            "agent_id",
            "trace_id",
            "span_id",
            "checkpoint_id",
            "checkpoint_ns",
            "handoff_id",
            "from_agent",
            "to_agent",
            "attempt",
        ):
            if key in event and event[key] is not None:
                result[f"external_{key}"] = event[key]
        result["observer_schema_version"] = FRAMEWORK_OBSERVER_SCHEMA_VERSION
        return result

    @staticmethod
    def _required(event: dict[str, Any], *keys: str) -> str:
        value = FrameworkEvidenceObserver._optional(event, *keys)
        if not value:
            raise ValueError(f"framework evidence event requires one of: {', '.join(keys)}")
        return value

    @staticmethod
    def _optional(event: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = event.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    @staticmethod
    def _dict(event: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = event.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(f"framework evidence field {key} must be a dictionary")
            return dict(value)
        return {}
