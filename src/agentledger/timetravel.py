from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
from typing import Any

from .blobstore import LocalBlobStore
from .diff import diff_dict
from .evidence import decode_payload
from .jsonutil import merge_patch
from .store import SQLiteStore


@dataclass(frozen=True)
class TimeTravelFrame:
    seq: int
    event_id: str
    event_type: str
    step_id: str | None
    agent_role: str | None
    state_version: int | None
    timestamp: float
    state_changed: bool
    changed_keys: list[str]
    patch: dict[str, Any] | None = None
    state_diff: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "seq": self.seq,
            "event_id": self.event_id,
            "type": self.event_type,
            "step_id": self.step_id,
            "agent_role": self.agent_role,
            "state_version": self.state_version,
            "timestamp": self.timestamp,
            "state_changed": self.state_changed,
            "changed_keys": self.changed_keys,
            "patch": self.patch,
        }
        if self.state_diff is not None:
            payload["state_diff"] = self.state_diff
        if self.state_after is not None:
            payload["state_after"] = self.state_after
        return payload


@dataclass(frozen=True)
class TimeTravelReport:
    run_id: str
    at_seq: int | None
    event_count: int
    timeline: list[TimeTravelFrame]
    state_at_seq: dict[str, Any]
    selected_event: TimeTravelFrame | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "at_seq": self.at_seq,
            "event_count": self.event_count,
            "timeline": [frame.to_dict() for frame in self.timeline],
            "state_at_seq": self.state_at_seq,
            "selected_event": self.selected_event.to_dict() if self.selected_event is not None else None,
        }

    def to_html(self) -> str:
        """Render a dependency-free static debug report for local incident review."""
        changed_count = sum(1 for frame in self.timeline if frame.state_changed)
        rows = "\n".join(_frame_row(frame) for frame in self.timeline)
        selected = self.selected_event.to_dict() if self.selected_event is not None else None
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgentLedger Time Travel Report</title>
  <style>
    :root {{
      --bg: #f5f0e8;
      --ink: #201a16;
      --muted: #6d6259;
      --line: #d8c9b9;
      --panel: #fffaf2;
      --accent: #0f6b5f;
      --changed: #ffe0a8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: radial-gradient(circle at top left, #fff7d1 0, transparent 28rem), linear-gradient(135deg, #f9efe1, var(--bg));
      font-family: Georgia, "Times New Roman", serif;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(30px, 4vw, 54px); line-height: 1; letter-spacing: -0.04em; }}
    .lede {{ margin: 0 0 24px; color: var(--muted); font-size: 17px; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 22px; }}
    .card {{ padding: 14px 16px; border: 1px solid var(--line); background: rgba(255,250,242,0.86); border-radius: 16px; box-shadow: 0 16px 36px rgba(32,26,22,0.06); }}
    .label {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .value {{ display: block; margin-top: 6px; font-size: 22px; font-weight: 700; overflow-wrap: anywhere; }}
    table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 18px; background: var(--panel); box-shadow: 0 18px 46px rgba(32,26,22,0.08); }}
    th, td {{ padding: 11px 12px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }}
    th {{ background: #eadccc; color: #4a4038; font-size: 12px; text-transform: uppercase; letter-spacing: 0.07em; }}
    tr.changed td {{ background: linear-gradient(90deg, var(--changed), var(--panel) 44%); }}
    code {{ padding: 2px 5px; border-radius: 7px; background: #efe2d1; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    details {{ margin-top: 6px; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; }}
    pre {{ max-height: 260px; overflow: auto; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: #fffdf8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.45; }}
    .section {{ margin-top: 22px; }}
    @media (max-width: 820px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>AgentLedger Time Travel Report</h1>
    <p class="lede">Static debug artifact generated from the event log. It is safe to archive and does not start a server.</p>
    <section class="cards">
      <div class="card"><span class="label">Run</span><span class="value">{escape(self.run_id)}</span></div>
      <div class="card"><span class="label">Events</span><span class="value">{self.event_count}</span></div>
      <div class="card"><span class="label">State Changes</span><span class="value">{changed_count}</span></div>
      <div class="card"><span class="label">Selected Seq</span><span class="value">{self.at_seq if self.at_seq is not None else "-"}</span></div>
    </section>
    <section>
      <table>
        <thead>
          <tr><th>Seq</th><th>Event</th><th>Step</th><th>Role</th><th>State</th><th>Changed Keys</th><th>Details</th></tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </section>
    <section class="section">
      <h2>State At Selected Point</h2>
      <pre>{_json_block(self.state_at_seq)}</pre>
    </section>
    <section class="section">
      <h2>Selected Event</h2>
      <pre>{_json_block(selected)}</pre>
    </section>
  </main>
</body>
</html>
"""

    def write_html(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_html(), encoding="utf-8")
        return target


class TimeTravelDebugger:
    """Reconstruct committed state checkpoints from an append-only event log."""

    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def inspect(self, run_id: str, *, at_seq: int | None = None, include_states: bool = False, include_diffs: bool = False) -> TimeTravelReport:
        state: dict[str, Any] = {}
        state_at_seq: dict[str, Any] | None = None
        selected_event: TimeTravelFrame | None = None
        timeline: list[TimeTravelFrame] = []
        rows = self.store.events(run_id)
        for row in rows:
            payload = decode_payload(self.blobs, row["payload_ref"])
            before = deepcopy(state)
            patch = self._patch_for_event(row["type"], payload)
            if patch is not None:
                state = merge_patch(state, patch)
            changes = diff_dict(before, state)
            frame = TimeTravelFrame(
                seq=int(row["seq"]),
                event_id=row["event_id"],
                event_type=row["type"],
                step_id=row["step_id"],
                agent_role=row["agent_role"],
                state_version=row["state_version"],
                timestamp=float(row["timestamp"]),
                state_changed=changes["changed_count"] > 0,
                changed_keys=sorted(changes["changed"].keys()),
                patch=patch,
                state_diff=changes if include_diffs else None,
                state_after=deepcopy(state) if include_states else None,
            )
            timeline.append(frame)
            if at_seq is not None and int(row["seq"]) <= at_seq:
                state_at_seq = deepcopy(state)
                selected_event = frame

        if at_seq is None:
            state_at_seq = deepcopy(state)
        elif state_at_seq is None:
            state_at_seq = {}
        return TimeTravelReport(
            run_id=run_id,
            at_seq=at_seq,
            event_count=len(timeline),
            timeline=timeline,
            state_at_seq=state_at_seq,
            selected_event=selected_event,
        )

    def _patch_for_event(self, event_type: str, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        if event_type == "run_created":
            initial_state = payload.get("initial_state", {})
            return initial_state if isinstance(initial_state, dict) else {}
        if event_type in {"state_committed", "system_state_patch_applied"}:
            patch = payload.get("patch")
            return patch if isinstance(patch, dict) else {}
        return None


def _frame_row(frame: TimeTravelFrame) -> str:
    css = " class=\"changed\"" if frame.state_changed else ""
    changed = ", ".join(frame.changed_keys) if frame.changed_keys else "-"
    state_version = frame.state_version if frame.state_version is not None else "-"
    details = {
        "event_id": frame.event_id,
        "timestamp": frame.timestamp,
        "patch": frame.patch,
        "state_diff": frame.state_diff,
        "state_after": frame.state_after,
    }
    return f"""          <tr{css}>
            <td><code>{frame.seq}</code></td>
            <td>{escape(frame.event_type)}</td>
            <td>{escape(frame.step_id or "-")}</td>
            <td>{escape(frame.agent_role or "-")}</td>
            <td>{state_version}</td>
            <td>{escape(changed)}</td>
            <td><details><summary>Inspect</summary><pre>{_json_block(details)}</pre></details></td>
          </tr>"""


def _json_block(value: Any) -> str:
    return escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
