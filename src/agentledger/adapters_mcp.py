from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable

from .tools import ToolRegistry, ToolSpec

MCPCall = Callable[[str, dict[str, Any]], Any]
MCPResourceRead = Callable[[str], Any]


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
