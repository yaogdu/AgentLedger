from __future__ import annotations

from typing import Any

from .adapters import FrameworkAdapter, PythonFunctionAdapter
from .ids import new_id


class LangGraphCheckpointerAdapter:
    """Dependency-free LangGraph-style checkpointer adapter.

    Runtime core does not import LangGraph. This adapter exposes the common
    checkpointer shape (`put`, `get`, `get_tuple`, `list`, `put_writes`) using
    plain dictionaries so optional packages can wrap it with LangGraph's exact
    classes without changing AgentLedger state semantics.
    """

    name = "langgraph-checkpointer"

    def __init__(self, runtime: Any):
        self.runtime = runtime

    def config_for_run(self, run_id: str, *, thread_id: str | None = None, checkpoint_ns: str = "") -> dict[str, Any]:
        return {"configurable": {"agentledger_run_id": run_id, "thread_id": thread_id or run_id, "checkpoint_ns": checkpoint_ns}}

    def checkpoint_from_run(self, run_id: str) -> dict[str, Any]:
        state, state_version, session_id = self.runtime.store.load_state(run_id)
        return {"run_id": run_id, "session_id": session_id, "state_version": state_version, "state": state}

    def persist_checkpoint(self, run_id: str, checkpoint: dict[str, Any], *, reason: str = "langgraph checkpoint") -> int:
        return self.runtime.store.apply_system_state_patch(run_id=run_id, patch={"langgraph_checkpoint": checkpoint}, reason=reason)

    def put(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        new_versions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = self._run_id_from_config(config)
        checkpoint_id = str(checkpoint.get("id") or checkpoint.get("checkpoint_id") or new_id("lgckpt"))
        next_config = self._with_checkpoint_id(config, checkpoint_id)
        record = {
            "checkpoint": {**checkpoint, "id": checkpoint_id},
            "metadata": metadata or {},
            "new_versions": new_versions or {},
            "config": next_config,
        }
        self.runtime.store.apply_system_state_patch(
            run_id=run_id,
            patch={"langgraph_checkpoint": record, "langgraph_pending_writes": []},
            reason="langgraph checkpoint put",
        )
        return next_config

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        new_versions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.put(config, checkpoint, metadata, new_versions)

    def get_tuple(self, config: dict[str, Any]) -> dict[str, Any] | None:
        run_id = self._run_id_from_config(config)
        state = self.runtime.store.final_state(run_id)
        record = state.get("langgraph_checkpoint")
        if record is None:
            return None
        if "checkpoint" not in record:
            record = {"checkpoint": record, "metadata": {}, "config": config}
        return {
            "config": record.get("config", config),
            "checkpoint": record.get("checkpoint"),
            "metadata": record.get("metadata", {}),
            "parent_config": record.get("parent_config"),
            "pending_writes": state.get("langgraph_pending_writes", []),
        }

    async def aget_tuple(self, config: dict[str, Any]) -> dict[str, Any] | None:
        return self.get_tuple(config)

    def get(self, config: dict[str, Any]) -> dict[str, Any] | None:
        item = self.get_tuple(config)
        return item["checkpoint"] if item is not None else None

    async def aget(self, config: dict[str, Any]) -> dict[str, Any] | None:
        return self.get(config)

    def list(self, config: dict[str, Any] | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        if config is None:
            return []
        item = self.get_tuple(config)
        return [item] if item is not None else []

    async def alist(self, config: dict[str, Any] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        return self.list(config, **kwargs)

    def put_writes(self, config: dict[str, Any], writes: list[Any], task_id: str, task_path: str = "") -> None:
        run_id = self._run_id_from_config(config)
        state = self.runtime.store.final_state(run_id)
        pending = list(state.get("langgraph_pending_writes", []))
        pending.append({"task_id": task_id, "task_path": task_path, "writes": writes, "config": config})
        self.runtime.store.apply_system_state_patch(
            run_id=run_id,
            patch={"langgraph_pending_writes": pending},
            reason="langgraph pending writes",
        )

    async def aput_writes(self, config: dict[str, Any], writes: list[Any], task_id: str, task_path: str = "") -> None:
        self.put_writes(config, writes, task_id, task_path)

    def _run_id_from_config(self, config: dict[str, Any]) -> str:
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        run_id = configurable.get("agentledger_run_id") or configurable.get("run_id")
        if not run_id:
            raise ValueError("LangGraph config must include configurable.agentledger_run_id or configurable.run_id")
        return str(run_id)

    def _with_checkpoint_id(self, config: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
        configurable = dict(config.get("configurable", {}))
        configurable["checkpoint_id"] = checkpoint_id
        return {**config, "configurable": configurable}


class LangGraphNodeAdapter(FrameworkAdapter):
    """Wrap a callable node as a Runtime.run_once-compatible agent."""

    name = "langgraph-node"

    def __init__(self, node: Any, *, role: str = "LangGraphAgent"):
        self.node = node
        self.role = role

    def map_run_spec(self, framework_run: Any = None) -> dict[str, Any]:
        return {"adapter": self.name, "role": self.role, "node": getattr(self.node, "__name__", repr(self.node))}

    def as_agent(self):
        return PythonFunctionAdapter(self.node, role=self.role).as_agent()
