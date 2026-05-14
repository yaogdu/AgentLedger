from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .jsonutil import sha256_json


class LocalBlobStore:
    """Content-addressed JSON blob store for local-first development."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(self, value: Any) -> tuple[str, str]:
        digest = sha256_json(value)
        algo, hex_digest = digest.split(":", 1)
        path = self.root / algo / f"{hex_digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return digest, f"blob://{algo}/{hex_digest}.json"

    def get_json(self, ref: str) -> Any:
        if not ref.startswith("blob://"):
            raise ValueError(f"unsupported blob ref: {ref}")
        rel = ref.removeprefix("blob://")
        path = self.root / rel
        return json.loads(path.read_text(encoding="utf-8"))
