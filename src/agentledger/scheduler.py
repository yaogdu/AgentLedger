from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .store import SQLiteStore


@dataclass(frozen=True)
class RecoverySummary:
    recovered_steps: int

    def to_dict(self) -> dict[str, Any]:
        return {"recovered_steps": self.recovered_steps}


class RuntimeScheduler:
    """Small local scheduler facade for lease recovery and cancellation.

    This is not a distributed scheduler yet. It defines the runtime-owned control
    plane operations that later worker pools, Ray, Kubernetes, or Temporal-style
    orchestrators can call.
    """

    def __init__(self, store: SQLiteStore):
        self.store = store

    def recover_expired_leases(self) -> RecoverySummary:
        return RecoverySummary(recovered_steps=self.store.recover_expired_leases())

    def cancel_run(self, run_id: str, *, reason: str = "cancelled by scheduler") -> int:
        return self.store.cancel_run(run_id=run_id, reason=reason)

    def status(self, run_id: str) -> dict[str, Any]:
        run = self.store.run(run_id)
        steps = self.store.steps(run_id)
        return {
            "run_id": run_id,
            "run_status": run["status"],
            "state_version": run["state_version"],
            "steps": [
                {
                    "step_id": row["step_id"],
                    "status": row["status"],
                    "owner": row["owner"],
                    "attempt": row["attempt"],
                    "lease_until": row["lease_until"],
                    "last_error_type": row["last_error_type"] if "last_error_type" in row.keys() else None,
                }
                for row in steps
            ],
            "cost_summary": self.store.cost_summary(run_id),
        }
