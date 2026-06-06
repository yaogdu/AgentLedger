from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import EvidenceExporter, InspectorDataSource, Runtime, ToolSpec


def create_ticket(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": "TICKET-1001",
        "title": args["title"],
        "priority": args.get("priority", "normal"),
    }


async def support_agent(ctx: Any, state: dict[str, Any]) -> None:
    ticket = await ctx.call_tool(
        "ticket.create",
        {"title": "Review high-risk agent action", "priority": "high"},
    )
    ctx.write_state_patch("ticket", ticket)


def compact_view(report_data: dict[str, Any]) -> dict[str, Any]:
    """Build a small custom view from the stable Inspector read model."""

    return {
        "schema_version": report_data["schema_version"],
        "run_id": report_data["run"]["run_id"],
        "status": report_data["run"]["status"],
        "risk_flags": report_data["risk_flags"],
        "tool_calls": [
            {
                "tool_name": row.get("tool_name"),
                "status": row.get("status"),
                "external_id": row.get("external_id"),
            }
            for row in report_data["tool_ledger"]
        ],
    }


def main() -> None:
    workdir = Path(tempfile.mkdtemp(prefix="agentledger-inspector-demo-"))
    root = workdir / ".agentledger"
    runtime = Runtime.local(root)
    runtime.registry.register(
        ToolSpec(
            name="ticket.create",
            func=create_ticket,
            side_effect="external_write",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string"},
                },
                "required": ["title"],
            },
        )
    )

    run_id, _ = runtime.create_run(initial_state={})
    ok = asyncio.run(runtime.run_once(support_agent, run_id=run_id, agent_role="SupportAgent"))
    if not ok:
        raise RuntimeError(f"example run failed: {run_id}")

    inspector = InspectorDataSource()
    runtime_report = inspector.from_sqlite(
        db_path=root / "state.db",
        blob_root=root / "blobs",
        run_id=run_id,
    )
    json_path = workdir / "inspector.json"
    html_path = workdir / "inspector.html"
    runtime_report.write(json_path)
    runtime_report.write_html(html_path)

    evidence_dir = workdir / "evidence" / run_id
    EvidenceExporter(store=runtime.store, blobs=runtime.blobs).export(run_id).write_dir(evidence_dir)
    evidence_report = inspector.from_evidence_path(evidence_dir)

    payload = {
        "run_id": run_id,
        "runtime_root": str(root),
        "sqlite_db": str(root / "state.db"),
        "evidence_dir": str(evidence_dir),
        "inspector_json": str(json_path),
        "inspector_html": str(html_path),
        "runtime_schema": runtime_report.to_dict()["schema_version"],
        "evidence_schema": evidence_report.to_dict()["schema_version"],
        "custom_view": compact_view(runtime_report.to_dict()),
        "note": "Use read-only DB credentials and keep access control outside Inspector.",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

