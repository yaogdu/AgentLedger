from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import Runtime


async def reader_agent(ctx: Any, _state: dict[str, Any]) -> None:
    doc = await ctx.call_tool("docs.read", {"path": "README.md"})
    ctx.write_state_patch("doc", doc)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")

        @rt.tool(
            name="docs.read",
            description="Read a repository document by path.",
            input_schema={
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string", "minLength": 1}},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["content"],
                "properties": {"content": {"type": "string"}},
                "additionalProperties": False,
            },
        )
        def docs_read(args: dict[str, Any]) -> dict[str, str]:
            return {"content": f"read:{args['path']}"}

        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(reader_agent, run_id=run_id, agent_role="ReaderAgent")
        print(
            json.dumps(
                {
                    "ok": ok,
                    "run_id": run_id,
                    "manifest": rt.registry.manifest(),
                    "openai_tools": rt.registry.openai_tools(),
                    "state": rt.store.final_state(run_id),
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
