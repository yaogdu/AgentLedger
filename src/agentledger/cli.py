from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .blobstore import LocalBlobStore
from .examples import crash_once_agent, recovery_agent, register_fake_github
from .replay import ReplayEngine
from .runtime import Runtime
from .store import SQLiteStore


def runtime_from_root(root: str) -> Runtime:
    return Runtime.local(root)


def cmd_init(args: argparse.Namespace) -> None:
    runtime_from_root(args.root)
    print(f"initialized AgentLedger store at {args.root}")


def cmd_doctor(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root)
    print(f"store={rt.store.path}")
    print("status=ok")


def cmd_run(args: argparse.Namespace) -> None:
    if args.example != "examples/side_effect_idempotency":
        raise SystemExit("only examples/side_effect_idempotency is available in v0.1")
    rt = runtime_from_root(args.root)
    external_path = Path(args.root) / "external_issues.json"
    register_fake_github(rt, external_path)
    run_id, _ = rt.create_run(initial_state={"crashed_once": False})
    first_ok = asyncio.run(rt.run_once(crash_once_agent, run_id=run_id, agent_role="ExecutorAgent"))
    if not first_ok:
        rt.store.apply_system_state_patch(
            run_id=run_id,
            patch={"crashed_once": True},
            reason="demo recovery marker after simulated worker crash",
        )
    second_ok = asyncio.run(rt.run_once(recovery_agent, run_id=run_id, agent_role="ExecutorAgent"))
    issues = json.loads(external_path.read_text(encoding="utf-8"))
    print(json.dumps({"run_id": run_id, "first_attempt_ok": first_ok, "second_attempt_ok": second_ok, "external_issue_count": len(issues), "external_issues_path": str(external_path)}, indent=2))


def cmd_debug(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root)
    for event in rt.store.events(args.run_id):
        state = event["state_version"] if event["state_version"] is not None else "-"
        print(f"{event['seq']:03d} {event['type']} step={event['step_id'] or '-'} state={state}")


def cmd_ledger(args: argparse.Namespace) -> None:
    rt = runtime_from_root(args.root)
    rows = []
    for row in rt.store.ledger(args.run_id):
        rows.append({k: row[k] for k in row.keys() if k in {"tool_name", "status", "idempotency_key", "external_id", "response_ref", "error_type"}})
    print(json.dumps(rows, indent=2))


def cmd_replay(args: argparse.Namespace) -> None:
    root = Path(args.root)
    store = SQLiteStore(root / "state.db")
    blobs = LocalBlobStore(root / "blobs")
    summary = ReplayEngine(store=store, blobs=blobs).replay(args.run_id)
    print(json.dumps(summary.__dict__, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentledger")
    parser.add_argument("--root", default=".agentledger", help="runtime data root")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.set_defaults(func=cmd_init)
    doctor = sub.add_parser("doctor")
    doctor.set_defaults(func=cmd_doctor)
    run = sub.add_parser("run")
    run.add_argument("example")
    run.set_defaults(func=cmd_run)
    debug = sub.add_parser("debug")
    debug.add_argument("run_id")
    debug.set_defaults(func=cmd_debug)
    ledger = sub.add_parser("ledger")
    ledger.add_argument("run_id")
    ledger.set_defaults(func=cmd_ledger)
    replay = sub.add_parser("replay")
    replay.add_argument("run_id")
    replay.set_defaults(func=cmd_replay)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
