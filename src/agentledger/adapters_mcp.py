from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from .adapters_omp import (
    ExecutionArtifact,
    ExecutionEvidenceBridge,
    ExecutionSession,
    ExecutionStateChange,
    ExecutionToolExecution,
    ExecutionToolProposal,
    ExecutionTurn,
)
from .runtime import Runtime
from .tools import ToolRegistry, ToolSpec

MCPCall = Callable[[str, dict[str, Any]], Any]
MCPResourceRead = Callable[[str], Any]
MCP_OBSERVER_SCHEMA_VERSION = "agentledger.mcp.observer.v1"


@dataclass(frozen=True)
class MCPResourceDescriptor:
    uri: str
    name: str
    mime_type: str = "application/json"

    def to_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "name": self.name, "mimeType": self.mime_type}


class InMemoryMCPToolServer:
    """Dependency-free MCP-style tool server fixture for examples/tests."""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict[str, Any], MCPCall]] = {}

    def add_tool(self, descriptor: dict[str, Any], handler: MCPCall) -> None:
        self._tools[descriptor["name"]] = (descriptor, handler)

    def list_tools(self) -> list[dict[str, Any]]:
        return [self._tools[name][0] for name in sorted(self._tools)]

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        try:
            _descriptor, handler = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"MCP tool not found: {name}") from exc
        return handler(name, args)


class InMemoryMCPContextServer:
    """Dependency-free MCP-style context/resource server fixture."""

    def __init__(self) -> None:
        self._resources: dict[str, tuple[MCPResourceDescriptor, MCPResourceRead]] = {}

    def add_resource(self, *, uri: str, name: str, reader: MCPResourceRead, mime_type: str = "application/json") -> None:
        self._resources[uri] = (MCPResourceDescriptor(uri=uri, name=name, mime_type=mime_type), reader)

    def list_resources(self) -> list[dict[str, Any]]:
        return [self._resources[uri][0].to_dict() for uri in sorted(self._resources)]

    def read_resource(self, uri: str) -> Any:
        try:
            descriptor, reader = self._resources[uri]
        except KeyError as exc:
            raise KeyError(f"MCP resource not found: {uri}") from exc
        return {"resource": descriptor.to_dict(), "content": reader(uri)}


class MCPToolAdapter:
    """Map MCP-style tool descriptors into AgentLedger ToolSpec objects.

    The adapter is dependency-free: callers provide a `client_call` function that
    knows how to invoke an MCP client. Runtime core still owns policy, ledger,
    audit, budget, replay, and shadow semantics through ToolGateway.
    """

    name = "mcp-tool"

    def __init__(self, client_call: MCPCall):
        self.client_call = client_call

    def tool_spec_from_descriptor(self, descriptor: dict[str, Any]) -> ToolSpec:
        tool_name = descriptor["name"]
        annotations = descriptor.get("annotations", {}) or {}
        input_schema = descriptor.get("inputSchema") or descriptor.get("input_schema") or {}
        side_effect = annotations.get("side_effect", "none")
        risk_level = annotations.get("risk_level", "low")
        idempotency_required = bool(annotations.get("idempotency_required", side_effect != "none"))
        approval_required = bool(annotations.get("approval_required", False))
        sandbox_required = bool(annotations.get("sandbox_required", False))
        sandbox_policy = dict(annotations.get("sandbox_policy") or {})
        sandbox_executor = annotations.get("sandbox_executor")

        async def call(args: dict[str, Any]) -> Any:
            result = self.client_call(tool_name, args)
            if inspect.isawaitable(result):
                return await result
            return result

        return ToolSpec(
            name=tool_name,
            func=call,
            version=str(descriptor.get("version", "v1")),
            input_schema=input_schema,
            output_schema=descriptor.get("outputSchema") or descriptor.get("output_schema") or {},
            side_effect=side_effect,
            risk_level=risk_level,
            idempotency_required=idempotency_required,
            approval_required=approval_required,
            sandbox_required=sandbox_required,
            sandbox_executor=str(sandbox_executor) if sandbox_executor is not None else None,
            sandbox_policy=sandbox_policy,
        )

    def register(self, registry: ToolRegistry, descriptor: dict[str, Any]) -> ToolSpec:
        spec = self.tool_spec_from_descriptor(descriptor)
        registry.register(spec)
        return spec

    def register_all(self, registry: ToolRegistry, descriptors: list[dict[str, Any]]) -> list[ToolSpec]:
        return [self.register(registry, descriptor) for descriptor in descriptors]


