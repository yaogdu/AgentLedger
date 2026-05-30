from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contract import CONTRACT_VERSION


@dataclass(frozen=True)
class AdapterCertificationBundle:
    """Machine-readable certification manifest for an optional adapter package.

    The bundle is intentionally evidence-oriented. It records what can be
    checked locally, what commands prove the local contract, and which parts
    still require external production validation.
    """

    adapter: str
    adapter_type: str
    package_name: str
    adapter_version: str
    contract_version: str = CONTRACT_VERSION
    conformance_commands: list[str] = field(default_factory=list)
    smoke_commands: list[str] = field(default_factory=list)
    required_external_services: list[str] = field(default_factory=list)
    security_assumptions: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    production_validation_required: bool = True
    production_validation_status: str = "external-required"
    production_validation_reason: str = "requires real service credentials, load/concurrency checks, and restore or rollback drills"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "agentledger.adapter_certification.v1",
            "adapter": self.adapter,
            "adapter_type": self.adapter_type,
            "package_name": self.package_name,
            "adapter_version": self.adapter_version,
            "agentledger_contract_version": self.contract_version,
            "conformance_commands": list(self.conformance_commands),
            "smoke_commands": list(self.smoke_commands),
            "required_external_services": list(self.required_external_services),
            "security_assumptions": list(self.security_assumptions),
            "known_limitations": list(self.known_limitations),
            "production_validation": {
                "required": self.production_validation_required,
                "status": self.production_validation_status,
                "reason": self.production_validation_reason,
            },
        }


