from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentledger import AgentContext, EvidenceExporter, Runtime, ToolSpec
from agentledger.failure import FailureAttributionReporter
from agentledger.inspector import InspectorDataSource
from agentledger.replay import ReplayEngine


@dataclass(frozen=True)
class FakeOpenAIResponse:
    provider: str
    model: str
    output_text: str
    tool_call: dict[str, Any]
    usage: dict[str, int]


class FakeOpenAIAgentsRunner:
    """Dependency-free facade that models an SDK-style agent runner."""

    async def arun(self, payload: dict[str, Any]) -> FakeOpenAIResponse:
        return FakeOpenAIResponse(
            provider="openai-agents-sdk-style",
            model="local-fake-agent-model",
            output_text="Create a customer support ticket after approval.",
            tool_call={
                "name": "ticket.create",
                "arguments": {
                    "customer": payload["customer"],
                    "summary": payload["summary"],
                    "_logical_operation": f"create-ticket:{payload['customer']}",
                },
            },
            usage={"input_tokens": 91, "output_tokens": 34, "total_tokens": 125},
        )


def _compact_approvals(rt: Runtime, run_id: str) -> list[dict[str, Any]]:
    return [
        {key: row[key] for key in ("approval_id", "tool_name", "risk_level", "status", "reason")}
        for row in rt.store.approval_requests(run_id)
    ]


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
        root = Path(tempfile.mkdtemp(prefix="agentledger-openai-agents-"))
    root.mkdir(parents=True, exist_ok=True)

    external_actions: list[dict[str, Any]] = []
    rt = Runtime.local(root / ".agentledger")
    runner = FakeOpenAIAgentsRunner()

    def create_ticket(args: dict[str, Any]) -> dict[str, Any]:
        action = {
            "external_id": f"TICKET-{len(external_actions) + 1}",
            "customer": args["customer"],
            "summary": args["summary"],
        }
        external_actions.append(action)
        return action

    rt.registry.register(
        ToolSpec(
            name="ticket.create",
            func=create_ticket,
            description="Create an external support ticket.",
            side_effect="external_write",
            risk_level="high",
            idempotency_required=True,
            approval_required=True,
            input_schema={
                "type": "object",
                "required": ["customer", "summary"],
                "properties": {
                    "customer": {"type": "string", "minLength": 1},
                    "summary": {"type": "string", "minLength": 1},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": True,
            },
        )
    )

    run_id, _ = rt.create_run(
        initial_state={
            "agent_run_id": "openai-agents-sdk-style-approval-replay",
            "customer": "acme",
            "summary": "Priority support escalation",
        }
    )

    async def agent(ctx: AgentContext, state: dict[str, Any]) -> None:
        approved = any(row["status"] == "APPROVED" and row["tool_name"] == "ticket.create" for row in ctx.store.approval_requests(ctx.run_id))
        archived = _latest_tool_proposal(ctx, "ticket.create") if approved else None
        resumed_from_evidence = archived is not None
        if archived is not None:
            proposal_ref, tool_args = archived
        else:
            request = {
                "provider": "openai-agents-sdk-style",
                "model": "local-fake-agent-model",
                "messages": [{"role": "user", "content": state["summary"]}],
                "tools": [spec.to_openai_tool() for spec in rt.registry.list()],
            }
            response = await runner.arun({"customer": state["customer"], "summary": state["summary"]})
            response_payload = asdict(response)
            refs = ctx.record_model_call(
                provider=response.provider,
                model=response.model,
                request=request,
                response=response_payload,
                usage=response.usage,
                total_usd=0.0042,
                metadata={"framework": "openai-agents-sdk-style", "network": "disabled"},
            )
            tool_call = response.tool_call
            tool_args = dict(tool_call["arguments"])
            proposal_ref = ctx.record_tool_call_proposal(
                tool_name=tool_call["name"],
                arguments=tool_args,
                provider=response.provider,
                model=response.model,
                model_call_ref=refs["request_ref"],
                confidence=0.89,
                reason="SDK-style runner proposed a high-risk ticket tool call.",
                metadata={"framework": "openai-agents-sdk-style"},
            )
        ticket = await ctx.call_tool("ticket.create", tool_args)
        ctx.write_state_patch(
            "ticket",
            {
                "proposal_ref": proposal_ref,
                "resumed_from_evidence": resumed_from_evidence,
                "result": ticket,
            },
        )

    try:
        first_ok = await rt.run_once(agent, run_id=run_id, agent_role="OpenAIAgent")
        approval = rt.store.approval_requests(run_id)[0]
        rt.store.approve_request(approval["approval_id"], approver="maintainer", reason="demo approval")
        second_ok = await rt.run_once(agent, run_id=run_id, agent_role="OpenAIAgent")

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
            "ok": second_ok,
            "run_id": run_id,
            "first_attempt_waited_for_approval": not first_ok,
            "second_attempt_ok": second_ok,
            "model_call_count": inspector["summary"]["model_call_count"],
            "tool_call_proposal_count": inspector["summary"]["tool_call_proposal_count"],
            "approval_count": len(_compact_approvals(rt, run_id)),
            "approvals": _compact_approvals(rt, run_id),
            "tool_ledger": _compact_ledger(rt, run_id),
            "external_action_count": len(external_actions),
            "resume_used_archived_tool_proposal": bool(rt.store.final_state(run_id)["ticket"]["resumed_from_evidence"]),
            "replay": {
                "safe": replay.replay_safe,
                "event_count": replay.event_count,
                "tool_call_count": replay.tool_call_count,
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
