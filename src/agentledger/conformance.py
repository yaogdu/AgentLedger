from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import tempfile
from pathlib import Path
from typing import Any, Callable

StoreFactory = Callable[[], Any]
BlobFactory = Callable[[], Any]
AdapterFactory = Callable[[], Any]


@dataclass(frozen=True)
class ConformanceCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class ConformanceReport:
    name: str
    passed: bool
    checks: list[ConformanceCheck]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "checks": [check.to_dict() for check in self.checks]}


class StateStoreConformanceRunner:
    """Executable conformance checks for StateStore implementations."""

    def __init__(self, store_factory: StoreFactory, *, name: str = "state-store", close_stores: bool = False):
        self.store_factory = store_factory
        self.name = name
        self.close_stores = close_stores

    def run(self) -> ConformanceReport:
        checks = [
            self._check_create_claim_commit(),
            self._check_stale_lease_rejected(),
            self._check_expired_lease_recovered(),
            self._check_cancel_fences_worker(),
        ]
        return ConformanceReport(name=self.name, passed=all(check.passed for check in checks), checks=checks)

    def _check_create_claim_commit(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, step_id = store.create_run(initial_state={"x": 1})
            claim = store.claim_step(worker_id="conf-a", run_id=run_id)
            assert claim is not None
            version = store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=claim.lease_token, base_version=0, patch={"ok": True})
            assert version == 1
            assert store.final_state(run_id)["ok"] is True
            return ConformanceCheck("create_claim_commit", True, "state commit and event flow succeeded")
        except Exception as exc:  # pragma: no cover - returned for adapter diagnostics
            return ConformanceCheck("create_claim_commit", False, repr(exc))
        finally:
            self._close_store(store)

    def _check_stale_lease_rejected(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, step_id = store.create_run(initial_state={})
            store.claim_step(worker_id="conf-a", run_id=run_id)
            try:
                store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token="bad-token", base_version=0, patch={"bad": True})
            except RuntimeError:
                return ConformanceCheck("stale_lease_rejected", True, "bad lease token was rejected")
            return ConformanceCheck("stale_lease_rejected", False, "bad lease token was accepted")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("stale_lease_rejected", False, repr(exc))
        finally:
            self._close_store(store)

    def _check_expired_lease_recovered(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, _ = store.create_run(initial_state={})
            claim = store.claim_step(worker_id="conf-a", run_id=run_id, lease_seconds=0)
            assert claim is not None
            recovered = store.recover_expired_leases()
            assert recovered >= 1
            second = store.claim_step(worker_id="conf-b", run_id=run_id)
            assert second is not None and second.attempt == 2
            return ConformanceCheck("expired_lease_recovered", True, "expired lease was rescheduled and reclaimed")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("expired_lease_recovered", False, repr(exc))
        finally:
            self._close_store(store)

    def _check_cancel_fences_worker(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, step_id = store.create_run(initial_state={})
            claim = store.claim_step(worker_id="conf-a", run_id=run_id)
            assert claim is not None
            cancelled = store.cancel_run(run_id=run_id, reason="conformance")
            assert cancelled == 1
            try:
                store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=claim.lease_token, base_version=0, patch={"late": True})
            except RuntimeError:
                return ConformanceCheck("cancel_fences_worker", True, "cancelled lease was fenced")
            return ConformanceCheck("cancel_fences_worker", False, "cancelled lease was accepted")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("cancel_fences_worker", False, repr(exc))
        finally:
            self._close_store(store)

    def _close_store(self, store: Any | None) -> None:
        if not self.close_stores:
            return
        close = getattr(store, "close", None)
        if callable(close):
            close()


class WorkerConformanceRunner:
    """Checks worker-pool lease invariants against a shared StateStore backend."""

    def __init__(self, store_factory: StoreFactory, *, name: str = "worker-runtime", workers: int = 4, concurrent: bool = False, close_stores: bool = True):
        self.store_factory = store_factory
        self.name = name
        self.workers = max(2, workers)
        self.concurrent = concurrent
        self.close_stores = close_stores

    def run(self) -> ConformanceReport:
        checks = [
            self._check_multi_worker_claims_distinct_steps(),
            self._check_heartbeat_fences_wrong_owner(),
            self._check_recovery_fences_previous_owner(),
        ]
        return ConformanceReport(name=self.name, passed=all(check.passed for check in checks), checks=checks)

    def _check_multi_worker_claims_distinct_steps(self) -> ConformanceCheck:
        coordinator = None
        try:
            coordinator = self.store_factory()
            run_ids: list[str] = []
            for index in range(self.workers):
                run_id, _ = coordinator.create_run(initial_state={"worker_conformance_index": index})
                run_ids.append(run_id)

            def claim(index: int) -> Any | None:
                store = self.store_factory()
                try:
                    for run_id in run_ids:
                        claimed = store.claim_step(worker_id=f"worker-conf-{index}", run_id=run_id, lease_seconds=30)
                        if claimed is not None:
                            return claimed
                    return None
                finally:
                    self._close_if_distinct(store, coordinator)

            if self.concurrent:
                with ThreadPoolExecutor(max_workers=self.workers) as executor:
                    claims = list(executor.map(claim, range(self.workers)))
            else:
                claims = [claim(index) for index in range(self.workers)]

            successful = [claim for claim in claims if claim is not None]
            if len(successful) != self.workers:
                return ConformanceCheck("multi_worker_claims_distinct_steps", False, f"expected {self.workers} claims, got {len(successful)}")
            step_ids = {claim.step_id for claim in successful}
            run_ids = {claim.run_id for claim in successful}
            if len(step_ids) != self.workers or len(run_ids) != self.workers:
                return ConformanceCheck("multi_worker_claims_distinct_steps", False, "duplicate step or run was claimed")
            extra_store = self.store_factory()
            try:
                extra = None
                for run_id in run_ids:
                    extra = extra_store.claim_step(worker_id="worker-conf-extra", run_id=run_id, lease_seconds=30)
                    if extra is not None:
                        break
            finally:
                self._close_if_distinct(extra_store, coordinator)
            if extra is not None:
                return ConformanceCheck("multi_worker_claims_distinct_steps", False, "claimed more steps than were pending")
            return ConformanceCheck("multi_worker_claims_distinct_steps", True, f"{self.workers} workers claimed {self.workers} distinct steps")
        except Exception as exc:  # pragma: no cover - returned for adapter diagnostics
            return ConformanceCheck("multi_worker_claims_distinct_steps", False, repr(exc))
        finally:
            self._close_if_present(coordinator)

    def _check_heartbeat_fences_wrong_owner(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, step_id = store.create_run(initial_state={})
            claim = store.claim_step(worker_id="worker-conf-heartbeat", run_id=run_id)
            assert claim is not None
            try:
                store.heartbeat(step_id=step_id, lease_token="bad-token")
            except RuntimeError:
                lease_until = store.heartbeat(step_id=step_id, lease_token=claim.lease_token, lease_seconds=120)
                assert lease_until >= claim.lease_until
                return ConformanceCheck("heartbeat_fences_wrong_owner", True, "bad heartbeat token rejected and current lease extended")
            return ConformanceCheck("heartbeat_fences_wrong_owner", False, "bad heartbeat token was accepted")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("heartbeat_fences_wrong_owner", False, repr(exc))
        finally:
            self._close_if_present(store)

    def _check_recovery_fences_previous_owner(self) -> ConformanceCheck:
        store = None
        try:
            store = self.store_factory()
            run_id, step_id = store.create_run(initial_state={})
            old_claim = store.claim_step(worker_id="worker-conf-old", run_id=run_id, lease_seconds=0)
            assert old_claim is not None
            recovered = store.recover_expired_leases()
            assert recovered >= 1
            new_claim = store.claim_step(worker_id="worker-conf-new", run_id=run_id)
            assert new_claim is not None and new_claim.attempt == old_claim.attempt + 1
            try:
                store.commit_state_patch(run_id=run_id, step_id=step_id, lease_token=old_claim.lease_token, base_version=0, patch={"stale": True})
            except RuntimeError:
                return ConformanceCheck("recovery_fences_previous_owner", True, "old lease was fenced after recovery")
            return ConformanceCheck("recovery_fences_previous_owner", False, "old lease committed after recovery")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("recovery_fences_previous_owner", False, repr(exc))
        finally:
            self._close_if_present(store)

    def _close_if_distinct(self, store: Any, protected: Any) -> None:
        if store is protected:
            return
        self._close_if_present(store)

    def _close_if_present(self, store: Any | None) -> None:
        if not self.close_stores:
            return
        close = getattr(store, "close", None)
        if callable(close):
            close()


class BlobStoreConformanceRunner:
    """Executable conformance checks for BlobStore implementations."""

    def __init__(self, blob_factory: BlobFactory, *, name: str = "blob-store"):
        self.blob_factory = blob_factory
        self.name = name

    def run(self) -> ConformanceReport:
        checks = [
            self._check_roundtrip_json(),
            self._check_content_addressed_ref_is_stable(),
            self._check_bad_ref_rejected(),
        ]
        return ConformanceReport(name=self.name, passed=all(check.passed for check in checks), checks=checks)

    def _check_roundtrip_json(self) -> ConformanceCheck:
        try:
            blobs = self.blob_factory()
            value = {"hello": "world", "nested": {"n": 1}, "items": [1, 2, 3]}
            digest, ref = blobs.put_json(value)
            assert digest.startswith("sha256:")
            assert blobs.get_json(ref) == value
            return ConformanceCheck("roundtrip_json", True, "put_json/get_json roundtrip succeeded")
        except Exception as exc:  # pragma: no cover - returned for adapter diagnostics
            return ConformanceCheck("roundtrip_json", False, repr(exc))

    def _check_content_addressed_ref_is_stable(self) -> ConformanceCheck:
        try:
            blobs = self.blob_factory()
            value = {"stable": True, "order": ["a", "b"]}
            first = blobs.put_json(value)
            second = blobs.put_json(value)
            assert first == second
            return ConformanceCheck("content_addressed_ref_is_stable", True, "same JSON value produced same digest/ref")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("content_addressed_ref_is_stable", False, repr(exc))

    def _check_bad_ref_rejected(self) -> ConformanceCheck:
        try:
            blobs = self.blob_factory()
            try:
                blobs.get_json("unsupported://blob")
            except ValueError:
                return ConformanceCheck("bad_ref_rejected", True, "unsupported blob ref was rejected")
            return ConformanceCheck("bad_ref_rejected", False, "unsupported blob ref was accepted")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("bad_ref_rejected", False, repr(exc))


class MediaRuntimeConformanceRunner:
    """Executable conformance checks for media/stream runtime contracts."""

    def __init__(self, runtime_factory: Callable[[], Any], *, name: str = "media-runtime"):
        self.runtime_factory = runtime_factory
        self.name = name

    def run(self) -> ConformanceReport:
        checks = [
            self._check_media_evidence_replay_chain(),
            self._check_media_tool_ledger_chain(),
        ]
        return ConformanceReport(name=self.name, passed=all(check.passed for check in checks), checks=checks)

    def _check_media_evidence_replay_chain(self) -> ConformanceCheck:
        try:
            from .evidence import EvidenceExporter
            from .eval import EvidenceRegressionRunner
            from .media import MediaMetadata, StreamChunkRef
            from .replay import ReplayEngine
            from .review import AdversarialReviewRunner
            from .trace import TraceExporter

            runtime = self.runtime_factory()
            run_id, _ = runtime.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                _digest, blob_ref = ctx.blobs.put_json({"media": "payload"})
                await ctx.create_media_artifact("frame", "frame", content_ref=blob_ref, media_metadata=MediaMetadata(kind="frame", frame_index=1))
                await ctx.create_stream_checkpoint(
                    "checkpoint",
                    stream_id="camera-1",
                    consumer_id="vision-agent",
                    offset=1,
                    chunk=StreamChunkRef(stream_id="camera-1", chunk_id="chunk-1", offset=1, content_ref=blob_ref),
                )

            ok = asyncio.run(runtime.run_once(agent, run_id=run_id, agent_role="MediaConformanceAgent"))
            if not ok:
                return ConformanceCheck("media_evidence_replay_chain", False, "runtime.run_once returned false")
            bundle = EvidenceExporter(store=runtime.store, blobs=runtime.blobs).export(run_id).to_dict()
            replay = ReplayEngine(store=runtime.store, blobs=runtime.blobs).replay(run_id)
            eval_report = EvidenceRegressionRunner().evaluate(bundle)
            review_report = AdversarialReviewRunner().evaluate(bundle)
            trace_names = {span.name for span in TraceExporter().spans(bundle)}
            passed = (
                bundle["summary"]["media_artifact_count"] == 1
                and bundle["summary"]["stream_checkpoint_count"] == 1
                and replay.media_artifact_count == 1
                and replay.stream_checkpoint_count == 1
                and eval_report.passed
                and review_report.passed
                and {"media_artifact", "stream_checkpoint"}.issubset(trace_names)
            )
            return ConformanceCheck("media_evidence_replay_chain", passed, f"run_id={run_id}")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("media_evidence_replay_chain", False, repr(exc))

    def _check_media_tool_ledger_chain(self) -> ConformanceCheck:
        try:
            from .evidence import EvidenceExporter
            from .media import ArtifactLineage, MediaMetadata
            from .media_tools import register_media_tool_conventions

            runtime = self.runtime_factory()

            def extract_frames(args: dict[str, Any]) -> dict[str, Any]:
                return {
                    "frame_refs": [{"uri": "s3://media/conformance/frame.jpg", "frame_index": 1, "timestamp_start_seconds": 1.0}],
                    "metadata": {"source_ref": args["source_ref"]},
                }

            register_media_tool_conventions(runtime.registry, {"video.extract_frames": extract_frames})
            run_id, _ = runtime.create_run(initial_state={})

            async def agent(ctx: Any, _state: dict[str, Any]) -> None:
                result = await ctx.call_tool("video.extract_frames", {"source_ref": "s3://media/conformance/video.mp4", "_logical_operation": "media-conformance"})
                frame = result["frame_refs"][0]
                await ctx.create_media_artifact(
                    "frame-from-tool",
                    "frame",
                    uri=frame["uri"],
                    media_metadata=MediaMetadata(kind="frame", frame_index=frame["frame_index"]),
                    lineage=ArtifactLineage(source_blob_refs=["s3://media/conformance/video.mp4"], tool_call_ids=["video.extract_frames"]),
                )

            ok = asyncio.run(runtime.run_once(agent, run_id=run_id, agent_role="MediaConformanceAgent"))
            if not ok:
                return ConformanceCheck("media_tool_ledger_chain", False, "runtime.run_once returned false")
            bundle = EvidenceExporter(store=runtime.store, blobs=runtime.blobs).export(run_id).to_dict()
            passed = bundle["summary"]["tool_ledger_count"] == 1 and bundle["summary"]["media_artifact_count"] == 1
            return ConformanceCheck("media_tool_ledger_chain", passed, f"run_id={run_id}")
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("media_tool_ledger_chain", False, repr(exc))


class FrameworkAdapterConformanceRunner:
    """Executable certification fixture for dependency-free framework adapters."""

    def __init__(self, adapter_factory: AdapterFactory, *, name: str = "framework-adapter"):
        self.adapter_factory = adapter_factory
        self.name = name

    def run(self) -> ConformanceReport:
        checks = [
            self._check_run_spec_maps_adapter(),
            self._check_runtime_run_once_completes(),
            self._check_evidence_export_works(),
        ]
        return ConformanceReport(name=self.name, passed=all(check.passed for check in checks), checks=checks)

    def _check_run_spec_maps_adapter(self) -> ConformanceCheck:
        try:
            adapter = self.adapter_factory()
            spec = adapter.map_run_spec({"id": "certification-run"})
            if not isinstance(spec, dict):
                return ConformanceCheck("run_spec_maps_adapter", False, "map_run_spec did not return a dict")
            if not spec.get("adapter"):
                return ConformanceCheck("run_spec_maps_adapter", False, "map_run_spec omitted adapter name")
            return ConformanceCheck("run_spec_maps_adapter", True, f"adapter={spec['adapter']}")
        except Exception as exc:  # pragma: no cover - returned for adapter diagnostics
            return ConformanceCheck("run_spec_maps_adapter", False, repr(exc))

    def _check_runtime_run_once_completes(self) -> ConformanceCheck:
        try:
            runtime, run_id, tmp = self._run_adapter_once()
            try:
                run = runtime.store.run(run_id)
                if run["status"] != "completed":
                    return ConformanceCheck("runtime_run_once_completes", False, f"run status was {run['status']!r}")
                return ConformanceCheck("runtime_run_once_completes", True, "adapter callable completed inside Runtime.run_once")
            finally:
                runtime.store.close()
                tmp.cleanup()
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("runtime_run_once_completes", False, repr(exc))

    def _check_evidence_export_works(self) -> ConformanceCheck:
        try:
            runtime, run_id, tmp = self._run_adapter_once()
            try:
                from .evidence import EvidenceExporter

                bundle = EvidenceExporter(store=runtime.store, blobs=runtime.blobs).export(run_id).to_dict()
                event_types = {event["type"] for event in bundle.get("events", [])}
                if "agent_started" not in event_types or "state_committed" not in event_types:
                    return ConformanceCheck("evidence_export_works", False, "evidence did not contain expected runtime events")
                return ConformanceCheck("evidence_export_works", True, f"events={bundle['summary']['event_count']}")
            finally:
                runtime.store.close()
                tmp.cleanup()
        except Exception as exc:  # pragma: no cover
            return ConformanceCheck("evidence_export_works", False, repr(exc))

    def _run_adapter_once(self) -> tuple[Any, str, tempfile.TemporaryDirectory[str]]:
        from .runtime import Runtime

        tmp = tempfile.TemporaryDirectory()
        try:
            root = Path(tmp.name) / ".agentledger"
            runtime = Runtime.local(root)
            adapter = self.adapter_factory()
            run_id, _ = runtime.create_run(initial_state={"topic": self.name})
            role = getattr(adapter, "role", "FrameworkAdapter")
            ok = asyncio.run(runtime.run_once(adapter.as_agent(), run_id=run_id, agent_role=role))
            if not ok:
                raise RuntimeError("adapter run_once returned false")
            return runtime, run_id, tmp
        except Exception:
            tmp.cleanup()
            raise
