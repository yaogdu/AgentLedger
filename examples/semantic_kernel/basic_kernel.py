from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from agentledger import Runtime, SemanticKernelAdapter


class FakeKernel:
    async def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        return {"summary": f"kernel processed {payload['topic']}"}


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        adapter = SemanticKernelAdapter(FakeKernel(), input_mapper=lambda _ctx, state: {"topic": state["topic"]})
        run_id, _ = rt.create_run(initial_state={"topic": "tool governance"})
        ok = await rt.run_once(adapter.as_agent(), run_id=run_id, agent_role=adapter.role)
        print(json.dumps({"ok": ok, "run_id": run_id, "state": rt.store.final_state(run_id)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
