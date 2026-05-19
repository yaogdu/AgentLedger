from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HIGH_RISK_LEVELS = {"high", "destructive", "sensitive", "financial_or_legal"}
POLICY_EFFECTS = {"allow", "deny", "require_approval"}
POLICY_CONTROL_KINDS = {"audit", "approval", "sandbox", "redact", "budget", "deny"}
ACTION_TIERS = ("L0", "L1", "L2", "L3", "L4", "L5")
DEFAULT_POLICY_VERSION = "local-v1"


@dataclass
class RolePolicy:
    allow_tools: set[str] | None = None
    deny_tools: set[str] = field(default_factory=set)
    allow_risk: set[str] | None = None
    deny_risk: set[str] = field(default_factory=set)


@dataclass
class PolicyControl:
    """A runtime action the original gate must enforce."""

    kind: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "reason": self.reason, "metadata": dict(self.metadata)}


@dataclass
class PolicyFinding:
    """Evidence produced by a policy evaluator."""

    id: str
    severity: str
    source: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "source": self.source,
            "message": self.message,
            "evidence": dict(self.evidence),
        }


@dataclass
class PolicyRequest:
    """Normalized policy input from any runtime gate.

    The current runtime uses this for tool calls. The shape is intentionally
    stage-agnostic so future model, memory, output, sub-agent, and media gates
    can use the same policy contract without changing the enforcement point.
    """

    stage: str
    subject: dict[str, Any]
    action: dict[str, Any]
    resource: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    policy_version: str = DEFAULT_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "subject": dict(self.subject),
            "action": dict(self.action),
            "resource": dict(self.resource),
            "context": dict(self.context),
            "signals": dict(self.signals),
            "runtime_state": dict(self.runtime_state),
            "policy_version": self.policy_version,
        }

    @classmethod
    def for_tool(
        cls,
        *,
        role: str,
        tool_name: str,
        risk_level: str,
        side_effect: str = "none",
        approval_required: bool = False,
        sandbox_required: bool = False,
        idempotency_required: bool = False,
        subject: dict[str, Any] | None = None,
        resource: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        signals: dict[str, Any] | None = None,
        runtime_state: dict[str, Any] | None = None,
        policy_version: str = DEFAULT_POLICY_VERSION,
    ) -> "PolicyRequest":
        subject_payload = {"kind": "agent", "role": role}
        subject_payload.update(subject or {})
        return cls(
            stage="tool",
            subject=subject_payload,
            action={
                "kind": "tool",
                "name": tool_name,
                "risk_level": risk_level,
                "side_effect": side_effect,
                "approval_required": approval_required,
                "sandbox_required": sandbox_required,
                "idempotency_required": idempotency_required,
            },
            resource=resource or {"kind": "tool", "name": tool_name},
            context=context or {},
            signals=signals or {},
            runtime_state=runtime_state or {},
            policy_version=policy_version,
        )


@dataclass
class PolicyDecision:
    """Decision contract returned from the PDP to the original gate."""

    effect: str
    action_tier: str
    risk_level: str
    controls: list[PolicyControl] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    findings: list[PolicyFinding] = field(default_factory=list)
    policy_version: str = DEFAULT_POLICY_VERSION
    subject_scope: str | None = None
    delegation_allowed: bool | None = None

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    def requires_control(self, kind: str) -> bool:
        return any(control.kind == kind for control in self.controls)

    @property
    def requires_approval(self) -> bool:
        return self.effect == "require_approval" or self.requires_control("approval")

    @property
    def requires_sandbox(self) -> bool:
        return self.requires_control("sandbox")

    def primary_reason(self) -> str:
        if self.reasons:
            return self.reasons[0]
        if self.effect == "allow":
            return "policy allowed"
        if self.effect == "require_approval":
            return "approval required"
        return "policy denied"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "effect": self.effect,
            "allowed": self.allowed,
            "action_tier": self.action_tier,
            "risk_level": self.risk_level,
            "controls": [control.to_dict() for control in self.controls],
            "reasons": list(self.reasons),
            "findings": [finding.to_dict() for finding in self.findings],
            "policy_version": self.policy_version,
        }
        if self.subject_scope is not None:
            payload["subject_scope"] = self.subject_scope
        if self.delegation_allowed is not None:
            payload["delegation_allowed"] = self.delegation_allowed
        return payload


