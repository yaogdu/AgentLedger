from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable

from .context import AgentContext

AgentCallable = Callable[[AgentContext, dict[str, Any]], Any]


class FrameworkAdapter(ABC):
    """Base contract for framework adapters.

    Adapters map framework-specific concepts into AgentLedger's stable runtime
    boundary. Core imports no LangGraph/CrewAI/AutoGen/etc dependencies.
    """

    name = "framework"

    def map_run_spec(self, framework_run: Any) -> dict[str, Any]:
        return {"adapter": self.name, "framework_run": repr(framework_run)}

    def map_step(self, framework_step: Any) -> dict[str, Any]:
        return {"adapter": self.name, "framework_step": repr(framework_step)}

    @abstractmethod
    def as_agent(self) -> AgentCallable:
        """Return a callable compatible with Runtime.run_once."""


class PythonFunctionAdapter(FrameworkAdapter):
    """Adapter for a plain Python function or coroutine.

    This proves the framework-agnostic SDK path before adding heavier optional
    integrations.
    """

    name = "python-function"

    def __init__(self, func: AgentCallable, *, role: str = "Agent"):
        self.func = func
        self.role = role

    def map_run_spec(self, framework_run: Any = None) -> dict[str, Any]:
        return {"adapter": self.name, "role": self.role, "function": getattr(self.func, "__name__", repr(self.func))}

    def as_agent(self) -> AgentCallable:
        async def wrapped(ctx: AgentContext, state: dict[str, Any]) -> Any:
            result = self.func(ctx, state)
            if inspect.isawaitable(result):
                return await result
            return result

        return wrapped


def python_agent(*, role: str = "Agent") -> Callable[[AgentCallable], PythonFunctionAdapter]:
    def decorator(func: AgentCallable) -> PythonFunctionAdapter:
        return PythonFunctionAdapter(func, role=role)

    return decorator
