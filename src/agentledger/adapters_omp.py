from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .context import AgentContext
from .ids import new_id
from .runtime import Runtime


OMP_ADAPTER_SCHEMA_VERSION = "agentledger.omp.adapter.v1"

_SUCCESS_LEDGER_STATUSES = {"SUCCEEDED", "COMPENSATED"}
_FAILURE_LEDGER_STATUSES = {"FAILED_NO_EFFECT", "PENDING_VERIFICATION"}
_ALL_LEDGER_STATUSES = _SUCCESS_LEDGER_STATUSES | _FAILURE_LEDGER_STATUSES | {"RESERVED", "RUNNING"}


@dataclass(frozen=True)
class OmpSession:
    session_id: str
    initial_state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None


@dataclass(frozen=True)
class OmpTurn:
    session_id: str
    turn_id: str
    agent_role: str = "OMPAgent"
    state_patch: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OmpModelCall:
    session_id: str
    turn_id: str
    provider: str
    model: str
    request: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    total_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OmpToolProposal:
    session_id: str
    turn_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    model_call_ref: str | None = None
    confidence: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OmpToolExecution:
    session_id: str
    turn_id: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    tool_call_id: str | None = None
    tool_version: str = "external"
    idempotency_key: str | None = None
    ledger_status: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    external_id: str | None = None
    causal_token: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OmpFailure:
    session_id: str
    turn_id: str
    error_type: str
    message: str
    retryable: bool | None = None
    status: str = "failed"
    terminal: bool = True
    category: str = "runtime"
    provider: str | None = None
    model: str | None = None
    request: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    total_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    approval_id: str | None = None


@dataclass(frozen=True)
class OmpStateChange:
    session_id: str
    reason: str
    patch: dict[str, Any] = field(default_factory=dict)
    turn_id: str | None = None
    label: str = "state"
    commit_status: str = "committed"
    before_snapshot: Any = None
    after_snapshot: Any = None
    diff: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _BridgeSession:
    run_id: str
    session_id: str
    initial_step_id: str | None = None


@dataclass
class _ActiveTurn:
    run_id: str
    session_id: str
    step_id: str
    lease_token: str
    attempt: int
    state_version: int
    agent_role: str


