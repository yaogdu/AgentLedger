from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from .blobstore import LocalBlobStore
from .ids import CausalToken, new_id
from .policy import PolicyEngine
from .store import SQLiteStore

ToolFunc = Callable[[dict[str, Any]], Any]


@dataclass
class ToolSpec:
    name: str
    func: ToolFunc
    version: str = "v1"
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effect: str = "none"
    risk_level: str = "low"
    idempotency_required: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        self._tools[spec.name] = spec
        return spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc


def tool(*, name: str, side_effect: str = "none", risk_level: str = "low", idempotency: bool = False, input_schema: dict[str, Any] | None = None, output_schema: dict[str, Any] | None = None, version: str = "v1"):
    def decorator(func: ToolFunc) -> ToolSpec:
        return ToolSpec(name=name, func=func, side_effect=side_effect, risk_level=risk_level, idempotency_required=idempotency, input_schema=input_schema or {}, output_schema=output_schema or {}, version=version)
    return decorator


class PermissionDenied(RuntimeError):
    pass


class ToolGateway:
    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore, registry: ToolRegistry, policy: PolicyEngine | None = None):
        self.store = store
        self.blobs = blobs
        self.registry = registry
        self.policy = policy or PolicyEngine()

    async def call(self, ctx: Any, tool_name: str, args: dict[str, Any]) -> Any:
        spec = self.registry.get(tool_name)
        self._validate_input(spec, args)
        allowed, reason = self.policy.check_tool(ctx.agent_role, tool_name, spec.risk_level)
        request = {"tool": tool_name, "args": args, "reason": reason}
        request_hash, request_ref = self.blobs.put_json(request)
        token = CausalToken(ctx.run_id, ctx.step_id, ctx.attempt, ctx.state_version, None, ctx.lease_token)
        tool_call_id = new_id("toolcall")
        idempotency_key = self._idempotency_key(ctx, spec, args, request_hash)
        self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_requested", payload=request, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token.to_json(), payload_hash=request_hash, payload_ref=request_ref)
        self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_permission_decided", payload={"tool": tool_name, "allowed": allowed, "reason": reason}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token.to_json())
        if not allowed:
            raise PermissionDenied(reason)

        managed_side_effect = spec.side_effect != "none" or spec.idempotency_required
        if managed_side_effect:
            existing = self.store.reserve_ledger(
                run_id=ctx.run_id,
                session_id=ctx.session_id,
                step_id=ctx.step_id,
                tool_name=tool_name,
                tool_version=spec.version,
                tool_call_id=tool_call_id,
                idempotency_key=idempotency_key,
                causal_token=token.to_json(),
                request_hash=request_hash,
                request_ref=request_ref,
            )
            if existing is not None and existing["status"] == "SUCCEEDED":
                response = self.blobs.get_json(existing["response_ref"])
                self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_completed", payload={"tool": tool_name, "replayed_from_ledger": True, "idempotency_key": idempotency_key}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token.to_json(), payload_hash=existing["response_hash"], payload_ref=existing["response_ref"])
                return response
            if existing is not None and existing["status"] == "PENDING_VERIFICATION":
                raise RuntimeError("tool side effect pending verification")
            if existing is not None and existing["status"] in {"RESERVED", "RUNNING"}:
                raise RuntimeError("tool side effect already in progress")
            self.store.update_ledger(idempotency_key=idempotency_key, status="RUNNING")

        try:
            result = spec.func(args)
            if inspect.isawaitable(result):
                result = await result
            response_hash, response_ref = self.blobs.put_json(result)
            if managed_side_effect:
                external_id = result.get("external_id") if isinstance(result, dict) else None
                self.store.update_ledger(idempotency_key=idempotency_key, status="SUCCEEDED", external_id=external_id, response_hash=response_hash, response_ref=response_ref)
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_completed", payload={"tool": tool_name, "idempotency_key": idempotency_key}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token.to_json(), payload_hash=response_hash, payload_ref=response_ref)
            return result
        except Exception as exc:
            if managed_side_effect:
                self.store.update_ledger(idempotency_key=idempotency_key, status="PENDING_VERIFICATION", error_type=type(exc).__name__)
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_failed", payload={"tool": tool_name, "error": repr(exc)}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token.to_json())
            raise

    def _idempotency_key(self, ctx: Any, spec: ToolSpec, args: dict[str, Any], request_hash: str) -> str:
        logical = args.get("_logical_operation") if isinstance(args, dict) else None
        return f"{ctx.run_id}:{ctx.step_id}:{spec.name}:{logical or request_hash}"

    def _validate_input(self, spec: ToolSpec, args: dict[str, Any]) -> None:
        schema = spec.input_schema or {}
        required = schema.get("required", [])
        for key in required:
            if key not in args:
                raise ValueError(f"missing required tool arg {key!r} for {spec.name}")
