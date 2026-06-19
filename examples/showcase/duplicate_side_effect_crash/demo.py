from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from agentledger import AgentContext, EvidenceExporter, ReplayEngine, Runtime, SimulatedCrash, ToolSpec
from agentledger.inspector import InspectorDataSource


def _read_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _append_email(path: Path, *, subject: str) -> dict[str, Any]:
    emails = _read_json(path)
    email = {"message_id": f"EMAIL-{len(emails) + 1}", "subject": subject}
    path.write_text(json.dumps([*emails, email], indent=2, sort_keys=True), encoding="utf-8")
    return email


def _reset_demo_root(root: Path) -> None:
    marker = root / ".agentledger_showcase_demo_root"
    generated_names = {
        ".agentledger",
        "evidence",
        "naive_outbox.json",
        "agentledger_outbox.json",
        "crashed_once",
        "runs.html",
        "inspector.html",
        marker.name,
    }
    if not marker.exists():
        unexpected = sorted(path.name for path in root.iterdir() if path.name not in generated_names)
        if unexpected:
            raise RuntimeError(
                f"refusing to reset non-empty unmarked showcase directory: {root}. "
                "Choose an empty AGENTLEDGER_SHOWCASE_ROOT or remove the directory yourself."
            )
        marker.write_text("AgentLedger duplicate side-effect showcase output\n", encoding="utf-8")

    for name in generated_names - {marker.name}:
        path = root / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _naive_retry(root: Path) -> dict[str, Any]:
    outbox = root / "naive_outbox.json"
    crashed_once = {"value": False}

    def agent() -> None:
        _append_email(outbox, subject="Payment failed")
        if not crashed_once["value"]:
            crashed_once["value"] = True
            raise RuntimeError("worker crashed after email send, before checkpoint")

    first_error = None
    try:
        agent()
    except RuntimeError as exc:
        first_error = str(exc)
    agent()
    return {
        "first_error": first_error,
        "external_email_count": len(_read_json(outbox)),
        "risk": "duplicate side effect",
    }


async def _agentledger_retry(root: Path) -> dict[str, Any]:
    runtime_root = root / ".agentledger"
    outbox = root / "agentledger_outbox.json"
    crash_marker = root / "crashed_once"
    tool_executions = {"email.send": 0}
    rt = Runtime.local(runtime_root)

    def send_email(args: dict[str, Any]) -> dict[str, Any]:
        tool_executions["email.send"] += 1
        return _append_email(outbox, subject=args["subject"])

    rt.registry.register(
        ToolSpec(
            name="email.send",
            func=send_email,
            side_effect="external_write",
            idempotency_required=True,
            input_schema={"type": "object", "required": ["subject"]},
        )
    )

    async def agent(ctx: AgentContext, _state: dict[str, Any]) -> None:
        email = await ctx.call_tool(
            "email.send",
            {
                "subject": "Payment failed",
                "_logical_operation": "notify-payment-failure",
            },
        )
        if not crash_marker.exists():
            crash_marker.write_text("crashed after email send, before checkpoint\n", encoding="utf-8")
            raise SimulatedCrash("worker crashed after email send, before checkpoint")
        ctx.write_state_patch("email", email)
        ctx.write_state_patch("recovered", True)

    run_id, _ = rt.create_run(initial_state={"agent_run_id": "showcase-duplicate-side-effect"})
    first_ok = await rt.run_once(agent, run_id=run_id, worker_id="worker-before-crash", agent_role="BillingAgent")
    second_ok = await rt.run_once(agent, run_id=run_id, worker_id="worker-after-restart", agent_role="BillingAgent")
    evidence_dir = EvidenceExporter(store=rt.store, blobs=rt.blobs).export(run_id).write_dir(root / "evidence")
    replay = ReplayEngine(store=rt.store, blobs=rt.blobs).replay(run_id)

    source = InspectorDataSource()
    single_html = root / "inspector.html"
    runs_html = root / "runs.html"
    source.from_runtime_store(store=rt.store, blobs=rt.blobs, run_id=run_id, include_payloads=True).write_html(single_html)
    source.runs_from_sqlite(
        db_path=runtime_root / "state.db",
        blob_root=runtime_root / "blobs",
        limit=20,
        run_link_template="inspector.html",
    ).write_html(runs_html)

    ledger = [
        {key: row[key] for key in ("tool_name", "status", "external_id", "idempotency_key")}
        for row in rt.store.ledger(run_id)
    ]
    result = {
        "run_id": run_id,
        "first_attempt_ok": first_ok,
        "second_attempt_ok": second_ok,
        "external_email_count": len(_read_json(outbox)),
        "actual_tool_executions": tool_executions["email.send"],
        "tool_ledger": ledger,
        "replay": {
            "safe": replay.replay_safe,
            "event_count": replay.event_count,
            "tool_call_count": replay.tool_call_count,
        },
        "evidence_dir": str(evidence_dir),
        "inspector_html": str(single_html),
        "runs_html": str(runs_html),
    }
    rt.close()
    return result


async def main() -> None:
    root = Path(os.environ["AGENTLEDGER_SHOWCASE_ROOT"]) if "AGENTLEDGER_SHOWCASE_ROOT" in os.environ else Path(tempfile.mkdtemp(prefix="agentledger-showcase-"))
    root.mkdir(parents=True, exist_ok=True)
    _reset_demo_root(root)

    naive = _naive_retry(root)
    guarded = await _agentledger_retry(root)

    print("Agent called a side-effecting tool. The worker crashed after the side effect, before checkpoint.")
    print()
    print("WITHOUT runtime ledger")
    print(f"  first_error: {naive['first_error']}")
    print(f"  external_email_count_after_retry: {naive['external_email_count']}")
    print(f"  risk: {naive['risk']}")
    print()
    print("WITH AgentLedger")
    print(f"  first_attempt_ok: {str(guarded['first_attempt_ok']).lower()}")
    print(f"  second_attempt_ok: {str(guarded['second_attempt_ok']).lower()}")
    print(f"  external_email_count_after_retry: {guarded['external_email_count']}")
    print(f"  actual_tool_executions: {guarded['actual_tool_executions']}")
    print(f"  replay_safe: {str(guarded['replay']['safe']).lower()}")
    print(f"  runs_html: {guarded['runs_html']}")
    print(f"  inspector_html: {guarded['inspector_html']}")
    print()
    print(json.dumps({"ok": True, "demo_root": str(root), "naive": naive, "agentledger": guarded}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