class PolicyEvaluator:
    """Base class for small, dependency-free policy evaluators."""

    name = "policy_evaluator"

    def applies_to(self, request: PolicyRequest) -> bool:
        return True

    def evaluate(self, request: PolicyRequest) -> list[PolicyFinding]:
        return []


class _RoleCapabilityEvaluator(PolicyEvaluator):
    name = "role_capability"

    def __init__(self, engine: "PolicyEngine") -> None:
        self.engine = engine

    def evaluate(self, request: PolicyRequest) -> list[PolicyFinding]:
        role = str(request.subject.get("role") or request.subject.get("id") or "")
        tool_name = str(request.action.get("name") or "")
        risk_level = str(request.action.get("risk_level") or "low")
        result = self.engine._check_tool_policy(role, tool_name, risk_level)
        approval_required = bool(request.action.get("approval_required") or request.signals.get("approval_required"))
        approval_status = str(request.runtime_state.get("approval_status") or "NONE").upper()
        allowed = bool(result["allowed"])
        decision_effect = "allow" if allowed else "deny"
        severity = "info" if allowed else "critical"
        controls = [] if allowed else ["deny", "audit"]
        reason = str(result["reason"])
        if result["rule"] == "default_deny_high_risk" and approval_required:
            if approval_status == "APPROVED":
                allowed = True
                decision_effect = "allow"
                severity = "info"
                controls = ["audit"]
                reason = "high-risk action approved by policy gate"
            else:
                decision_effect = "require_approval"
                severity = "warning"
                controls = ["approval", "audit"]
                reason = "high-risk action requires approval by default"
        return [
            PolicyFinding(
                id=str(result["rule"]),
                severity=severity,
                source=self.name,
                message=reason,
                evidence={
                    "role": role,
                    "tool": tool_name,
                    "risk_level": risk_level,
                    "allowed": allowed,
                    "decision_effect": decision_effect,
                    "controls": controls,
                    "matched_rule": result["rule"],
                },
            )
        ]


class _ActionBoundaryEvaluator(PolicyEvaluator):
    name = "action_boundary"

    def evaluate(self, request: PolicyRequest) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        action_tier = infer_action_tier(request)
        findings.append(
            PolicyFinding(
                id="action_tier_inferred",
                severity="info",
                source=self.name,
                message=f"action tier inferred as {action_tier}",
                evidence={"action_tier": action_tier},
            )
        )

        risk_level = str(request.action.get("risk_level") or "low")
        approval_required = bool(request.action.get("approval_required") or request.signals.get("approval_required"))
        approval_status = str(request.runtime_state.get("approval_status") or "NONE").upper()
        if approval_status == "DENIED":
            findings.append(
                PolicyFinding(
                    id="approval_denied",
                    severity="critical",
                    source=self.name,
                    message="approval denied for action",
                    evidence={"decision_effect": "deny", "controls": ["deny", "audit"], "approval_status": approval_status},
                )
            )
        elif approval_required and approval_status != "APPROVED":
            findings.append(
                PolicyFinding(
                    id="approval_required",
                    severity="warning",
                    source=self.name,
                    message="approval required before action execution",
                    evidence={
                        "decision_effect": "require_approval",
                        "controls": ["approval", "audit"],
                        "approval_status": approval_status,
                        "risk_level": risk_level,
                    },
                )
            )
        elif approval_required and approval_status == "APPROVED":
            findings.append(
                PolicyFinding(
                    id="approval_satisfied",
                    severity="info",
                    source=self.name,
                    message="approval already satisfied",
                    evidence={"approval_status": approval_status, "controls": ["audit"]},
                )
            )

        if bool(request.action.get("sandbox_required") or request.signals.get("sandbox_required")):
            findings.append(
                PolicyFinding(
                    id="sandbox_required",
                    severity="info",
                    source=self.name,
                    message="sandbox boundary required for action",
                    evidence={"controls": ["sandbox", "audit"]},
                )
            )
        return findings


