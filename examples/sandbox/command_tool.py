from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import Runtime, ToolSpec


def command_tool(args: dict[str, Any]) -> dict[str, Any]:
    return {"dry_run": True, "argv": args["_sandbox_command"]}


async def agent(ctx: Any, _state: dict[str, Any]) -> None:
    result = await ctx.call_tool("cmd.echo", {"_sandbox_command": ["python", "-c", "print('hello')"]})
    ctx.write_state_patch("sandbox_result", result)


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        rt.registry.register(
            ToolSpec(
                name="cmd.echo",
                func=command_tool,
                side_effect="external_write",
                risk_level="low",
                idempotency_required=True,
                sandbox_required=True,
                sandbox_executor="local",
            )
        )
        run_id, _ = rt.create_run(initial_state={})
        ok = await rt.run_once(agent, run_id=run_id, agent_role="SandboxAgent")
        print(json.dumps({"ok": ok, "run_id": run_id, "state": rt.store.final_state(run_id)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
