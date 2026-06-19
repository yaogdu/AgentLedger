from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReviewCheck:
    name: str
    passed: bool
    severity: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "severity": self.severity, "detail": self.detail}


@dataclass(frozen=True)
class AdversarialReviewReport:
    passed: bool
    run_id: str | None
    checks: list[ReviewCheck]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "run_id": self.run_id,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata,
        }


class AdversarialReviewRunner:
    """Read-only pre-release checklist over an evidence bundle."""

    FAILURE_EVENTS = {"error_raised", "step_failed", "model_call_failed", "tool_call_failed", "tool_call_blocked"}
    HIGH_RISK_LEVELS = {"high", "destructive", "sensitive"}

    def evaluate(self, evidence: dict[str, Any], *, max_total_usd: float | None = None) -> AdversarialReviewReport:
        summary = evidence.get("summary", {})
        events = evidence.get("events", [])
        steps = evidence.get("steps", [])
        ledger = evidence.get("tool_ledger", [])
        approvals = evidence.get("approval_requests", [])
        artifacts = evidence.get("artifacts", [])
        media_artifacts = evidence.get("media_artifacts", [])
        stream_checkpoints = evidence.get("stream_checkpoints", [])
        cost_summary = summary.get("cost_summary", {})

        checks = [
            ReviewCheck("no_failed_steps", not summary.get("has_failed_steps", False), "blocker", "no step is in failed status"),
            ReviewCheck("no_pending_verification", not summary.get("has_pending_verification", False), "blocker", "no side effect is pending verification"),
            ReviewCheck("no_pending_approvals", not summary.get("has_pending_approvals", False), "blocker", "no approval request is still pending"),
            ReviewCheck("completed_steps_have_completion_events", self._completed_steps_have_events(steps, events), "blocker", "completed steps have step_completed events"),
            ReviewCheck("ledger_statuses_known", self._ledger_statuses_known(ledger), "blocker", "Tool Ledger rows use known statuses"),
            ReviewCheck("event_sequence_contiguous", self._event_sequence_contiguous(events), "blocker", "event sequence has no gaps"),
            ReviewCheck("artifacts_have_blob_refs", self._artifacts_have_blob_refs(artifacts), "warning", "artifacts have blob refs and hashes"),
            ReviewCheck("media_artifacts_have_refs", self._media_artifacts_have_refs(media_artifacts), "blocker", "media artifacts have kind and durable refs"),
            ReviewCheck("stream_checkpoints_have_offsets", self._stream_checkpoints_have_offsets(stream_checkpoints), "blocker", "stream checkpoints have stream, consumer, and offset"),
            ReviewCheck("high_risk_approvals_decided", self._high_risk_approvals_decided(approvals), "blocker", "high-risk approval requests are decided"),
            ReviewCheck("no_blocking_failure_events", not any(event.get("type") in self.FAILURE_EVENTS for event in events), "warning", "no blocking failure events are present"),
        ]
        if max_total_usd is not None:
            total = float(cost_summary.get("total_usd", 0.0) or 0.0)
            checks.append(ReviewCheck("max_total_usd", total <= max_total_usd, "blocker", f"total_usd={total}, limit={max_total_usd}"))

        passed = all(check.passed for check in checks if check.severity == "blocker")
        return AdversarialReviewReport(
            passed=passed,
            run_id=evidence.get("run", {}).get("run_id"),
            checks=checks,
            metadata={
                "event_count": len(events),
                "step_count": len(steps),
                "tool_ledger_count": len(ledger),
                "approval_count": len(approvals),
                "artifact_count": len(artifacts),
                "media_artifact_count": len(media_artifacts),
                "stream_checkpoint_count": len(stream_checkpoints),
                "cost_summary": cost_summary,
            },
        )

    def _completed_steps_have_events(self, steps: list[dict[str, Any]], events: list[dict[str, Any]]) -> bool:
        completed = [step.get("step_id") for step in steps if step.get("status") == "completed"]
        completed_events = {event.get("step_id") for event in events if event.get("type") == "step_completed"}
        return all(step_id in completed_events for step_id in completed)

    def _ledger_statuses_known(self, ledger: list[dict[str, Any]]) -> bool:
        known = {"SUCCEEDED", "FAILED_NO_EFFECT", "PENDING_VERIFICATION", "COMPENSATED", "RUNNING", "RESERVED"}
        return all(row.get("status") in known for row in ledger)

    def _event_sequence_contiguous(self, events: list[dict[str, Any]]) -> bool:
        seqs = [int(event.get("seq", 0)) for event in events]
        return seqs == list(range(1, len(seqs) + 1))

    def _artifacts_have_blob_refs(self, artifacts: list[dict[str, Any]]) -> bool:
        return all(row.get("blob_ref") and row.get("blob_hash") for row in artifacts)

    def _media_artifacts_have_refs(self, media_artifacts: list[dict[str, Any]]) -> bool:
        return all(row.get("kind") and (row.get("uri") or row.get("content_ref") or row.get("blob_ref")) for row in media_artifacts)

    def _stream_checkpoints_have_offsets(self, stream_checkpoints: list[dict[str, Any]]) -> bool:
        return all(row.get("stream_id") and row.get("consumer_id") and row.get("offset") is not None for row in stream_checkpoints)

    def _high_risk_approvals_decided(self, approvals: list[dict[str, Any]]) -> bool:
        high_risk = [row for row in approvals if row.get("risk_level") in self.HIGH_RISK_LEVELS]
        return all(row.get("status") in {"APPROVED", "DENIED"} for row in high_risk)