class _RuntimeStateEvaluator(PolicyEvaluator):
    name = "runtime_state"

    def evaluate(self, request: PolicyRequest) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        execution_mode = str(request.runtime_state.get("execution_mode") or "").lower()
        side_effect = str(request.action.get("side_effect") or "none")
        if execution_mode == "shadow" and side_effect != "none":
            findings.append(
                PolicyFinding(
                    id="shadow_side_effect_boundary",
                    severity="info",
                    source=self.name,
                    message="shadow mode requires side-effect replay or blocking",
                    evidence={"controls": ["audit"], "execution_mode": execution_mode, "side_effect": side_effect},
                )
            )
        if request.context.get("parent_run_id") or request.subject.get("kind") == "sub_agent":
            findings.append(
                PolicyFinding(
                    id="delegation_context_present",
                    severity="info",
                    source=self.name,
                    message="delegated or child-agent context included in policy request",
                    evidence={
                        "parent_run_id": request.context.get("parent_run_id"),
                        "parent_step_id": request.context.get("parent_step_id"),
                        "delegated_by": request.context.get("delegated_by"),
                    },
                )
            )
        if request.resource.get("kind") in {"media_artifact", "stream_checkpoint"}:
            findings.append(
                PolicyFinding(
                    id="media_resource_boundary",
                    severity="info",
                    source=self.name,
                    message="media or stream resource is governed as a durable runtime reference",
                    evidence={"resource_kind": request.resource.get("kind"), "controls": ["audit"]},
                )
            )
        return findings


class DecisionComposer:
    """Compose evaluator findings into one gate-enforceable decision."""

    def compose(self, request: PolicyRequest, findings: list[PolicyFinding], *, policy_version: str) -> PolicyDecision:
        effect = "allow"
        controls: dict[str, PolicyControl] = {
            "audit": PolicyControl("audit", "runtime decision must be recorded")
        }
        reasons: list[str] = []
        action_tier = infer_action_tier(request)
        risk_level = str(request.action.get("risk_level") or "low")

        for finding in findings:
            reasons.append(finding.message)
            suggested_tier = finding.evidence.get("action_tier")
            if isinstance(suggested_tier, str):
                action_tier = max_action_tier(action_tier, suggested_tier)
            for control_kind in finding.evidence.get("controls") or []:
                if isinstance(control_kind, str):
                    controls.setdefault(control_kind, PolicyControl(control_kind, finding.message))
            decision_effect = finding.evidence.get("decision_effect")
            if decision_effect == "deny":
                effect = "deny"
            elif decision_effect == "require_approval" and effect != "deny":
                effect = "require_approval"

        if effect == "deny":
            controls.setdefault("deny", PolicyControl("deny", "policy decision denied the action"))
        if effect == "require_approval":
            controls.setdefault("approval", PolicyControl("approval", "policy decision requires approval"))

        subject_scope = str(request.subject.get("role") or request.subject.get("kind") or "") or None
        delegation_value = request.context.get("delegation_allowed")
        delegation_allowed = delegation_value if isinstance(delegation_value, bool) else None
        return PolicyDecision(
            effect=effect,
            action_tier=action_tier,
            risk_level=risk_level,
            controls=[controls[key] for key in sorted(controls)],
            reasons=dedupe_preserve_order(reasons),
            findings=findings,
            policy_version=policy_version,
            subject_scope=subject_scope,
            delegation_allowed=delegation_allowed,
        )