class MCPContextAdapter:
    """Expose MCP-style context/resource reads through ToolGateway."""

    name = "mcp-context"

    def __init__(self, resource_read: Callable[[str], Any]):
        self.resource_read = resource_read

    def read_tool_spec(self, *, name: str = "mcp.context.read", risk_level: str = "low") -> ToolSpec:
        async def call(args: dict[str, Any]) -> Any:
            uri = args["uri"]
            result = self.resource_read(uri)
            if inspect.isawaitable(result):
                return await result
            return result

        return ToolSpec(
            name=name,
            func=call,
            version="v1",
            description="Read an MCP-style context resource by URI.",
            input_schema={
                "type": "object",
                "required": ["uri"],
                "properties": {"uri": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            side_effect="none",
            risk_level=risk_level,
        )

    def register_read_tool(self, registry: ToolRegistry, *, name: str = "mcp.context.read", risk_level: str = "low") -> ToolSpec:
        spec = self.read_tool_spec(name=name, risk_level=risk_level)
        registry.register(spec)
        return spec


class MCPEvidenceObserver:
    """Observe normalized MCP tool, resource, and prompt events."""

    name = "mcp-evidence-observer"

    def __init__(self, runtime: Runtime, *, app_name: str, run_id: str | None = None):
        self.bridge = ExecutionEvidenceBridge(runtime, app_name=app_name, source="mcp")
        self.run_id = run_id

    def observe(self, event: dict[str, Any]) -> Any:
        if not isinstance(event, dict):
            raise TypeError("MCP evidence event must be a dictionary")
        event_type = self._event_type(event)
        session_id = self._session_id(event)
        self._ensure_bound_session(event, session_id)
        if event_type in {"session_started", "connection_started"}:
            return self.bridge.record_session_started(
                ExecutionSession(
                    session_id=session_id,
                    initial_state=self._dict(event, "initial_state"),
                    metadata=self._metadata(event),
                    run_id=self._runtime_run_id(event),
                )
            )
        if event_type in {"request_started", "turn_started"}:
            return self.bridge.record_turn_started(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    agent_role=str(event.get("agent_role") or "MCPAgent"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"tool_call_proposed", "tool_call_requested"}:
            return self.bridge.record_tool_proposal(
                ExecutionToolProposal(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    tool_name=self._required(event, "tool_name", "tool"),
                    arguments=self._dict(event, "arguments", "args"),
                    provider=self._optional(event, "server_name", "provider"),
                    model=self._optional(event, "model"),
                    model_call_ref=self._optional(event, "model_call_ref"),
                    confidence=event.get("confidence"),
                    reason=self._optional(event, "reason"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"tool_call_completed", "tool_call_failed", "tool_execution"}:
            return self.bridge.record_tool_execution(
                ExecutionToolExecution(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    tool_name=self._required(event, "tool_name", "tool"),
                    arguments=self._dict(event, "arguments", "args"),
                    result=event.get("result"),
                    tool_call_id=self._optional(event, "tool_call_id"),
                    tool_version=str(event.get("tool_version") or "external"),
                    idempotency_key=self._optional(event, "idempotency_key"),
                    ledger_status=self._optional(event, "ledger_status", "status"),
                    error_type=self._optional(event, "error_type"),
                    error_message=self._optional(event, "error_message", "error"),
                    external_id=self._optional(event, "external_id"),
                    causal_token=self._optional(event, "causal_token"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {
            "resource_read",
            "resource_read_completed",
            "resource_read_failed",
            "prompt_get",
            "prompt_get_completed",
            "prompt_get_failed",
        }:
            return self.bridge.record_execution_event(
                session_id=session_id,
                turn_id=self._optional(event, "turn_id", "request_id"),
                event_name="task_receipt_recorded",
                causal_token=self._optional(event, "causal_token", "request_id"),
                payload={
                    "receipt_type": event_type,
                    "request_id": self._optional(event, "request_id"),
                    "resource_uri": self._optional(event, "resource_uri", "uri"),
                    "prompt_name": self._optional(event, "prompt_name"),
                    "mime_type": self._optional(event, "mime_type"),
                    "content_ref": self._optional(event, "content_ref"),
                    "status": self._optional(event, "status", "state"),
                    "error": self._optional(event, "error"),
                    "metadata": self._metadata(event),
                },
            )
        if event_type in {"state_change", "state_change_recorded"}:
            return self.bridge.record_state_change(
                ExecutionStateChange(
                    session_id=session_id,
                    turn_id=self._optional(event, "turn_id", "request_id"),
                    reason=self._required(event, "reason"),
                    patch=self._dict(event, "patch"),
                    label=str(event.get("label") or "state"),
                    commit_status=str(event.get("commit_status") or "committed"),
                    before_snapshot=event.get("before_snapshot"),
                    after_snapshot=event.get("after_snapshot"),
                    diff=event.get("diff"),
                    metadata=self._metadata(event),
                )
            )
        if event_type in {"artifact_recorded", "artifact_created", "media_artifact_recorded"}:
            return self.bridge.record_artifact(
                ExecutionArtifact(
                    session_id=session_id,
                    turn_id=self._optional(event, "turn_id", "request_id"),
                    name=self._required(event, "name", "artifact_name"),
                    kind=str(event.get("kind") or "artifact"),
                    uri=self._optional(event, "uri"),
                    content_ref=self._optional(event, "content_ref"),
                    external_id=self._optional(event, "external_id", "artifact_id"),
                    metadata=self._metadata(event),
                    lineage=self._dict(event, "lineage"),
                    derived_outputs=self._dict(event, "derived_outputs"),
                )
            )
        if event_type in {"request_completed", "turn_completed"}:
            return self.bridge.record_turn_completed(
                ExecutionTurn(
                    session_id=session_id,
                    turn_id=self._turn_id(event),
                    state_patch=self._dict(event, "state_patch"),
                    metadata=self._metadata(event),
                )
            )
        raise ValueError(f"unsupported MCP evidence event type: {event_type}")

    def _ensure_bound_session(self, event: dict[str, Any], session_id: str) -> None:
        run_id = self._runtime_run_id(event)
        if run_id is None:
            return
        self.bridge.record_session_started(
            ExecutionSession(
                session_id=session_id,
                initial_state=self._dict(event, "initial_state"),
                metadata=self._metadata(event),
                run_id=run_id,
            )
        )

    def _runtime_run_id(self, event: dict[str, Any]) -> str | None:
        return self._optional(event, "runtime_run_id", "agentledger_run_id") or self.run_id

    @staticmethod
    def _event_type(event: dict[str, Any]) -> str:
        value = event.get("type") or event.get("event_type")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("MCP evidence event requires type")
        return value.strip().lower().replace(".", "_")

    @classmethod
    def _session_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "session_id", "connection_id")

    @classmethod
    def _turn_id(cls, event: dict[str, Any]) -> str:
        return cls._required(event, "turn_id", "request_id")

    @staticmethod
    def _metadata(event: dict[str, Any]) -> dict[str, Any]:
        metadata = event.get("metadata", {})
        if not isinstance(metadata, dict):
            raise TypeError("MCP evidence metadata must be a dictionary")
        result = dict(metadata)
        for key in (
            "session_id",
            "connection_id",
            "turn_id",
            "request_id",
            "server_name",
            "server_uri",
            "tool_name",
            "resource_uri",
            "prompt_name",
            "mime_type",
            "attempt",
        ):
            if key in event and event[key] is not None:
                result[f"external_{key}"] = event[key]
        result["observer_schema_version"] = MCP_OBSERVER_SCHEMA_VERSION
        return result

    @staticmethod
    def _required(event: dict[str, Any], *keys: str) -> str:
        value = MCPEvidenceObserver._optional(event, *keys)
        if not value:
            raise ValueError(f"MCP evidence event requires one of: {', '.join(keys)}")
        return value

    @staticmethod
    def _optional(event: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = event.get(key)
            if value is not None and str(value).strip():
                return str(value)
        return None

    @staticmethod
    def _dict(event: dict[str, Any], *keys: str) -> dict[str, Any]:
        for key in keys:
            value = event.get(key)
            if value is None:
                continue
            if not isinstance(value, dict):
                raise TypeError(f"MCP evidence field {key} must be a dictionary")
            return dict(value)
        return {}
