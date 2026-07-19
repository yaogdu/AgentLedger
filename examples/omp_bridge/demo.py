from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agentledger import (
    InspectorDataSource,
    OmpLedgerBridge,
    OmpModelCall,
    OmpSession,
    OmpStateChange,
    OmpToolExecution,
    OmpToolProposal,
    OmpTurn,
    Runtime,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime = Runtime.local(Path(tmp) / ".agentledger")
        bridge = OmpLedgerBridge(runtime, app_name="omp-demo")

        run_id = bridge.record_session_started(
            OmpSession(
                session_id="omp-session-1",
                initial_state={"task": "review contract"},
                metadata={"runtime": "synthetic-omp"},
            )
        )
        bridge.record_turn_started(
            OmpTurn(
                session_id="omp-session-1",
                turn_id="turn-1",
                agent_role="OMPPlanner",
                metadata={"phase": "planning"},
            )
        )
        refs = bridge.record_model_call(
            OmpModelCall(
                session_id="omp-session-1",
                turn_id="turn-1",
                provider="openai-compatible-gateway",
                model="legal-router",
                request={"messages": [{"role": "user", "content": "find payment clause"}]},
                response={"tool_calls": [{"name": "contract.search", "arguments": {"clause": "payment"}}]},
                usage={"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
                total_usd=0.003,
            )
        )
        bridge.record_tool_proposal(
            OmpToolProposal(
                session_id="omp-session-1",
                turn_id="turn-1",
                tool_name="contract.search",
                arguments={"clause": "payment"},
                provider="openai-compatible-gateway",
                model="legal-router",
                model_call_ref=refs["request_ref"],
                reason="model proposed a contract search",
            )
        )
        bridge.record_tool_execution(
            OmpToolExecution(
                session_id="omp-session-1",
                turn_id="turn-1",
                tool_name="contract.search",
                arguments={"clause": "payment"},
                result={"matches": ["Section 9.2"], "external_id": "search-001"},
                ledger_status="SUCCEEDED",
            )
        )
        bridge.record_state_change(
            OmpStateChange(
                session_id="omp-session-1",
                turn_id="turn-1",
                reason="persist normalized runtime-adjacent state",
                patch={"memory_version": 1},
                before_snapshot={"memory_version": 0},
                after_snapshot={"memory_version": 1},
                diff={"memory_version": [0, 1]},
            )
        )
        bridge.record_turn_completed(
            OmpTurn(
                session_id="omp-session-1",
                turn_id="turn-1",
                state_patch={"last_tool": "contract.search"},
            )
        )

        report = InspectorDataSource().from_runtime_store(store=runtime.store, blobs=runtime.blobs, run_id=run_id).to_dict()
        print(
            json.dumps(
                {
                    "run_id": run_id,
                    "events": [event["type"] for event in report["timeline"]],
                    "tool_ledger": [dict(row) for row in runtime.store.ledger(run_id)],
                    "final_state": runtime.store.final_state(run_id),
                    "model_call_count": report["summary"]["model_call_count"],
                    "tool_call_proposal_count": report["summary"]["tool_call_proposal_count"],
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
