from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from agentledger import AgentContext, EvidenceExporter, ReplayEngine, Runtime, SimulatedCrash, ToolSpec


def _read_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


async def main() -> None:
    root = Path(os.environ["AGENTLEDGER_DEMO_ROOT"]) if "AGENTLEDGER_DEMO_ROOT" in os.environ else Path(tempfile.mkdtemp(prefix="agentledger-three-minute-"))
    external_tickets = root / "external_tickets.json"
    crash_marker = root / "worker_crashed_once"
    tool_executions = {"ticket.create": 0}
    rt = Runtime.local(root)

    def create_ticket(args: dict[str, Any]) -> dict[str, Any]:
        tool_executions["ticket.create"] += 1
        tickets = _read_json(external_tickets)
        ticket = {"external_id": f"TICKET-{len(tickets) + 1}", "title": args["title"]}
        external_tickets.write_text(json.dumps([*tickets, ticket], indent=2), encoding="utf-8")  # agentledger: ignore-boundary - demo external system behind a runtime-managed tool
        return ticket

    rt.registry.register(
        ToolSpec(
            name="ticket.create",
            func=create_ticket,
            side_effect="external_write",
            idempotency_required=True,
            input_schema={"type": "object", "required": ["title"]},
        )
    )

    async def support_agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
        ticket = await ctx.call_tool(
            "ticket.create",
            {"title": "Investigate failed payment", "_logical_operation": "open-payment-ticket"},
        )
        if not crash_marker.exists():
            crash_marker.write_text("crashed after tool success, before state commit\n", encoding="utf-8")  # agentledger: ignore-boundary - deterministic crash marker for the demo
            raise SimulatedCrash("after external ticket create, before state commit")
        ctx.write_state_patch("ticket", ticket)
        ctx.write_state_patch("recovered", True)

    run_id, _ = rt.create_run(initial_state={})
    first_ok = await rt.run_once(support_agent, run_id=run_id, worker_id="worker-before-crash", agent_role="SupportAgent")
    second_ok = await rt.run_once(support_agent, run_id=run_id, worker_id="worker-after-restart", agent_role="SupportAgent")
    evidence_path = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(root / "evidence")
    replay = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)

    ledger = [
        {key: row[key] for key in ("tool_name", "status", "external_id", "idempotency_key")}
        for row in rt.store.ledger(run_id)
    ]
    print(
        json.dumps(
            {
                "run_id": run_id,
                "first_attempt_ok": first_ok,
                "second_attempt_ok": second_ok,
                "external_ticket_count": len(_read_json(external_tickets)),
                "actual_tool_executions": tool_executions["ticket.create"],
                "tool_ledger": ledger,
                "final_state": rt.store.final_state(run_id),
                "replay": {
                    "safe": replay.replay_safe,
                    "event_count": replay.event_count,
                    "tool_call_count": replay.tool_call_count,
                },
                "demo_root": str(root),
                "evidence_dir": str(evidence_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
