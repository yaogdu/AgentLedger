from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .blobstore import LocalBlobStore
from .evidence import EvidenceExporter
from .store import SQLiteStore


@dataclass(frozen=True)
class BackupCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class BackupReadinessReport:
    run_id: str
    passed: bool
    checks: list[BackupCheck]
    refs_checked: int
    missing_refs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "refs_checked": self.refs_checked,
            "missing_refs": self.missing_refs,
        }


class BackupReadinessChecker:
    """Read-only checks for whether a run has enough data to be backed up."""

    def __init__(self, *, store: SQLiteStore, blobs: LocalBlobStore):
        self.store = store
        self.blobs = blobs

    def check_run(self, run_id: str) -> BackupReadinessReport:
        checks: list[BackupCheck] = []
        missing_refs: list[str] = []
        refs = self._payload_refs(run_id)

        try:
            self.store.run(run_id)
            checks.append(BackupCheck("run_metadata_exists", True, "run row is present"))
        except Exception as exc:
            checks.append(BackupCheck("run_metadata_exists", False, repr(exc)))

        schema_version = self.store.schema_version() if hasattr(self.store, "schema_version") else None
        checks.append(BackupCheck("schema_version_recorded", schema_version is not None, f"schema_version={schema_version}"))

        for ref in refs:
            try:
                self.blobs.get_json(ref)
            except Exception:
                missing_refs.append(ref)
        checks.append(BackupCheck("payload_refs_resolvable", not missing_refs, f"checked={len(refs)}, missing={len(missing_refs)}"))

        evidence: dict[str, Any] | None = None
        try:
            evidence = EvidenceExporter(store=self.store, blobs=self.blobs).export(run_id).to_dict()
            checks.append(BackupCheck("evidence_exportable", True, "evidence bundle can be constructed"))
        except Exception as exc:
            checks.append(BackupCheck("evidence_exportable", False, repr(exc)))

        if evidence is not None:
            checks.append(BackupCheck("media_stream_evidence_shape", self._media_stream_shape_ok(evidence), "media artifacts and stream checkpoints have required refs/cursors"))

        return BackupReadinessReport(
            run_id=run_id,
            passed=all(check.passed for check in checks),
            checks=checks,
            refs_checked=len(refs),
            missing_refs=missing_refs,
        )

    def _payload_refs(self, run_id: str) -> list[str]:
        refs: list[str] = []
        for row in self.store.events(run_id):
            self._append_ref(refs, row["payload_ref"])
        for row in self.store.ledger(run_id):
            self._append_ref(refs, row["request_ref"])
            self._append_ref(refs, row["response_ref"])
        for row in self.store.artifacts(run_id):
            self._append_ref(refs, row["blob_ref"])
            self._append_refs_from_value(refs, self._decode_metadata(row["metadata_json"]))
        return refs

    def _append_ref(self, refs: list[str], value: Any) -> None:
        if isinstance(value, str) and value.startswith("blob://"):
            refs.append(value)

    def _append_refs_from_value(self, refs: list[str], value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                self._append_refs_from_value(refs, item)
            return
        if isinstance(value, list):
            for item in value:
                self._append_refs_from_value(refs, item)
            return
        self._append_ref(refs, value)

    def _decode_metadata(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return data if isinstance(data, dict) else {}
        return {}

    def _media_stream_shape_ok(self, evidence: dict[str, Any]) -> bool:
        media_ok = all(row.get("kind") and (row.get("uri") or row.get("content_ref") or row.get("blob_ref")) for row in evidence.get("media_artifacts", []))
        stream_ok = all(row.get("stream_id") and row.get("consumer_id") and row.get("offset") is not None for row in evidence.get("stream_checkpoints", []))
        return media_ok and stream_ok
