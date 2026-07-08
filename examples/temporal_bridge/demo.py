from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentledger import AgentContext, EvidenceExporter, Runtime, SimulatedCrash, ToolSpec
from agentledger.failure import FailureAttributionReporter
from agentledger.inspector import InspectorDataSource
from agentledger.replay import ReplayEngine


@dataclass
class TemporalStyleActivityContext:
    workflow_id: str
    workflow_run_id: str
    activity_id: str
    attempt: int

    def metadata(self) -> dict[str, Any]:
        return {
            "external_workflow_id": self.workflow_id,
            "external_workflow_run_id": self.workflow_run_id,
            "external_activity_id": self.activity_id,
            "external_activity_attempt": self.attempt,
        }


@dataclass
class TemporalStyleWorkflowFacade:
    workflow_id: str = "wf-agent-review-001"
    workflow_run_id: str = "wf-run-local-001"
    activity_id: str = "activity-run-agent-node"
    attempts: list[dict[str, Any]] = field(default_factory=list)

    async def run_activity_with_retry(self, activity: Any, *, max_attempts: int = 2) -> dict[str, Any]:
        last_result: dict[str, Any] | None = None
        for attempt in range(1, max_attempts + 1):
            ctx = TemporalStyleActivityContext(
                workflow_id=self.workflow_id,
                workflow_run_id=self.workflow_run_id,
                activity_id=self.activity_id,
                attempt=attempt,
            )
            last_result = await activity(ctx)
            self.attempts.append({"attempt": attempt, "ok": bool(last_result["activity_ok"]), "run_id": last_result["run_id"]})
            if last_result["activity_ok"]:
                return last_result
        assert last_result is not None
        return last_result


def _compact_ledger(rt: Runtime, run_id: str) -> list[dict[str, Any]]:
    return [
        {key: row[key] for key in ("tool_name", "status", "external_id", "idempotency_key")}
        for row in rt.store.ledger(run_id)
    ]


def _latest_tool_proposal(ctx: AgentContext, tool_name: str) -> tuple[str, dict[str, Any]] | None:
    for row in reversed(list(ctx.store.events(ctx.run_id))):
        if row["type"] != "tool_call_proposed" or not row["payload_ref"]:
            continue
        payload = ctx.blobs.get_json(row["payload_ref"])
        if payload.get("tool") == tool_name:
            return row["payload_ref"], dict(payload.get("args") or {})
    return None


