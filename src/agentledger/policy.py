from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PolicyEngine:
    """Minimal allowlist policy for v0.1."""

    allowed_tools: dict[str, set[str]] = field(default_factory=dict)

    def allow_tool(self, role: str, tool_name: str) -> None:
        self.allowed_tools.setdefault(role, set()).add(tool_name)

    def check_tool(self, role: str, tool_name: str, risk_level: str) -> tuple[bool, str]:
        allowed = self.allowed_tools.get(role)
        if allowed is None:
            if risk_level in {"high", "destructive", "sensitive"}:
                return False, "high-risk tool denied by default"
            return True, "default allow for low/medium risk in local runtime"
        if tool_name in allowed:
            return True, "allowed by role policy"
        return False, f"tool {tool_name} not allowed for role {role}"
