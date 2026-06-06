from __future__ import annotations

from collections import Counter
import sqlite3
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from typing import Any

from .blobstore import LocalBlobStore
from .diff import load_evidence_path
from .evidence import EvidenceExporter
from .protocol import EvidenceBlobStoreProtocol, EvidenceStateStoreProtocol
from .storage_mysql import MySQLStore, MySQLStoreConfig
from .storage_postgres import PostgresStore, PostgresStoreConfig
from .store import SQLiteStore


INSPECTOR_SCHEMA_VERSION = "agentledger.inspector.v1"


@dataclass(frozen=True)
class InspectorReport:
    """Language-neutral read model for AgentLedger runtime evidence."""

    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True)

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json() + "\n", encoding="utf-8")
        return target

    def write_html(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_html(), encoding="utf-8")
        return target

    def to_html(self) -> str:
        run = self.data.get("run", {})
        summary = self.data.get("summary", {})
        risk_flags = self.data.get("risk_flags", [])
        evidence = self.data.get("evidence", {})
        navigation = [
            ("evidence", "Evidence"),
            ("risk-flags", "Risk Flags"),
            ("timeline", "Timeline"),
            ("steps", "Steps"),
            ("tool-ledger", "Tool Ledger"),
            ("approvals", "Approvals"),
            ("cost-failure", "Cost / Failure"),
            ("policy-decisions", "Policy"),
            ("artifacts", "Artifacts"),
        ]
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Inspector</title>
  <style>
    :root {{
      --bg: #f7f8f5;
      --surface: #ffffff;
      --surface-2: #f0f4ef;
      --ink: #17211b;
      --muted: #5d6b61;
      --line: #d5ded6;
      --accent: #11695f;
      --accent-2: #7a4d00;
      --danger: #a23b3b;
      --danger-bg: #fff1f1;
      --warn-bg: #fff7df;
      --ok-bg: #edf8ef;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--bg);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 28px 18px 48px; }}
    header {{ margin-bottom: 22px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 48px); line-height: 1.05; letter-spacing: 0; }}
    h2 {{ margin: 30px 0 12px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ margin: 20px 0 10px; font-size: 15px; letter-spacing: 0; }}
    .lede {{ margin: 0; max-width: 900px; color: var(--muted); font-size: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 18px 0 16px; }}
    .card {{ min-width: 0; padding: 13px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .value {{ display: block; margin-top: 6px; font-size: 21px; font-weight: 700; overflow-wrap: anywhere; }}
    .status-ok {{ background: var(--ok-bg); }}
    .status-warn {{ background: var(--warn-bg); }}
    .status-risk {{ background: var(--danger-bg); }}
    .section {{ margin-top: 18px; }}
    .panel {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 20px; }}
    .nav a, .link-list a {{ color: var(--accent); text-decoration: none; }}
    .nav a {{ padding: 6px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); font-size: 13px; }}
    .nav a:hover, .link-list a:hover {{ text-decoration: underline; }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{ display: inline-flex; gap: 6px; align-items: center; max-width: 100%; padding: 5px 8px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface-2); color: var(--ink); font-size: 13px; overflow-wrap: anywhere; }}
    .pill.risk {{ border-color: #e4b6b6; background: var(--danger-bg); color: var(--danger); }}
    .link-list {{ display: flex; flex-wrap: wrap; gap: 6px; min-width: 160px; }}
    .link-list a {{ display: inline-flex; align-items: center; gap: 4px; max-width: 260px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 999px; background: #fbfdfb; font-size: 12px; }}
    .link-list .ref-kind {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--surface); }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
    th {{ background: var(--surface-2); color: #334137; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }}
    tr.risk td {{ background: var(--danger-bg); }}
    tr.warn td {{ background: var(--warn-bg); }}
    code {{ padding: 2px 5px; border-radius: 6px; background: #e8eee8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    details {{ margin-top: 4px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 650; }}
    pre {{ max-height: 300px; overflow: auto; padding: 11px; border: 1px solid var(--line); border-radius: 8px; background: #fbfdfb; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }}
    :target {{ scroll-margin-top: 14px; outline: 2px solid #82b7ad; outline-offset: 2px; }}
    @media (max-width: 900px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid-2 {{ grid-template-columns: 1fr; }}
      table {{ display: block; overflow-x: auto; }}
    }}
    @media (max-width: 560px) {{
      main {{ padding: 22px 12px 36px; }}
      .cards {{ grid-template-columns: 1fr; }}
      .value {{ font-size: 18px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AgentLedger Inspector</h1>
      <p class="lede">Read-only runtime view generated from AgentLedger evidence. It does not start a server, mutate state, call tools, or contact model providers.</p>
    </header>
    {_nav(navigation)}
    <section class="cards">
      <div class="card"><span class="label">Run</span><span class="value">{escape(str(run.get("run_id", "-")))}</span></div>
      <div class="card {_status_class(str(run.get("status", "")))}"><span class="label">Status</span><span class="value">{escape(str(run.get("status", "-")))}</span></div>
      <div class="card"><span class="label">Events</span><span class="value">{summary.get("event_count", 0)}</span></div>
      <div class="card {_risk_card_class(risk_flags)}"><span class="label">Risk Flags</span><span class="value">{len(risk_flags)}</span></div>
    </section>

    <section class="panel" id="evidence">
      <h2>Evidence</h2>
      <div class="grid-2">
        <pre>{_json_block(evidence)}</pre>
        <pre>{_json_block(summary)}</pre>
      </div>
    </section>

    <section class="section" id="risk-flags">
      <h2>Risk Flags</h2>
      {_pills(risk_flags, risk=True) if risk_flags else "<p>No active risk flags detected in the evidence summary.</p>"}
    </section>

    <section class="section" id="timeline">
      <h2>Run Timeline</h2>
      {_table(["seq", "type", "step_id", "agent_role", "state_version", "summary"], self.data.get("timeline", []), risk_key="severity", risk_values={"risk"}, warn_values={"warn"})}
    </section>

    <section class="section grid-2">
      <div id="steps">
        <h2>Steps</h2>
        {_table(["step_id", "status", "attempt", "last_error_type"], self.data.get("steps", []), risk_key="status", risk_values={"failed"}, warn_values={"waiting_human", "retry_scheduled", "running"})}
      </div>
      <div id="tool-ledger">
        <h2>Tool Ledger</h2>
        {_table(["tool_name", "status", "external_id", "error_type"], self.data.get("tool_ledger", []), risk_key="status", risk_values={"PENDING_VERIFICATION"}, warn_values={"RESERVED", "RUNNING"})}
      </div>
    </section>

    <section class="section grid-2">
      <div id="approvals">
        <h2>Approvals</h2>
        {_table(["approval_id", "tool_name", "risk_level", "status"], self.data.get("approvals", []), risk_key="status", risk_values={"DENIED"}, warn_values={"PENDING"})}
      </div>
      <div id="cost-failure">
        <h2>Cost And Failure</h2>
        <h3>Cost Records</h3>
        {_table(["category", "name", "amount", "unit"], self.data.get("cost_records", []))}
        <h3>Failures</h3>
        {_table(["seq", "type", "step_id", "summary"], self.data.get("failure_events", []), risk_key="severity", risk_values={"risk"})}
      </div>
    </section>

    <section class="section" id="policy-decisions">
      <h2>Policy Decisions</h2>
      {_table(["seq", "type", "tool_name", "allowed", "action_tier", "summary"], self.data.get("policy_decisions", []), risk_key="allowed", risk_values={False, "False", "false"})}
    </section>

    <section class="section" id="artifacts">
      <h2>Artifacts</h2>
      {_table(["name", "blob_hash", "blob_ref", "kind", "uri", "content_ref"], self.data.get("artifacts", []))}
    </section>
  </main>
</body>
</html>
"""


@dataclass(frozen=True)
class InspectorRedactionPolicy:
    """Read-model redaction policy for Inspector JSON and HTML output."""

    keys: tuple[str, ...] = ()
    replacement: str = "<redacted>"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "InspectorRedactionPolicy":
        keys = value.get("keys", [])
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise ValueError("Inspector redaction policy must contain a string list field named 'keys'")
        replacement = value.get("replacement", "<redacted>")
        if not isinstance(replacement, str):
            raise ValueError("Inspector redaction policy field 'replacement' must be a string")
        return cls(keys=tuple(keys), replacement=replacement)

    @classmethod
    def from_path(cls, path: str | Path) -> "InspectorRedactionPolicy":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Inspector redaction policy file must contain a JSON object")
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return {"keys": list(self.keys), "replacement": self.replacement}

    def apply(self, value: Any) -> Any:
        if not self.keys:
            return value
        normalized = {key.casefold() for key in self.keys}
        return _redact_value(value, normalized, self.replacement)


class InspectorReportBuilder:
    """Build language-neutral Inspector reports from runtime stores or evidence bundles."""

    def from_runtime(
        self,
        *,
        store: EvidenceStateStoreProtocol,
        blobs: EvidenceBlobStoreProtocol,
        run_id: str,
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        evidence = EvidenceExporter(store=store, blobs=blobs).export(run_id).to_dict()
        return self.from_evidence(evidence, source={"kind": "runtime_store", "run_id": run_id}, include_payloads=include_payloads, redaction_policy=redaction_policy)

    def from_evidence_path(self, path: str | Path, *, include_payloads: bool = False, redaction_policy: InspectorRedactionPolicy | None = None) -> InspectorReport:
        evidence = load_evidence_path(path)
        return self.from_evidence(evidence, source={"kind": "evidence_path", "path": str(path)}, include_payloads=include_payloads, redaction_policy=redaction_policy)

    def from_evidence(
        self,
        evidence: dict[str, Any],
        *,
        source: dict[str, Any] | None = None,
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        redaction = redaction_policy or InspectorRedactionPolicy()
        if redaction.keys:
            evidence = redaction.apply(evidence)
        run = _run_summary(evidence.get("run", {}))
        steps = [_project_step(row) for row in evidence.get("steps", [])]
        ledger = [_project_ledger(row) for row in evidence.get("tool_ledger", [])]
        approvals = [_project_approval(row) for row in evidence.get("approval_requests", [])]
        artifacts = _artifacts(evidence)
        cost_records = [_project_cost(row) for row in evidence.get("cost_records", [])]
        timeline = [_timeline_event(event, include_payloads=include_payloads) for event in evidence.get("events", [])]
        policy_decisions = [_policy_decision(event, include_payloads=include_payloads) for event in evidence.get("events", []) if event.get("type") == "tool_permission_decided"]
        policy_decisions = [row for row in policy_decisions if row is not None]
        _decorate_report_links(timeline=timeline, steps=steps, ledger=ledger, approvals=approvals, policy_decisions=policy_decisions, artifacts=artifacts)
        failure_events = [event for event in timeline if _is_failure_event(event.get("type"))]
        summary = {
            **_safe_dict(evidence.get("summary")),
            "event_type_counts": dict(Counter(event.get("type", "-") for event in evidence.get("events", []))),
            "step_status_counts": dict(Counter(row.get("status", "-") for row in steps)),
            "tool_ledger_status_counts": dict(Counter(row.get("status", "-") for row in ledger)),
            "approval_status_counts": dict(Counter(row.get("status", "-") for row in approvals)),
            "failure_event_count": len(failure_events),
            "policy_decision_count": len(policy_decisions),
        }
        risk_flags = _risk_flags(summary, steps, ledger, approvals, failure_events, policy_decisions)
        data = {
            "schema_version": INSPECTOR_SCHEMA_VERSION,
            "source": source or {"kind": "evidence_bundle"},
            "run": run,
            "summary": summary,
            "risk_flags": risk_flags,
            "timeline": timeline,
            "steps": steps,
            "tool_ledger": ledger,
            "approvals": approvals,
            "policy_decisions": policy_decisions,
            "cost_records": cost_records,
            "failure_events": failure_events,
            "artifacts": artifacts,
            "evidence": {
                "schema_version": evidence.get("schema_version"),
                "bundle_hash": evidence.get("bundle_hash"),
                "run_id": run.get("run_id"),
                "replay_safe_inputs": True,
                "artifact_count": len(artifacts),
                "media_artifact_count": len(evidence.get("media_artifacts", [])),
                "stream_checkpoint_count": len(evidence.get("stream_checkpoints", [])),
            },
        }
        if redaction.keys:
            data["redaction"] = {
                "enabled": True,
                "redacted_keys": list(redaction.keys),
                "replacement": redaction.replacement,
            }
        return InspectorReport(data)


class ReadOnlySQLiteStore(SQLiteStore):
    """SQLiteStore opened in read-only mode for Inspector usage."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"AgentLedger SQLite database not found: {self.path}")
        uri = f"file:{self.path.resolve()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True, timeout=30)
        self._closed = False
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")

    def init(self) -> None:
        # Inspector must never create or migrate user databases.
        return None


class ReadOnlyLocalBlobStore(LocalBlobStore):
    """Local blob reader that does not create directories or write blobs."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        if not self.root.exists():
            raise FileNotFoundError(f"AgentLedger blob root not found: {self.root}")

    def put_json(self, value: Any) -> tuple[str, str]:
        raise RuntimeError("Inspector blob store is read-only")


def _read_only_error(operation: str) -> RuntimeError:
    return RuntimeError(f"Inspector data sources are read-only; {operation} is not allowed")


class _ReadOnlyStateStoreMixin:
    """Block runtime write/control methods on Inspector DB connections."""

    def init(self) -> None:
        return None

    def migration_status(self) -> Any:
        raise _read_only_error("migration_status")

    def schema_version(self) -> Any:
        raise _read_only_error("schema_version")

    def _ensure_migration_table(self) -> None:
        raise _read_only_error("migration table creation")

    def _apply_migrations(self) -> None:
        raise _read_only_error("migration application")

    def create_run(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("create_run")

    def claim_step(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("claim_step")

    def heartbeat(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("heartbeat")

    def recover_expired_leases(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("recover_expired_leases")

    def cancel_run(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("cancel_run")

    def mark_waiting_human(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("mark_waiting_human")

    def request_approval(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("request_approval")

    def approve_request(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("approve_request")

    def deny_request(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("deny_request")

    def _decide_approval(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("approval decision")

    def commit_state_patch(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("commit_state_patch")

    def apply_system_state_patch(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("apply_system_state_patch")

    def mark_retry(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("mark_retry")

    def mark_failed(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("mark_failed")

    def append_event(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("append_event")

    def _append_event_in_tx(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("append_event")

    def reserve_ledger(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("reserve_ledger")

    def update_ledger(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("update_ledger")

    def create_artifact(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("create_artifact")

    def record_cost(self, *args: Any, **kwargs: Any) -> Any:
        raise _read_only_error("record_cost")


class ReadOnlyPostgresStore(_ReadOnlyStateStoreMixin, PostgresStore):
    """Postgres StateStore opened for Inspector reads only."""

    def _configure_schema(self) -> None:
        if self._schema_configured:
            return
        schema = self.config.schema or "public"
        if schema != "public":
            quoted = self._quote_identifier(schema)
            self.conn.execute(f"SET search_path TO {quoted}")
            self.conn.commit()
        self._schema_configured = True


class ReadOnlyMySQLStore(_ReadOnlyStateStoreMixin, MySQLStore):
    """MySQL StateStore opened for Inspector reads only."""


class InspectorDataSource:
    """Read-only data source for Inspector reports.

    The source can read directly from a runtime DB or from an exported evidence
    bundle. UI authors can reuse this class and render the returned read model
    with their own frontend.
    """

    def __init__(self, *, builder: InspectorReportBuilder | None = None):
        self.builder = builder or InspectorReportBuilder()

    def from_evidence_path(self, path: str | Path, *, include_payloads: bool = False, redaction_policy: InspectorRedactionPolicy | None = None) -> InspectorReport:
        return self.builder.from_evidence_path(path, include_payloads=include_payloads, redaction_policy=redaction_policy)

    def from_runtime_store(
        self,
        *,
        store: EvidenceStateStoreProtocol,
        blobs: EvidenceBlobStoreProtocol,
        run_id: str,
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        """Build an Inspector report from an application-provided read store.

        This is the extension seam for custom StateStore/BlobStore
        implementations and custom UI backends. The caller owns connection
        lifecycle and must provide read-only store credentials or wrappers.
        """
        return self.builder.from_runtime(store=store, blobs=blobs, run_id=run_id, include_payloads=include_payloads, redaction_policy=redaction_policy)

    def from_sqlite(
        self,
        *,
        db_path: str | Path,
        blob_root: str | Path,
        run_id: str,
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        store = ReadOnlySQLiteStore(db_path)
        try:
            blobs = ReadOnlyLocalBlobStore(blob_root)
            return self.from_runtime_store(store=store, blobs=blobs, run_id=run_id, include_payloads=include_payloads, redaction_policy=redaction_policy)
        finally:
            store.close()

    def from_postgres(
        self,
        *,
        dsn: str,
        blob_root: str | Path,
        run_id: str,
        schema: str = "agentledger",
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        store = ReadOnlyPostgresStore(PostgresStoreConfig(dsn=dsn, schema=schema))
        try:
            store._configure_schema()
            blobs = ReadOnlyLocalBlobStore(blob_root)
            return self.from_runtime_store(store=store, blobs=blobs, run_id=run_id, include_payloads=include_payloads, redaction_policy=redaction_policy)
        finally:
            store.close()

    def from_mysql(
        self,
        *,
        dsn: str,
        blob_root: str | Path,
        run_id: str,
        database: str | None = None,
        include_payloads: bool = False,
        redaction_policy: InspectorRedactionPolicy | None = None,
    ) -> InspectorReport:
        store = ReadOnlyMySQLStore(MySQLStoreConfig(dsn=dsn, database=database))
        try:
            store._configure_schema()
            blobs = ReadOnlyLocalBlobStore(blob_root)
            return self.from_runtime_store(store=store, blobs=blobs, run_id=run_id, include_payloads=include_payloads, redaction_policy=redaction_policy)
        finally:
            store.close()


def _run_summary(run: Any) -> dict[str, Any]:
    row = _safe_dict(run)
    return {key: row.get(key) for key in ["run_id", "session_id", "status", "state_version", "created_at", "updated_at", "initial_state"] if key in row}


def _project_step(row: Any) -> dict[str, Any]:
    item = _safe_dict(row)
    return _select(item, ["step_id", "run_id", "session_id", "status", "attempt", "state_version", "owner", "lease_until", "last_error_type", "last_error", "created_at", "updated_at"])


def _project_ledger(row: Any) -> dict[str, Any]:
    item = _safe_dict(row)
    return _select(item, ["tool_name", "status", "idempotency_key", "external_id", "request_hash", "response_hash", "response_ref", "error_type", "error", "created_at", "updated_at"])


def _project_approval(row: Any) -> dict[str, Any]:
    item = _safe_dict(row)
    return _select(item, ["approval_id", "approval_key", "run_id", "step_id", "tool_name", "risk_level", "status", "reason", "requested_by", "approved_by", "decision_reason", "created_at", "updated_at"])


def _project_cost(row: Any) -> dict[str, Any]:
    item = _safe_dict(row)
    return _select(item, ["category", "name", "amount", "unit", "agent_role", "step_id", "created_at"])


def _timeline_event(event: dict[str, Any], *, include_payloads: bool) -> dict[str, Any]:
    payload = event.get("payload")
    item = {
        "seq": event.get("seq"),
        "event_id": event.get("event_id"),
        "type": event.get("type"),
        "step_id": event.get("step_id"),
        "agent_role": event.get("agent_role"),
        "state_version": event.get("state_version"),
        "timestamp": event.get("timestamp"),
        "summary": _payload_summary(payload),
        "severity": "risk" if _is_failure_event(event.get("type")) else "warn" if _is_wait_event(event.get("type")) else "info",
    }
    related_refs = _related_refs_from_event(event)
    if related_refs:
        item["related_refs"] = related_refs
    if include_payloads:
        item["payload"] = payload
    return item


def _policy_decision(event: dict[str, Any], *, include_payloads: bool) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        return {
            "seq": event.get("seq"),
            "type": event.get("type"),
            "tool_name": payload.get("tool_name"),
            "allowed": payload.get("allowed"),
            "action_tier": payload.get("action_tier"),
            "summary": _payload_summary(payload),
        }
    row = {
        "seq": event.get("seq"),
        "type": event.get("type"),
        "tool_name": payload.get("tool_name") or decision.get("tool_name"),
        "allowed": decision.get("allowed"),
        "action_tier": decision.get("action_tier"),
        "summary": _payload_summary(decision),
        "finding_count": len(decision.get("findings", [])) if isinstance(decision.get("findings"), list) else 0,
        "control_count": len(decision.get("controls", [])) if isinstance(decision.get("controls"), list) else 0,
    }
    if include_payloads:
        row["decision"] = decision
    return row


def _artifacts(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in evidence.get("artifacts", []):
        item = _safe_dict(row)
        metadata = _metadata(item)
        rows.append(
            {
                **_select(item, ["artifact_id", "name", "blob_hash", "blob_ref", "metadata_json", "created_at"]),
                "kind": metadata.get("kind"),
                "uri": metadata.get("uri"),
                "content_ref": metadata.get("content_ref"),
            }
        )
    for row in evidence.get("media_artifacts", []):
        item = _safe_dict(row)
        rows.append({**_select(item, ["artifact_id", "name", "blob_hash", "blob_ref", "kind", "uri", "content_ref"]), "artifact_group": "media"})
    for row in evidence.get("stream_checkpoints", []):
        item = _safe_dict(row)
        rows.append({**_select(item, ["artifact_id", "name", "blob_hash", "blob_ref", "stream_id", "consumer_id", "offset", "watermark"]), "artifact_group": "stream"})
    return rows


def _decorate_report_links(
    *,
    timeline: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    policy_decisions: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
) -> None:
    anchors: dict[tuple[str, str], str] = {}
    _anchor_rows(steps, kind="step", key="step_id", anchors=anchors)
    _anchor_rows(ledger, kind="tool", key="tool_name", anchors=anchors)
    _anchor_rows(approvals, kind="approval", key="approval_id", anchors=anchors)
    _anchor_rows(artifacts, kind="artifact", key="artifact_id", anchors=anchors)
    _anchor_rows(policy_decisions, kind="policy", key="seq", anchors=anchors)
    _anchor_rows(timeline, kind="event", key="seq", anchors=anchors)

    for row in timeline:
        _attach_related_links(row, anchors)
    for row in approvals:
        refs = []
        if row.get("step_id") is not None:
            refs.append({"kind": "step", "value": str(row["step_id"])})
        if row.get("tool_name") is not None:
            refs.append({"kind": "tool", "value": str(row["tool_name"])})
        row["related_refs"] = _merge_related_refs(row.get("related_refs"), refs)
        _attach_related_links(row, anchors)
    for row in policy_decisions:
        refs = []
        if row.get("tool_name") is not None:
            refs.append({"kind": "tool", "value": str(row["tool_name"])})
        row["related_refs"] = _merge_related_refs(row.get("related_refs"), refs)
        _attach_related_links(row, anchors)
    for row in ledger:
        refs = []
        if row.get("response_ref") is not None:
            refs.append({"kind": "blob", "value": str(row["response_ref"])})
        row["related_refs"] = _merge_related_refs(row.get("related_refs"), refs)
    for row in artifacts:
        refs = []
        if row.get("blob_ref") is not None:
            refs.append({"kind": "blob", "value": str(row["blob_ref"])})
        if row.get("content_ref") is not None:
            refs.append({"kind": "content", "value": str(row["content_ref"])})
        row["related_refs"] = _merge_related_refs(row.get("related_refs"), refs)


def _anchor_rows(rows: list[dict[str, Any]], *, kind: str, key: str, anchors: dict[tuple[str, str], str]) -> None:
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        raw_value = row.get(key)
        suffix = _slug(raw_value if raw_value is not None else index)
        anchor = f"{kind}-{suffix}"
        if anchor in seen:
            anchor = f"{anchor}-{index}"
        seen.add(anchor)
        row["anchor"] = anchor
        if raw_value is not None:
            anchors[(kind, str(raw_value))] = anchor


def _related_refs_from_event(event: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if event.get("step_id") is not None:
        refs.append({"kind": "step", "value": str(event["step_id"])})
    payload = event.get("payload")
    if isinstance(payload, dict):
        for kind, keys in {
            "tool": ["tool_name", "name"],
            "approval": ["approval_id"],
            "artifact": ["artifact_id"],
            "blob": ["payload_ref", "blob_ref", "response_ref"],
        }.items():
            for key in keys:
                value = payload.get(key)
                if value is not None:
                    refs.append({"kind": kind, "value": str(value)})
    if event.get("payload_ref") is not None:
        refs.append({"kind": "blob", "value": str(event["payload_ref"])})
    return _merge_related_refs(None, refs)


def _merge_related_refs(existing: Any, extra: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for ref in list(existing) if isinstance(existing, list) else []:
        if not isinstance(ref, dict):
            continue
        kind = ref.get("kind")
        value = ref.get("value")
        if kind is None or value is None:
            continue
        key = (str(kind), str(value))
        if key not in seen:
            seen.add(key)
            merged.append({"kind": key[0], "value": key[1]})
    for ref in extra:
        key = (str(ref["kind"]), str(ref["value"]))
        if key not in seen:
            seen.add(key)
            merged.append({"kind": key[0], "value": key[1]})
    return merged


def _attach_related_links(row: dict[str, Any], anchors: dict[tuple[str, str], str]) -> None:
    links = []
    for ref in row.get("related_refs", []):
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind", ""))
        value = str(ref.get("value", ""))
        target = anchors.get((kind, value))
        if target:
            links.append({"kind": kind, "value": value, "href": f"#{target}"})
    if links:
        row["related_links"] = links


def _risk_flags(
    summary: dict[str, Any],
    steps: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    failure_events: list[dict[str, Any]],
    policy_decisions: list[dict[str, Any]],
) -> list[str]:
    flags: list[str] = []
    if summary.get("has_pending_approvals") or any(row.get("status") == "PENDING" for row in approvals):
        flags.append("pending approval")
    if summary.get("has_pending_verification") or any(row.get("status") == "PENDING_VERIFICATION" for row in ledger):
        flags.append("pending tool verification")
    if summary.get("has_failed_steps") or any(row.get("status") == "failed" for row in steps):
        flags.append("failed step")
    if failure_events:
        flags.append("failure events present")
    if any(row.get("allowed") is False for row in policy_decisions):
        flags.append("policy denial")
    return flags


def _payload_summary(payload: Any) -> str:
    if payload is None:
        return "-"
    if isinstance(payload, dict):
        parts = []
        for key in ["tool_name", "status", "reason", "error_type", "error", "approval_id", "provider", "name"]:
            if key in payload and payload[key] is not None:
                parts.append(f"{key}={payload[key]}")
        if parts:
            return ", ".join(str(part) for part in parts)
        keys = ", ".join(sorted(str(key) for key in payload.keys())[:6])
        return f"keys: {keys}" if keys else "{}"
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    text = str(payload)
    return text if len(text) <= 120 else text[:117] + "..."


def _is_failure_event(event_type: Any) -> bool:
    return str(event_type) in {"error_raised", "step_failed", "tool_call_failed", "tool_call_blocked", "run_cancelled", "step_cancelled"}


def _is_wait_event(event_type: Any) -> bool:
    return str(event_type) in {"step_waiting_human", "approval_requested", "step_retry_scheduled", "lease_expired"}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _select(row: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    return {key: row.get(key) for key in keys if key in row}


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    metadata_json = row.get("metadata_json")
    if isinstance(metadata_json, dict):
        return metadata_json
    if isinstance(metadata_json, str):
        try:
            parsed = json.loads(metadata_json)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _table(
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    risk_key: str | None = None,
    risk_values: set[Any] | None = None,
    warn_values: set[Any] | None = None,
) -> str:
    if not rows:
        return "<p>No records.</p>"
    include_links = any(row.get("related_links") for row in rows)
    links_head = "<th>Links</th>" if include_links else ""
    head = "".join(f"<th>{escape(column)}</th>" for column in columns) + links_head + "<th>Details</th>"
    body = "\n".join(_table_row(columns, row, risk_key=risk_key, risk_values=risk_values or set(), warn_values=warn_values or set(), include_links=include_links) for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _table_row(columns: list[str], row: dict[str, Any], *, risk_key: str | None, risk_values: set[Any], warn_values: set[Any], include_links: bool) -> str:
    status = row.get(risk_key) if risk_key else None
    css = "risk" if status in risk_values else "warn" if status in warn_values else ""
    cells = "".join(f"<td>{escape(str(row.get(column, '-')))}</td>" for column in columns)
    links = f"<td>{_link_list(row.get('related_links'))}</td>" if include_links else ""
    details = f"<td><details><summary>JSON</summary><pre>{_json_block(row)}</pre></details></td>"
    return f"<tr{_row_attrs(row.get('anchor'), css)}>{cells}{links}{details}</tr>"


def _row_attrs(anchor: Any, css: str) -> str:
    attrs = []
    if anchor:
        attrs.append(f"id=\"{escape(str(anchor), quote=True)}\"")
    if css:
        attrs.append(f"class=\"{escape(css, quote=True)}\"")
    return " " + " ".join(attrs) if attrs else ""


def _nav(items: list[tuple[str, str]]) -> str:
    links = "".join(f"<a href=\"#{escape(anchor, quote=True)}\">{escape(label)}</a>" for anchor, label in items)
    return f"<nav class=\"nav\" aria-label=\"Inspector sections\">{links}</nav>"


def _link_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "-"
    links = []
    for item in value:
        if not isinstance(item, dict):
            continue
        href = item.get("href")
        kind = item.get("kind")
        ref_value = item.get("value")
        if not href or kind is None or ref_value is None:
            continue
        links.append(
            f"<a href=\"{escape(str(href), quote=True)}\"><span class=\"ref-kind\">{escape(str(kind))}</span>{escape(str(ref_value))}</a>"
        )
    return "<div class=\"link-list\">" + "".join(links) + "</div>" if links else "-"


def _slug(value: Any) -> str:
    text = str(value)
    chars: list[str] = []
    last_dash = False
    for char in text:
        if char.isascii() and char.isalnum():
            chars.append(char.lower())
            last_dash = False
        elif not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-") or "item"


def _json_block(value: Any) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _pills(values: list[str], *, risk: bool = False) -> str:
    css = " risk" if risk else ""
    return "<div class=\"pill-row\">" + "".join(f"<span class=\"pill{css}\">{escape(value)}</span>" for value in values) + "</div>"


def _status_class(status: str) -> str:
    if status in {"completed", "ok", "succeeded"}:
        return "status-ok"
    if status in {"failed", "cancelled"}:
        return "status-risk"
    if status in {"waiting_human", "retry_scheduled", "running"}:
        return "status-warn"
    return ""


def _risk_card_class(risk_flags: list[str]) -> str:
    return "status-risk" if risk_flags else "status-ok"


def _redact_value(value: Any, normalized_keys: set[str], replacement: str) -> Any:
    if isinstance(value, dict):
        return {
            key: replacement if str(key).casefold() in normalized_keys else _redact_value(item, normalized_keys, replacement)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, normalized_keys, replacement) for item in value]
    if isinstance(value, str):
        parsed = _parse_json_like_string(value)
        if parsed is not None:
            redacted = _redact_value(parsed, normalized_keys, replacement)
            if redacted != parsed:
                return json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    return value


def _parse_json_like_string(value: str) -> Any:
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
