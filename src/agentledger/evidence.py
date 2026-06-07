from __future__ import annotations

from html import escape
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .blobstore import LocalBlobStore
from .jsonutil import sha256_json
from .store import SQLiteStore


def row_to_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def decode_payload(blobs: LocalBlobStore, payload_ref: str | None) -> Any:
    if payload_ref is None:
        return None
    if payload_ref.startswith("blob://"):
        return blobs.get_json(payload_ref)
    try:
        return json.loads(payload_ref)
    except json.JSONDecodeError:
        return payload_ref


@dataclass(frozen=True)
class EvidenceBundle:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True)

    def to_html(self) -> str:
        data = self.to_dict()
        run = data.get("run", {})
        summary = data.get("summary", {})
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Evidence Report</title>
  <style>
    :root {{
      --bg: #eef2ea;
      --ink: #17211b;
      --muted: #667368;
      --line: #cad7cc;
      --panel: #fbfff8;
      --accent: #2f6f4e;
      --warn: #fff0c2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at 10% 0%, #fff3bf 0, transparent 26rem), linear-gradient(135deg, #f7f3e7, var(--bg));
      font-family: Georgia, "Times New Roman", serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 52px); letter-spacing: -0.04em; }}
    h2 {{ margin: 28px 0 12px; font-size: 24px; }}
    .lede {{ margin: 0 0 24px; color: var(--muted); font-size: 17px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    .card {{ padding: 14px 16px; border: 1px solid var(--line); background: rgba(251,255,248,0.9); border-radius: 16px; box-shadow: 0 16px 36px rgba(23,33,27,0.06); }}
    .label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .value {{ display: block; margin-top: 6px; font-size: 22px; font-weight: 700; overflow-wrap: anywhere; }}
    table {{ width: 100%; table-layout: fixed; border-collapse: collapse; overflow: hidden; border-radius: 16px; background: var(--panel); box-shadow: 0 14px 34px rgba(23,33,27,0.07); }}
    th, td {{ padding: 10px 11px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: #dfe8dc; color: #334137; font-size: 12px; text-transform: uppercase; letter-spacing: 0.07em; }}
    tr.risk td {{ background: linear-gradient(90deg, var(--warn), var(--panel) 48%); }}
    tr.details-row td {{ padding-top: 0; background: #fefff9; }}
    tr.details-row.risk td {{ background: linear-gradient(90deg, var(--warn), var(--panel) 48%); }}
    .record-details {{ margin: 0; }}
    code {{ padding: 2px 5px; border-radius: 7px; background: #e7eee5; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    details {{ margin-top: 5px; max-width: 100%; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; }}
    pre {{ max-width: 100%; max-height: 260px; overflow: auto; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #fefff9; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word; }}
    @media (max-width: 820px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>AgentLedger Evidence Report</h1>
    <p class="lede">Static review artifact generated from an evidence bundle. It does not start a server or call tools.</p>
    <section class="cards">
      <div class="card"><span class="label">Run</span><span class="value">{escape(str(run.get("run_id", "-")))}</span></div>
      <div class="card"><span class="label">Status</span><span class="value">{escape(str(run.get("status", "-")))}</span></div>
      <div class="card"><span class="label">Events</span><span class="value">{summary.get("event_count", 0)}</span></div>
      <div class="card"><span class="label">Bundle Hash</span><span class="value">{escape(str(data.get("bundle_hash", "-")))}</span></div>
    </section>
    <h2>Summary</h2>
    <pre>{_json_block(summary)}</pre>
    <h2>Final State</h2>
    <pre>{_json_block(data.get("final_state", {}))}</pre>
    <h2>Steps</h2>
    {_table(["step_id", "status", "attempt", "last_error_type"], data.get("steps", []), risk_key="status", risk_values={"failed", "waiting_human", "retry_scheduled"})}
    <h2>Tool Ledger</h2>
    {_table(["tool_name", "status", "external_id", "error_type"], data.get("tool_ledger", []), risk_key="status", risk_values={"PENDING_VERIFICATION", "RUNNING", "RESERVED"})}
    <h2>Approvals</h2>
    {_table(["approval_id", "tool_name", "risk_level", "status"], data.get("approval_requests", []), risk_key="status", risk_values={"PENDING", "DENIED"})}
    <h2>Artifacts</h2>
    {_table(["name", "blob_hash", "blob_ref", "metadata_json"], data.get("artifacts", []))}
    <h2>Media Artifacts</h2>
    {_table(["name", "kind", "uri", "content_ref", "blob_ref"], data.get("media_artifacts", []))}
    <h2>Stream Checkpoints</h2>
    {_table(["name", "stream_id", "consumer_id", "offset", "watermark", "blob_ref"], data.get("stream_checkpoints", []))}
    <h2>Cost Records</h2>
    {_table(["category", "name", "amount", "unit"], data.get("cost_records", []))}
    <h2>Events</h2>
    {_table(["seq", "type", "step_id", "agent_role"], data.get("events", []), risk_key="type", risk_values={"error_raised", "step_failed", "tool_call_failed", "tool_call_blocked"})}
  </main>
</body>
</html>
"""

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

    def write_dir(self, path: str | Path) -> Path:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        (target / "bundle.json").write_text(self.to_json() + "\n", encoding="utf-8")
        for name in ["steps", "tool_ledger", "approval_requests", "artifacts", "media_artifacts", "stream_checkpoints", "cost_records"]:
            (target / f"{name}.json").write_text(json.dumps(data.get(name, []), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "events.jsonl").write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in data.get("events", [])), encoding="utf-8")
        (target / "summary.json").write_text(json.dumps(data.get("summary", {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (target / "final_state.json").write_text(json.dumps(data.get("final_state", {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": data.get("schema_version"),
            "bundle_hash": data.get("bundle_hash"),
            "run_id": data.get("run", {}).get("run_id"),
            "files": ["bundle.json", "summary.json", "events.jsonl", "steps.json", "tool_ledger.json", "approval_requests.json", "artifacts.json", "media_artifacts.json", "stream_checkpoints.json", "cost_records.json", "final_state.json"],
        }
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target


class EvidenceExporter:
    """Build a replay-ready and external-eval-ready evidence bundle for a run."""

    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def export(self, run_id: str) -> EvidenceBundle:
        run_row = self.store.run(run_id)
        run = row_to_dict(run_row)
        events: list[dict[str, Any]] = []
        initial_state: dict[str, Any] = {}
        for row in self.store.events(run_id):
            event = row_to_dict(row)
            payload = decode_payload(self.blobs, event.get("payload_ref"))
            event["payload"] = payload
            events.append(event)
            if event["type"] == "run_created" and isinstance(payload, dict):
                initial_state = payload.get("initial_state", {})
        steps = [row_to_dict(row) for row in self.store.steps(run_id)]
        ledger = [row_to_dict(row) for row in self.store.ledger(run_id)]
        approvals = [row_to_dict(row) for row in self.store.approval_requests(run_id)]
        artifacts = [_artifact_row(row) for row in self.store.artifacts(run_id)]
        media_artifacts = [entry for row in artifacts if (entry := _media_artifact(row)) is not None]
        stream_checkpoints = [entry for row in artifacts if (entry := _stream_checkpoint(row)) is not None]
        costs = [row_to_dict(row) for row in self.store.cost_records(run_id)]
        final_state = self.store.final_state(run_id)
        summary = {
            "event_count": len(events),
            "step_count": len(steps),
            "tool_ledger_count": len(ledger),
            "artifact_count": len(artifacts),
            "media_artifact_count": len(media_artifacts),
            "stream_checkpoint_count": len(stream_checkpoints),
            "approval_count": len(approvals),
            "has_pending_approvals": any(row.get("status") == "PENDING" for row in approvals),
            "cost_summary": self.store.cost_summary(run_id),
            "has_pending_verification": any(row.get("status") == "PENDING_VERIFICATION" for row in ledger),
            "has_failed_steps": any(row.get("status") == "failed" for row in steps),
        }
        data = {
            "schema_version": "agentledger.evidence.v1",
            "bundle_hash": None,
            "run": {**run, "initial_state": initial_state},
            "steps": steps,
            "events": events,
            "tool_ledger": ledger,
            "approval_requests": approvals,
            "artifacts": artifacts,
            "media_artifacts": media_artifacts,
            "stream_checkpoints": stream_checkpoints,
            "cost_records": costs,
            "summary": summary,
            "final_state": final_state,
        }
        data["bundle_hash"] = sha256_json({key: value for key, value in data.items() if key != "bundle_hash"})
        return EvidenceBundle(data)


def _table(columns: list[str], rows: list[dict[str, Any]], *, risk_key: str | None = None, risk_values: set[str] | None = None) -> str:
    if not rows:
        return "<p>No records.</p>"
    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = "\n".join(_table_row(columns, row, risk_key=risk_key, risk_values=risk_values or set()) for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _table_row(columns: list[str], row: dict[str, Any], *, risk_key: str | None, risk_values: set[str]) -> str:
    risk = risk_key is not None and str(row.get(risk_key)) in risk_values
    cells = "".join(f"<td>{escape(str(row.get(column, '-')))}</td>" for column in columns)
    css = " class=\"risk\"" if risk else ""
    details_css = "details-row risk" if risk else "details-row"
    details = f"<tr class=\"{details_css}\"><td colspan=\"{len(columns)}\"><details class=\"record-details\"><summary>JSON</summary><pre>{_json_block(row)}</pre></details></td></tr>"
    return f"<tr{css}>{cells}</tr>{details}"


def _json_block(value: Any) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _artifact_row(row: Any) -> dict[str, Any]:
    artifact = row_to_dict(row)
    artifact["metadata"] = _metadata(artifact)
    return artifact


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata_json")
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    return {}


def _media_artifact(row: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _metadata(row).get("agentledger_media")
    if not isinstance(metadata, dict):
        return None
    return {
        "artifact_id": row.get("artifact_id"),
        "name": row.get("name"),
        "blob_hash": row.get("blob_hash"),
        "blob_ref": row.get("blob_ref"),
        "kind": metadata.get("kind"),
        "uri": metadata.get("uri"),
        "content_ref": metadata.get("content_ref"),
        "metadata": metadata.get("metadata", {}),
        "lineage": metadata.get("lineage", {}),
    }


def _stream_checkpoint(row: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _metadata(row).get("agentledger_stream")
    if not isinstance(metadata, dict):
        return None
    return {
        "artifact_id": row.get("artifact_id"),
        "name": row.get("name"),
        "blob_hash": row.get("blob_hash"),
        "blob_ref": row.get("blob_ref"),
        "stream_id": metadata.get("stream_id"),
        "consumer_id": metadata.get("consumer_id"),
        "offset": metadata.get("offset"),
        "watermark": metadata.get("watermark"),
        "chunk": metadata.get("chunk", {}),
        "partial_result_ref": metadata.get("partial_result_ref"),
        "backpressure": metadata.get("backpressure", {}),
    }
