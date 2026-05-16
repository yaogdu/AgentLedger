from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .blobstore import LocalBlobStore
from .cost import BudgetController
from .media import ArtifactLineage, EventStreamCheckpoint, MediaArtifact, MediaMetadata, StreamChunkRef
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
    budget: BudgetController
    execution_mode: str = "normal"
    source_run_id: str | None = None
    pending_patch: dict[str, Any] = field(default_factory=dict)

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        return await self.gateway.call(self, tool_name, args)

    def heartbeat(self, lease_seconds: int = 60) -> float:
        return self.store.heartbeat(step_id=self.step_id, lease_token=self.lease_token, lease_seconds=lease_seconds)

    async def call_model(self, request: dict[str, Any]) -> dict[str, Any]:
        """Stable model boundary: archive request/response and record usage.

        Real providers will live behind a ModelProvider adapter. The local runtime
        keeps a mock provider so replay/evidence-check/CLI flows work with zero network deps.
        """
        usage_hint = request.get("mock_usage", {}) if isinstance(request, dict) else {}
        estimated_tokens = int(usage_hint.get("total_tokens", request.get("estimated_tokens", 0) if isinstance(request, dict) else 0) or 0)
        self.budget.before_model_call(self.store, self.run_id, estimated_tokens=estimated_tokens)
        req_hash, req_ref = self.blobs.put_json(request)
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="model_call_requested", payload={"request_ref": req_ref}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=req_hash, payload_ref=req_ref)
        response = {
            "content": request.get("mock_response", ""),
            "provider": request.get("provider", "mock"),
            "usage": usage_hint or {"total_tokens": 0},
        }
        resp_hash, resp_ref = self.blobs.put_json(response)
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="model_call_completed", payload={"response_ref": resp_ref}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=resp_hash, payload_ref=resp_ref)
        total_tokens = int(response["usage"].get("total_tokens", 0) or 0)
        if total_tokens:
            self.store.record_cost(
                run_id=self.run_id,
                session_id=self.session_id,
                step_id=self.step_id,
                category="model",
                name=response["provider"],
                amount=float(total_tokens),
                unit="token",
                metadata={"usage": response["usage"]},
            )
        cost_usd = float(request.get("mock_cost_usd", 0.0) or 0.0)
        if cost_usd:
            self.store.record_cost(
                run_id=self.run_id,
                session_id=self.session_id,
                step_id=self.step_id,
                category="model",
                name=response["provider"],
                amount=cost_usd,
                unit="usd",
                metadata={"usage": response["usage"]},
            )
            self.budget.after_cost_recorded(self.store, self.run_id)
        return response

    def write_state_patch(self, key: str, patch: Any) -> None:
        self.pending_patch[key] = patch
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="state_patch_proposed", payload={"key": key, "patch": patch}, agent_role=self.agent_role, state_version=self.state_version)

    async def create_artifact(self, name: str, content: Any, metadata: dict[str, Any] | None = None) -> str:
        digest, ref = self.blobs.put_json(content)
        artifact_id = self.store.create_artifact(run_id=self.run_id, step_id=self.step_id, name=name, blob_hash=digest, blob_ref=ref, metadata=metadata)
        self.store.append_event(run_id=self.run_id, session_id=self.session_id, step_id=self.step_id, event_type="artifact_created", payload={"artifact_id": artifact_id, "name": name}, agent_role=self.agent_role, state_version=self.state_version, payload_hash=digest, payload_ref=ref)
        return artifact_id

    async def create_media_artifact(
        self,
        name: str,
        kind: str,
        *,
        uri: str | None = None,
        content_ref: str | None = None,
        media_metadata: MediaMetadata | dict[str, Any] | None = None,
        lineage: ArtifactLineage | dict[str, Any] | None = None,
        derived_outputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a media manifest artifact without processing raw media bytes."""

        artifact = MediaArtifact(
            kind=kind,
            uri=uri,
            content_ref=content_ref,
            metadata=media_metadata,
            lineage=lineage,
            derived_outputs=derived_outputs or {},
        )
        artifact_metadata = dict(metadata or {})
        artifact_metadata.update(artifact.to_artifact_metadata())
        return await self.create_artifact(name=name, content=artifact.to_content(), metadata=artifact_metadata)

    async def create_stream_checkpoint(
        self,
        name: str,
        *,
        stream_id: str,
        consumer_id: str,
        offset: int | str,
        watermark: float | str | None = None,
        chunk: StreamChunkRef | dict[str, Any] | None = None,
        partial_result_ref: str | None = None,
        backpressure: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a resumable stream cursor as a normal runtime artifact."""

        checkpoint = EventStreamCheckpoint(
            stream_id=stream_id,
            consumer_id=consumer_id,
            offset=offset,
            watermark=watermark,
            chunk=chunk,
            partial_result_ref=partial_result_ref,
            backpressure=backpressure or {},
            metadata=metadata or {},
        )
        artifact_metadata = checkpoint.to_artifact_metadata()
        return await self.create_artifact(name=name, content=checkpoint.to_content(), metadata=artifact_metadata)

    def yield_(self, reason: str, next_intent: str | None = None) -> dict[str, Any]:
        return {"status": "yield", "reason": reason, "next_intent": next_intent}
