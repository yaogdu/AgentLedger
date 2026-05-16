from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import MCPToolAdapter, Runtime


def fake_mcp_call(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"tool": name, "content": f"document:{args['path']}"}


async def agent(ctx: Any, _state: dict[str, Any]) -> None:
    doc = await ctx.call_tool("mcp.docs.read", {"path": "README.md"})
    ctx.write_state_patch("doc", doc)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        MCPToolAdapter(fake_mcp_call).register(
            rt.registry,
            {
                "name": "mcp.docs.read",
                "inputSchema": {"type": "object", "required": ["path"]},
                "annotations": {"side_effect": "none", "risk_level": "low"},
            },
        )
        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(agent, run_id=run_id, agent_role="ReaderAgent")
        print(json.dumps({"ok": ok, "run_id": run_id, "state": rt.store.final_state(run_id)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
