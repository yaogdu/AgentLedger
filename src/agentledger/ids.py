from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


@dataclass(frozen=True)
class CausalToken:
    run_id: str
    step_id: str
    attempt: int
    state_version: int
    event_seq: int | None
    lease_token: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> "CausalToken":
        return cls(**json.loads(value))


def now_ts() -> float:
    return time.time()
