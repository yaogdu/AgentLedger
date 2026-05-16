from __future__ import annotations

from typing import Any, Callable

from .tools import ToolRegistry, ToolSpec

ToolCallable = Callable[[dict[str, Any]], Any]


def _not_implemented(args: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError("media tool convention has no executor; inject an adapter implementation")


def media_tool_specs(executors: dict[str, ToolCallable] | None = None) -> list[ToolSpec]:
    """Return dependency-free ToolSpec conventions for media/stream adapters."""

    funcs = executors or {}
    return [
        ToolSpec(
            name="audio.transcribe",
            description="Transcribe an audio artifact ref and return transcript artifact refs.",
            func=funcs.get("audio.transcribe", _not_implemented),
            side_effect="external_read",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["source_ref"],
                "properties": {
                    "source_ref": {"type": "string", "minLength": 1},
                    "mime_type": {"type": "string"},
                    "language": {"type": "string"},
                    "options": {"type": "object"},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["transcript_ref"],
                "properties": {
                    "transcript_ref": {"type": "string", "minLength": 1},
                    "language": {"type": "string"},
                    "segments": {"type": "array", "items": {"type": "object"}},
                    "artifact_id": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="video.extract_frames",
            description="Extract frame artifact refs from a video artifact ref.",
            func=funcs.get("video.extract_frames", _not_implemented),
            side_effect="external_read",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["source_ref"],
                "properties": {
                    "source_ref": {"type": "string", "minLength": 1},
                    "interval_seconds": {"type": "number", "minimum": 0},
                    "max_frames": {"type": "integer", "minimum": 1},
                    "options": {"type": "object"},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["frame_refs"],
                "properties": {
                    "frame_refs": {"type": "array", "items": {"type": "object"}},
                    "timeline_ref": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="frame.describe",
            description="Describe a frame artifact ref and return a derived text artifact ref.",
            func=funcs.get("frame.describe", _not_implemented),
            side_effect="external_read",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["frame_ref"],
                "properties": {
                    "frame_ref": {"type": "string", "minLength": 1},
                    "prompt": {"type": "string"},
                    "options": {"type": "object"},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["description"],
                "properties": {
                    "description": {"type": "string"},
                    "artifact_id": {"type": "string"},
                    "description_ref": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="video.summarize",
            description="Summarize video, frame, transcript, or segment artifact refs.",
            func=funcs.get("video.summarize", _not_implemented),
            side_effect="external_read",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["source_refs"],
                "properties": {
                    "source_refs": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                    "prompt": {"type": "string"},
                    "options": {"type": "object"},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["summary"],
                "properties": {
                    "summary": {"type": "string"},
                    "summary_ref": {"type": "string"},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="stream.consume",
            description="Consume a stream chunk and return a durable checkpoint or partial result refs.",
            func=funcs.get("stream.consume", _not_implemented),
            side_effect="external_read",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["stream_id", "consumer_id", "offset"],
                "properties": {
                    "stream_id": {"type": "string", "minLength": 1},
                    "consumer_id": {"type": "string", "minLength": 1},
                    "offset": {"type": ["integer", "string"]},
                    "max_chunks": {"type": "integer", "minimum": 1},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["checkpoint"],
                "properties": {
                    "checkpoint": {"type": "object"},
                    "chunks": {"type": "array", "items": {"type": "object"}},
                    "partial_result_ref": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        ToolSpec(
            name="stream.emit",
            description="Emit a stream event or derived chunk through a managed adapter.",
            func=funcs.get("stream.emit", _not_implemented),
            side_effect="external_write",
            risk_level="medium",
            idempotency_required=True,
            input_schema={
                "type": "object",
                "required": ["stream_id", "payload_ref"],
                "properties": {
                    "stream_id": {"type": "string", "minLength": 1},
                    "payload_ref": {"type": "string", "minLength": 1},
                    "partition_key": {"type": "string"},
                    "_logical_operation": {"type": "string"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["external_id"],
                "properties": {
                    "external_id": {"type": "string"},
                    "offset": {"type": ["integer", "string"]},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
        ),
    ]


def register_media_tool_conventions(
    registry: ToolRegistry,
    executors: dict[str, ToolCallable] | None = None,
) -> list[ToolSpec]:
    specs = media_tool_specs(executors)
    for spec in specs:
        registry.register(spec)
    return specs
