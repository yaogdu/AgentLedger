from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


FAILURE_ENVELOPE_SCHEMA_VERSION = "agentledger.failure.envelope.v1"
FAILURE_LIFECYCLE_SCHEMA_VERSION = "agentledger.failure.lifecycle.v1"
FAILURE_CAUSAL_GRAPH_SCHEMA_VERSION = "agentledger.failure.causal_graph.v1"
FAILURE_REPLAY_PLAN_SCHEMA_VERSION = "agentledger.failure.replay_plan.v1"
FAILURE_REGRESSION_SCHEMA_VERSION = "agentledger.failure.regression.v1"
FAILURE_EXPORT_SCHEMA_VERSION = "agentledger.failure.export.v1"
FAILURE_ALERT_SCHEMA_VERSION = "agentledger.failure.alerts.v1"


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
    failure_lifecycle: dict[str, Any]
    failure_causal_graph: dict[str, Any]
    failure_replay_plan: dict[str, Any]
    failure_alerts: dict[str, Any]
    failure_export: dict[str, Any]

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
            "failure_lifecycle": self.failure_lifecycle,
            "failure_causal_graph": self.failure_causal_graph,
            "failure_replay_plan": self.failure_replay_plan,
            "failure_alerts": self.failure_alerts,
            "failure_export": self.failure_export,
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
        "model_call_failed",
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


