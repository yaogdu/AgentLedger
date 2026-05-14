from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .blobstore import LocalBlobStore
from .ids import new_id, now_ts
from .store import SQLiteStore
from .tools import ToolGateway


@dataclass
class AgentContext:
    run_id: str
    session_id: str
    step_id: str
    agent_role: str
    lease_token: str
    attempt: int
    state_version: int
    store: SQLiteStore
    gateway: ToolGateway
    blobs: LocalBlobStore
    pending_patch: dict[str, Any] = field(default_factory=dict)

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        return await self.gateway.call(self, tool_name, args)

    async def call_model(self, request: dict[str, Any]) -> dict[str, Any]:
        """v0.1 model boundary: archive request/response without real provider dependency."""
        req_hash, req_ref = self.blobs.put_json(request)
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="model_call_requested", payload={"request_ref": req_ref}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=req_hash, payload_ref=req_ref)
        response = {"content": request.get("mock_response", ""), "provider": "mock"}
        resp_hash, resp_ref = self.blobs.put_json(response)
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="model_call_completed", payload={"response_ref": resp_ref}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=resp_hash, payload_ref=resp_ref)
        return response

    def write_state_patch(self, key: str, patch: Any) -> None:
        self.pending_patch[key] = patch
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="state_patch_proposed", payload={"key": key, "patch": patch}, agent_role=self.agent_role, state_version=self.state_version)

    async def create_artifact(self, name: str, content: Any, metadata: dict[str, Any] | None = None) -> str:
        digest, ref = self.blobs.put_json(content)
        artifact_id = new_id("art")
        self.store.conn.execute(
            "INSERT INTO artifacts(artifact_id, run_id, step_id, name, blob_hash, blob_ref, metadata_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (artifact_id, self.run_id, self.step_id, name, digest, ref, json.dumps(metadata or {}), now_ts()),
        )
        self.store.conn.commit()
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="artifact_created", payload={"artifact_id": artifact_id, "name": name}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=digest, payload_ref=ref)
        return artifact_id

    def yield_(self, reason: str, next_intent: str | None = None) -> dict[str, Any]:
        return {"status": "yield", "reason": reason, "next_intent": next_intent}
