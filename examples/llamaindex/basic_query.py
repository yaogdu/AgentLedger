from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from agentledger import LlamaIndexAdapter, Runtime


class FakeQueryEngine:
    def query(self, payload: dict[str, str]) -> dict[str, str]:
        return {"answer": f"durable answer for {payload['question']}"}


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        adapter = LlamaIndexAdapter(FakeQueryEngine(), input_mapper=lambda _ctx, state: {"question": state["question"]})
        run_id, _ = rt.create_run(initial_state={"question": "agent runtime"})
        ok = await rt.run_once(adapter.as_agent(), run_id=run_id, agent_role=adapter.role)
        print(json.dumps({"ok": ok, "run_id": run_id, "state": rt.store.final_state(run_id)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