class FailureLifecycleBuilder:
    """Derive lifecycle events from normalized failure envelopes."""

    def from_envelopes(
        self,
        *,
        run_id: str,
        run_status: str,
        envelopes: list[dict[str, Any]],
        events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for envelope in envelopes:
            rows.extend(self._events_for_envelope(envelope, run_status=run_status))
        for event in events or []:
            if str(event.get("type") or "") == "failure_regressed":
                rows.append(
                    self._lifecycle_event(
                        stage="failure_regressed",
                        run_id=run_id,
                        failure_id=_text(_safe_dict(event.get("payload")).get("failure_id")),
                        message=_message(_safe_dict(event.get("payload")).get("message"), "failure regressed"),
                        event_seq=event.get("seq"),
                        occurred_at=event.get("timestamp"),
                        severity="risk",
                        refs=_refs(event_seq=event.get("seq")),
                    )
                )
        rows = _dedupe_lifecycle_events(sorted(rows, key=_lifecycle_sort_key))
        stage_counts: dict[str, int] = {}
        for row in rows:
            stage = str(row.get("stage") or "")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        return {
            "schema_version": FAILURE_LIFECYCLE_SCHEMA_VERSION,
            "run_id": run_id,
            "run_status": run_status,
            "events": rows,
            "stage_counts": stage_counts,
            "terminal": any(row.get("stage") == "failure_terminal" for row in rows),
            "recoverable": any(row.get("stage") in {"failure_recovery_scheduled", "failure_recovered"} for row in rows),
            "regressed": any(row.get("stage") == "failure_regressed" for row in rows),
        }

    def _events_for_envelope(self, envelope: dict[str, Any], *, run_status: str) -> list[dict[str, Any]]:
        failure_id = str(envelope.get("failure_id") or "")
        refs = _merge_refs(envelope.get("causal_refs"), envelope.get("evidence_refs"))
        rows = [
            self._lifecycle_event(
                stage="failure_detected",
                run_id=str(envelope.get("run_id") or ""),
                failure_id=failure_id,
                message=str(envelope.get("message") or "failure detected"),
                event_seq=envelope.get("event_seq"),
                occurred_at=envelope.get("occurred_at"),
                severity=str(envelope.get("severity") or "warn"),
                refs=refs,
                envelope=envelope,
            )
        ]
        if envelope.get("category") or envelope.get("status") == "classified":
            rows.append(
                self._lifecycle_event(
                    stage="failure_classified",
                    run_id=str(envelope.get("run_id") or ""),
                    failure_id=failure_id,
                    message=str(envelope.get("category") or "classified"),
                    event_seq=envelope.get("event_seq"),
                    occurred_at=envelope.get("occurred_at"),
                    severity=str(envelope.get("severity") or "warn"),
                    refs=refs,
                    envelope=envelope,
                )
            )
        status = str(envelope.get("status") or "")
        recoverability = str(envelope.get("recoverability") or "")
        if status == "recovery_scheduled" or recoverability == "auto_retry":
            rows.append(
                self._lifecycle_event(
                    stage="failure_recovery_scheduled",
                    run_id=str(envelope.get("run_id") or ""),
                    failure_id=failure_id,
                    message="runtime recovery scheduled",
                    event_seq=envelope.get("event_seq"),
                    occurred_at=envelope.get("occurred_at"),
                    severity="warn",
                    refs=refs,
                    envelope=envelope,
                )
            )
        if status in {"waiting_human", "unknown_side_effect"} or recoverability in {"human_required", "manual_verification"}:
            rows.append(
                self._lifecycle_event(
                    stage="failure_recovery_scheduled",
                    run_id=str(envelope.get("run_id") or ""),
                    failure_id=failure_id,
                    message=_recovery_message(envelope),
                    event_seq=envelope.get("event_seq"),
                    occurred_at=envelope.get("occurred_at"),
                    severity="warn",
                    refs=refs,
                    envelope=envelope,
                )
            )
        if status == "recovered" or (run_status == "completed" and recoverability in {"auto_retry", "recoverable"}):
            rows.append(
                self._lifecycle_event(
                    stage="failure_recovered",
                    run_id=str(envelope.get("run_id") or ""),
                    failure_id=failure_id,
                    message="failure recovered",
                    event_seq=envelope.get("event_seq"),
                    occurred_at=envelope.get("occurred_at"),
                    severity="info",
                    refs=refs,
                    envelope=envelope,
                )
            )
        if status in {"terminal", "blocked"} or recoverability == "terminal":
            rows.append(
                self._lifecycle_event(
                    stage="failure_terminal",
                    run_id=str(envelope.get("run_id") or ""),
                    failure_id=failure_id,
                    message=str(envelope.get("message") or "terminal failure"),
                    event_seq=envelope.get("event_seq"),
                    occurred_at=envelope.get("occurred_at"),
                    severity="risk",
                    refs=refs,
                    envelope=envelope,
                )
            )
        return rows

    def _lifecycle_event(
        self,
        *,
        stage: str,
        run_id: str,
        failure_id: str | None,
        message: str,
        event_seq: Any,
        occurred_at: Any,
        severity: str,
        refs: list[dict[str, str]],
        envelope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "schema_version": FAILURE_LIFECYCLE_SCHEMA_VERSION,
            "stage": stage,
            "run_id": run_id,
            "message": message,
            "severity": severity,
            "causal_refs": refs,
        }
        for key, value in {
            "failure_id": failure_id,
            "event_seq": event_seq,
            "occurred_at": occurred_at,
        }.items():
            if value is not None and value != "":
                row[key] = value
        if envelope:
            row["category"] = envelope.get("category")
            row["recoverability"] = envelope.get("recoverability")
            row["retryability"] = envelope.get("retryability")
            row["owner"] = envelope.get("owner")
        return row


class FailureCausalGraphBuilder:
    """Build a portable graph linking failures back to runtime evidence."""

    def from_snapshot(
        self,
        *,
        run_id: str,
        run_status: str,
        envelopes: list[dict[str, Any]],
        steps: list[dict[str, Any]],
        ledger: list[dict[str, Any]],
        approvals: list[dict[str, Any]],
        events: list[dict[str, Any]],
        cost_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, str]] = []

        def add_node(kind: str, node_id: Any, **attrs: Any) -> str:
            node_key = _node_key(kind, node_id)
            nodes.setdefault(node_key, {"id": node_key, "kind": kind, **{k: v for k, v in attrs.items() if v is not None}})
            return node_key

        def add_edge(source: str, target: str, kind: str) -> None:
            edge = {"source": source, "target": target, "kind": kind}
            if edge not in edges:
                edges.append(edge)

        run_node = add_node("run", run_id, status=run_status)
        for step in steps:
            step_node = add_node("step", step.get("step_id"), status=step.get("status"), attempt=step.get("attempt"))
            add_edge(run_node, step_node, "contains_step")
        for event in events:
            event_node = add_node("event", event.get("seq"), event_type=event.get("type"), step_id=event.get("step_id"))
            add_edge(run_node, event_node, "emitted_event")
            if event.get("step_id"):
                add_edge(_node_key("step", event.get("step_id")), event_node, "step_emitted_event")
        for entry in ledger:
            tool_node = add_node("tool", entry.get("tool_name"), status=entry.get("status"))
            add_edge(run_node, tool_node, "used_tool")
            if entry.get("step_id"):
                add_edge(_node_key("step", entry.get("step_id")), tool_node, "step_used_tool")
        for approval in approvals:
            approval_node = add_node("approval", approval.get("approval_id"), status=approval.get("status"), tool_name=approval.get("tool_name"))
            add_edge(run_node, approval_node, "requested_approval")
            if approval.get("step_id"):
                add_edge(_node_key("step", approval.get("step_id")), approval_node, "step_requested_approval")
        for record in cost_records or []:
            cost_node = add_node("cost", record.get("cost_id") or f"{record.get('category')}:{record.get('name')}", category=record.get("category"), name=record.get("name"), amount=record.get("amount"), unit=record.get("unit"))
            add_edge(run_node, cost_node, "recorded_cost")
            if record.get("step_id"):
                add_edge(_node_key("step", record.get("step_id")), cost_node, "step_recorded_cost")
        for envelope in envelopes:
            failure_node = add_node("failure", envelope.get("failure_id"), category=envelope.get("category"), status=envelope.get("status"), owner=envelope.get("owner"))
            add_edge(run_node, failure_node, "has_failure")
            for ref in _merge_refs(envelope.get("causal_refs"), envelope.get("evidence_refs")):
                ref_node = add_node(str(ref.get("kind") or "ref"), ref.get("value"))
                add_edge(ref_node, failure_node, "caused_or_evidenced")
        return {
            "schema_version": FAILURE_CAUSAL_GRAPH_SCHEMA_VERSION,
            "run_id": run_id,
            "nodes": sorted(nodes.values(), key=lambda row: str(row.get("id"))),
            "edges": sorted(edges, key=lambda row: (row["source"], row["target"], row["kind"])),
            "summary": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "failure_node_count": sum(1 for row in nodes.values() if row.get("kind") == "failure"),
            },
        }


