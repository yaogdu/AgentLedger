from __future__ import annotations

import inspect
from typing import Any, Callable

from .adapters import AgentCallable, FrameworkAdapter
from .context import AgentContext

InputMapper = Callable[[AgentContext, dict[str, Any]], Any]


def default_input_mapper(_ctx: AgentContext, state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


class MethodFrameworkAdapter(FrameworkAdapter):
    """Dependency-free facade for framework objects with conventional methods."""

    name = "method-framework"

    def __init__(
        self,
        target: Any,
        *,
        role: str = "FrameworkAgent",
        method_candidates: tuple[str, ...],
        input_mapper: InputMapper | None = None,
        output_key: str | None = "output",
    ):
        self.target = target
        self.role = role
        self.method_candidates = method_candidates
        self.input_mapper = input_mapper or default_input_mapper
        self.output_key = output_key

    def map_run_spec(self, framework_run: Any = None) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "role": self.role,
            "target": type(self.target).__name__,
            "methods": list(self.method_candidates),
        }

    def as_agent(self) -> AgentCallable:
        async def wrapped(ctx: AgentContext, state: dict[str, Any]) -> Any:
            payload = self.input_mapper(ctx, state)
            result = await self._invoke(payload)
            if self.output_key is not None:
                ctx.write_state_patch(self.output_key, result)
            return result

        return wrapped

    async def _invoke(self, payload: Any) -> Any:
        for name in self.method_candidates:
            method = getattr(self.target, name, None)
            if method is None:
                continue
            result = method(payload)
            if inspect.isawaitable(result):
                return await result
            return result
        if callable(self.target):
            result = self.target(payload)
            if inspect.isawaitable(result):
                return await result
            return result
        raise AttributeError(f"{type(self.target).__name__} does not expose any of {self.method_candidates!r}")


class LangChainRunnableAdapter(MethodFrameworkAdapter):
    """Wrap a LangChain-style Runnable without importing LangChain."""

    name = "langchain-runnable"

    def __init__(self, runnable: Any, *, role: str = "LangChainAgent", input_mapper: InputMapper | None = None, output_key: str | None = "langchain_output"):
        super().__init__(runnable, role=role, method_candidates=("ainvoke", "invoke"), input_mapper=input_mapper, output_key=output_key)


class CrewAIAdapter(MethodFrameworkAdapter):
    """Wrap a CrewAI-style Crew/Task object without importing CrewAI."""

    name = "crewai"

    def __init__(self, crew_or_task: Any, *, role: str = "CrewAIAgent", input_mapper: InputMapper | None = None, output_key: str | None = "crewai_output"):
        super().__init__(crew_or_task, role=role, method_candidates=("akickoff", "kickoff", "arun", "run"), input_mapper=input_mapper, output_key=output_key)


class AutoGenAdapter(MethodFrameworkAdapter):
    """Wrap an AutoGen-style agent object without importing AutoGen."""

    name = "autogen"

    def __init__(self, agent: Any, *, role: str = "AutoGenAgent", input_mapper: InputMapper | None = None, output_key: str | None = "autogen_output"):
        super().__init__(
            agent,
            role=role,
            method_candidates=("a_generate_reply", "generate_reply", "a_run", "run", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class OpenAIAgentsSDKAdapter(MethodFrameworkAdapter):
    """Wrap an OpenAI Agents SDK-style runner without importing the SDK."""

    name = "openai-agents-sdk"

    def __init__(self, agent_or_runner: Any, *, role: str = "OpenAIAgent", input_mapper: InputMapper | None = None, output_key: str | None = "openai_agent_output"):
        super().__init__(
            agent_or_runner,
            role=role,
            method_candidates=("arun", "run", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class LlamaIndexAdapter(MethodFrameworkAdapter):
    """Wrap a LlamaIndex-style query/chat/retriever object without importing LlamaIndex."""

    name = "llamaindex"

    def __init__(self, query_engine_or_agent: Any, *, role: str = "LlamaIndexAgent", input_mapper: InputMapper | None = None, output_key: str | None = "llamaindex_output"):
        super().__init__(
            query_engine_or_agent,
            role=role,
            method_candidates=("aquery", "query", "achat", "chat", "aretrieve", "retrieve", "ainvoke", "invoke"),
            input_mapper=input_mapper,
            output_key=output_key,
        )


class SemanticKernelAdapter(MethodFrameworkAdapter):
    """Wrap a Semantic Kernel-style kernel/function object without importing it."""

    name = "semantic-kernel"

    def __init__(self, kernel_or_function: Any, *, role: str = "SemanticKernelAgent", input_mapper: InputMapper | None = None, output_key: str | None = "semantic_kernel_output"):
        super().__init__(
            kernel_or_function,
            role=role,
            method_candidates=("ainvoke", "invoke", "invoke_prompt", "run_async", "run"),
            input_mapper=input_mapper,
            output_key=output_key,
        )
