from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MODEL_EVIDENCE_SCHEMA_VERSION = "agentledger.model.evidence.v1"


@dataclass(frozen=True)
class ModelCallRecord:
    """Runtime evidence for a model call made by user code or a framework."""

    provider: str
    model: str
    request: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    total_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def request_payload(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "request": self.request or {},
            "metadata": dict(self.metadata),
        }

    def response_payload(self, *, request_ref: str | None = None, request_hash: str | None = None) -> dict[str, Any]:
        payload = {
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "response": self.response or {},
            "usage": dict(self.usage),
            "total_usd": float(self.total_usd),
            "metadata": dict(self.metadata),
        }
        if request_ref is not None:
            payload["request_ref"] = request_ref
        if request_hash is not None:
            payload["request_hash"] = request_hash
        return payload


@dataclass(frozen=True)
class ModelFailureRecord:
    provider: str
    model: str
    error_type: str
    message: str
    retryable: bool | None = None
    request: dict[str, Any] | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    total_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def request_payload(self) -> dict[str, Any]:
        return {
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "request": self.request or {},
            "metadata": dict(self.metadata),
        }

    def failure_payload(self, *, request_ref: str | None = None, request_hash: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
            "provider": self.provider,
            "model": self.model,
            "error_type": self.error_type,
            "error": self.message,
            "usage": dict(self.usage),
            "total_usd": float(self.total_usd),
            "metadata": dict(self.metadata),
        }
        if self.retryable is not None:
            payload["retryable"] = bool(self.retryable)
        if request_ref is not None:
            payload["request_ref"] = request_ref
        if request_hash is not None:
            payload["request_hash"] = request_hash
        return payload


@dataclass(frozen=True)
class ToolCallProposal:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    model_call_ref: str | None = None
    confidence: float | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": MODEL_EVIDENCE_SCHEMA_VERSION,
            "tool": self.tool_name,
            "args": dict(self.arguments),
            "metadata": dict(self.metadata),
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.model is not None:
            payload["model"] = self.model
        if self.model_call_ref is not None:
            payload["model_call_ref"] = self.model_call_ref
        if self.confidence is not None:
            payload["confidence"] = float(self.confidence)
        if self.reason is not None:
            payload["reason"] = self.reason
        return payload


def usage_total_tokens(usage: dict[str, Any] | None) -> int:
    if not isinstance(usage, dict):
        return 0
    for key in ("total_tokens", "totalTokens", "tokens"):
        value = usage.get(key)
        if value is not None:
            return int(value or 0)
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", usage.get("inputTokens", 0)))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", usage.get("outputTokens", 0)))
    return int(input_tokens or 0) + int(output_tokens or 0)
