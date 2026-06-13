from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


FAILURE_ENVELOPE_SCHEMA_VERSION = "agentledger.failure.envelope.v1"


class RetryableAgentError(RuntimeError):
    """Agent code can raise this to request retry under the run retry policy."""


class NonRetryableAgentError(RuntimeError):
    """Agent code can raise this to fail immediately."""


@dataclass(frozen=True)
class FailureClassification:
    error_type: str
    message: str
    retryable: bool
    category: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "retryable": self.retryable,
            "category": self.category,
        }


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RetryPolicy":
        data = data or {}
        return cls(max_attempts=int(data.get("max_attempts", 3)))

    def to_dict(self) -> dict[str, Any]:
        return {"max_attempts": self.max_attempts}

    def allows_retry_after_attempt(self, attempt: int) -> bool:
        return attempt < self.max_attempts


def classify_exception(exc: BaseException) -> FailureClassification:
    error_type = type(exc).__name__
    if isinstance(exc, NonRetryableAgentError):
        return FailureClassification(error_type=error_type, message=str(exc), retryable=False, category="non_retryable_agent_error")
    if isinstance(exc, RetryableAgentError):
        return FailureClassification(error_type=error_type, message=str(exc), retryable=True, category="retryable_agent_error")
    if isinstance(exc, TimeoutError):
        return FailureClassification(error_type=error_type, message=str(exc), retryable=True, category="timeout")
    return FailureClassification(error_type=error_type, message=str(exc), retryable=False, category="unhandled_exception")


@dataclass(frozen=True)
class FailureAttributionReport:
    run_id: str
    run_status: str
    summary: dict[str, Any]
    root_causes: list[dict[str, Any]]
    failed_steps: list[dict[str, Any]]
    pending_verification: list[dict[str, Any]]
    pending_approvals: list[dict[str, Any]]
    failure_events: list[dict[str, Any]]
    failure_envelopes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_status": self.run_status,
            "summary": self.summary,
            "root_causes": self.root_causes,
            "failed_steps": self.failed_steps,
            "pending_verification": self.pending_verification,
            "pending_approvals": self.pending_approvals,
            "failure_events": self.failure_events,
            "failure_envelopes": self.failure_envelopes,
        }


