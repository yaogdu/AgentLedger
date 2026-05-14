from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def merge_patch(target: Any, patch: Any) -> Any:
    """Apply RFC 7396 JSON Merge Patch semantics."""
    if not isinstance(patch, dict):
        return deepcopy(patch)
    if not isinstance(target, dict):
        target = {}
    result = deepcopy(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = merge_patch(result.get(key, {}), value)
        else:
            result[key] = deepcopy(value)
    return result
