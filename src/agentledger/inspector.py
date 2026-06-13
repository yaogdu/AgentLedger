from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import sqlite3
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .blobstore import LocalBlobStore
from .diff import load_evidence_path
from .evidence import decode_payload, EvidenceExporter
from .failure import FailureAlertEvaluator, FailureCausalGraphBuilder, FailureEnvelopeBuilder, FailureExportMapper, FailureLifecycleBuilder, FailureReplayPlanner
from .protocol import EvidenceBlobStoreProtocol, EvidenceStateStoreProtocol
from .storage_mysql import MySQLStore, MySQLStoreConfig
from .storage_postgres import PostgresStore, PostgresStoreConfig
from .store import SQLiteStore


INSPECTOR_SCHEMA_VERSION = "agentledger.inspector.v1"
INSPECTOR_RUN_INDEX_SCHEMA_VERSION = "agentledger.inspector.runs.v1"


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
            ("event-stream", "Event Stream"),
            ("failures", "Failures"),
            ("failure-lifecycle", "Failure Lifecycle"),
            ("failure-replay", "Replay Plan"),
            ("failure-alerts", "Alerts"),
            ("failure-causal-graph", "Causal Graph"),
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
    .section-note {{ margin: -4px 0 12px; color: var(--muted); font-size: 13px; }}
    .panel {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 20px; }}
    .nav a, .link-list a {{ color: var(--accent); text-decoration: none; }}
    .nav a {{ padding: 6px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); font-size: 13px; }}
    .nav a:hover, .link-list a:hover {{ text-decoration: underline; }}
    .pill-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .pill {{ display: inline-flex; gap: 6px; align-items: center; max-width: 100%; padding: 5px 8px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface-2); color: var(--ink); font-size: 13px; overflow-wrap: anywhere; }}
    .pill.risk {{ border-color: #e4b6b6; background: var(--danger-bg); color: var(--danger); }}
    .event-list {{ display: grid; gap: 10px; }}
    .event-item {{ display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: 14px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .event-item.risk {{ background: var(--danger-bg); }}
    .event-item.warn {{ background: var(--warn-bg); }}
    .event-time-block {{ color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }}
    .event-seq {{ display: inline-flex; margin-top: 6px; padding: 2px 6px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface-2); color: var(--ink); font-size: 12px; }}
    .event-main {{ min-width: 0; }}
    .event-title {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; margin-bottom: 5px; }}
    .event-type {{ font-weight: 700; overflow-wrap: anywhere; }}
    .event-summary {{ margin: 3px 0 8px; overflow-wrap: anywhere; }}
    .event-meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }}
    .event-meta code {{ max-width: 100%; overflow-wrap: anywhere; }}
    .event-details {{ margin-top: 8px; }}
    .link-list {{ display: flex; flex-wrap: wrap; gap: 6px; min-width: 160px; }}
    .link-list a {{ display: inline-flex; align-items: center; gap: 4px; max-width: 260px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 999px; background: #fbfdfb; font-size: 12px; }}
    .link-list .ref-kind {{ color: var(--muted); }}
    .table-wrap {{ width: 100%; max-width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    table {{ width: 100%; min-width: 760px; table-layout: fixed; border-collapse: collapse; background: var(--surface); }}
    th, td {{ padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: var(--surface-2); color: #334137; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }}
    td.event-time {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
    tr.details-row td {{ padding-top: 0; background: #fbfdfb; }}
    tr.details-row.risk td {{ background: var(--danger-bg); }}
    tr.details-row.warn td {{ background: var(--warn-bg); }}
    .record-details {{ margin: 0; }}
    tr.risk td {{ background: var(--danger-bg); }}
    tr.warn td {{ background: var(--warn-bg); }}
    code {{ padding: 2px 5px; border-radius: 6px; background: #e8eee8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    details {{ margin-top: 4px; max-width: 100%; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 650; }}
    pre {{ max-width: 100%; max-height: 300px; overflow: auto; padding: 11px; border: 1px solid var(--line); border-radius: 8px; background: #fbfdfb; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }}
    .grid-2 {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }}
    .grid-2 > * {{ min-width: 0; }}
    .section.grid-2 {{ grid-template-columns: minmax(0, 1fr); }}
    :target {{ scroll-margin-top: 14px; outline: 2px solid #82b7ad; outline-offset: 2px; }}
    @media (max-width: 900px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid-2 {{ grid-template-columns: 1fr; }}
      .event-item {{ grid-template-columns: 1fr; }}
      table {{ min-width: 680px; }}
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

    <section class="section" id="event-stream">
      <h2>Event Stream</h2>
      <p class="section-note">Chronological event view keyed by runtime run id and agent run id, with links back to detailed timeline records.</p>
      {_event_stream(self.data.get("event_stream", []))}
    </section>

    <section class="section" id="failures">
      <h2>Failure Envelopes</h2>
      <p class="section-note">Normalized failure read model for terminal failures, recoverable retries, approval waits, blocked tools, and unknown side-effect states.</p>
      {_table(["failure_id", "category", "status", "recoverability", "retryability", "owner", "message"], self.data.get("failure_envelopes", []), risk_key="severity", risk_values={"risk"}, warn_values={"warn"})}
    </section>

    <section class="section" id="failure-lifecycle">
      <h2>Failure Lifecycle</h2>
      <p class="section-note">Runtime-owned failure stages derived from the normalized read model: detected, classified, recovery scheduled, recovered, terminal, and regressed.</p>
      {_table(["stage", "failure_id", "category", "recoverability", "retryability", "owner", "message"], self.data.get("failure_lifecycle", {}).get("events", []), risk_key="severity", risk_values={"risk"}, warn_values={"warn"})}
    </section>

    <section class="section grid-2">
      <div id="failure-replay">
        <h2>Failure Replay Plan</h2>
        <p class="section-note">Evidence-only replay guidance that blocks unsafe automatic side-effect replay when manual verification is required.</p>
        {_table(["failure_id", "category", "status", "replay_action", "replay_safe", "requires_manual_verification", "reason"], self.data.get("failure_replay_plan", {}).get("actions", []), risk_key="replay_safe", risk_values={False, "False", "false"}, warn_values={None})}
      </div>
      <div id="failure-alerts">
        <h2>Failure Alerts</h2>
        <p class="section-note">Local alert records for downstream sinks. Inspector does not send alerts externally.</p>
        {_table(["kind", "severity", "message"], self.data.get("failure_alerts", {}).get("alerts", []), risk_key="severity", risk_values={"risk"}, warn_values={"warn"})}
      </div>
    </section>

    <section class="section grid-2" id="failure-causal-graph">
      <div>
        <h2>Failure Causal Nodes</h2>
        {_table(["id", "kind", "status", "category", "owner"], self.data.get("failure_causal_graph", {}).get("nodes", []), risk_key="kind", risk_values={"failure"})}
      </div>
      <div>
        <h2>Failure Causal Edges</h2>
        {_table(["source", "target", "kind"], self.data.get("failure_causal_graph", {}).get("edges", []))}
      </div>
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
class InspectorRunIndex:
    """Read-only run index for AgentLedger Inspector."""

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
        source = self.data.get("source", {})
        summary = self.data.get("summary", {})
        runs = self.data.get("runs", [])
        navigation = [("runs", "Runs"), ("metadata", "Metadata")]
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Inspector Runs</title>
  <style>
    :root {{
      --bg: #f7f8f5;
      --surface: #ffffff;
      --surface-2: #f0f4ef;
      --ink: #17211b;
      --muted: #5d6b61;
      --line: #d5ded6;
      --accent: #11695f;
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
    .lede {{ margin: 0; max-width: 900px; color: var(--muted); font-size: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 18px 0 16px; }}
    .card {{ min-width: 0; padding: 13px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }}
    .value {{ display: block; margin-top: 6px; font-size: 21px; font-weight: 700; overflow-wrap: anywhere; }}
    .status-ok {{ background: var(--ok-bg); }}
    .status-warn {{ background: var(--warn-bg); }}
    .status-risk {{ background: var(--danger-bg); }}
    .section {{ margin-top: 18px; }}
    .section-note {{ margin: -4px 0 12px; color: var(--muted); font-size: 13px; }}
    .panel {{ padding: 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
    .metadata-panel {{ margin-top: 36px; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 20px; }}
    .nav a, .link-list a {{ color: var(--accent); text-decoration: none; }}
    .nav a {{ padding: 6px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); font-size: 13px; }}
    .nav a:hover, .link-list a:hover {{ text-decoration: underline; }}
    .link-list {{ display: flex; flex-wrap: wrap; gap: 6px; min-width: 160px; }}
    .link-list a {{ display: inline-flex; align-items: center; gap: 4px; max-width: 260px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 999px; background: #fbfdfb; font-size: 12px; }}
    .link-list .ref-kind {{ color: var(--muted); }}
    .run-list {{ display: grid; gap: 28px; }}
    .pager {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 0 0 12px; }}
    .pager[hidden] {{ display: none; }}
    .pager button {{ min-height: 30px; padding: 4px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); color: var(--accent); font: inherit; font-size: 13px; font-weight: 650; cursor: pointer; }}
    .pager button:disabled {{ cursor: default; color: var(--muted); opacity: 0.55; }}
    .pager-status {{ color: var(--muted); font-size: 13px; }}
    .run-item {{ min-width: 0; max-width: 100%; padding: 16px 18px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); overflow: hidden; }}
    .run-item.warn {{ border-color: #e0c46e; background: var(--warn-bg); }}
    .run-item.risk {{ border-color: #e4b6b6; background: var(--danger-bg); }}
    .run-head {{ display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; }}
    .run-title {{ min-width: 0; flex: 1 1 420px; }}
    .run-title h3 {{ margin: 0; font-size: 16px; line-height: 1.3; letter-spacing: 0; overflow-wrap: anywhere; }}
    .run-title a {{ color: var(--ink); text-decoration: none; }}
    .run-title a:hover {{ color: var(--accent); text-decoration: underline; }}
    .run-sub {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .badge {{ display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; padding: 5px 9px; border: 1px solid var(--line); border-radius: 999px; background: #fbfdfb; color: var(--ink); font-size: 12px; overflow-wrap: anywhere; word-break: break-word; white-space: normal; }}
    .badge-label {{ flex: 0 0 auto; color: var(--muted); }}
    .badge-value {{ min-width: 0; overflow-wrap: anywhere; word-break: break-word; }}
    .badge.ok {{ background: var(--ok-bg); }}
    .badge.warn {{ background: #fff9e8; border-color: #e0c46e; }}
    .badge.risk {{ background: #fff7f7; border-color: #e4b6b6; color: var(--danger); }}
    .run-actions {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; max-width: 100%; }}
    .run-actions a {{ display: inline-flex; align-items: center; min-height: 28px; padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: #fbfdfb; color: var(--accent); font-size: 13px; font-weight: 650; text-decoration: none; }}
    .run-actions a:hover {{ text-decoration: underline; }}
    .run-fields {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 20px; margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--line); }}
    .run-field {{ min-width: 0; }}
    .run-field .label {{ text-transform: none; letter-spacing: 0; }}
    .run-field .field-value {{ display: block; margin-top: 3px; font-size: 13px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }}
    .run-metrics {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .metric {{ display: inline-flex; align-items: baseline; gap: 6px; min-width: 0; padding: 5px 9px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255, 255, 255, 0.72); font-size: 12px; }}
    .metric strong {{ font-size: 13px; }}
    .run-details {{ margin: 16px 0 6px; }}
    details {{ margin-top: 4px; max-width: 100%; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 650; }}
    pre {{ max-width: 100%; max-height: 300px; overflow: auto; padding: 11px; border: 1px solid var(--line); border-radius: 8px; background: #fbfdfb; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }}
    :target {{ scroll-margin-top: 14px; outline: 2px solid #82b7ad; outline-offset: 2px; }}
    @media (max-width: 900px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .run-title {{ flex-basis: 100%; }}
      .run-actions {{ justify-content: flex-start; }}
    }}
    @media (max-width: 760px) {{
      .run-fields {{ grid-template-columns: 1fr; }}
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
      <h1>AgentLedger Inspector Runs</h1>
      <p class="lede">Read-only run index generated from AgentLedger runtime metadata. It does not start a server, mutate state, call tools, approve requests, or manage users.</p>
    </header>
    {_nav(navigation)}
    <section class="cards">
      <div class="card"><span class="label">Runs</span><span class="value">{summary.get("run_count", 0)}</span></div>
      <div class="card status-warn"><span class="label">Active</span><span class="value">{summary.get("active_run_count", 0)}</span></div>
      <div class="card status-risk"><span class="label">Failed</span><span class="value">{summary.get("failed_run_count", 0)}</span></div>
      <div class="card"><span class="label">Total USD</span><span class="value">{escape(str(summary.get("total_usd", 0)))}</span></div>
    </section>
    <section class="section" id="runs">
      <h2>Runs</h2>
      <p class="section-note">Single-run Inspector links are shown when a run link template is configured.</p>
      {_run_index_list(runs)}
    </section>
    <section class="panel metadata-panel" id="metadata">
      <h2>Metadata</h2>
      <pre>{_json_block({"schema_version": self.data.get("schema_version"), "source": source, "summary": summary})}</pre>
    </section>
  </main>
  {_run_index_script()}
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
        events = [_safe_dict(event) for event in evidence.get("events", [])]
        timeline = [_timeline_event(event, include_payloads=include_payloads) for event in events]
        policy_decisions = [_policy_decision(event, include_payloads=include_payloads) for event in events if event.get("type") == "tool_permission_decided"]
        policy_decisions = [row for row in policy_decisions if row is not None]
        _decorate_report_links(timeline=timeline, steps=steps, ledger=ledger, approvals=approvals, policy_decisions=policy_decisions, artifacts=artifacts)
        agent_run_id = _find_agent_run_id(evidence)
        event_stream = _chronological_event_stream(timeline, runtime_run_id=run.get("run_id"), agent_run_id=agent_run_id)
        failure_events = [event for event in timeline if _is_failure_event(event.get("type"))]
        failure_envelopes = FailureEnvelopeBuilder().from_snapshot(
            run_id=str(run.get("run_id") or ""),
            run_status=str(run.get("status") or ""),
            steps=steps,
            ledger=ledger,
            approvals=approvals,
            events=events,
        )
        failure_lifecycle = FailureLifecycleBuilder().from_envelopes(
            run_id=str(run.get("run_id") or ""),
            run_status=str(run.get("status") or ""),
            envelopes=failure_envelopes,
            events=events,
        )
        failure_causal_graph = FailureCausalGraphBuilder().from_snapshot(
            run_id=str(run.get("run_id") or ""),
            run_status=str(run.get("status") or ""),
            envelopes=failure_envelopes,
            steps=steps,
            ledger=ledger,
            approvals=approvals,
            events=events,
            cost_records=cost_records,
        )
        failure_replay_plan = FailureReplayPlanner().plan(
            run_id=str(run.get("run_id") or ""),
            envelopes=failure_envelopes,
            ledger=ledger,
            events=events,
        )
        failure_alerts = FailureAlertEvaluator().evaluate(
            run_id=str(run.get("run_id") or ""),
            envelopes=failure_envelopes,
            replay_plan=failure_replay_plan,
            cost_records=cost_records,
        )
        _decorate_failure_envelope_links(failure_envelopes=failure_envelopes, timeline=timeline, steps=steps, ledger=ledger, approvals=approvals)
        summary = {
            **_safe_dict(evidence.get("summary")),
            "event_type_counts": dict(Counter(event.get("type", "-") for event in events)),
            "step_status_counts": dict(Counter(row.get("status", "-") for row in steps)),
            "tool_ledger_status_counts": dict(Counter(row.get("status", "-") for row in ledger)),
            "approval_status_counts": dict(Counter(row.get("status", "-") for row in approvals)),
            "failure_event_count": len(failure_events),
            "failure_envelope_count": len(failure_envelopes),
            "failure_lifecycle_event_count": len(failure_lifecycle.get("events", [])),
            "failure_alert_count": failure_alerts.get("alert_count", 0),
            "unsafe_replay_side_effect_count": failure_replay_plan.get("unsafe_side_effect_count", 0),
            "terminal_failure_count": sum(1 for item in failure_envelopes if item.get("status") == "terminal"),
            "recoverable_failure_count": sum(1 for item in failure_envelopes if item.get("recoverability") in {"auto_retry", "recoverable", "manual_verification", "human_required"}),
            "policy_decision_count": len(policy_decisions),
        }
        failure_export = FailureExportMapper().export(
            run_id=str(run.get("run_id") or ""),
            run_status=str(run.get("status") or ""),
            summary=summary,
            envelopes=failure_envelopes,
            lifecycle=failure_lifecycle,
            causal_graph=failure_causal_graph,
            replay_plan=failure_replay_plan,
            alerts=failure_alerts,
        )
        risk_flags = _risk_flags(summary, steps, ledger, approvals, failure_events, policy_decisions)
        data = {
            "schema_version": INSPECTOR_SCHEMA_VERSION,
            "source": source or {"kind": "evidence_bundle"},
            "run": run,
            "summary": summary,
            "risk_flags": risk_flags,
            "agent_run_id": agent_run_id,
            "event_stream": event_stream,
            "timeline": timeline,
            "steps": steps,
            "tool_ledger": ledger,
            "approvals": approvals,
            "policy_decisions": policy_decisions,
            "cost_records": cost_records,
            "failure_events": failure_events,
            "failure_envelopes": failure_envelopes,
            "failure_lifecycle": failure_lifecycle,
            "failure_causal_graph": failure_causal_graph,
            "failure_replay_plan": failure_replay_plan,
            "failure_alerts": failure_alerts,
            "failure_export": failure_export,
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

    def run_index(
        self,
        *,
        store: EvidenceStateStoreProtocol,
        blobs: EvidenceBlobStoreProtocol | None = None,
        limit: int = 100,
        status: str | None = None,
        source: dict[str, Any] | None = None,
        run_link_template: str | None = None,
    ) -> InspectorRunIndex:
        rows = [_run_index_row(store=store, blobs=blobs, run=row, run_link_template=run_link_template) for row in store.runs(limit=limit, status=status)]
        active_statuses = {"pending", "running", "waiting_human", "retry_scheduled"}
        summary = {
            "run_count": len(rows),
            "active_run_count": sum(1 for row in rows if row.get("status") in active_statuses),
            "failed_run_count": sum(1 for row in rows if row.get("status") == "failed"),
            "total_usd": round(sum(float(row.get("total_usd") or 0) for row in rows), 6),
            "limit": limit,
            "status_filter": status,
        }
        return InspectorRunIndex(
            {
                "schema_version": INSPECTOR_RUN_INDEX_SCHEMA_VERSION,
                "source": source or {"kind": "runtime_store"},
                "summary": summary,
                "runs": rows,
            }
        )


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

    def runs_from_runtime_store(
        self,
        *,
        store: EvidenceStateStoreProtocol,
        blobs: EvidenceBlobStoreProtocol | None = None,
        limit: int = 100,
        status: str | None = None,
        run_link_template: str | None = None,
    ) -> InspectorRunIndex:
        """Build a read-only run index from an application-provided store."""
        return self.builder.run_index(store=store, blobs=blobs, limit=limit, status=status, source={"kind": "runtime_store"}, run_link_template=run_link_template)

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

    def runs_from_sqlite(
        self,
        *,
        db_path: str | Path,
        blob_root: str | Path | None = None,
        limit: int = 100,
        status: str | None = None,
        run_link_template: str | None = None,
    ) -> InspectorRunIndex:
        store = ReadOnlySQLiteStore(db_path)
        try:
            blobs = _optional_local_blob_store(blob_root)
            return self.builder.run_index(
                store=store,
                blobs=blobs,
                limit=limit,
                status=status,
                source={"kind": "runtime_store", "backend": "sqlite", "db_path": str(db_path)},
                run_link_template=run_link_template,
            )
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

    def runs_from_postgres(
        self,
        *,
        dsn: str,
        schema: str = "agentledger",
        blob_root: str | Path | None = None,
        limit: int = 100,
        status: str | None = None,
        run_link_template: str | None = None,
    ) -> InspectorRunIndex:
        store = ReadOnlyPostgresStore(PostgresStoreConfig(dsn=dsn, schema=schema))
        try:
            store._configure_schema()
            blobs = _optional_local_blob_store(blob_root)
            return self.builder.run_index(
                store=store,
                blobs=blobs,
                limit=limit,
                status=status,
                source={"kind": "runtime_store", "backend": "postgres", "schema": schema},
                run_link_template=run_link_template,
            )
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

    def runs_from_mysql(
        self,
        *,
        dsn: str,
        database: str | None = None,
        blob_root: str | Path | None = None,
        limit: int = 100,
        status: str | None = None,
        run_link_template: str | None = None,
    ) -> InspectorRunIndex:
        store = ReadOnlyMySQLStore(MySQLStoreConfig(dsn=dsn, database=database))
        try:
            store._configure_schema()
            blobs = _optional_local_blob_store(blob_root)
            return self.builder.run_index(
                store=store,
                blobs=blobs,
                limit=limit,
                status=status,
                source={"kind": "runtime_store", "backend": "mysql", "database": database},
                run_link_template=run_link_template,
            )
        finally:
            store.close()


def _run_summary(run: Any) -> dict[str, Any]:
    row = _safe_dict(run)
    return {key: row.get(key) for key in ["run_id", "session_id", "status", "state_version", "created_at", "updated_at", "initial_state"] if key in row}


def _run_index_row(
    *,
    store: EvidenceStateStoreProtocol,
    blobs: EvidenceBlobStoreProtocol | None,
    run: Any,
    run_link_template: str | None,
) -> dict[str, Any]:
    run_row = _plain_dict(run)
    run_id = str(run_row.get("run_id", ""))
    steps = [_plain_dict(row) for row in store.steps(run_id)]
    events = [_plain_dict(row) for row in store.events(run_id)]
    ledger = [_plain_dict(row) for row in store.ledger(run_id)]
    approvals = [_plain_dict(row) for row in store.approval_requests(run_id)]
    cost_summary = _safe_dict(store.cost_summary(run_id))
    agent_run_id = _find_agent_run_id(run_row)
    if agent_run_id is None:
        agent_run_id = _find_agent_run_id(_decode_json_field(run_row.get("state_json")))
    if agent_run_id is None:
        agent_run_id = _find_agent_run_id(_decode_json_field(run_row.get("initial_state")))
    if agent_run_id is None:
        agent_run_id = _agent_run_id_from_events(events, blobs)
    failure_count = sum(1 for event in events if _is_failure_event(event.get("type"))) + sum(1 for step in steps if step.get("status") == "failed")
    status = run_row.get("status")
    row = {
        "run_id": run_id,
        "agent_run_id": agent_run_id or "-",
        "session_id": run_row.get("session_id", "-"),
        "status": status or "-",
        "created_at": _format_timestamp(run_row.get("created_at")),
        "updated_at": _format_timestamp(run_row.get("updated_at")),
        "event_count": len(events),
        "step_count": len(steps),
        "tool_call_count": len(ledger),
        "approval_count": len(approvals),
        "failure_count": failure_count,
        "total_usd": round(float(cost_summary.get("total_usd") or 0), 6),
        "severity": "risk" if status in {"failed", "cancelled"} or failure_count else "warn" if status in {"pending", "running", "waiting_human", "retry_scheduled"} else "info",
        "cost_summary": cost_summary,
        "raw_created_at": run_row.get("created_at"),
        "raw_updated_at": run_row.get("updated_at"),
    }
    href = _run_link(run_link_template, run_id)
    if href:
        row["related_links"] = [{"kind": "inspector", "value": "open", "href": href}]
    return row


def _agent_run_id_from_events(events: list[dict[str, Any]], blobs: EvidenceBlobStoreProtocol | None) -> str | None:
    for event in events:
        found = _find_agent_run_id(event)
        if found:
            return found
        payload_ref = event.get("payload_ref")
        if blobs is not None and isinstance(payload_ref, str):
            try:
                payload = decode_payload(blobs, payload_ref)
            except Exception:
                payload = None
            found = _find_agent_run_id(payload)
            if found:
                return found
    return None


def _run_link(template: str | None, run_id: str) -> str | None:
    if not template:
        return None
    return template.format(run_id=quote(run_id, safe=""), raw_run_id=run_id)


def _optional_local_blob_store(blob_root: str | Path | None) -> ReadOnlyLocalBlobStore | None:
    if blob_root is None:
        return None
    root = Path(blob_root)
    if not root.exists():
        return None
    return ReadOnlyLocalBlobStore(root)


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
        "runtime_run_id": event.get("run_id"),
        "agent_run_id": _find_agent_run_id(event),
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


def _chronological_event_stream(timeline: list[dict[str, Any]], *, runtime_run_id: Any, agent_run_id: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in timeline:
        seq = event.get("seq")
        links = []
        if event.get("anchor") and seq is not None:
            links.append({"kind": "event", "value": str(seq), "href": f"#{event['anchor']}"})
        links.extend(link for link in event.get("related_links", []) if isinstance(link, dict))
        row = {
            "time": _format_timestamp(event.get("timestamp")),
            "timestamp": event.get("timestamp"),
            "runtime_run_id": event.get("runtime_run_id") or runtime_run_id or "-",
            "agent_run_id": event.get("agent_run_id") or agent_run_id or "-",
            "seq": seq,
            "type": event.get("type"),
            "step_id": event.get("step_id"),
            "summary": event.get("summary"),
            "severity": event.get("severity"),
        }
        if links:
            row["related_links"] = _dedupe_links(links)
        rows.append(row)
    return sorted(rows, key=lambda row: (_timestamp_sort_value(row.get("timestamp")), _seq_sort_value(row.get("seq"))))


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


def _decorate_failure_envelope_links(
    *,
    failure_envelopes: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
) -> None:
    anchors: dict[tuple[str, str], str] = {}
    _collect_existing_anchor(steps, kind="step", key="step_id", anchors=anchors)
    _collect_existing_anchor(ledger, kind="tool", key="tool_name", anchors=anchors)
    _collect_existing_anchor(approvals, kind="approval", key="approval_id", anchors=anchors)
    _collect_existing_anchor(timeline, kind="event", key="seq", anchors=anchors)
    for row in failure_envelopes:
        refs = []
        for key, kind in [("step_id", "step"), ("tool_name", "tool"), ("approval_id", "approval"), ("event_seq", "event")]:
            if row.get(key) is not None:
                refs.append({"kind": kind, "value": str(row[key])})
        for ref_list_key in ["causal_refs", "evidence_refs"]:
            for ref in row.get(ref_list_key, []):
                if not isinstance(ref, dict):
                    continue
                kind = ref.get("kind")
                value = ref.get("value")
                if kind is not None and value is not None:
                    refs.append({"kind": str(kind), "value": str(value)})
        row["related_refs"] = _merge_related_refs(row.get("related_refs"), refs)
        _attach_related_links(row, anchors)


def _collect_existing_anchor(rows: list[dict[str, Any]], *, kind: str, key: str, anchors: dict[tuple[str, str], str]) -> None:
    for row in rows:
        value = row.get(key)
        anchor = row.get("anchor")
        if value is not None and anchor:
            anchors[(kind, str(value))] = str(anchor)


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


def _find_agent_run_id(value: Any, *, _depth: int = 0) -> str | None:
    if _depth > 8:
        return None
    preferred_keys = ("agent_run_id", "legal_agent_run_id", "business_agent_run_id", "workflow_run_id")
    if isinstance(value, dict):
        for key in preferred_keys:
            candidate = value.get(key)
            if candidate is not None:
                return str(candidate)
        for item in value.values():
            found = _find_agent_run_id(item, _depth=_depth + 1)
            if found:
                return found
    elif isinstance(value, list):
        for item in value[:100]:
            found = _find_agent_run_id(item, _depth=_depth + 1)
            if found:
                return found
    elif isinstance(value, str) and any(key in value for key in preferred_keys):
        parsed = _parse_json_like_string(value)
        if parsed is not None:
            return _find_agent_run_id(parsed, _depth=_depth + 1)
    return None


def _format_timestamp(value: Any) -> str:
    numeric = _numeric_timestamp(value)
    if numeric is None:
        return "-" if value is None else str(value)
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, OverflowError, ValueError):
        return str(value)


def _timestamp_sort_value(value: Any) -> float:
    numeric = _numeric_timestamp(value)
    return numeric if numeric is not None else float("inf")


def _numeric_timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return _epoch_seconds(float(value))
    if isinstance(value, str):
        text = value.strip()
        try:
            return _epoch_seconds(float(text))
        except ValueError:
            pass
        normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    return None


def _epoch_seconds(value: float) -> float:
    absolute = abs(value)
    if absolute >= 1_000_000_000_000_000:
        return value / 1_000_000
    if absolute >= 100_000_000_000:
        return value / 1_000
    return value


def _seq_sort_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for link in links:
        kind = str(link.get("kind", ""))
        value = str(link.get("value", ""))
        href = str(link.get("href", ""))
        key = (kind, value, href)
        if kind and value and href and key not in seen:
            seen.add(key)
            deduped.append({"kind": kind, "value": value, "href": href})
    return deduped


def _is_failure_event(event_type: Any) -> bool:
    return str(event_type) in {"error_raised", "step_failed", "tool_call_failed", "tool_call_blocked", "run_cancelled", "step_cancelled"}


def _is_wait_event(event_type: Any) -> bool:
    return str(event_type) in {"step_waiting_human", "approval_requested", "step_retry_scheduled", "lease_expired"}


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _plain_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    keys = getattr(value, "keys", None)
    if callable(keys):
        try:
            return {key: value[key] for key in keys()}
        except Exception:
            return {}
    return {}


def _decode_json_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


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
    head = "".join(f"<th>{escape(column)}</th>" for column in columns) + links_head
    body = "\n".join(_table_row(columns, row, risk_key=risk_key, risk_values=risk_values or set(), warn_values=warn_values or set(), include_links=include_links) for row in rows)
    return f"<div class=\"table-wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _run_index_list(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return "<p>No records.</p>"
    items = [_run_index_item(row, index=index) for index, row in enumerate(rows, start=1) if isinstance(row, dict)]
    if not items:
        return "<p>No records.</p>"
    return f"""<div class="pager" data-run-pager hidden>
  <button type="button" data-run-prev>Prev</button>
  <span class="pager-status" data-run-page-status></span>
  <button type="button" data-run-next>Next</button>
</div>
<div class="run-list" data-run-list data-page-size="20">{"".join(items)}</div>"""


def _run_index_item(row: dict[str, Any], *, index: int) -> str:
    severity = str(row.get("severity") or "info")
    css = " risk" if severity == "risk" else " warn" if severity == "warn" else ""
    status = _display_value(row.get("status"))
    status_css = _status_badge_class(status)
    run_id = _display_value(row.get("run_id"))
    href = _first_related_href(row.get("related_links"), kind="inspector")
    title = f"<a href=\"{escape(href, quote=True)}\">{escape(run_id)}</a>" if href else escape(run_id)
    metrics = [
        ("events", row.get("event_count", 0)),
        ("steps", row.get("step_count", 0)),
        ("tools", row.get("tool_call_count", 0)),
        ("approvals", row.get("approval_count", 0)),
        ("failures", row.get("failure_count", 0)),
        ("usd", row.get("total_usd", 0)),
    ]
    metric_html = "".join(f"<span class=\"metric\"><strong>{escape(str(_display_value(value)))}</strong>{escape(label)}</span>" for label, value in metrics)
    return f"""<article class="run-item{css}" data-run-item data-run-index="{index}">
  <div class="run-head">
    <div class="run-title">
      <h3>{title}</h3>
      <div class="run-sub">
        <span class="badge {status_css}"><span class="badge-value">{escape(status)}</span></span>
        <span class="badge"><span class="badge-label">agent</span><span class="badge-value">{escape(_display_value(row.get("agent_run_id")))}</span></span>
        <span class="badge"><span class="badge-label">session</span><span class="badge-value">{escape(_display_value(row.get("session_id")))}</span></span>
      </div>
    </div>
    {_run_actions(row.get("related_links"))}
  </div>
  <div class="run-fields">
    <div class="run-field"><span class="label">Created</span><span class="field-value">{escape(_display_value(row.get("created_at")))}</span></div>
    <div class="run-field"><span class="label">Updated</span><span class="field-value">{escape(_display_value(row.get("updated_at")))}</span></div>
    <div class="run-field"><span class="label">Runtime Run</span><span class="field-value">{escape(run_id)}</span></div>
    <div class="run-field"><span class="label">Agent Run</span><span class="field-value">{escape(_display_value(row.get("agent_run_id")))}</span></div>
  </div>
  <div class="run-metrics">{metric_html}</div>
  <details class="run-details"><summary>Full JSON</summary><pre>{_json_block(row)}</pre></details>
</article>"""


def _run_actions(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "<div class=\"run-actions\"></div>"
    links = []
    for item in value:
        if not isinstance(item, dict):
            continue
        href = item.get("href")
        kind = item.get("kind")
        ref_value = item.get("value")
        if not href or kind is None or ref_value is None:
            continue
        label = "Open Inspector" if str(kind) == "inspector" else f"{kind}: {ref_value}"
        links.append(f"<a href=\"{escape(str(href), quote=True)}\">{escape(str(label))}</a>")
    return "<div class=\"run-actions\">" + "".join(links) + "</div>" if links else "<div class=\"run-actions\"></div>"


def _first_related_href(value: Any, *, kind: str) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict) and item.get("kind") == kind and item.get("href"):
            return str(item["href"])
    return None


def _status_badge_class(status: str) -> str:
    if status in {"completed", "succeeded", "success"}:
        return "ok"
    if status in {"failed", "cancelled", "denied"}:
        return "risk"
    if status in {"pending", "running", "waiting_human", "retry_scheduled"}:
        return "warn"
    return ""


def _display_value(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def _inline_value(value: Any) -> str:
    return f"<span>{escape(_display_value(value))}</span>"


def _event_stream(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return "<p>No records.</p>"
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        severity = str(row.get("severity") or "info")
        css = " risk" if severity == "risk" else " warn" if severity == "warn" else ""
        seq = row.get("seq", "-")
        step = row.get("step_id") or "-"
        runtime_run_id = row.get("runtime_run_id") or "-"
        agent_run_id = row.get("agent_run_id") or "-"
        items.append(
            f"""<article class="event-item{css}">
  <div class="event-time-block">
    <div>{escape(str(row.get("time", "-")))}</div>
    <span class="event-seq">seq {escape(str(seq))}</span>
  </div>
  <div class="event-main">
    <div class="event-title">
      <span class="event-type">{escape(str(row.get("type", "-")))}</span>
    </div>
    <p class="event-summary">{escape(str(row.get("summary", "-")))}</p>
    <div class="event-meta">
      <code>runtime {escape(str(runtime_run_id))}</code>
      <code>agent {escape(str(agent_run_id))}</code>
      <code>step {escape(str(step))}</code>
    </div>
    {_link_list(row.get("related_links"))}
    <details class="event-details"><summary>JSON</summary><pre>{_json_block(row)}</pre></details>
  </div>
</article>"""
        )
    return "<div class=\"event-list\">" + "\n".join(items) + "</div>" if items else "<p>No records.</p>"


def _table_row(columns: list[str], row: dict[str, Any], *, risk_key: str | None, risk_values: set[Any], warn_values: set[Any], include_links: bool) -> str:
    status = row.get(risk_key) if risk_key else None
    css = "risk" if status in risk_values else "warn" if status in warn_values else ""
    cells = "".join(_table_cell(column, row.get(column, "-")) for column in columns)
    links = f"<td>{_link_list(row.get('related_links'))}</td>" if include_links else ""
    colspan = len(columns) + (1 if include_links else 0)
    details_row = f"<tr class=\"details-row{(' ' + css) if css else ''}\"><td colspan=\"{colspan}\"><details class=\"record-details\"><summary>JSON</summary><pre>{_json_block(row)}</pre></details></td></tr>"
    return f"<tr{_row_attrs(row.get('anchor'), css)}>{cells}{links}</tr>{details_row}"


def _table_cell(column: str, value: Any) -> str:
    css = " class=\"event-time\"" if column in {"time", "timestamp"} else ""
    return f"<td{css}>{escape(str(value))}</td>"


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


def _run_index_script() -> str:
    return """<script>
(function () {
  var list = document.querySelector('[data-run-list]');
  var pager = document.querySelector('[data-run-pager]');
  if (!list || !pager) return;
  var items = Array.prototype.slice.call(list.querySelectorAll('[data-run-item]'));
  var pageSize = parseInt(list.getAttribute('data-page-size') || '20', 10);
  if (!items.length || !isFinite(pageSize) || pageSize <= 0) return;
  if (items.length <= pageSize) return;
  var prev = pager.querySelector('[data-run-prev]');
  var next = pager.querySelector('[data-run-next]');
  var status = pager.querySelector('[data-run-page-status]');
  var page = 0;
  var pages = Math.ceil(items.length / pageSize);
  function paint() {
    var start = page * pageSize;
    var end = start + pageSize;
    items.forEach(function (item, index) {
      item.hidden = index < start || index >= end;
    });
    if (status) {
      status.textContent = 'Page ' + (page + 1) + ' / ' + pages + ' - ' + items.length + ' runs';
    }
    if (prev) prev.disabled = page <= 0;
    if (next) next.disabled = page >= pages - 1;
  }
  if (prev) {
    prev.addEventListener('click', function () {
      if (page > 0) {
        page -= 1;
        paint();
      }
    });
  }
  if (next) {
    next.addEventListener('click', function () {
      if (page < pages - 1) {
        page += 1;
        paint();
      }
    });
  }
  pager.hidden = false;
  paint();
}());
</script>"""


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
