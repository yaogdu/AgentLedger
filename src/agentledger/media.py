from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MEDIA_SCHEMA_VERSION = "agentledger.media.v0"
STREAM_SCHEMA_VERSION = "agentledger.stream.v0"

MEDIA_KINDS = {
    "image",
    "audio",
    "video",
    "frame",
    "audio_segment",
    "video_segment",
    "transcript",
    "embedding",
    "derived",
}


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return value
    raise TypeError(f"expected dict-like value, got {type(value).__name__}")


def _validate_non_negative(name: str, value: float | int | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must be non-negative")


def validate_media_kind(kind: str) -> str:
    if kind not in MEDIA_KINDS:
        allowed = ", ".join(sorted(MEDIA_KINDS))
        raise ValueError(f"unsupported media kind {kind!r}; expected one of: {allowed}")
    return kind


@dataclass(frozen=True)
class ArtifactLineage:
    """Refs that explain how an artifact was derived without embedding payloads."""

    source_artifact_ids: list[str] = field(default_factory=list)
    source_blob_refs: list[str] = field(default_factory=list)
    tool_call_ids: list[str] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "source_artifact_ids": list(self.source_artifact_ids),
                "source_blob_refs": list(self.source_blob_refs),
                "tool_call_ids": list(self.tool_call_ids),
                "event_ids": list(self.event_ids),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True)
class MediaMetadata:
    """Portable metadata for media refs; runtime-core does not process codecs."""

    kind: str
    mime_type: str | None = None
    codec: str | None = None
    duration_seconds: float | None = None
    fps: float | None = None
    sample_rate_hz: int | None = None
    width: int | None = None
    height: int | None = None
    channels: int | None = None
    timestamp_start_seconds: float | None = None
    timestamp_end_seconds: float | None = None
    frame_index: int | None = None
    segment_index: int | None = None
    transcript_language: str | None = None
    embedding_model: str | None = None
    source_uri: str | None = None
    checksum: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_media_kind(self.kind)
        for name in [
            "duration_seconds",
            "fps",
            "sample_rate_hz",
            "width",
            "height",
            "channels",
            "timestamp_start_seconds",
            "timestamp_end_seconds",
            "frame_index",
            "segment_index",
        ]:
            _validate_non_negative(name, getattr(self, name))

    def to_dict(self) -> dict[str, Any]:
        data = _drop_none(
            {
                "schema_version": MEDIA_SCHEMA_VERSION,
                "kind": self.kind,
                "mime_type": self.mime_type,
                "codec": self.codec,
                "duration_seconds": self.duration_seconds,
                "fps": self.fps,
                "sample_rate_hz": self.sample_rate_hz,
                "width": self.width,
                "height": self.height,
                "channels": self.channels,
                "timestamp_start_seconds": self.timestamp_start_seconds,
                "timestamp_end_seconds": self.timestamp_end_seconds,
                "frame_index": self.frame_index,
                "segment_index": self.segment_index,
                "transcript_language": self.transcript_language,
                "embedding_model": self.embedding_model,
                "source_uri": self.source_uri,
                "checksum": self.checksum,
            }
        )
        if self.extra:
            data["extra"] = dict(self.extra)
        return data


@dataclass(frozen=True)
class MediaArtifact:
    """Manifest for a media artifact reference and its lineage."""

    kind: str
    uri: str | None = None
    content_ref: str | None = None
    metadata: MediaMetadata | dict[str, Any] | None = None
    lineage: ArtifactLineage | dict[str, Any] | None = None
    derived_outputs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_media_kind(self.kind)

    def to_content(self) -> dict[str, Any]:
        metadata = _as_dict(self.metadata)
        if not metadata:
            metadata = MediaMetadata(kind=self.kind).to_dict()
        else:
            metadata = {"schema_version": metadata.get("schema_version", MEDIA_SCHEMA_VERSION), **metadata}
            metadata["kind"] = self.kind
        return _drop_none(
            {
                "schema_version": MEDIA_SCHEMA_VERSION,
                "kind": self.kind,
                "uri": self.uri,
                "content_ref": self.content_ref,
                "metadata": metadata,
                "lineage": _as_dict(self.lineage),
                "derived_outputs": dict(self.derived_outputs) if self.derived_outputs else None,
            }
        )

    def to_artifact_metadata(self) -> dict[str, Any]:
        content = self.to_content()
        return {
            "agentledger_media": _drop_none(
                {
                    "schema_version": MEDIA_SCHEMA_VERSION,
                    "kind": self.kind,
                    "uri": self.uri,
                    "content_ref": self.content_ref,
                    "metadata": content.get("metadata", {}),
                    "lineage": content.get("lineage", {}),
                }
            )
        }


@dataclass(frozen=True)
class StreamChunkRef:
    """Reference to an immutable chunk in an external or runtime BlobStore."""

    stream_id: str
    chunk_id: str
    offset: int | str
    content_ref: str | None = None
    content_hash: str | None = None
    sequence: int | None = None
    event_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.offset, int):
            _validate_non_negative("offset", self.offset)
        _validate_non_negative("sequence", self.sequence)

    def to_dict(self) -> dict[str, Any]:
        return _drop_none(
            {
                "schema_version": STREAM_SCHEMA_VERSION,
                "stream_id": self.stream_id,
                "chunk_id": self.chunk_id,
                "offset": self.offset,
                "content_ref": self.content_ref,
                "content_hash": self.content_hash,
                "sequence": self.sequence,
                "event_time": self.event_time,
                "metadata": dict(self.metadata) if self.metadata else None,
            }
        )


@dataclass(frozen=True)
class EventStreamCheckpoint:
    """Durable cursor for resumable stream consumers."""

    stream_id: str
    consumer_id: str
    offset: int | str
    watermark: float | str | None = None
    chunk: StreamChunkRef | dict[str, Any] | None = None
    partial_result_ref: str | None = None
    backpressure: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.offset, int):
            _validate_non_negative("offset", self.offset)

    def to_content(self) -> dict[str, Any]:
        return _drop_none(
            {
                "schema_version": STREAM_SCHEMA_VERSION,
                "stream_id": self.stream_id,
                "consumer_id": self.consumer_id,
                "offset": self.offset,
                "watermark": self.watermark,
                "chunk": _as_dict(self.chunk),
                "partial_result_ref": self.partial_result_ref,
                "backpressure": dict(self.backpressure) if self.backpressure else None,
                "metadata": dict(self.metadata) if self.metadata else None,
            }
        )

    def to_artifact_metadata(self) -> dict[str, Any]:
        content = self.to_content()
        return {
            "agentledger_stream": _drop_none(
                {
                    "schema_version": STREAM_SCHEMA_VERSION,
                    "stream_id": self.stream_id,
                    "consumer_id": self.consumer_id,
                    "offset": self.offset,
                    "watermark": self.watermark,
                    "chunk": content.get("chunk", {}),
                    "partial_result_ref": self.partial_result_ref,
                    "backpressure": content.get("backpressure", {}),
                }
            )
        }