async def run_demo(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        root = Path(tempfile.mkdtemp(prefix="agentledger-temporal-bridge-"))
    root.mkdir(parents=True, exist_ok=True)

    external_actions: list[dict[str, Any]] = []
    rt = Runtime.local(root / ".agentledger")
    workflow = TemporalStyleWorkflowFacade()
    run_id: str | None = None

    def create_record(args: dict[str, Any]) -> dict[str, Any]:
        action = {
            "external_id": f"CASE-{len(external_actions) + 1}",
            "title": args["title"],
            "workflow_id": args["workflow_id"],
        }
        external_actions.append(action)
        return action

    rt.registry.register(
        ToolSpec(
            name="case.create",
            func=create_record,
            description="Create an external review case.",
            side_effect="external_write",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["title", "workflow_id"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "workflow_id": {"type": "string", "minLength": 1},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": True,
            },
        )
    )

    async def agent(ctx: AgentContext, state: dict[str, Any]) -> None:
        workflow_metadata = state["workflow"]
        archived = _latest_tool_proposal(ctx, "case.create") if state.get("crashed_once") else None
        resumed_from_evidence = archived is not None
        if archived is not None:
            proposal_ref, tool_args = archived
        else:
            tool_args = {
                "title": state["title"],
                "workflow_id": workflow_metadata["external_workflow_id"],
                "_logical_operation": f"case:{workflow_metadata['external_workflow_id']}",
            }
            ctx.record_model_call(
                provider="temporal-style-local-facade",
                model="activity-planner",
                request={
                    "messages": [{"role": "user", "content": "create review case"}],
                    "workflow": workflow_metadata,
                },
                response={
                    "output_text": "Create one external review case.",
                    "tool_call": "case.create",
                },
                usage={"input_tokens": 37, "output_tokens": 13, "total_tokens": 50},
                total_usd=0.0017,
                metadata={"execution_backend": "temporal-style-local-facade", **workflow_metadata},
            )
            proposal_ref = ctx.record_tool_call_proposal(
                tool_name="case.create",
                arguments=tool_args,
                provider="temporal-style-local-facade",
                model="activity-planner",
                reason="activity-local model proposed a case creation tool.",
                metadata=workflow_metadata,
            )
        case = await ctx.call_tool("case.create", tool_args)
        if not state.get("crashed_once"):
            raise SimulatedCrash("activity crashed after side effect before workflow-level success")
        ctx.write_state_patch("case", {"result": case, "proposal_ref": proposal_ref, "resumed_from_evidence": resumed_from_evidence})
        ctx.write_state_patch("workflow_completed", True)

    async def activity(activity_ctx: TemporalStyleActivityContext) -> dict[str, Any]:
        nonlocal run_id
        if run_id is None:
            run_id, _ = rt.create_run(
                initial_state={
                    "agent_run_id": "temporal-bridge-retry-safety",
                    "title": "Review high-risk customer request",
                    "crashed_once": False,
                    "workflow": activity_ctx.metadata(),
                },
                retry_policy={"max_attempts": 3},
            )
        else:
            rt.store.apply_system_state_patch(
                run_id=run_id,
                patch={"crashed_once": True, "workflow": activity_ctx.metadata()},
                reason="Temporal-style retry observed previous activity crash",
            )
        ok = await rt.run_once(
            agent,
            run_id=run_id,
            worker_id=f"temporal-worker-{activity_ctx.attempt}",
            agent_role="TemporalActivityAgent",
        )
        return {"activity_ok": ok, "run_id": run_id, "workflow": activity_ctx.metadata()}

    try:
        activity_result = await workflow.run_activity_with_retry(activity, max_attempts=2)
        assert run_id is not None
        evidence_dir = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(root / "evidence")
        inspector_html = InspectorDataSource().from_runtime_store(
            store=rt.store,
            blobs=rt.blobs,
            run_id=run_id,
            include_payloads=True,
        ).write_html(root / "inspector.html")
        replay = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)
        inspector = InspectorDataSource().from_runtime_store(store=rt.store, blobs=rt.blobs, run_id=run_id).to_dict()
        failure_report = FailureAttributionReporter(rt.store).report(run_id).to_dict()
        return {
            "ok": bool(activity_result["activity_ok"]),
            "run_id": run_id,
            "workflow": {
                "workflow_id": workflow.workflow_id,
                "workflow_run_id": workflow.workflow_run_id,
                "activity_id": workflow.activity_id,
                "attempts": workflow.attempts,
            },
            "activity_attempt_count": len(workflow.attempts),
            "external_action_count": len(external_actions),
            "actual_tool_executions": len(external_actions),
            "retry_used_archived_tool_proposal": bool(rt.store.final_state(run_id)["case"]["resumed_from_evidence"]),
            "model_call_count": inspector["summary"]["model_call_count"],
            "tool_call_proposal_count": inspector["summary"]["tool_call_proposal_count"],
            "tool_ledger": _compact_ledger(rt, run_id),
            "replay": {
                "safe": replay.replay_safe,
                "event_count": replay.event_count,
                "tool_call_count": replay.tool_call_count,
                "does_not_start_new_workflow": True,
            },
            "failure_summary": failure_report["summary"],
            "evidence_dir": str(evidence_dir),
            "inspector_html": str(inspector_html),
            "final_state": rt.store.final_state(run_id),
        }
    finally:
        rt.close()


async def main() -> None:
    print(json.dumps(await run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
