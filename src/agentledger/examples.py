from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import AgentContext
from .runtime import Runtime, SimulatedCrash
from .tools import ToolSpec


def register_fake_github(runtime: Runtime, external_path: Path) -> None:
    external_path.parent.mkdir(parents=True, exist_ok=True)
    if not external_path.exists():
        external_path.write_text("[]", encoding="utf-8")

    def create_issue(args: dict[str, Any]) -> dict[str, Any]:
        issues = json.loads(external_path.read_text(encoding="utf-8"))
        issue_id = f"ISSUE-{len(issues) + 1}"
        issue = {"external_id": issue_id, "title": args["title"], "body": args.get("body", "")}
        issues.append(issue)
        external_path.write_text(json.dumps(issues, indent=2), encoding="utf-8")
        return issue

    runtime.registry.register(
        ToolSpec(
            name="github.create_issue",
            func=create_issue,
            side_effect="external_write",
            risk_level="medium",
            idempotency_required=True,
            input_schema={"type": "object", "required": ["title"]},
        )
    )


async def crash_once_agent(ctx: AgentContext, state: dict[str, Any]) -> None:
    issue = await ctx.call_tool(
        "github.create_issue",
        {
            "title": "Crash recovery bug",
            "body": "Created by AgentLedger demo",
            "_logical_operation": "create-crash-recovery-issue",
        },
    )
    if not state.get("crashed_once"):
        # The external issue is already created and ledgered, but state is not committed.
        raise SimulatedCrash("after external side effect before state commit")
    ctx.write_state_patch("issue", issue)


async def recovery_agent(ctx: AgentContext, state: dict[str, Any]) -> None:
    issue = await ctx.call_tool(
        "github.create_issue",
        {
            "title": "Crash recovery bug",
            "body": "Created by AgentLedger demo",
            "_logical_operation": "create-crash-recovery-issue",
        },
    )
    ctx.write_state_patch("issue", issue)
    ctx.write_state_patch("recovered", True)