_PROFILES: dict[str, dict[str, Any]] = {
    "postgres": {
        "adapter": "postgres",
        "adapter_type": "state_store",
        "package_name": "agentledger-postgres",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger state conformance --backend postgres",
            "PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 -m agentledger migrate status --dialect postgres",
            "PYTHONPATH=src python3 -m agentledger migrate up --dialect postgres",
        ],
        "required_external_services": ["postgres"],
        "security_assumptions": [
            "DSN credentials are provided through environment or secret manager and are redacted from evidence",
            "schema/user permissions are scoped to AgentLedger tables",
            "backup and restore are owned by the deployment environment",
        ],
        "known_limitations": [
            "local injected conformance is not a substitute for real-service transaction, lock, and restore drills",
        ],
    },
    "mysql": {
        "adapter": "mysql",
        "adapter_type": "state_store",
        "package_name": "agentledger-mysql",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger state conformance --backend mysql",
            "PYTHONPATH=src python3 -m agentledger worker conformance --backend mysql --concurrent",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 -m agentledger migrate status --dialect mysql",
            "PYTHONPATH=src python3 -m agentledger migrate up --dialect mysql",
        ],
        "required_external_services": ["mysql"],
        "security_assumptions": [
            "DSN credentials are provided through environment or secret manager and are redacted from evidence",
            "database/user permissions are scoped to AgentLedger tables",
            "backup and restore are owned by the deployment environment",
        ],
        "known_limitations": [
            "local injected conformance is not a substitute for real-service transaction, lock, and restore drills",
        ],
    },
    "s3": {
        "adapter": "s3",
        "adapter_type": "blob_store",
        "package_name": "agentledger-s3",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger blob conformance --backend s3",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./evidence/run",
        ],
        "required_external_services": ["s3-compatible-object-store"],
        "security_assumptions": [
            "bucket credentials are scoped to the configured prefix",
            "large payloads and media refs are encrypted according to the deployment policy",
            "lifecycle and retention rules are configured outside runtime-core",
        ],
        "known_limitations": [
            "local injected conformance does not prove IAM, KMS, lifecycle, multipart, or restore behavior",
        ],
    },
    "mcp": {
        "adapter": "mcp",
        "adapter_type": "tool_context_protocol",
        "package_name": "agentledger-mcp",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 examples/mcp/basic_tool.py",
            "PYTHONPATH=src python3 examples/mcp/context_read.py",
        ],
        "required_external_services": ["mcp-server"],
        "security_assumptions": [
            "MCP tools are registered as ToolSpec entries with explicit risk and side-effect metadata",
            "resource reads that affect agent inputs are audited through ToolGateway",
        ],
        "known_limitations": [
            "dependency-free fixtures prove mapping semantics, not every upstream MCP transport edge case",
        ],
    },
    "docker": {
        "adapter": "docker",
        "adapter_type": "sandbox",
        "package_name": "agentledger-sandbox-docker",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger sandbox inspect examples/sandbox/sandbox.yaml",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 examples/sandbox/command_tool.py",
        ],
        "required_external_services": ["docker-daemon"],
        "security_assumptions": [
            "sandbox policy is fail-closed when Docker is unavailable",
            "network, filesystem, environment, and secret exposure are explicitly configured",
        ],
        "known_limitations": [
            "runtime-core does not prove container escape resistance or host hardening",
        ],
    },
    "otel": {
        "adapter": "otel",
        "adapter_type": "observability",
        "package_name": "agentledger-otel",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger trace <run_id> --format otlp --out ./trace.otlp.json",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 -m agentledger trace <run_id> --out ./trace.jsonl",
        ],
        "required_external_services": ["optional-otlp-collector"],
        "security_assumptions": [
            "trace exporters redact secrets and avoid embedding raw tool payloads unless explicitly allowed",
            "collector endpoint and headers are deployment configuration, not runtime-core defaults",
        ],
        "known_limitations": [
            "file/JSON export is dependency-free; collector delivery needs deployment-specific verification",
        ],
    },
    "langfuse": {
        "adapter": "langfuse",
        "adapter_type": "observability",
        "package_name": "agentledger-langfuse",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger evidence export <run_id> --out ./evidence",
        ],
        "smoke_commands": [
            "python3 -c 'from agentledger_langfuse import LangfuseTraceExporter; print(LangfuseTraceExporter.__name__)'",
        ],
        "required_external_services": ["optional-langfuse-endpoint"],
        "security_assumptions": [
            "Langfuse receives exported runtime evidence and traces; AgentLedger remains the execution-path enforcement layer",
            "project keys, auth headers, and endpoint routing are user deployment configuration",
        ],
        "known_limitations": [
            "adapter is a dependency-free payload/export boundary; Langfuse SDK and server-specific ingestion behavior must be validated by the application",
        ],
    },
    "langgraph": {
        "adapter": "langgraph",
        "adapter_type": "framework",
        "package_name": "agentledger-langgraph",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger adapter conformance --kind langgraph-node",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 examples/langgraph/basic_graph.py",
        ],
        "required_external_services": [],
        "security_assumptions": [
            "framework tool calls that create side effects are routed through AgentLedger ToolGateway",
            "checkpoints and state refs remain behind AgentLedger StateStore or durable artifact refs",
        ],
        "known_limitations": [
            "dependency-free facade proves runtime boundary semantics; native LangGraph version compatibility must be certified per package release",
        ],
        "production_validation_required": False,
        "production_validation_status": "local-contract-verified",
        "production_validation_reason": "framework facade certification can be checked locally; production app behavior still depends on user workflow code",
    },
    "temporal": {
        "adapter": "temporal",
        "adapter_type": "execution_backend",
        "package_name": "agentledger-temporal",
        "conformance_commands": [
            "PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent",
        ],
        "smoke_commands": [
            "PYTHONPATH=src python3 -m agentledger worker plan examples/transient_retry --backend postgres --replicas 2",
        ],
        "required_external_services": ["temporal-service"],
        "security_assumptions": [
            "Temporal owns generic workflow scheduling; AgentLedger still owns agent evidence, Tool Ledger, and state/fencing semantics",
            "workflow retry policy must not bypass AgentLedger idempotency and replay rules",
        ],
        "known_limitations": [
            "runtime-core only defines the execution backend boundary; real Temporal worker deployment must be certified separately",
        ],
    },
}


def supported_adapter_certification_profiles() -> list[str]:
    return sorted(_PROFILES)


def build_adapter_certification_bundle(
    kind: str,
    *,
    adapter_version: str,
    package_name: str | None = None,
) -> AdapterCertificationBundle:
    try:
        profile = _PROFILES[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported adapter certification kind: {kind}") from exc

    values = dict(profile)
    values["adapter_version"] = adapter_version
    if package_name is not None:
        values["package_name"] = package_name
    return AdapterCertificationBundle(**values)
