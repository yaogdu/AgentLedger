from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import InMemoryMCPToolServer, MCPToolAdapter, Runtime


def _compact_approvals(rt: Runtime, run_id: str) -> list[dict[str, Any]]:
    return [
        {key: row[key] for key in ("approval_id", "tool_name", "risk_level", "status", "reason")}
        for row in rt.store.approval_requests(run_id)
    ]


async def main() -> None:
    external_actions: list[dict[str, Any]] = []

    def create_pr(_name: str, args: dict[str, Any]) -> dict[str, Any]:
        action = {"external_id": f"PR-{len(external_actions) + 1}", "title": args["title"]}
        external_actions.append(action)
        return action

    async def agent(ctx: Any, _state: dict[str, Any]) -> None:
        result = await ctx.call_tool(
            "mcp.github.create_pr",
            {"title": "Update runtime docs", "_logical_operation": "docs-pr"},
        )
        ctx.write_state_patch("pull_request", result)

    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        tool_server = InMemoryMCPToolServer()
        tool_server.add_tool(
            {
                "name": "mcp.github.create_pr",
                "inputSchema": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string", "minLength": 1}},
                    "additionalProperties": True,
                },
                "annotations": {
                    "side_effect": "external_write",
                    "risk_level": "high",
                    "idempotency_required": True,
                    "approval_required": True,
                    "sandbox_required": True,
                    "sandbox_policy": {"network": "deny", "filesystem": "read-only"},
                },
            },
            create_pr,
        )
        MCPToolAdapter(tool_server.call_tool).register_all(rt.registry, tool_server.list_tools())

        run_id, _ = rt.create_run(initial_state={})
        first_ok = await rt.run_once(agent, run_id=run_id, agent_role="MCPAgent")
        approval = rt.store.approval_requests(run_id)[0]
        rt.store.approve_request(approval["approval_id"], approver="maintainer", reason="demo approval")
        second_ok = await rt.run_once(agent, run_id=run_id, agent_role="MCPAgent")

        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "first_attempt_waited_for_approval": not first_ok,
                    "second_attempt_ok": second_ok,
                    "approvals": _compact_approvals(rt, run_id),
                    "external_action_count": len(external_actions),
                    "tool_manifest": rt.registry.manifest(),
                    "final_state": rt.store.final_state(run_id),
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
