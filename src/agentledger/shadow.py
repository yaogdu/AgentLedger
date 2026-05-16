from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .context import AgentContext
from .evidence import EvidenceExporter
from .store import SQLiteStore
from .blobstore import LocalBlobStore

AgentFunc = Callable[[AgentContext, dict[str, Any]], Any]


@dataclass(frozen=True)
class ShadowReport:
    source_run_id: str
    shadow_run_id: str
    ok: bool
    state_diff: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_run_id": self.source_run_id,
            "shadow_run_id": self.shadow_run_id,
            "ok": self.ok,
            "state_diff": self.state_diff,
        }


class ShadowRunner:
    """Run candidate agent code against archived side effects.

    Shadow mode may execute local pure code, but managed side-effect tools are
    satisfied from the source run's Tool Ledger and never call the real tool.
    """

    def __init__(self, runtime: Any):
        self.runtime = runtime

    async def run(self, agent: AgentFunc, *, source_run_id: str, agent_role: str = "ShadowAgent") -> ShadowReport:
        evidence = EvidenceExporter(store=self.runtime.store, blobs=self.runtime.blobs).export(source_run_id).to_dict()
        initial_state = evidence.get("run", {}).get("initial_state", {})
        shadow_run_id, _ = self.runtime.create_run(initial_state=initial_state)
        ok = await self.runtime.run_once(
            agent,
            run_id=shadow_run_id,
            agent_role=agent_role,
            execution_mode="shadow",
            source_run_id=source_run_id,
        )
        source_final = self.runtime.store.final_state(source_run_id)
        shadow_final = self.runtime.store.final_state(shadow_run_id)
        return ShadowReport(source_run_id=source_run_id, shadow_run_id=shadow_run_id, ok=ok, state_diff=diff_dicts(source_final, shadow_final))


def diff_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(left) | set(right))
    changed: dict[str, Any] = {}
    for key in keys:
        if left.get(key) != right.get(key):
            changed[key] = {"source": left.get(key), "shadow": right.get(key)}
    return {"changed": changed, "changed_count": len(changed)}