class FailureEnvelopeBuilder:
    """Build a normalized failure read model from runtime state and events."""

    FAILURE_EVENT_TYPES = {
        "failure_classified",
        "error_raised",
        "step_failed",
        "step_retry_scheduled",
        "step_waiting_human",
        "lease_expired",
        "run_cancel_requested",
        "run_cancelled",
        "step_cancelled",
        "tool_call_failed",
        "tool_approval_required",
        "tool_call_blocked",
    }

    def from_snapshot(
        self,
        *,
        run_id: str,
        run_status: str,
        steps: list[dict[str, Any]],
        ledger: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        envelopes: list[dict[str, Any]] = []
        for row in steps:
            status = str(row.get("status") or "")
            if status in {"failed", "retry_scheduled", "waiting_human"}:
                envelopes.append(self._from_step(run_id=run_id, run_status=run_status, row=row))
        for row in ledger:
            status = str(row.get("status") or "")
            if status in {"PENDING_VERIFICATION", "FAILED", "ERROR"}:
                envelopes.append(self._from_ledger(run_id=run_id, run_status=run_status, row=row))
        for row in approvals:
            status = str(row.get("status") or "")
            if status in {"PENDING", "DENIED"}:
                envelopes.append(self._from_approval(run_id=run_id, run_status=run_status, row=row))
        for event in events:
            event_type = str(event.get("type") or "")
            if event_type in self.FAILURE_EVENT_TYPES:
                envelopes.append(self._from_event(run_id=run_id, run_status=run_status, event=event))
        if run_status == "cancelled" and not any(item.get("category") == "cancellation" for item in envelopes):
            envelopes.append(
                self._envelope(
                    run_id=run_id,
                    source_kind="run",
                    source_id=run_id,
                    category="cancellation",
                    status="terminal",
                    severity="risk",
                    recoverability="terminal",
                    retryability="not_retryable",
                    owner="runtime",
                    message="run was cancelled",
                    causal_refs=[{"kind": "run", "value": run_id}],
                    evidence_refs=[],
                )
            )
        return _dedupe_envelopes(envelopes)

    def _from_step(self, *, run_id: str, run_status: str, row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("status") or "")
        if status == "retry_scheduled":
            failure_status = "recovery_scheduled"
            severity = "warn"
            recoverability = "auto_retry"
            retryability = "retryable"
        elif status == "waiting_human":
            failure_status = "waiting_human"
            severity = "warn"
            recoverability = "human_required"
            retryability = "unknown"
        else:
            failure_status = "terminal" if run_status in {"failed", "cancelled"} else "failed"
            severity = "risk"
            recoverability = "terminal" if run_status in {"failed", "cancelled"} else "recoverable"
            retryability = "not_retryable" if run_status in {"failed", "cancelled"} else "unknown"
        step_id = _text(row.get("step_id"))
        return self._envelope(
            run_id=run_id,
            source_kind="step",
            source_id=step_id or run_id,
            category=_category_from_text(row.get("last_error_type"), row.get("last_error"), default="agent"),
            status=failure_status,
            severity=severity,
            recoverability=recoverability,
            retryability=retryability,
            owner="agent",
            message=_message(row.get("last_error"), row.get("last_error_type"), "step failure"),
            step_id=step_id,
            occurred_at=row.get("updated_at") or row.get("created_at"),
            causal_refs=_refs(step_id=step_id),
            evidence_refs=_refs(step_id=step_id),
            details={
                "attempt": row.get("attempt"),
                "last_error_type": row.get("last_error_type"),
                "last_error": row.get("last_error"),
                "step_status": row.get("status"),
            },
        )

    def _from_ledger(self, *, run_id: str, run_status: str, row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("status") or "")
        terminal = status in {"FAILED", "ERROR"}
        step_id = _text(row.get("step_id"))
        tool_name = _text(row.get("tool_name"))
        return self._envelope(
            run_id=run_id,
            source_kind="tool_ledger",
            source_id=_text(row.get("ledger_id")) or tool_name or step_id or run_id,
            category="tool",
            status="terminal" if terminal else "unknown_side_effect",
            severity="risk" if terminal else "warn",
            recoverability="terminal" if terminal else "manual_verification",
            retryability="not_retryable" if terminal else "unknown",
            owner="tool",
            message=_message(row.get("error"), row.get("error_type"), "tool side effect requires verification"),
            step_id=step_id,
            tool_name=tool_name,
            occurred_at=row.get("updated_at") or row.get("created_at"),
            causal_refs=_refs(step_id=step_id, tool_name=tool_name),
            evidence_refs=_refs(step_id=step_id, tool_name=tool_name, blob_ref=row.get("response_ref")),
            details={
                "ledger_status": row.get("status"),
                "error_type": row.get("error_type"),
                "idempotency_key": row.get("idempotency_key"),
                "external_id": row.get("external_id"),
            },
        )

    def _from_approval(self, *, run_id: str, run_status: str, row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("status") or "")
        denied = status == "DENIED"
        step_id = _text(row.get("step_id"))
        tool_name = _text(row.get("tool_name"))
        approval_id = _text(row.get("approval_id"))
        return self._envelope(
            run_id=run_id,
            source_kind="approval",
            source_id=approval_id or tool_name or step_id or run_id,
            category="policy" if denied else "approval",
            status="blocked" if denied else "waiting_human",
            severity="risk" if denied else "warn",
            recoverability="terminal" if denied and run_status in {"failed", "cancelled"} else "human_required",
            retryability="not_retryable" if denied else "unknown",
            owner="policy",
            message=_message(row.get("decision_reason"), row.get("reason"), "approval is pending" if not denied else "approval denied"),
            step_id=step_id,
            tool_name=tool_name,
            approval_id=approval_id,
            occurred_at=row.get("updated_at") or row.get("created_at"),
            causal_refs=_refs(step_id=step_id, tool_name=tool_name, approval_id=approval_id),
            evidence_refs=_refs(step_id=step_id, tool_name=tool_name, approval_id=approval_id),
            details={
                "approval_status": row.get("status"),
                "risk_level": row.get("risk_level"),
                "requested_by": row.get("requested_by"),
                "approved_by": row.get("approved_by"),
            },
        )

    def _from_event(self, *, run_id: str, run_status: str, event: dict[str, Any]) -> dict[str, Any]:
        payload = _safe_dict(event.get("payload"))
        event_type = str(event.get("type") or "")
        category = _category_from_event(event_type, payload)
        status = _event_failure_status(event_type, payload, run_status)
        severity = "risk" if status in {"terminal", "blocked", "failed"} else "warn"
        recoverability = _event_recoverability(event_type, payload, run_status)
        retryability = _event_retryability(event_type, payload, recoverability)
        step_id = _text(event.get("step_id") or payload.get("step_id"))
        tool_name = _text(payload.get("tool_name") or payload.get("tool") or payload.get("name"))
        approval_id = _text(payload.get("approval_id"))
        seq = event.get("seq")
        return self._envelope(
            run_id=run_id,
            source_kind="event",
            source_id=str(seq) if seq is not None else event_type,
            category=category,
            status=status,
            severity=severity,
            recoverability=recoverability,
            retryability=retryability,
            owner=_owner_for_category(category),
            message=_message(payload.get("error"), payload.get("reason"), payload.get("error_type"), event_type),
            step_id=step_id,
            tool_name=tool_name,
            approval_id=approval_id,
            event_seq=seq,
            event_type=event_type,
            occurred_at=event.get("timestamp"),
            causal_refs=_refs(step_id=step_id, tool_name=tool_name, approval_id=approval_id, event_seq=seq),
            evidence_refs=_refs(step_id=step_id, tool_name=tool_name, approval_id=approval_id, event_seq=seq, blob_ref=event.get("payload_ref")),
            details={"payload": payload} if payload else {},
        )

    def _envelope(
        self,
        *,
        run_id: str,
        source_kind: str,
        source_id: str,
        category: str,
        status: str,
        severity: str,
        recoverability: str,
        retryability: str,
        owner: str,
        message: str,
        step_id: str | None = None,
        tool_name: str | None = None,
        approval_id: str | None = None,
        event_seq: Any = None,
        event_type: str | None = None,
        occurred_at: Any = None,
        causal_refs: list[dict[str, str]] | None = None,
        evidence_refs: list[dict[str, str]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        envelope = {
            "schema_version": FAILURE_ENVELOPE_SCHEMA_VERSION,
            "failure_id": _failure_id(run_id, source_kind, source_id),
            "run_id": run_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "category": category,
            "status": status,
            "severity": severity,
            "recoverability": recoverability,
            "retryability": retryability,
            "owner": owner,
            "message": message,
            "causal_refs": causal_refs or [],
            "evidence_refs": evidence_refs or [],
        }
        for key, value in {
            "step_id": step_id,
            "tool_name": tool_name,
            "approval_id": approval_id,
            "event_seq": event_seq,
            "event_type": event_type,
            "occurred_at": occurred_at,
        }.items():
            if value is not None:
                envelope[key] = value
        if details:
            envelope["details"] = details
        return envelope


class FailureAttributionReporter:
    """Summarize failure signals already recorded by the runtime."""

    FAILURE_EVENT_TYPES = FailureEnvelopeBuilder.FAILURE_EVENT_TYPES

    def __init__(self, store: Any):
        self.store = store

    def report(self, run_id: str) -> FailureAttributionReport:
        run = self.store.run(run_id)
        steps = [self._row_dict(row) for row in self.store.steps(run_id)]
        ledger = [self._row_dict(row) for row in self.store.ledger(run_id)]
        approvals = [self._row_dict(row) for row in self.store.approval_requests(run_id)]
        events = [self._event_dict(row) for row in self.store.events(run_id) if row["type"] in self.FAILURE_EVENT_TYPES]

        failed_steps = [self._step_failure(row) for row in steps if row.get("status") == "failed"]
        pending_verification = [self._ledger_failure(row) for row in ledger if row.get("status") == "PENDING_VERIFICATION"]
        pending_approvals = [self._approval_failure(row) for row in approvals if row.get("status") == "PENDING"]
        retry_scheduled_steps = [row for row in steps if row.get("status") == "retry_scheduled"]
        waiting_human_steps = [row for row in steps if row.get("status") == "waiting_human"]

        root_causes: list[dict[str, Any]] = []
        root_causes.extend({"kind": "failed_step", **item} for item in failed_steps)
        root_causes.extend({"kind": "pending_verification", **item} for item in pending_verification)
        root_causes.extend({"kind": "pending_approval", **item} for item in pending_approvals)
        for row in retry_scheduled_steps:
            root_causes.append({"kind": "retry_scheduled", "step_id": row.get("step_id"), "error_type": row.get("last_error_type"), "error": row.get("last_error")})
        for row in waiting_human_steps:
            root_causes.append({"kind": "waiting_human", "step_id": row.get("step_id"), "reason": row.get("last_error")})
        if run["status"] == "cancelled":
            root_causes.append({"kind": "cancelled_run", "run_id": run_id})
        failure_envelopes = FailureEnvelopeBuilder().from_snapshot(
            run_id=run_id,
            run_status=run["status"],
            steps=steps,
            ledger=ledger,
            approvals=approvals,
            events=events,
        )

        summary = {
            "failed_step_count": len(failed_steps),
            "retry_scheduled_step_count": len(retry_scheduled_steps),
            "waiting_human_step_count": len(waiting_human_steps),
            "pending_verification_count": len(pending_verification),
            "pending_approval_count": len(pending_approvals),
            "failure_event_count": len(events),
            "root_cause_count": len(root_causes),
            "failure_envelope_count": len(failure_envelopes),
            "terminal_failure_count": sum(1 for item in failure_envelopes if item.get("status") == "terminal"),
            "recoverable_failure_count": sum(1 for item in failure_envelopes if item.get("recoverability") in {"auto_retry", "recoverable", "manual_verification", "human_required"}),
        }
        return FailureAttributionReport(
            run_id=run_id,
            run_status=run["status"],
            summary=summary,
            root_causes=root_causes,
            failed_steps=failed_steps,
            pending_verification=pending_verification,
            pending_approvals=pending_approvals,
            failure_events=events,
            failure_envelopes=failure_envelopes,
        )

    def _step_failure(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "step_id": row.get("step_id"),
            "status": row.get("status"),
            "attempt": row.get("attempt"),
            "error_type": row.get("last_error_type"),
            "error": row.get("last_error"),
        }

    def _ledger_failure(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "ledger_id": row.get("ledger_id"),
            "step_id": row.get("step_id"),
            "tool_name": row.get("tool_name"),
            "status": row.get("status"),
            "error_type": row.get("error_type"),
            "idempotency_key": row.get("idempotency_key"),
        }

    def _approval_failure(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "approval_id": row.get("approval_id"),
            "step_id": row.get("step_id"),
            "tool_name": row.get("tool_name"),
            "risk_level": row.get("risk_level"),
            "status": row.get("status"),
            "reason": row.get("reason"),
        }

    def _event_dict(self, row: Any) -> dict[str, Any]:
        data = self._row_dict(row)
        data["payload"] = self._decode_inline_payload(data.get("payload_ref"))
        return {key: data.get(key) for key in ["seq", "type", "step_id", "agent_role", "timestamp", "payload_ref", "payload"]}

    def _row_dict(self, row: Any) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    def _decode_inline_payload(self, ref: Any) -> Any:
        if not isinstance(ref, str) or ref.startswith("blob://"):
            return None
        try:
            return json.loads(ref)
        except json.JSONDecodeError:
            return ref


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _message(*values: Any) -> str:
    for value in values:
        if value is not None and value != "":
            return str(value)
    return "failure signal"


def _failure_id(run_id: str, source_kind: str, source_id: str) -> str:
    return "failure-" + "-".join(_slug(part) for part in [run_id, source_kind, source_id] if part)


def _slug(value: Any) -> str:
    text = str(value)
    chars = [char.lower() if char.isalnum() else "-" for char in text]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "unknown"


def _category_from_text(*values: Any, default: str) -> str:
    text = " ".join(str(value).lower() for value in values if value is not None)
    for category in ["sandbox", "budget", "policy", "model", "tool", "runtime"]:
        if category in text:
            return category
    if "approval" in text or "permission" in text or "denied" in text:
        return "policy"
    if "lease" in text or "worker" in text:
        return "runtime"
    if "cancel" in text:
        return "cancellation"
    if "retry" in text:
        return "retry"
    return default


def _category_from_event(event_type: str, payload: dict[str, Any]) -> str:
    if event_type in {"tool_call_failed", "tool_call_blocked", "tool_approval_required"}:
        return "tool"
    if event_type in {"run_cancel_requested", "run_cancelled", "step_cancelled"}:
        return "cancellation"
    if event_type in {"lease_expired"}:
        return "runtime"
    if event_type in {"step_retry_scheduled"}:
        return "retry"
    if event_type in {"step_waiting_human"}:
        return "approval"
    return _category_from_text(event_type, payload.get("error_type"), payload.get("error"), payload.get("reason"), default="agent")


def _event_failure_status(event_type: str, payload: dict[str, Any], run_status: str) -> str:
    if event_type in {"step_failed", "run_cancelled", "step_cancelled"} or (run_status in {"failed", "cancelled"} and event_type in {"error_raised"}):
        return "terminal"
    if event_type in {"tool_call_blocked"}:
        return "blocked"
    if event_type in {"step_retry_scheduled", "lease_expired"}:
        return "recovery_scheduled"
    if event_type in {"step_waiting_human", "tool_approval_required"}:
        return "waiting_human"
    if event_type == "failure_classified":
        return "classified"
    if payload.get("retryable") is True:
        return "recoverable"
    return "failed"


def _event_recoverability(event_type: str, payload: dict[str, Any], run_status: str) -> str:
    if run_status in {"failed", "cancelled"} and event_type in {"step_failed", "run_cancelled", "step_cancelled"}:
        return "terminal"
    if event_type in {"step_retry_scheduled", "lease_expired"}:
        return "auto_retry"
    if event_type in {"step_waiting_human", "tool_approval_required"}:
        return "human_required"
    if event_type == "tool_call_blocked":
        return "manual_intervention"
    if payload.get("retryable") is True:
        return "recoverable"
    return "unknown"


def _event_retryability(event_type: str, payload: dict[str, Any], recoverability: str) -> str:
    if payload.get("retryable") is True or recoverability == "auto_retry":
        return "retryable"
    if payload.get("retryable") is False or event_type in {"tool_call_blocked", "run_cancelled", "step_cancelled"}:
        return "not_retryable"
    return "unknown"


def _owner_for_category(category: str) -> str:
    if category in {"tool", "model", "policy", "sandbox", "budget", "runtime"}:
        return category
    if category in {"approval", "cancellation", "retry"}:
        return "runtime"
    return "agent"


def _refs(
    *,
    step_id: Any = None,
    tool_name: Any = None,
    approval_id: Any = None,
    event_seq: Any = None,
    blob_ref: Any = None,
) -> list[dict[str, str]]:
    refs = []
    for kind, value in [
        ("step", step_id),
        ("tool", tool_name),
        ("approval", approval_id),
        ("event", event_seq),
        ("blob", blob_ref),
    ]:
        if value is not None and value != "":
            refs.append({"kind": kind, "value": str(value)})
    return refs


def _dedupe_envelopes(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for envelope in envelopes:
        failure_id = str(envelope.get("failure_id") or "")
        if failure_id and failure_id not in seen:
            seen.add(failure_id)
            deduped.append(envelope)
    return deduped