@dataclass
class PolicyEngine:
    """Runtime policy PDP for local core and adapter tests.

    The engine now exposes a normalized policy request and decision contract,
    while keeping the original role/tool/risk helper API for compatibility.
    Built-in evaluators stay deterministic and dependency-free; OPA, Cedar,
    PII, injection, DLP, or enterprise policy services should plug in as
    optional evaluators/adapters instead of becoming core dependencies.
    """

    allowed_tools: dict[str, set[str]] = field(default_factory=dict)
    roles: dict[str, RolePolicy] = field(default_factory=dict)
    default_by_risk: dict[str, str] = field(default_factory=dict)
    policy_version: str = DEFAULT_POLICY_VERSION
    evaluators: list[PolicyEvaluator] = field(default_factory=list)
    composer: DecisionComposer = field(default_factory=DecisionComposer)

    def allow_tool(self, role: str, tool_name: str) -> None:
        self.allowed_tools.setdefault(role, set()).add(tool_name)
        policy = self.roles.setdefault(role, RolePolicy(allow_tools=set()))
        if policy.allow_tools is None:
            policy.allow_tools = set()
        policy.allow_tools.add(tool_name)

    def register_evaluator(self, evaluator: PolicyEvaluator) -> None:
        self.evaluators.append(evaluator)

    def check_tool(self, role: str, tool_name: str, risk_level: str) -> tuple[bool, str]:
        request = PolicyRequest.for_tool(role=role, tool_name=tool_name, risk_level=risk_level, policy_version=self.policy_version)
        decision = self.evaluate(request)
        return decision.allowed, decision.primary_reason()

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        evaluators = self.evaluators or self._default_evaluators()
        findings: list[PolicyFinding] = []
        for evaluator in evaluators:
            if evaluator.applies_to(request):
                findings.extend(evaluator.evaluate(request))
        return self.composer.compose(request, findings, policy_version=request.policy_version or self.policy_version)

    def explain(self, role: str, tool_name: str, risk_level: str) -> dict[str, Any]:
        request = PolicyRequest.for_tool(role=role, tool_name=tool_name, risk_level=risk_level, policy_version=self.policy_version)
        decision = self.evaluate(request)
        return {
            "role": role,
            "tool": tool_name,
            "risk_level": risk_level,
            "allowed": decision.allowed,
            "reason": decision.primary_reason(),
            "decision": decision.to_dict(),
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "PolicyEngine":
        data = load_policy_document(path)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyEngine":
        defaults = data.get("defaults", {}) or {}
        roles_data = data.get("roles", {}) or {}
        roles: dict[str, RolePolicy] = {}
        for role, value in roles_data.items():
            value = value or {}
            allow_tools = _optional_set(value.get("allow_tools"))
            deny_tools = set(value.get("deny_tools") or [])
            allow_risk = _optional_set(value.get("allow_risk"))
            deny_risk = set(value.get("deny_risk") or [])
            roles[role] = RolePolicy(allow_tools=allow_tools, deny_tools=deny_tools, allow_risk=allow_risk, deny_risk=deny_risk)
        version = str(data.get("version") or DEFAULT_POLICY_VERSION)
        return cls(roles=roles, default_by_risk=dict(defaults), policy_version=version)

    def _default_evaluators(self) -> list[PolicyEvaluator]:
        return [_RoleCapabilityEvaluator(self), _ActionBoundaryEvaluator(), _RuntimeStateEvaluator()]

    def _check_tool_policy(self, role: str, tool_name: str, risk_level: str) -> dict[str, Any]:
        role_policy = self.roles.get(role)
        if role_policy is None and role in self.allowed_tools:
            role_policy = RolePolicy(allow_tools=self.allowed_tools[role])
        if role_policy is not None:
            if tool_name in role_policy.deny_tools:
                return {"allowed": False, "reason": f"tool {tool_name} explicitly denied for role {role}", "rule": "role_deny_tool"}
            if tool_name in (role_policy.allow_tools or set()):
                return {"allowed": True, "reason": "allowed by role policy", "rule": "role_allow_tool"}
            if risk_level in role_policy.deny_risk:
                return {"allowed": False, "reason": f"risk level {risk_level} denied for role {role}", "rule": "role_deny_risk"}
            if risk_level in (role_policy.allow_risk or set()):
                return {"allowed": True, "reason": f"risk level {risk_level} allowed for role {role}", "rule": "role_allow_risk"}
            if role_policy.allow_tools is not None or role_policy.allow_risk is not None:
                return {"allowed": False, "reason": f"tool {tool_name} not allowed for role {role}", "rule": "role_allowlist_miss"}

        default = self.default_by_risk.get(risk_level)
        if default == "allow":
            return {"allowed": True, "reason": f"risk level {risk_level} allowed by default policy", "rule": "default_allow_risk"}
        if default == "deny":
            return {"allowed": False, "reason": f"risk level {risk_level} denied by default policy", "rule": "default_deny_risk"}
        if risk_level in HIGH_RISK_LEVELS:
            return {"allowed": False, "reason": "high-risk tool denied by default", "rule": "default_deny_high_risk"}
        return {"allowed": True, "reason": "default allow for low/medium risk in local runtime", "rule": "default_allow_low_medium"}


def infer_action_tier(request: PolicyRequest) -> str:
    explicit = request.action.get("action_tier") or request.signals.get("action_tier")
    if isinstance(explicit, str) and explicit in ACTION_TIERS:
        return explicit
    action_kind = str(request.action.get("kind") or request.stage or "").lower()
    side_effect = str(request.action.get("side_effect") or "none").lower()
    if bool(request.action.get("sandbox_required") or request.signals.get("sandbox_required")):
        return "L5"
    if action_kind in {"code", "browser", "shell"}:
        return "L5"
    if side_effect in {"external_write", "external", "destructive", "financial_or_legal"}:
        return "L4"
    if side_effect in {"local_write", "artifact_write"}:
        return "L3"
    if action_kind in {"rag", "retrieval"}:
        return "L1"
    if action_kind in {"answer", "model", "model_call"}:
        return "L0"
    return "L2"


def max_action_tier(left: str, right: str) -> str:
    try:
        return left if ACTION_TIERS.index(left) >= ACTION_TIERS.index(right) else right
    except ValueError:
        return left


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _optional_set(value: Any) -> set[str] | None:
    if value is None:
        return None
    return set(value or [])


def load_policy_document(path: str | Path) -> dict[str, Any]:
    source = Path(path).read_text(encoding="utf-8")
    stripped = source.lstrip()
    if stripped.startswith("{"):
        return json.loads(source)
    return parse_policy_yaml(source)


def parse_policy_yaml(source: str) -> dict[str, Any]:
    """Parse the dependency-free policy YAML subset used by AgentLedger.

    Supported shape:

    version: 1
    defaults:
      low: allow
      high: deny
    roles:
      ExecutorAgent:
        allow_tools:
          - github.create_issue
        deny_risk:
          - destructive
    """
    data: dict[str, Any] = {}
    section: str | None = None
    current_role: str | None = None
    current_list: str | None = None
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        content = line.strip()
        if indent == 0:
            current_role = None
            current_list = None
            if content.endswith(":"):
                section = content[:-1]
                data.setdefault(section, {})
            else:
                key, value = _split_scalar(content)
                data[key] = value
                section = None
            continue
        if section == "defaults" and indent == 2:
            key, value = _split_scalar(content)
            data.setdefault("defaults", {})[key] = str(value)
            continue
        if section == "roles" and indent == 2:
            current_role = content[:-1] if content.endswith(":") else content
            data.setdefault("roles", {}).setdefault(current_role, {})
            current_list = None
            continue
        if section == "roles" and indent == 4 and current_role:
            if content.endswith(":"):
                current_list = content[:-1]
                data["roles"][current_role].setdefault(current_list, [])
            else:
                key, value = _split_scalar(content)
                data["roles"][current_role][key] = value
            continue
        if section == "roles" and indent == 6 and current_role and current_list and content.startswith("-"):
            data["roles"][current_role].setdefault(current_list, []).append(content[1:].strip())
            continue
        raise ValueError(f"unsupported policy YAML line: {raw}")
    return data


def _split_scalar(content: str) -> tuple[str, Any]:
    if ":" not in content:
        raise ValueError(f"expected key: value, got {content!r}")
    key, value = content.split(":", 1)
    value = value.strip()
    if value in {"true", "false"}:
        parsed: Any = value == "true"
    elif value.isdigit():
        parsed = int(value)
    else:
        parsed = value.strip('"\'')
    return key.strip(), parsed
