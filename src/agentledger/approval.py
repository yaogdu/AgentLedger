from __future__ import annotations

from dataclasses import dataclass
from typing import Any


APPROVAL_PENDING = "PENDING"
APPROVAL_APPROVED = "APPROVED"
APPROVAL_DENIED = "DENIED"


class ApprovalRequired(RuntimeError):
    def __init__(self, approval_id: str, message: str, metadata: dict[str, Any] | None = None):
        super().__init__(message)
        self.approval_id = approval_id
        self.metadata = metadata or {}


@dataclass(frozen=True)
class ApprovalDecision:
    approval_id: str
    status: str
    approver: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "status": self.status,
            "approver": self.approver,
            "reason": self.reason,
        }
