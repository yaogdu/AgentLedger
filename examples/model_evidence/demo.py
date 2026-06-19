from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from agentledger import InspectorDataSource, Runtime, ToolSpec


def fake_enterprise_gateway(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "cmpl_demo_001",
        "output_text": "Search the contract clause before answering.",
        "tool_call": {"name": "contract.search", "arguments": {"clause": "payment terms"}},
        "usage": {"input_tokens": 42, "output_tokens": 18, "total_tokens": 60},
    }


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        rt = Runtime.local(Path(tmp) / ".agentledger")
        rt.registry.register(ToolSpec(name="contract.search", func=lambda args: {"matches": [args["clause"]]}))
        run_id, _ = rt.create_run(initial_state={"question": "Can we terminate for late payment?"})

        async def agent(ctx: Any, state: dict[str, Any]) -> None:
            request = {
                "provider": "enterprise-gateway",
                "model": "openai-compatible-legal-router",
                "messages": [{"role": "user", "content": state["question"]}],
            }
            response = fake_enterprise_gateway(request)
            refs = ctx.record_model_call(
                provider=request["provider"],
                model=request["model"],
                request=request,
                response=response,
                usage=response["usage"],
                total_usd=0.012,
                metadata={"gateway_policy": "internal-only"},
            )
            tool_call = response["tool_call"]
            proposal_ref = ctx.record_tool_call_proposal(
                tool_name=tool_call["name"],
                arguments=tool_call["arguments"],
                provider=request["provider"],
                model=request["model"],
                model_call_ref=refs["request_ref"],
                reason="model response proposed a contract search",
            )
            result = await ctx.call_tool(tool_call["name"], tool_call["arguments"])
            ctx.write_state_patch("answer", {"tool_result": result, "proposal_ref": proposal_ref})

        ok = await rt.run_once(agent, run_id=run_id, agent_role="LegalAgent")
        report = InspectorDataSource().from_runtime_store(store=rt.store, blobs=rt.blobs, run_id=run_id).to_dict()
        print(
            json.dumps(
                {
                    "ok": ok,
                    "run_id": run_id,
                    "model_call_count": report["summary"]["model_call_count"],
                    "tool_call_proposal_count": report["summary"]["tool_call_proposal_count"],
                    "model_calls": report["model_calls"],
                    "tool_proposals": report["tool_proposals"],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
