from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import InMemoryMCPContextServer, InMemoryMCPToolServer, MCPContextAdapter, MCPToolAdapter, Runtime


async def agent(ctx: Any, _state: dict[str, Any]) -> None:
    policy = await ctx.call_tool("mcp.context.read", {"uri": "agentledger://policy/local"})
    doc = await ctx.call_tool("mcp.docs.read", {"path": "README.md"})
    ctx.write_state_patch("context", policy)
    ctx.write_state_patch("doc", doc)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        context_server = InMemoryMCPContextServer()
        context_server.add_resource(
            uri="agentledger://policy/local",
            name="Local policy summary",
            reader=lambda _uri: {"default_risk": "low", "runtime_managed": True},
        )
        MCPContextAdapter(context_server.read_resource).register_read_tool(rt.registry)

        tool_server = InMemoryMCPToolServer()
        tool_server.add_tool(
            {
                "name": "mcp.docs.read",
                "inputSchema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                    "additionalProperties": False,
                },
                "outputSchema": {"type": "object"},
                "annotations": {"side_effect": "none", "risk_level": "low"},
            },
            lambda name, args: {"tool": name, "content": f"document:{args['path']}"},
        )
        MCPToolAdapter(tool_server.call_tool).register_all(rt.registry, tool_server.list_tools())

        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(agent, run_id=run_id, agent_role="MCPAgent")
        print(
            json.dumps(
                {
                    "ok": ok,
                    "run_id": run_id,
                    "resources": context_server.list_resources(),
                    "tools": rt.registry.manifest(),
                    "state": rt.store.final_state(run_id),
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
