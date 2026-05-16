from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HIGH_RISK_LEVELS = {"high", "destructive", "sensitive", "financial_or_legal"}


@dataclass
class RolePolicy:
    allow_tools: set[str] | None = None
    deny_tools: set[str] = field(default_factory=set)
    allow_risk: set[str] | None = None
    deny_risk: set[str] = field(default_factory=set)


@dataclass
class PolicyEngine:
    """Role/capability policy for local runtime and adapter tests.

    The first implementation intentionally accepts a small YAML subset so the
    core package remains dependency-free. JSON is also accepted for stricter
    tooling and generated policy files.
    """

    allowed_tools: dict[str, set[str]] = field(default_factory=dict)
    roles: dict[str, RolePolicy] = field(default_factory=dict)
    default_by_risk: dict[str, str] = field(default_factory=dict)

    def allow_tool(self, role: str, tool_name: str) -> None:
        self.allowed_tools.setdefault(role, set()).add(tool_name)
        policy = self.roles.setdefault(role, RolePolicy(allow_tools=set()))
        if policy.allow_tools is None:
            policy.allow_tools = set()
        policy.allow_tools.add(tool_name)

    def check_tool(self, role: str, tool_name: str, risk_level: str) -> tuple[bool, str]:
        role_policy = self.roles.get(role)
        if role_policy is None and role in self.allowed_tools:
            role_policy = RolePolicy(allow_tools=self.allowed_tools[role])
        if role_policy is not None:
            if tool_name in role_policy.deny_tools:
                return False, f"tool {tool_name} explicitly denied for role {role}"
            if tool_name in (role_policy.allow_tools or set()):
                return True, "allowed by role policy"
            if risk_level in role_policy.deny_risk:
                return False, f"risk level {risk_level} denied for role {role}"
            if risk_level in (role_policy.allow_risk or set()):
                return True, f"risk level {risk_level} allowed for role {role}"
            if role_policy.allow_tools is not None or role_policy.allow_risk is not None:
                return False, f"tool {tool_name} not allowed for role {role}"

        default = self.default_by_risk.get(risk_level)
        if default == "allow":
            return True, f"risk level {risk_level} allowed by default policy"
        if default == "deny":
            return False, f"risk level {risk_level} denied by default policy"
        if risk_level in HIGH_RISK_LEVELS:
            return False, "high-risk tool denied by default"
        return True, "default allow for low/medium risk in local runtime"

    def explain(self, role: str, tool_name: str, risk_level: str) -> dict[str, Any]:
        allowed, reason = self.check_tool(role, tool_name, risk_level)
        return {"role": role, "tool": tool_name, "risk_level": risk_level, "allowed": allowed, "reason": reason}

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
        return cls(roles=roles, default_by_risk=dict(defaults))


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
