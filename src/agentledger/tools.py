from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .approval import ApprovalRequired
from .blobstore import LocalBlobStore
from .cost import BudgetController
from .ids import CausalToken, new_id
from .policy import PolicyDecision, PolicyEngine, PolicyRequest
from .sandbox import SandboxExecutor, SandboxPolicy, create_sandbox_executor
from .store import SQLiteStore

ToolFunc = Callable[[dict[str, Any]], Any]


@dataclass
class ToolSpec:
    name: str
    func: ToolFunc
    version: str = "v1"
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effect: str = "none"
    risk_level: str = "low"
    idempotency_required: bool = False
    approval_required: bool = False
    sandbox_required: bool = False
    sandbox_executor: str | None = None
    sandbox_policy: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "side_effect": self.side_effect,
            "risk_level": self.risk_level,
            "idempotency_required": self.idempotency_required,
            "approval_required": self.approval_required,
            "sandbox_required": self.sandbox_required,
            "sandbox_executor": self.sandbox_executor,
            "sandbox_policy": self.sandbox_policy,
        }

    def to_openai_tool(self) -> dict[str, Any]:
        parameters = self.input_schema or {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }


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

    def list(self) -> list[ToolSpec]:
        return [self._tools[name] for name in sorted(self._tools)]

    def manifest(self) -> dict[str, Any]:
        return {"tools": [spec.to_dict() for spec in self.list()]}

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_tool() for spec in self.list()]


def tool(
    *,
    name: str,
    description: str = "",
    side_effect: str = "none",
    risk_level: str = "low",
    idempotency: bool = False,
    approval_required: bool = False,
    sandbox_required: bool = False,
    sandbox_executor: str | None = None,
    sandbox_policy: dict[str, Any] | None = None,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    version: str = "v1",
):
    def decorator(func: ToolFunc) -> ToolSpec:
        return ToolSpec(
            name=name,
            func=func,
            description=description,
            side_effect=side_effect,
            risk_level=risk_level,
            idempotency_required=idempotency,
            approval_required=approval_required,
            sandbox_required=sandbox_required,
            sandbox_executor=sandbox_executor,
            sandbox_policy=sandbox_policy or {},
            input_schema=input_schema or {},
            output_schema=output_schema or {},
            version=version,
        )
    return decorator


class PermissionDenied(RuntimeError):
    pass


class ToolValidationError(ValueError):
    pass


