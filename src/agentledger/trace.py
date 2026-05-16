from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .evidence import EvidenceBundle


@dataclass(frozen=True)
class TraceSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    start_time: float
    end_time: float
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "attributes": self.attributes,
        }


class TraceExporter:
    """Export evidence events as structured local trace spans.

    This is intentionally not an OpenTelemetry dependency. The JSONL format is a
    stable bridge that a later `runtime-otel` package can translate into OTLP.
    """

    def spans(self, evidence: EvidenceBundle | dict[str, Any]) -> list[TraceSpan]:
        data = evidence.to_dict() if isinstance(evidence, EvidenceBundle) else evidence
        run_id = data.get("run", {}).get("run_id", "run_unknown")
        events = data.get("events", [])
        spans: list[TraceSpan] = []
        for event in events:
            seq = int(event.get("seq", len(spans) + 1))
            timestamp = float(event.get("timestamp", 0.0) or 0.0)
            spans.append(
                TraceSpan(
                    trace_id=run_id,
                    span_id=f"evt-{seq:06d}",
                    parent_span_id=None,
                    name=str(event.get("type", "event")),
                    start_time=timestamp,
                    end_time=timestamp,
                    attributes={
                        "agentledger.run_id": run_id,
                        "agentledger.session_id": event.get("session_id"),
                        "agentledger.step_id": event.get("step_id"),
                        "agentledger.seq": seq,
                        "agentledger.state_version": event.get("state_version"),
                        "agentledger.payload_hash": event.get("payload_hash"),
                        "agentledger.payload_ref": event.get("payload_ref"),
                    },
                )
            )
        run_updated_at = float(data.get("run", {}).get("updated_at", 0.0) or 0.0)
        for index, artifact in enumerate(data.get("media_artifacts", []), start=1):
            spans.append(
                TraceSpan(
                    trace_id=run_id,
                    span_id=f"media-{index:06d}",
                    parent_span_id=None,
                    name="media_artifact",
                    start_time=run_updated_at,
                    end_time=run_updated_at,
                    attributes={
                        "agentledger.run_id": run_id,
                        "agentledger.artifact_id": artifact.get("artifact_id"),
                        "agentledger.artifact_name": artifact.get("name"),
                        "agentledger.media_kind": artifact.get("kind"),
                        "agentledger.media_uri": artifact.get("uri"),
                        "agentledger.media_content_ref": artifact.get("content_ref"),
                        "agentledger.blob_hash": artifact.get("blob_hash"),
                        "agentledger.blob_ref": artifact.get("blob_ref"),
                    },
                )
            )
        for index, checkpoint in enumerate(data.get("stream_checkpoints", []), start=1):
            spans.append(
                TraceSpan(
                    trace_id=run_id,
                    span_id=f"stream-{index:06d}",
                    parent_span_id=None,
                    name="stream_checkpoint",
                    start_time=run_updated_at,
                    end_time=run_updated_at,
                    attributes={
                        "agentledger.run_id": run_id,
                        "agentledger.artifact_id": checkpoint.get("artifact_id"),
                        "agentledger.artifact_name": checkpoint.get("name"),
                        "agentledger.stream_id": checkpoint.get("stream_id"),
                        "agentledger.consumer_id": checkpoint.get("consumer_id"),
                        "agentledger.stream_offset": checkpoint.get("offset"),
                        "agentledger.stream_watermark": checkpoint.get("watermark"),
                        "agentledger.blob_hash": checkpoint.get("blob_hash"),
                        "agentledger.blob_ref": checkpoint.get("blob_ref"),
                    },
                )
            )
        return spans

    def to_jsonl(self, evidence: EvidenceBundle | dict[str, Any]) -> str:
        return "".join(json.dumps(span.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for span in self.spans(evidence))

    def write_jsonl(self, evidence: EvidenceBundle | dict[str, Any], path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_jsonl(evidence), encoding="utf-8")
        return target


@dataclass(frozen=True)
class OTLPResource:
    service_name: str = "agentledger"
    service_version: str | None = None
    attributes: dict[str, Any] | None = None


class OTLPTraceExporter:
    """Translate AgentLedger evidence spans into dependency-free OTLP JSON."""

    def __init__(self, *, resource: OTLPResource | None = None, trace_exporter: TraceExporter | None = None) -> None:
        self.resource = resource or OTLPResource()
        self.trace_exporter = trace_exporter or TraceExporter()

    def to_otlp_json(self, evidence: EvidenceBundle | dict[str, Any]) -> dict[str, Any]:
        spans = [self._span_to_otlp(span) for span in self.trace_exporter.spans(evidence)]
        return {
            "resourceSpans": [
                {
                    "resource": {"attributes": self._resource_attributes()},
                    "scopeSpans": [
                        {
                            "scope": {"name": "agentledger", "version": self.resource.service_version or "1.0.0"},
                            "spans": spans,
                        }
                    ],
                }
            ]
        }

    def to_json(self, evidence: EvidenceBundle | dict[str, Any]) -> str:
        return json.dumps(self.to_otlp_json(evidence), ensure_ascii=False, indent=2, sort_keys=True)

    def write_json(self, evidence: EvidenceBundle | dict[str, Any], path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(evidence) + "\n", encoding="utf-8")
        return target

    def post_json(
        self,
        evidence: EvidenceBundle | dict[str, Any],
        endpoint: str,
        *,
        timeout: float = 10.0,
        opener: Any | None = None,
    ) -> dict[str, Any]:
        """Send dependency-free OTLP/JSON to a collector endpoint.

        The optional opener keeps tests and custom transports side-effect free.
        """
        body = self.to_json(evidence).encode("utf-8")
        request = Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        sender = opener or urlopen
        response = sender(request, timeout=timeout)
        status = getattr(response, "status", getattr(response, "code", None))
        response_body = response.read().decode("utf-8", errors="replace") if hasattr(response, "read") else ""
        if status is not None and int(status) >= 400:
            raise RuntimeError(f"OTLP collector returned HTTP {status}: {response_body}")
        return {"endpoint": endpoint, "status": status, "bytes_sent": len(body), "response": response_body}

    def _resource_attributes(self) -> list[dict[str, Any]]:
        attrs = {"service.name": self.resource.service_name}
        if self.resource.service_version:
            attrs["service.version"] = self.resource.service_version
        if self.resource.attributes:
            attrs.update(self.resource.attributes)
        return [{"key": key, "value": self._otlp_value(value)} for key, value in sorted(attrs.items())]

    def _span_to_otlp(self, span: TraceSpan) -> dict[str, Any]:
        attrs = {**span.attributes, "agentledger.original_trace_id": span.trace_id, "agentledger.original_span_id": span.span_id}
        item = {
            "traceId": self._hex_id(span.trace_id, 32),
            "spanId": self._hex_id(span.span_id, 16),
            "name": span.name,
            "kind": "SPAN_KIND_INTERNAL",
            "startTimeUnixNano": str(int(span.start_time * 1_000_000_000)),
            "endTimeUnixNano": str(int(span.end_time * 1_000_000_000)),
            "attributes": [{"key": key, "value": self._otlp_value(value)} for key, value in sorted(attrs.items()) if value is not None],
        }
        if span.parent_span_id:
            item["parentSpanId"] = self._hex_id(span.parent_span_id, 16)
        return item

    def _otlp_value(self, value: Any) -> dict[str, Any]:
        if isinstance(value, bool):
            return {"boolValue": value}
        if isinstance(value, int) and not isinstance(value, bool):
            return {"intValue": str(value)}
        if isinstance(value, float):
            return {"doubleValue": value}
        if value is None:
            return {"stringValue": ""}
        if isinstance(value, str):
            return {"stringValue": value}
        return {"stringValue": json.dumps(value, ensure_ascii=False, sort_keys=True)}

    def _hex_id(self, value: str, length: int) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