class FailureReplayPlanner:
    """Explain whether failure investigation can replay without unsafe side effects."""

    def plan(
        self,
        *,
        run_id: str,
        envelopes: list[dict[str, Any]],
        ledger: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        actions = [self._action_for_envelope(envelope) for envelope in envelopes]
        unsafe = [action for action in actions if not action.get("replay_safe")]
        manual = [action for action in actions if action.get("requires_manual_verification")]
        return {
            "schema_version": FAILURE_REPLAY_PLAN_SCHEMA_VERSION,
            "run_id": run_id,
            "mode": "evidence_only",
            "safe_to_replay": not unsafe,
            "unsafe_side_effect_count": len(unsafe),
            "manual_verification_count": len(manual),
            "recorded_tool_call_count": len(ledger),
            "recorded_event_count": len(events),
            "actions": actions,
        }

    def _action_for_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        status = str(envelope.get("status") or "")
        recoverability = str(envelope.get("recoverability") or "")
        category = str(envelope.get("category") or "")
        action = {
            "failure_id": envelope.get("failure_id"),
            "category": category,
            "status": status,
            "replay_action": "reuse_recorded_evidence",
            "replay_safe": True,
            "requires_manual_verification": False,
            "reason": "recorded runtime evidence can be inspected without calling external systems",
        }
        if status == "unknown_side_effect" or recoverability == "manual_verification":
            action.update(
                {
                    "replay_action": "manual_verify_side_effect",
                    "replay_safe": False,
                    "requires_manual_verification": True,
                    "reason": "Tool Ledger recorded an unknown side-effect state; replay must not call the external tool again automatically",
                }
            )
        elif status == "waiting_human" or recoverability == "human_required":
            action.update({"replay_action": "resume_after_approval", "reason": "runtime can resume after human approval without repeating completed side effects"})
        elif status == "recovery_scheduled" or recoverability == "auto_retry":
            action.update({"replay_action": "retry_from_checkpoint", "reason": "runtime retry is guarded by checkpoint, lease, and Tool Ledger evidence"})
        elif status in {"terminal", "blocked"}:
            action.update({"replay_action": "terminal_stop", "reason": "terminal failure should be replayed as evidence only unless the operator starts a new run"})
        if category in {"tool", "sandbox"} and status in {"failed", "terminal"} and not envelope.get("evidence_refs"):
            action.update({"replay_safe": False, "requires_manual_verification": True, "reason": "external boundary failure lacks evidence refs for automatic replay"})
        return action


class FailureAlertEvaluator:
    """Derive local alert records without sending them to an external sink."""

    def evaluate(
        self,
        *,
        run_id: str,
        envelopes: list[dict[str, Any]],
        replay_plan: dict[str, Any],
        cost_records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        alerts: list[dict[str, Any]] = []
        terminal = [item for item in envelopes if item.get("status") == "terminal"]
        if terminal:
            alerts.append(self._alert(run_id, "terminal_failure", "risk", f"{len(terminal)} terminal failure(s) recorded", terminal))
        unknown = [item for item in envelopes if item.get("status") == "unknown_side_effect"]
        if unknown:
            alerts.append(self._alert(run_id, "unknown_side_effect", "risk", f"{len(unknown)} tool side-effect state(s) require manual verification", unknown))
        blocked = [item for item in envelopes if item.get("status") == "blocked"]
        if blocked:
            alerts.append(self._alert(run_id, "policy_or_tool_blocked", "warn", f"{len(blocked)} failure(s) blocked by policy/tool gateway", blocked))
        total_usd = sum(float(row.get("amount") or 0) for row in cost_records or [] if row.get("unit") == "usd")
        if total_usd > 0 and terminal:
            alerts.append(
                {
                    "schema_version": FAILURE_ALERT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "kind": "costly_failure",
                    "severity": "warn",
                    "message": f"terminal failure consumed ${total_usd:.6f}",
                    "refs": [{"kind": "run", "value": run_id}],
                    "total_usd": round(total_usd, 6),
                }
            )
        if replay_plan.get("unsafe_side_effect_count", 0):
            alerts.append(
                {
                    "schema_version": FAILURE_ALERT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "kind": "unsafe_replay_blocked",
                    "severity": "risk",
                    "message": "failure replay plan blocks unsafe automatic replay",
                    "refs": [{"kind": "run", "value": run_id}],
                    "unsafe_side_effect_count": replay_plan.get("unsafe_side_effect_count"),
                }
            )
        return {
            "schema_version": FAILURE_ALERT_SCHEMA_VERSION,
            "run_id": run_id,
            "alerts": alerts,
            "alert_count": len(alerts),
        }

    def _alert(self, run_id: str, kind: str, severity: str, message: str, envelopes: list[dict[str, Any]]) -> dict[str, Any]:
        refs = [{"kind": "failure", "value": str(item.get("failure_id"))} for item in envelopes if item.get("failure_id")]
        return {"schema_version": FAILURE_ALERT_SCHEMA_VERSION, "run_id": run_id, "kind": kind, "severity": severity, "message": message, "refs": refs}


class FailureRegressionAnalyzer:
    """Compare two failure exports or envelope lists."""

    def compare(self, baseline: dict[str, Any] | list[dict[str, Any]], current: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        baseline_envelopes = _extract_envelopes(baseline)
        current_envelopes = _extract_envelopes(current)
        baseline_by_sig = {_failure_signature(item): item for item in baseline_envelopes}
        current_by_sig = {_failure_signature(item): item for item in current_envelopes}
        baseline_sigs = set(baseline_by_sig)
        current_sigs = set(current_by_sig)
        recurring = sorted(baseline_sigs & current_sigs)
        fixed = sorted(baseline_sigs - current_sigs)
        new = sorted(current_sigs - baseline_sigs)
        return {
            "schema_version": FAILURE_REGRESSION_SCHEMA_VERSION,
            "same": not new and not fixed,
            "recurring_failures": [current_by_sig[sig] for sig in recurring],
            "fixed_failures": [baseline_by_sig[sig] for sig in fixed],
            "new_failures": [current_by_sig[sig] for sig in new],
            "summary": {
                "baseline_failure_count": len(baseline_envelopes),
                "current_failure_count": len(current_envelopes),
                "recurring_failure_count": len(recurring),
                "fixed_failure_count": len(fixed),
                "new_failure_count": len(new),
            },
        }


class FailureExportMapper:
    """Build the portable failure export consumed by observability/eval tools."""

    def export(
        self,
        *,
        run_id: str,
        run_status: str,
        summary: dict[str, Any],
        envelopes: list[dict[str, Any]],
        lifecycle: dict[str, Any],
        causal_graph: dict[str, Any],
        replay_plan: dict[str, Any],
        alerts: dict[str, Any],
    ) -> dict[str, Any]:
        export = {
            "schema_version": FAILURE_EXPORT_SCHEMA_VERSION,
            "run_id": run_id,
            "run_status": run_status,
            "summary": summary,
            "failure_envelopes": envelopes,
            "failure_lifecycle": lifecycle,
            "failure_causal_graph": causal_graph,
            "failure_replay_plan": replay_plan,
            "failure_alerts": alerts,
        }
        export["external_mappings"] = {
            "opentelemetry": self._otel_mapping(run_id, lifecycle),
            "langfuse": self._langfuse_mapping(run_id, envelopes),
            "langsmith": self._langsmith_mapping(run_id, envelopes),
            "temporal": self._temporal_mapping(run_id, envelopes, replay_plan),
        }
        return export

    def _otel_mapping(self, run_id: str, lifecycle: dict[str, Any]) -> dict[str, Any]:
        events = []
        for row in lifecycle.get("events", []):
            events.append(
                {
                    "name": row.get("stage"),
                    "attributes": {
                        "agentledger.run_id": run_id,
                        "agentledger.failure_id": row.get("failure_id"),
                        "agentledger.failure.category": row.get("category"),
                        "agentledger.failure.owner": row.get("owner"),
                        "agentledger.failure.severity": row.get("severity"),
                    },
                }
            )
        return {"span_event_count": len(events), "span_events": events}

    def _langfuse_mapping(self, run_id: str, envelopes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "trace_id": run_id,
            "observations": [
                {
                    "id": item.get("failure_id"),
                    "type": "EVENT",
                    "name": f"agentledger.failure.{item.get('category')}",
                    "level": "ERROR" if item.get("severity") == "risk" else "WARNING",
                    "metadata": item,
                }
                for item in envelopes
            ],
        }

    def _langsmith_mapping(self, run_id: str, envelopes: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "feedback": [
                {
                    "key": "agentledger_failure",
                    "score": 0 if item.get("severity") == "risk" else 0.5,
                    "comment": item.get("message"),
                    "metadata": item,
                }
                for item in envelopes
            ],
        }

    def _temporal_mapping(self, run_id: str, envelopes: list[dict[str, Any]], replay_plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "workflow_id": run_id,
            "failure_count": len(envelopes),
            "non_retryable": any(item.get("retryability") == "not_retryable" for item in envelopes),
            "safe_to_replay": replay_plan.get("safe_to_replay"),
            "search_attributes": {
                "AgentLedgerFailureCount": len(envelopes),
                "AgentLedgerUnsafeReplay": bool(replay_plan.get("unsafe_side_effect_count")),
            },
        }


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
        all_events = [self._event_dict(row) for row in self.store.events(run_id)]
        events = [row for row in all_events if row["type"] in self.FAILURE_EVENT_TYPES]
        cost_records = [self._row_dict(row) for row in self.store.cost_records(run_id)]

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
        failure_lifecycle = FailureLifecycleBuilder().from_envelopes(run_id=run_id, run_status=run["status"], envelopes=failure_envelopes, events=events)
        failure_causal_graph = FailureCausalGraphBuilder().from_snapshot(
            run_id=run_id,
            run_status=run["status"],
            envelopes=failure_envelopes,
            steps=steps,
            ledger=ledger,
            approvals=approvals,
            events=all_events,
            cost_records=cost_records,
        )
        failure_replay_plan = FailureReplayPlanner().plan(run_id=run_id, envelopes=failure_envelopes, ledger=ledger, events=all_events)
        failure_alerts = FailureAlertEvaluator().evaluate(run_id=run_id, envelopes=failure_envelopes, replay_plan=failure_replay_plan, cost_records=cost_records)

        summary = {
            "failed_step_count": len(failed_steps),
            "retry_scheduled_step_count": len(retry_scheduled_steps),
            "waiting_human_step_count": len(waiting_human_steps),
            "pending_verification_count": len(pending_verification),
            "pending_approval_count": len(pending_approvals),
            "failure_event_count": len(events),
            "root_cause_count": len(root_causes),
            "failure_envelope_count": len(failure_envelopes),
            "failure_lifecycle_event_count": len(failure_lifecycle.get("events", [])),
            "failure_alert_count": failure_alerts.get("alert_count", 0),
            "unsafe_replay_side_effect_count": failure_replay_plan.get("unsafe_side_effect_count", 0),
            "terminal_failure_count": sum(1 for item in failure_envelopes if item.get("status") == "terminal"),
            "recoverable_failure_count": sum(1 for item in failure_envelopes if item.get("recoverability") in {"auto_retry", "recoverable", "manual_verification", "human_required"}),
        }
        failure_export = FailureExportMapper().export(
            run_id=run_id,
            run_status=run["status"],
            summary=summary,
            envelopes=failure_envelopes,
            lifecycle=failure_lifecycle,
            causal_graph=failure_causal_graph,
            replay_plan=failure_replay_plan,
            alerts=failure_alerts,
        )
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
            failure_lifecycle=failure_lifecycle,
            failure_causal_graph=failure_causal_graph,
            failure_replay_plan=failure_replay_plan,
            failure_alerts=failure_alerts,
            failure_export=failure_export,
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
    if event_type in {"model_call_failed"}:
        return "model"
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


def _merge_refs(*values: Any) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if not isinstance(value, list):
            continue
        for ref in value:
            if not isinstance(ref, dict):
                continue
            kind = ref.get("kind")
            raw = ref.get("value")
            if kind is None or raw is None:
                continue
            key = (str(kind), str(raw))
            if key in seen:
                continue
            seen.add(key)
            merged.append({"kind": key[0], "value": key[1]})
    return merged


def _dedupe_envelopes(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for envelope in envelopes:
        failure_id = str(envelope.get("failure_id") or "")
        if failure_id and failure_id not in seen:
            seen.add(failure_id)
            deduped.append(envelope)
    return deduped


def _dedupe_lifecycle_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for event in events:
        key = (str(event.get("stage") or ""), str(event.get("failure_id") or ""), str(event.get("event_seq") or ""))
        if key in seen:
            continue
        seen.add(key)
        rows.append(event)
    return rows


def _lifecycle_sort_key(row: dict[str, Any]) -> tuple[float, int, str, str]:
    occurred_at = row.get("occurred_at")
    try:
        ts = float(occurred_at)
    except (TypeError, ValueError):
        ts = 0.0
    seq = row.get("event_seq")
    try:
        seq_int = int(seq)
    except (TypeError, ValueError):
        seq_int = 0
    return (ts, seq_int, str(row.get("stage") or ""), str(row.get("failure_id") or ""))


def _recovery_message(envelope: dict[str, Any]) -> str:
    if envelope.get("status") == "unknown_side_effect" or envelope.get("recoverability") == "manual_verification":
        return "manual side-effect verification required"
    if envelope.get("status") == "waiting_human" or envelope.get("recoverability") == "human_required":
        return "human approval required before resume"
    return "recovery scheduled"


def _node_key(kind: str, value: Any) -> str:
    return f"{kind}:{_slug(value if value is not None and value != '' else 'unknown')}"


def _extract_envelopes(value: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ["failure_envelopes", "envelopes"]:
        items = value.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    nested = value.get("failure_export")
    if isinstance(nested, dict):
        return _extract_envelopes(nested)
    return []


def _failure_signature(envelope: dict[str, Any]) -> str:
    parts = [
        envelope.get("category"),
        envelope.get("status"),
        envelope.get("owner"),
        envelope.get("step_id"),
        envelope.get("tool_name"),
        envelope.get("event_type"),
        envelope.get("message"),
    ]
    return "|".join(str(part or "") for part in parts)
