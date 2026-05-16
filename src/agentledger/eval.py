from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .diff import EvidenceDiffer


@dataclass(frozen=True)
class EvidenceCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class EvidenceCheckReport:
    passed: bool
    checks: list[EvidenceCheck]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": [check.to_dict() for check in self.checks], "metadata": self.metadata}


class EvidenceRegressionRunner:
    """Side-effect-free evidence checks for runtime correctness and reliability invariants.

    This is not a full eval system. It consumes AgentLedger evidence bundles
    and never calls model providers, tools, judges, datasets, or external
    services. Full eval systems should integrate through adapters.
    """

    def evaluate(self, evidence: dict[str, Any], *, max_total_usd: float | None = None) -> EvidenceCheckReport:
        summary = evidence.get("summary", {})
        steps = evidence.get("steps", [])
        ledger = evidence.get("tool_ledger", [])
        media_artifacts = evidence.get("media_artifacts", [])
        stream_checkpoints = evidence.get("stream_checkpoints", [])
        checks = [
            EvidenceCheck(
                name="no_failed_steps",
                passed=not summary.get("has_failed_steps", False),
                detail="all steps completed or remain non-failed",
            ),
            EvidenceCheck(
                name="no_pending_verification",
                passed=not summary.get("has_pending_verification", False),
                detail="no side effect is waiting for human/external verification",
            ),
            EvidenceCheck(
                name="completed_steps_have_events",
                passed=all(self._has_completion_event(evidence, step.get("step_id")) for step in steps if step.get("status") == "completed"),
                detail="each completed step has a step_completed event",
            ),
            EvidenceCheck(
                name="managed_side_effects_are_ledgered",
                passed=all(row.get("status") in {"SUCCEEDED", "FAILED_NO_EFFECT", "PENDING_VERIFICATION", "COMPENSATED", "RUNNING", "RESERVED"} for row in ledger),
                detail="every ledger row has a known status",
            ),
            EvidenceCheck(
                name="media_artifacts_have_refs",
                passed=all(row.get("kind") and (row.get("uri") or row.get("content_ref") or row.get("blob_ref")) for row in media_artifacts),
                detail="media artifacts have kind and durable refs",
            ),
            EvidenceCheck(
                name="stream_checkpoints_have_offsets",
                passed=all(row.get("stream_id") and row.get("consumer_id") and row.get("offset") is not None for row in stream_checkpoints),
                detail="stream checkpoints have stream, consumer, and offset",
            ),
        ]
        if max_total_usd is not None:
            total = float(summary.get("cost_summary", {}).get("total_usd", 0.0))
            checks.append(EvidenceCheck(name="max_total_usd", passed=total <= max_total_usd, detail=f"total_usd={total}, limit={max_total_usd}"))
        return EvidenceCheckReport(passed=all(check.passed for check in checks), checks=checks)

    def evaluate_regression(
        self,
        golden: dict[str, Any],
        current: dict[str, Any],
        *,
        require_same_final_state: bool = True,
        require_same_event_types: bool = True,
        require_same_tool_ledger_statuses: bool = True,
        require_same_media_artifacts: bool = True,
        require_same_stream_checkpoints: bool = True,
        max_total_usd_delta: float | None = None,
    ) -> EvidenceCheckReport:
        diff = EvidenceDiffer().compare(golden, current).to_dict()
        changes = diff["changes"]
        checks: list[EvidenceCheck] = []
        if require_same_final_state:
            changed_count = changes["final_state"]["changed_count"]
            checks.append(EvidenceCheck("final_state_regression", changed_count == 0, f"changed_final_state_keys={changed_count}"))
        if require_same_event_types:
            changed_count = changes["event_types"]["changed_count"]
            checks.append(EvidenceCheck("event_type_regression", changed_count == 0, f"changed_event_type_positions={changed_count}"))
        if require_same_tool_ledger_statuses:
            changed_count = changes["tool_ledger"]["changed_count"]
            checks.append(EvidenceCheck("tool_ledger_status_regression", changed_count == 0, f"changed_ledger_status_positions={changed_count}"))
        if require_same_media_artifacts:
            changed_count = changes["media_artifacts"]["changed_count"]
            checks.append(EvidenceCheck("media_artifact_regression", changed_count == 0, f"changed_media_artifacts={changed_count}"))
        if require_same_stream_checkpoints:
            changed_count = changes["stream_checkpoints"]["changed_count"]
            checks.append(EvidenceCheck("stream_checkpoint_regression", changed_count == 0, f"changed_stream_checkpoints={changed_count}"))
        if max_total_usd_delta is not None:
            left_total = float(golden.get("summary", {}).get("cost_summary", {}).get("total_usd", 0.0))
            right_total = float(current.get("summary", {}).get("cost_summary", {}).get("total_usd", 0.0))
            delta = right_total - left_total
            checks.append(EvidenceCheck("max_total_usd_delta", delta <= max_total_usd_delta, f"total_usd_delta={delta}, limit={max_total_usd_delta}"))
        return EvidenceCheckReport(passed=all(check.passed for check in checks), checks=checks, metadata={"diff": diff})

    def _has_completion_event(self, evidence: dict[str, Any], step_id: str | None) -> bool:
        if step_id is None:
            return False
        return any(event.get("type") == "step_completed" and event.get("step_id") == step_id for event in evidence.get("events", []))


# Deprecated compatibility aliases. These names are intentionally not used in
# docs because full eval systems live outside runtime-core, but keeping the
# aliases avoids breaking pre-1.0 users of the side-effect-free evidence checks.
EvalCheck = EvidenceCheck
EvalReport = EvidenceCheckReport
EvalRunner = EvidenceRegressionRunner