class OmpLedgerBridge:
    """Translate normalized OMP runtime records into AgentLedger evidence."""

    name = "omp-ledger-bridge"

    def __init__(self, runtime: Runtime, *, app_name: str, worker_id: str | None = None, lease_seconds: int = 60):
        self.runtime = runtime
        self.app_name = app_name
        self.worker_id = worker_id or f"omp:{app_name}"
        self.lease_seconds = lease_seconds
        self._sessions: dict[str, _BridgeSession] = {}
        self._active_turns: dict[str, _ActiveTurn] = {}

    def record_session_started(self, session: OmpSession) -> str:
        if session.session_id in self._sessions:
            return self._sessions[session.session_id].run_id
        bridge_session = self._ensure_session(session)
        run = self.runtime.store.run(bridge_session.run_id)
        self.runtime.store.append_event(
            run_id=bridge_session.run_id,
            session_id=bridge_session.session_id,
            step_id=None,
            event_type="omp_session_started",
            payload=_compact(
                {
                    "schema_version": OMP_ADAPTER_SCHEMA_VERSION,
                    "adapter": self.name,
                    "app_name": self.app_name,
                    "external_session_id": session.session_id,
                    "metadata": dict(session.metadata),
                }
            ),
            state_version=int(run["state_version"]),
        )
        return bridge_session.run_id

    def record_turn_started(self, turn: OmpTurn) -> str:
        key = self._turn_key(turn.session_id, turn.turn_id)
        active = self._active_turns.get(key)
        if active is not None:
            return active.step_id
        session = self._ensure_session(OmpSession(session_id=turn.session_id))
        step_id = session.initial_step_id
        if step_id is None:
            step_id = self._next_runnable_step_id(session.run_id)
            if step_id is None:
                step_id = self.runtime.store.create_external_step(run_id=session.run_id)
        else:
            session.initial_step_id = None
        claim = self.runtime.store.claim_step(worker_id=self.worker_id, run_id=session.run_id, lease_seconds=self.lease_seconds)
        if claim is None:
            raise RuntimeError(f"no runnable step available for OMP turn {turn.turn_id}")
        active = _ActiveTurn(
            run_id=claim.run_id,
            session_id=claim.session_id,
            step_id=claim.step_id,
            lease_token=claim.lease_token,
            attempt=claim.attempt,
            state_version=claim.state_version,
            agent_role=turn.agent_role,
        )
        self._active_turns[key] = active
        self.runtime.store.append_event(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            event_type="omp_turn_started",
            payload=_compact(
                {
                    "schema_version": OMP_ADAPTER_SCHEMA_VERSION,
                    "adapter": self.name,
                    "app_name": self.app_name,
                    "external_session_id": turn.session_id,
                    "external_turn_id": turn.turn_id,
                    "metadata": dict(turn.metadata),
                }
            ),
            agent_role=turn.agent_role,
            state_version=active.state_version,
        )
        return active.step_id

    def record_turn_completed(self, turn: OmpTurn) -> int:
        active = self._require_turn(turn.session_id, turn.turn_id)
        new_version = self.runtime.store.commit_state_patch(
            run_id=active.run_id,
            step_id=active.step_id,
            lease_token=active.lease_token,
            base_version=active.state_version,
            patch=dict(turn.state_patch),
            checkpoint_id=f"omp:{turn.turn_id}:{active.attempt}",
        )
        self.runtime.store.append_event(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            event_type="omp_turn_completed",
            payload=_compact(
                {
                    "schema_version": OMP_ADAPTER_SCHEMA_VERSION,
                    "adapter": self.name,
                    "app_name": self.app_name,
                    "external_session_id": turn.session_id,
                    "external_turn_id": turn.turn_id,
                    "metadata": dict(turn.metadata),
                }
            ),
            agent_role=active.agent_role,
            state_version=new_version,
        )
        self._active_turns.pop(self._turn_key(turn.session_id, turn.turn_id), None)
        return new_version

    def record_model_call(self, record: OmpModelCall) -> dict[str, str | None]:
        return self._context_for(record.session_id, record.turn_id).record_model_call(
            provider=record.provider,
            model=record.model,
            request=dict(record.request),
            response=dict(record.response),
            usage=dict(record.usage),
            total_usd=float(record.total_usd),
            metadata=dict(record.metadata),
        )

    def record_tool_proposal(self, proposal: OmpToolProposal) -> str:
        return self._context_for(proposal.session_id, proposal.turn_id).record_tool_call_proposal(
            tool_name=proposal.tool_name,
            arguments=dict(proposal.arguments),
            provider=proposal.provider,
            model=proposal.model,
            model_call_ref=proposal.model_call_ref,
            confidence=proposal.confidence,
            reason=proposal.reason,
            metadata=dict(proposal.metadata),
        )

    def record_tool_execution(self, execution: OmpToolExecution) -> dict[str, Any]:
        active = self._require_turn(execution.session_id, execution.turn_id)
        tool_call_id = execution.tool_call_id or new_id("toolcall")
        request = _compact(
            {
                "schema_version": OMP_ADAPTER_SCHEMA_VERSION,
                "tool": execution.tool_name,
                "args": dict(execution.arguments),
                "tool_call_id": tool_call_id,
                "metadata": dict(execution.metadata),
            }
        )
        request_hash, request_ref = self.runtime.blobs.put_json(request)
        idempotency_key = execution.idempotency_key or f"omp:{execution.session_id}:{execution.turn_id}:{execution.tool_name}:{tool_call_id}"
        causal_token = execution.causal_token or f"omp:{execution.session_id}:{execution.turn_id}:{tool_call_id}"
        self.runtime.store.append_event(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            event_type="tool_call_requested",
            payload=request,
            agent_role=active.agent_role,
            state_version=active.state_version,
            causal_token=causal_token,
            payload_hash=request_hash,
            payload_ref=request_ref,
        )
        existing = self.runtime.store.reserve_ledger(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            tool_name=execution.tool_name,
            tool_version=execution.tool_version,
            tool_call_id=tool_call_id,
            idempotency_key=idempotency_key,
            causal_token=causal_token,
            request_hash=request_hash,
            request_ref=request_ref,
        )
        if existing is not None and existing["status"] == "SUCCEEDED":
            self.runtime.store.append_event(
                run_id=active.run_id,
                session_id=active.session_id,
                step_id=active.step_id,
                event_type="tool_call_completed",
                payload={"tool": execution.tool_name, "replayed_from_ledger": True, "idempotency_key": idempotency_key, "tool_call_id": tool_call_id},
                agent_role=active.agent_role,
                state_version=active.state_version,
                causal_token=causal_token,
                payload_hash=existing["response_hash"],
                payload_ref=existing["response_ref"],
            )
            return {"ledger_status": "SUCCEEDED", "replayed_from_ledger": True, "idempotency_key": idempotency_key, "tool_call_id": tool_call_id}
        if existing is not None and existing["status"] == "PENDING_VERIFICATION":
            raise RuntimeError("tool side effect pending verification")
        if existing is not None and existing["status"] in {"RESERVED", "RUNNING"}:
            raise RuntimeError("tool side effect already in progress")
        ledger_status = _ledger_status(execution.ledger_status, execution.error_message or execution.error_type)
        response_hash = response_ref = None
        if execution.result is not None:
            response_hash, response_ref = self.runtime.blobs.put_json(execution.result)
        self.runtime.store.update_ledger(
            idempotency_key=idempotency_key,
            status=ledger_status,
            external_id=execution.external_id or _external_id_from_result(execution.result),
            response_hash=response_hash,
            response_ref=response_ref,
            error_type=execution.error_type,
        )
        event_type = "tool_call_completed" if ledger_status in _SUCCESS_LEDGER_STATUSES else "tool_call_failed"
        payload = _compact(
            {
                "tool": execution.tool_name,
                "tool_call_id": tool_call_id,
                "idempotency_key": idempotency_key,
                "ledger_status": ledger_status,
                "error": execution.error_message,
                "error_type": execution.error_type,
            }
        )
        self.runtime.store.append_event(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            event_type=event_type,
            payload=payload,
            agent_role=active.agent_role,
            state_version=active.state_version,
            causal_token=causal_token,
            payload_hash=response_hash,
            payload_ref=response_ref,
        )
        if ledger_status not in {"RESERVED", "RUNNING"}:
            self.runtime.store.record_cost(
                run_id=active.run_id,
                session_id=active.session_id,
                step_id=active.step_id,
                category="tool",
                name=execution.tool_name,
                amount=1.0,
                unit="call",
                metadata={"external_runtime": "omp", "ledger_status": ledger_status},
            )
        return {"ledger_status": ledger_status, "idempotency_key": idempotency_key, "tool_call_id": tool_call_id}

    def record_failure(self, failure: OmpFailure) -> None:
        active = self._require_turn(failure.session_id, failure.turn_id)
        if failure.category == "model":
            self._context_for(failure.session_id, failure.turn_id).record_model_failure(
                provider=failure.provider or "custom",
                model=failure.model or "unknown",
                error_type=failure.error_type,
                message=failure.message,
                retryable=failure.retryable,
                request=dict(failure.request),
                usage=dict(failure.usage),
                total_usd=float(failure.total_usd),
                metadata=dict(failure.metadata),
            )
        if not failure.terminal:
            return
        status = failure.status.lower()
        if status in {"waiting_human", "approval_required"}:
            self.runtime.store.mark_waiting_human(run_id=active.run_id, step_id=active.step_id, reason=failure.message, approval_id=failure.approval_id)
        elif status in {"retry_scheduled", "retry"} or failure.retryable:
            self.runtime.store.mark_retry(run_id=active.run_id, step_id=active.step_id, error=failure.message, error_type=failure.error_type)
        else:
            self.runtime.store.mark_failed(run_id=active.run_id, step_id=active.step_id, error=failure.message, error_type=failure.error_type)
        self._active_turns.pop(self._turn_key(failure.session_id, failure.turn_id), None)

    def record_state_change(self, change: OmpStateChange) -> int | None:
        session = self._ensure_session(OmpSession(session_id=change.session_id))
        active = self._active_turns.get(self._turn_key(change.session_id, change.turn_id)) if change.turn_id else None
        artifact_refs: dict[str, Any] = {}
        artifact_prefix = f"omp-{change.label}"
        if change.before_snapshot is not None:
            artifact_refs["before_artifact_id"] = self._store_artifact(
                run_id=session.run_id,
                step_id=active.step_id if active else None,
                name=f"{artifact_prefix}-before",
                content=change.before_snapshot,
                metadata={"schema_version": OMP_ADAPTER_SCHEMA_VERSION, "kind": "before_snapshot", "external_session_id": change.session_id},
                agent_role=active.agent_role if active else None,
                state_version=active.state_version if active else self._run_state_version(session.run_id),
            )
        if change.after_snapshot is not None:
            artifact_refs["after_artifact_id"] = self._store_artifact(
                run_id=session.run_id,
                step_id=active.step_id if active else None,
                name=f"{artifact_prefix}-after",
                content=change.after_snapshot,
                metadata={"schema_version": OMP_ADAPTER_SCHEMA_VERSION, "kind": "after_snapshot", "external_session_id": change.session_id},
                agent_role=active.agent_role if active else None,
                state_version=active.state_version if active else self._run_state_version(session.run_id),
            )
        if change.diff is not None:
            artifact_refs["diff_artifact_id"] = self._store_artifact(
                run_id=session.run_id,
                step_id=active.step_id if active else None,
                name=f"{artifact_prefix}-diff",
                content=change.diff,
                metadata={"schema_version": OMP_ADAPTER_SCHEMA_VERSION, "kind": "diff", "external_session_id": change.session_id},
                agent_role=active.agent_role if active else None,
                state_version=active.state_version if active else self._run_state_version(session.run_id),
            )
        new_version: int | None = None
        if change.patch and change.commit_status.lower() in {"committed", "applied"}:
            new_version = self.runtime.store.apply_system_state_patch(run_id=session.run_id, patch=dict(change.patch), reason=change.reason)
            if active is not None:
                active.state_version = new_version
        event_state_version = new_version if new_version is not None else (active.state_version if active else self._run_state_version(session.run_id))
        self.runtime.store.append_event(
            run_id=session.run_id,
            session_id=session.session_id,
            step_id=active.step_id if active else None,
            event_type="omp_state_change_recorded",
            payload=_compact(
                {
                    "schema_version": OMP_ADAPTER_SCHEMA_VERSION,
                    "adapter": self.name,
                    "app_name": self.app_name,
                    "external_session_id": change.session_id,
                    "external_turn_id": change.turn_id,
                    "reason": change.reason,
                    "commit_status": change.commit_status,
                    "patch": dict(change.patch),
                    "artifacts": artifact_refs,
                    "metadata": dict(change.metadata),
                }
            ),
            agent_role=active.agent_role if active else None,
            state_version=event_state_version,
        )
        return new_version

    def _ensure_session(self, session: OmpSession) -> _BridgeSession:
        existing = self._sessions.get(session.session_id)
        if existing is not None:
            return existing
        if session.run_id is not None:
            run = self.runtime.store.run(session.run_id)
            pending_steps = [dict(row) for row in self.runtime.store.steps(session.run_id) if row["status"] in {"pending", "retry_scheduled"}]
            bridge_session = _BridgeSession(
                run_id=session.run_id,
                session_id=str(run["session_id"]),
                initial_step_id=pending_steps[0]["step_id"] if pending_steps else None,
            )
        else:
            run_id, step_id = self.runtime.create_run(initial_state=dict(session.initial_state))
            run = self.runtime.store.run(run_id)
            bridge_session = _BridgeSession(run_id=run_id, session_id=str(run["session_id"]), initial_step_id=step_id)
        self._sessions[session.session_id] = bridge_session
        return bridge_session

    def _require_turn(self, external_session_id: str, turn_id: str) -> _ActiveTurn:
        active = self._active_turns.get(self._turn_key(external_session_id, turn_id))
        if active is None:
            raise KeyError(f"OMP turn not active: {external_session_id}/{turn_id}")
        return active

    def _context_for(self, external_session_id: str, turn_id: str) -> AgentContext:
        active = self._require_turn(external_session_id, turn_id)
        return AgentContext(
            run_id=active.run_id,
            session_id=active.session_id,
            step_id=active.step_id,
            agent_role=active.agent_role,
            lease_token=active.lease_token,
            attempt=active.attempt,
            state_version=active.state_version,
            store=self.runtime.store,
            gateway=self.runtime.gateway,
            blobs=self.runtime.blobs,
            budget=self.runtime.budget,
        )

    def _store_artifact(
        self,
        *,
        run_id: str,
        step_id: str | None,
        name: str,
        content: Any,
        metadata: dict[str, Any],
        agent_role: str | None,
        state_version: int,
    ) -> str:
        blob_hash, blob_ref = self.runtime.blobs.put_json(content)
        artifact_id = self.runtime.store.create_artifact(run_id=run_id, step_id=step_id, name=name, blob_hash=blob_hash, blob_ref=blob_ref, metadata=metadata)
        self.runtime.store.append_event(
            run_id=run_id,
            session_id=self.runtime.store.run(run_id)["session_id"],
            step_id=step_id,
            event_type="artifact_created",
            payload={"artifact_id": artifact_id, "name": name},
            agent_role=agent_role,
            state_version=state_version,
            payload_hash=blob_hash,
            payload_ref=blob_ref,
        )
        return artifact_id

    def _run_state_version(self, run_id: str) -> int:
        return int(self.runtime.store.run(run_id)["state_version"])

    def _next_runnable_step_id(self, run_id: str) -> str | None:
        for row in self.runtime.store.steps(run_id):
            if row["status"] in {"pending", "retry_scheduled"}:
                return str(row["step_id"])
        return None

    @staticmethod
    def _turn_key(external_session_id: str, turn_id: str | None) -> str:
        return f"{external_session_id}\x1f{turn_id or ''}"


def _external_id_from_result(result: Any) -> str | None:
    if isinstance(result, dict):
        value = result.get("external_id")
        return str(value) if value is not None else None
    return None


def _ledger_status(value: str | None, error_message: str | None) -> str:
    if value is None:
        return "SUCCEEDED" if not error_message else "PENDING_VERIFICATION"
    normalized = str(value).strip().upper()
    aliases = {
        "SUCCESS": "SUCCEEDED",
        "SUCCEEDED": "SUCCEEDED",
        "COMPLETED": "SUCCEEDED",
        "OK": "SUCCEEDED",
        "FAILED": "PENDING_VERIFICATION",
        "FAILED_NO_EFFECT": "FAILED_NO_EFFECT",
        "NO_EFFECT": "FAILED_NO_EFFECT",
        "PENDING_VERIFICATION": "PENDING_VERIFICATION",
        "UNKNOWN": "PENDING_VERIFICATION",
        "COMPENSATED": "COMPENSATED",
        "RUNNING": "RUNNING",
        "RESERVED": "RESERVED",
    }
    status = aliases.get(normalized, normalized)
    if status not in _ALL_LEDGER_STATUSES:
        raise ValueError(f"unsupported Tool Ledger status: {value}")
    return status


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