class ToolGateway:
    def __init__(
        self,
        *,
        store: SQLiteStore,
        blobs: LocalBlobStore,
        registry: ToolRegistry,
        policy: PolicyEngine | None = None,
        budget: BudgetController | None = None,
        sandbox: SandboxExecutor | None = None,
    ):
        self.store = store
        self.blobs = blobs
        self.registry = registry
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        self.sandbox = sandbox or create_sandbox_executor()

    async def call(self, ctx: Any, tool_name: str, args: dict[str, Any]) -> Any:
        spec = self.registry.get(tool_name)
        self._validate_input(spec, args)
        request = {"tool": tool_name, "args": args}
        request_hash, request_ref = self.blobs.put_json(request)
        token = CausalToken(ctx.run_id, ctx.step_id, ctx.attempt, ctx.state_version, None, ctx.lease_token)
        token_json = token.to_json()
        tool_call_id = new_id("toolcall")
        idempotency_key = self._idempotency_key(ctx, spec, args, request_hash)
        approval_key = self._approval_key(ctx, spec, request_hash)
        managed_side_effect = spec.side_effect != "none" or spec.idempotency_required

        self.store.append_event(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            event_type="tool_call_requested",
            payload=request,
            agent_role=ctx.agent_role,
            state_version=ctx.state_version,
            causal_token=token_json,
            payload_hash=request_hash,
            payload_ref=request_ref,
        )

        approved_row = self.store.approval_for_key(approval_key)
        approved_status = approved_row["status"] if approved_row is not None else None
        decision = self.policy.evaluate(
            self._policy_request(
                ctx,
                spec,
                tool_name,
                approval_status=approved_status,
                managed_side_effect=managed_side_effect,
            )
        )
        if decision.effect == "deny":
            self._record_permission(ctx, tool_name, decision, token_json)
            raise PermissionDenied(decision.primary_reason())
        if decision.effect == "require_approval":
            approval = self.store.request_approval(
                approval_key=approval_key,
                run_id=ctx.run_id,
                session_id=ctx.session_id,
                step_id=ctx.step_id,
                tool_name=tool_name,
                risk_level=spec.risk_level,
                reason=decision.primary_reason(),
                request_hash=request_hash,
                request_ref=request_ref,
                requested_by=ctx.agent_role,
            )
            approval_id = approval["approval_id"]
            self._record_permission(ctx, tool_name, decision, token_json)
            self.store.append_event(
                run_id=ctx.run_id,
                session_id=ctx.session_id,
                step_id=ctx.step_id,
                event_type="tool_approval_required",
                payload={"tool": tool_name, "approval_id": approval_id, "approval_key": approval_key, "risk_level": spec.risk_level, "decision": decision.to_dict()},
                agent_role=ctx.agent_role,
                state_version=ctx.state_version,
                causal_token=token_json,
            )
            raise ApprovalRequired(approval_id, f"approval required for tool {tool_name}", metadata={"tool": tool_name, "approval_key": approval_key})

        self._record_permission(ctx, tool_name, decision, token_json)
        self.budget.before_tool_call(self.store, ctx.run_id)

        if ctx.execution_mode == "shadow" and managed_side_effect:
            response = self._shadow_response(ctx, spec, args, request_hash, token_json)
            self.store.record_cost(
                run_id=ctx.run_id,
                session_id=ctx.session_id,
                step_id=ctx.step_id,
                category="tool_shadow",
                name=tool_name,
                amount=1.0,
                unit="call",
                metadata={"source_run_id": ctx.source_run_id, "side_effect_blocked": True},
            )
            return response

        if managed_side_effect:
            existing = self.store.reserve_ledger(
                run_id=ctx.run_id,
                session_id=ctx.session_id,
                step_id=ctx.step_id,
                tool_name=tool_name,
                tool_version=spec.version,
                tool_call_id=tool_call_id,
                idempotency_key=idempotency_key,
                causal_token=token_json,
                request_hash=request_hash,
                request_ref=request_ref,
            )
            if existing is not None and existing["status"] == "SUCCEEDED":
                response = self.blobs.get_json(existing["response_ref"])
                self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_completed", payload={"tool": tool_name, "replayed_from_ledger": True, "idempotency_key": idempotency_key}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token_json, payload_hash=existing["response_hash"], payload_ref=existing["response_ref"])
                self.store.record_cost(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, category="tool", name=tool_name, amount=1.0, unit="call", metadata={"replayed_from_ledger": True})
                return response
            if existing is not None and existing["status"] == "PENDING_VERIFICATION":
                raise RuntimeError("tool side effect pending verification")
            if existing is not None and existing["status"] in {"RESERVED", "RUNNING"}:
                raise RuntimeError("tool side effect already in progress")
            self.store.update_ledger(idempotency_key=idempotency_key, status="RUNNING")

        try:
            result = await self._execute_tool(ctx, spec, args, token_json)
            self._validate_output(spec, result)
            response_hash, response_ref = self.blobs.put_json(result)
            if managed_side_effect:
                external_id = result.get("external_id") if isinstance(result, dict) else None
                self.store.update_ledger(idempotency_key=idempotency_key, status="SUCCEEDED", external_id=external_id, response_hash=response_hash, response_ref=response_ref)
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_completed", payload={"tool": tool_name, "idempotency_key": idempotency_key}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token_json, payload_hash=response_hash, payload_ref=response_ref)
            self.store.record_cost(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, category="tool", name=tool_name, amount=1.0, unit="call", metadata={"side_effect": spec.side_effect, "sandboxed": spec.sandbox_required, "sandbox_executor": spec.sandbox_executor})
            return result
        except Exception as exc:
            if managed_side_effect:
                self.store.update_ledger(idempotency_key=idempotency_key, status="PENDING_VERIFICATION", error_type=type(exc).__name__)
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_failed", payload={"tool": tool_name, "error": repr(exc)}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=token_json)
            raise

    def _policy_request(self, ctx: Any, spec: ToolSpec, tool_name: str, *, approval_status: str | None, managed_side_effect: bool) -> PolicyRequest:
        context: dict[str, Any] = {
            "run_id": ctx.run_id,
            "session_id": ctx.session_id,
            "step_id": ctx.step_id,
            "attempt": ctx.attempt,
            "state_version": ctx.state_version,
        }
        for attr in ("parent_run_id", "parent_step_id", "delegated_by"):
            value = getattr(ctx, attr, None)
            if value is not None:
                context[attr] = value
        return PolicyRequest.for_tool(
            role=ctx.agent_role,
            tool_name=tool_name,
            risk_level=spec.risk_level,
            side_effect=spec.side_effect,
            approval_required=spec.approval_required,
            sandbox_required=spec.sandbox_required,
            idempotency_required=spec.idempotency_required,
            subject={
                "kind": getattr(ctx, "subject_kind", "agent"),
                "role": ctx.agent_role,
                "worker_id": getattr(ctx, "worker_id", None),
            },
            resource={
                "kind": "tool",
                "name": tool_name,
                "version": spec.version,
            },
            context=context,
            signals={
                "managed_side_effect": managed_side_effect,
                "approval_required": spec.approval_required,
                "sandbox_required": spec.sandbox_required,
                "idempotency_required": spec.idempotency_required,
            },
            runtime_state={
                "approval_status": approval_status,
                "execution_mode": ctx.execution_mode,
                "source_run_id": ctx.source_run_id,
            },
            policy_version=self.policy.policy_version,
        )

    def _record_permission(self, ctx: Any, tool_name: str, decision: PolicyDecision, causal_token: str) -> None:
        self.store.append_event(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            event_type="tool_permission_decided",
            payload={"tool": tool_name, "allowed": decision.allowed, "reason": decision.primary_reason(), "decision": decision.to_dict()},
            agent_role=ctx.agent_role,
            state_version=ctx.state_version,
            causal_token=causal_token,
        )

    async def _execute_tool(self, ctx: Any, spec: ToolSpec, args: dict[str, Any], causal_token: str) -> Any:
        if not spec.sandbox_required:
            result = spec.func(args)
            if inspect.isawaitable(result):
                result = await result
            return result
        raw_policy = spec.sandbox_policy or {}
        policy = SandboxPolicy(
            tool_name=spec.name,
            run_id=ctx.run_id,
            step_id=ctx.step_id,
            executor=spec.sandbox_executor or raw_policy.get("executor", "default"),
            network=raw_policy.get("network", "deny"),
            filesystem=raw_policy.get("filesystem", "read-only"),
            timeout_seconds=int(raw_policy.get("timeout_seconds", 30)),
            resource_limits=dict(raw_policy.get("resource_limits") or {}),
            extra={key: value for key, value in raw_policy.items() if key not in {"executor", "network", "filesystem", "timeout_seconds", "resource_limits"}},
        )
        if hasattr(self.sandbox, "policy_for"):
            policy = self.sandbox.policy_for(policy)  # type: ignore[attr-defined]
        self.store.append_event(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            event_type="sandbox_started",
            payload=policy.to_dict(),
            agent_role=ctx.agent_role,
            state_version=ctx.state_version,
            causal_token=causal_token,
        )
        sandbox_result = await self.sandbox.run_tool(spec.func, args, policy)
        self.store.append_event(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            event_type="sandbox_completed",
            payload=sandbox_result.to_dict(),
            agent_role=ctx.agent_role,
            state_version=ctx.state_version,
            causal_token=causal_token,
        )
        if not sandbox_result.ok:
            raise RuntimeError(sandbox_result.error or "sandboxed tool failed")
        return sandbox_result.output

    def _shadow_response(self, ctx: Any, spec: ToolSpec, args: dict[str, Any], request_hash: str, causal_token: str) -> Any:
        if not ctx.source_run_id:
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_blocked", payload={"tool": spec.name, "reason": "shadow mode has no source_run_id"}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=causal_token)
            raise PermissionDenied("shadow mode blocks side effects without source_run_id")
        logical = args.get("_logical_operation") if isinstance(args, dict) else None
        existing = self.store.find_succeeded_ledger_response(run_id=ctx.source_run_id, tool_name=spec.name, logical_operation=logical, request_hash=request_hash)
        if existing is None:
            self.store.append_event(run_id=ctx.run_id, session_id=ctx.session_id, step_id=ctx.step_id, event_type="tool_call_blocked", payload={"tool": spec.name, "reason": "no archived side-effect response in source run", "source_run_id": ctx.source_run_id}, agent_role=ctx.agent_role, state_version=ctx.state_version, causal_token=causal_token)
            raise PermissionDenied("shadow mode blocks unmanaged side effect")
        response = self.blobs.get_json(existing["response_ref"])
        self.store.append_event(
            run_id=ctx.run_id,
            session_id=ctx.session_id,
            step_id=ctx.step_id,
            event_type="tool_call_completed",
            payload={"tool": spec.name, "shadow_replayed_from_run": ctx.source_run_id, "source_ledger_id": existing["ledger_id"]},
            agent_role=ctx.agent_role,
            state_version=ctx.state_version,
            causal_token=causal_token,
            payload_hash=existing["response_hash"],
            payload_ref=existing["response_ref"],
        )
        return response

    def _idempotency_key(self, ctx: Any, spec: ToolSpec, args: dict[str, Any], request_hash: str) -> str:
        logical = args.get("_logical_operation") if isinstance(args, dict) else None
        return f"{ctx.run_id}:{ctx.step_id}:{spec.name}:{logical or request_hash}"

    def _approval_key(self, ctx: Any, spec: ToolSpec, request_hash: str) -> str:
        return f"{ctx.run_id}:{ctx.step_id}:{spec.name}:{request_hash}"

    def _validate_input(self, spec: ToolSpec, args: dict[str, Any]) -> None:
        try:
            validate_tool_schema(spec.input_schema or {}, args, path="args")
        except ToolValidationError as exc:
            raise ToolValidationError(f"invalid input for tool {spec.name}: {exc}") from exc

    def _validate_output(self, spec: ToolSpec, result: Any) -> None:
        try:
            validate_tool_schema(spec.output_schema or {}, result, path="result")
        except ToolValidationError as exc:
            raise ToolValidationError(f"invalid output for tool {spec.name}: {exc}") from exc


