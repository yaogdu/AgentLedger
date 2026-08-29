from __future__ import annotations

from typing import Any

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
from .runtime import Runtime


DSH_OBSERVER_SCHEMA_VERSION = "agentledger.dsh.observer.v1"


class DSHEvidenceObserver:
    """Observe normalized DSH execution events without a DSH dependency."""

    name = "dsh-evidence-observer"

    def __init__(self, runtime: Runtime, *, app_name: str, run_id: str | None = None):
        self.bridge = ExecutionEvidenceBridge(runtime, app_name=app_name, source="dsh")
        self.run_id = run_id

    def observe(self, event: dict[str, Any]) -> Any:
        if not isinstance(event, dict):
            raise TypeError("DSH evidence event must be a dictionary")
        event_type = self._event_type(event)
        session_id = self._session_id(event)
        self._ensure_bound_session(event, session_id)
        if event_type in {"run_started", "session_started", "execution_started"}:
            return self.bridge.record_session_started(
                ExecutionSession(
                    session_id=session_id,
                    initial_state=self._dict(event, "initial_state"),
                    metadata=self._metadata(event),
                    run_id=self._runtime_run_id(event),
                )
            )
        if event_type in {"step_started", "turn_started"}:
            return self.bridge.record_turn_started(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    agent_role=str(event.get("agent_role") or "DSHAgent"),
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
        if event_type in {"tool_proposal", "tool_call_proposed"}:
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
                    turn_id=self._optional(event, "step_id", "turn_id"),
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
                    turn_id=self._optional(event, "step_id", "turn_id"),
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
        if event_type in {"side_effect_receipt", "task_receipt", "execution_receipt"}:
            return self.bridge.record_execution_event(
                session_id=session_id,
                turn_id=self._optional(event, "step_id", "turn_id"),
                event_name="task_receipt_recorded",
                causal_token=self._optional(event, "causal_token", "receipt_id"),
                payload={
                    "receipt_type": event_type,
                    "receipt_id": self._optional(event, "receipt_id"),
                    "task_id": self._optional(event, "task_id"),
                    "status": self._optional(event, "status", "state"),
                    "external_id": self._optional(event, "external_id"),
                    "artifact_refs": event.get("artifact_refs", event.get("artifacts")),
                    "metadata": self._metadata(event),
                },
            )
        if event_type in {"step_completed", "turn_completed"}:
            return self.bridge.record_turn_completed(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    state_patch=self._dict(event, "state_patch"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"step_failed", "turn_failed"}:
            return self.bridge.record_failure(
                ExecutionFailure(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    error_type=str(event.get("error_type") or "DSHStepFailure"),
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
        raise ValueError(f"unsupported DSH evidence event type: {event_type}")

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
            raise ValueError("DSH evidence event requires type")
        return value.strip().lower().replace(".", "_")

    @classmethod
    def _session_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "session_id", "execution_id", "run_id")

    @classmethod
    def _turn_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "step_id", "turn_id")

    @staticmethod
    def _metadata(event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("DSH evidence metadata must be a dictionary")
        result = dict(metadata)
        for key in (
            "execution_id",
            "run_id",
            "session_id",
            "step_id",
            "turn_id",
            "attempt",
            "worker_id",
            "parent_id",
            "trace_id",
            "sandbox_id",
            "task_id",
            "receipt_id",
        ):
            if key in event and event[key] is not None:
                result[f"external_{key}"] = event[key]
        result["observer_schema_version"] = DSH_OBSERVER_SCHEMA_VERSION
        return result

    @staticmethod
    def _required(event: dict[str, Any], *keys: str) -> str:
        value = DSHEvidenceObserver._optional(event, *keys)
        if not value:
            raise ValueError(f"DSH evidence event requires one of: {', '.join(keys)}")
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
                raise TypeError(f"DSH evidence field {key} must be a dictionary")
            return dict(value)
        return {}
