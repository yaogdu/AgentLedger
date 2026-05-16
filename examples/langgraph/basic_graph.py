from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import LangGraphCheckpointerAdapter, LangGraphNodeAdapter, Runtime


def plan_node(ctx: Any, state: dict[str, Any]) -> None:
    ctx.write_state_patch("plan", {"next": "write-summary", "input": state["topic"]})


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        run_id, _ = rt.create_run(initial_state={"topic": "durable agents"})
        adapter = LangGraphNodeAdapter(plan_node, role="PlannerAgent")
        ok = await rt.run_once(adapter.as_agent(), run_id=run_id, agent_role=adapter.role)
        checkpoint = LangGraphCheckpointerAdapter(rt).checkpoint_from_run(run_id)
        print(json.dumps({"ok": ok, "run_id": run_id, "checkpoint": checkpoint}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
