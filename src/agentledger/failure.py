from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


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
        }


class FailureAttributionReporter:
    """Summarize failure signals already recorded by the runtime."""

    FAILURE_EVENT_TYPES = {
        "failure_classified",
        "error_raised",
        "step_failed",
        "step_retry_scheduled",
        "step_waiting_human",
        "lease_expired",
        "run_cancel_requested",
        "run_cancelled",
        "tool_call_failed",
        "tool_approval_required",
        "tool_call_blocked",
    }

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

        summary = {
            "failed_step_count": len(failed_steps),
            "retry_scheduled_step_count": len(retry_scheduled_steps),
            "waiting_human_step_count": len(waiting_human_steps),
            "pending_verification_count": len(pending_verification),
            "pending_approval_count": len(pending_approvals),
            "failure_event_count": len(events),
            "root_cause_count": len(root_causes),
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
        return {key: data.get(key) for key in ["seq", "type", "step_id", "agent_role", "payload"]}

    def _row_dict(self, row: Any) -> dict[str, Any]:
        return {key: row[key] for key in row.keys()}

    def _decode_inline_payload(self, ref: Any) -> Any:
        if not isinstance(ref, str) or ref.startswith("blob://"):
            return None
        try:
            return json.loads(ref)
        except json.JSONDecodeError:
            return ref