def validate_tool_schema(schema: dict[str, Any], value: Any, *, path: str = "$") -> None:
    """Validate a dependency-free JSON Schema subset used by ToolSpec.

    Supported keywords intentionally stay small: type, required, properties,
    additionalProperties=false, items, enum, const, numeric/string/array/object
    bounds. Exact framework adapters can run stronger validators outside core.
    """
    if not schema:
        return
    for subschema in schema.get("allOf", []) or []:
        if isinstance(subschema, dict):
            validate_tool_schema(subschema, value, path=path)
    any_of = [subschema for subschema in schema.get("anyOf", []) or [] if isinstance(subschema, dict)]
    if any_of and not any(_schema_passes(subschema, value, path=path) for subschema in any_of):
        raise ToolValidationError(f"{path} must match at least one anyOf schema")
    one_of = [subschema for subschema in schema.get("oneOf", []) or [] if isinstance(subschema, dict)]
    if one_of:
        matches = sum(1 for subschema in one_of if _schema_passes(subschema, value, path=path))
        if matches != 1:
            raise ToolValidationError(f"{path} must match exactly one oneOf schema, matched {matches}")
    not_schema = schema.get("not")
    if isinstance(not_schema, dict) and _schema_passes(not_schema, value, path=path):
        raise ToolValidationError(f"{path} must not match forbidden schema")
    if "const" in schema and value != schema["const"]:
        raise ToolValidationError(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(f"{path} must be one of {schema['enum']!r}")

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_json_type(value, expected_type):
        raise ToolValidationError(f"{path} expected type {expected_type!r}, got {_json_type_name(value)!r}")

    if "required" in schema and not isinstance(value, dict):
        raise ToolValidationError(f"{path} expected object for required properties")
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                raise ToolValidationError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, subschema in properties.items():
                if key in value and isinstance(subschema, dict):
                    validate_tool_schema(subschema, value[key], path=f"{path}.{key}")
            additional = schema.get("additionalProperties", True)
            allowed = set(properties)
            extra = sorted(key for key in value if key not in allowed)
            if additional is False and extra:
                raise ToolValidationError(f"{path} has unexpected properties {extra!r}")
            if isinstance(additional, dict):
                for key in extra:
                    validate_tool_schema(additional, value[key], path=f"{path}.{key}")
        _check_bound(schema, "minProperties", len(value), path, ">=")
        _check_bound(schema, "maxProperties", len(value), path, "<=")

    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                validate_tool_schema(items, item, path=f"{path}[{index}]")
        if schema.get("uniqueItems") is True:
            seen: set[str] = set()
            for item in value:
                fingerprint = json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                if fingerprint in seen:
                    raise ToolValidationError(f"{path} must contain unique items")
                seen.add(fingerprint)
        _check_bound(schema, "minItems", len(value), path, ">=")
        _check_bound(schema, "maxItems", len(value), path, "<=")

    if isinstance(value, str):
        _check_bound(schema, "minLength", len(value), path, ">=")
        _check_bound(schema, "maxLength", len(value), path, "<=")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            raise ToolValidationError(f"{path} must match pattern {pattern!r}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _check_bound(schema, "minimum", value, path, ">=")
        _check_bound(schema, "maximum", value, path, "<=")
        _check_bound(schema, "exclusiveMinimum", value, path, ">")
        _check_bound(schema, "exclusiveMaximum", value, path, "<")
        if "multipleOf" in schema and schema["multipleOf"]:
            multiple = schema["multipleOf"]
            quotient = value / multiple
            if abs(quotient - round(quotient)) > 1e-12:
                raise ToolValidationError(f"{path} must be a multiple of {multiple}")


def _schema_passes(schema: dict[str, Any], value: Any, *, path: str) -> bool:
    try:
        validate_tool_schema(schema, value, path=path)
    except ToolValidationError:
        return False
    return True


def _matches_json_type(value: Any, expected_type: Any) -> bool:
    if isinstance(expected_type, list):
        return any(_matches_json_type(value, item) for item in expected_type)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _check_bound(schema: dict[str, Any], key: str, value: int | float, path: str, op: str) -> None:
    if key not in schema:
        return
    limit = schema[key]
    if op == ">=" and value < limit:
        raise ToolValidationError(f"{path} must be >= {limit}")
    if op == "<=" and value > limit:
        raise ToolValidationError(f"{path} must be <= {limit}")
    if op == ">" and value <= limit:
        raise ToolValidationError(f"{path} must be > {limit}")
    if op == "<" and value >= limit:
        raise ToolValidationError(f"{path} must be < {limit}")
