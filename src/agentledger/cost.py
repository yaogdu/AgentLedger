from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class BudgetExceeded(RuntimeError):
    """Raised when a run would cross a configured budget boundary."""


@dataclass(frozen=True)
class BudgetLimits:
    max_tool_calls: int | None = None
    max_model_tokens: int | None = None
    max_total_usd: float | None = None


class BudgetController:
    """Small local budget controller.

    The controller is deliberately store-backed: budget checks use recorded usage,
    not process-local counters, so future distributed workers can share the same
    semantics through the StateStore boundary.
    """

    def __init__(self, limits: BudgetLimits | None = None):
        self.limits = limits or BudgetLimits()

    def before_tool_call(self, store: Any, run_id: str) -> None:
        if self.limits.max_tool_calls is None:
            return
        used = int(store.cost_summary(run_id).get("tool_calls", 0))
        if used >= self.limits.max_tool_calls:
            raise BudgetExceeded(f"tool call budget exceeded: {used}/{self.limits.max_tool_calls}")

    def before_model_call(self, store: Any, run_id: str, estimated_tokens: int = 0) -> None:
        if self.limits.max_model_tokens is not None:
            used = int(store.cost_summary(run_id).get("model_tokens", 0))
            if used + max(estimated_tokens, 0) > self.limits.max_model_tokens:
                raise BudgetExceeded(f"model token budget exceeded: {used}+{estimated_tokens}/{self.limits.max_model_tokens}")
        if self.limits.max_total_usd is not None:
            used_usd = float(store.cost_summary(run_id).get("total_usd", 0.0))
            if used_usd > self.limits.max_total_usd:
                raise BudgetExceeded(f"cost budget exceeded: {used_usd}/{self.limits.max_total_usd} USD")

    def after_cost_recorded(self, store: Any, run_id: str) -> None:
        if self.limits.max_total_usd is None:
            return
        used_usd = float(store.cost_summary(run_id).get("total_usd", 0.0))
        if used_usd > self.limits.max_total_usd:
            raise BudgetExceeded(f"cost budget exceeded: {used_usd}/{self.limits.max_total_usd} USD")


def _empty_totals() -> dict[str, float]:
    return {"tool_calls": 0.0, "model_tokens": 0.0, "total_usd": 0.0}


def _add_amount(totals: dict[str, float], *, category: str, unit: str, amount: float) -> None:
    if category in {"tool", "tool_shadow"} and unit == "call":
        totals["tool_calls"] = totals.get("tool_calls", 0.0) + amount
    if category == "model" and unit == "token":
        totals["model_tokens"] = totals.get("model_tokens", 0.0) + amount
    if unit == "usd":
        totals["total_usd"] = totals.get("total_usd", 0.0) + amount
    key = f"{category}:{unit}"
    totals[key] = totals.get(key, 0.0) + amount


@dataclass(frozen=True)
class CostAttributionReport:
    run_id: str
    total: dict[str, float]
    by_agent: dict[str, dict[str, float]]
    by_step: dict[str, dict[str, Any]]
    by_category: dict[str, dict[str, float]]
    by_name: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "total": self.total,
            "by_agent": self.by_agent,
            "by_step": self.by_step,
            "by_category": self.by_category,
            "by_name": self.by_name,
        }


class CostAttributionReporter:
    """Build a read-only cost attribution report from durable cost records."""

    def __init__(self, store: Any):
        self.store = store

    def report(self, run_id: str) -> CostAttributionReport:
        step_agents = self._step_agent_roles(run_id)
        total = _empty_totals()
        by_agent: dict[str, dict[str, float]] = {}
        by_step: dict[str, dict[str, Any]] = {}
        by_category: dict[str, dict[str, float]] = {}
        by_name: dict[str, dict[str, float]] = {}

        for row in self.store.cost_records(run_id):
            step_id = row["step_id"] or "<run>"
            agent_role = step_agents.get(row["step_id"], "<unknown>")
            category = str(row["category"])
            name = str(row["name"])
            unit = str(row["unit"])
            amount = float(row["amount"])

            _add_amount(total, category=category, unit=unit, amount=amount)
            _add_amount(by_agent.setdefault(agent_role, _empty_totals()), category=category, unit=unit, amount=amount)
            step_bucket = by_step.setdefault(step_id, {"agent_role": agent_role, **_empty_totals()})
            _add_amount(step_bucket, category=category, unit=unit, amount=amount)
            _add_amount(by_category.setdefault(category, _empty_totals()), category=category, unit=unit, amount=amount)
            _add_amount(by_name.setdefault(name, _empty_totals()), category=category, unit=unit, amount=amount)

        return CostAttributionReport(
            run_id=run_id,
            total=total,
            by_agent=by_agent,
            by_step=by_step,
            by_category=by_category,
            by_name=by_name,
        )

    def _step_agent_roles(self, run_id: str) -> dict[str | None, str]:
        roles: dict[str | None, str] = {}
        for event in self.store.events(run_id):
            step_id = event["step_id"]
            if event["agent_role"]:
                roles[step_id] = event["agent_role"]
        return roles
