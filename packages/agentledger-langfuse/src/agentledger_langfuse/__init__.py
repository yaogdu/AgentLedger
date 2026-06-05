from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from agentledger.trace import TraceExporter, TraceSpan

__version__ = "1.2.4"


@dataclass(frozen=True)
class LangfuseProject:
    public_key: str | None = None
    project: str | None = None
    environment: str | None = None
    release: str | None = None
    tags: tuple[str, ...] = ()


class LangfuseTraceExporter:
    """Convert AgentLedger evidence spans into Langfuse-style ingestion records.

    The exporter is dependency-free and SDK-neutral. Applications that already
    use the Langfuse SDK can consume `to_ingestion_payload(...)`; deployments
    that prefer HTTP can call `post_json(...)` with their own endpoint and auth
    headers. Runtime-core does not own Langfuse project/key management.
    """

    def __init__(self, *, project: LangfuseProject | None = None, trace_exporter: TraceExporter | None = None) -> None:
        self.project = project or LangfuseProject()
        self.trace_exporter = trace_exporter or TraceExporter()

    def to_ingestion_payload(self, evidence: Any) -> dict[str, Any]:
        spans = self.trace_exporter.spans(evidence)
        return {
            "batch": [self._span_record(span) for span in spans],
            "metadata": {
                "source": "agentledger",
                "project": self.project.project,
                "environment": self.project.environment,
                "release": self.project.release,
                "tags": list(self.project.tags),
            },
        }

    def to_json(self, evidence: Any) -> str:
        return json.dumps(self.to_ingestion_payload(evidence), ensure_ascii=False, indent=2, sort_keys=True)

    def post_json(
        self,
        evidence: Any,
        endpoint: str,
        *,
        secret_key: str | None = None,
        timeout: float = 10.0,
        opener: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = self.to_json(evidence).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if self.project.public_key:
            request_headers["X-Langfuse-Public-Key"] = self.project.public_key
        if secret_key:
            request_headers["Authorization"] = f"Bearer {secret_key}"
        request = Request(endpoint, data=body, headers=request_headers, method="POST")
        sender = opener or urlopen
        response = sender(request, timeout=timeout)
        status = getattr(response, "status", getattr(response, "code", None))
        response_body = response.read().decode("utf-8", errors="replace") if hasattr(response, "read") else ""
        if status is not None and int(status) >= 400:
            raise RuntimeError(f"Langfuse endpoint returned HTTP {status}: {response_body}")
        return {"endpoint": endpoint, "status": status, "bytes_sent": len(body), "response": response_body}

    def _span_record(self, span: TraceSpan) -> dict[str, Any]:
        return {
            "type": "trace-span",
            "traceId": span.trace_id,
            "id": span.span_id,
            "parentObservationId": span.parent_span_id,
            "name": span.name,
            "startTime": span.start_time,
            "endTime": span.end_time,
            "metadata": {
                **span.attributes,
                "agentledger.exporter": "langfuse",
                "agentledger.project": self.project.project,
                "agentledger.environment": self.project.environment,
                "agentledger.release": self.project.release,
            },
            "tags": list(self.project.tags),
        }


__all__ = ["LangfuseProject", "LangfuseTraceExporter", "__version__"]
