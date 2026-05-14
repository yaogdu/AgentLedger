from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .blobstore import LocalBlobStore
from .store import SQLiteStore


@dataclass
class ReplaySummary:
    run_id: str
    event_count: int
    tool_call_count: int
    final_state: dict[str, Any]


class ReplayEngine:
    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def replay(self, run_id: str) -> ReplaySummary:
        events = self.store.events(run_id)
        tools = [e for e in events if e["type"].startswith("tool_call_")]
        # v0.1 replay validates evidence availability but never calls providers/tools.
        for event in events:
            ref = event["payload_ref"]
            if isinstance(ref, str) and ref.startswith("blob://"):
                self.blobs.get_json(ref)
        return ReplaySummary(run_id=run_id, event_count=len(events), tool_call_count=len(tools), final_state=self.store.final_state(run_id))
