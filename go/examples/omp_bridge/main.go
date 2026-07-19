package main

import (
	"encoding/json"
	"fmt"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

func main() {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	bridge := agentledger.NewOmpLedgerBridge(rt, "omp-demo")

	runID, err := bridge.RecordSessionStarted(agentledger.OmpSession{
		SessionID:    "omp-session-1",
		InitialState: agentledger.JSONObject{"task": "review contract"},
		Metadata:     agentledger.JSONObject{"runtime": "synthetic-omp"},
	})
	if err != nil {
		panic(err)
	}
	if _, err := bridge.RecordTurnStarted(agentledger.OmpTurn{
		SessionID: "omp-session-1",
		TurnID:    "turn-1",
		AgentRole: "OMPPlanner",
		Metadata:  agentledger.JSONObject{"phase": "planning"},
	}); err != nil {
		panic(err)
	}
	if err := bridge.RecordModelCall(agentledger.OmpModelCall{
		SessionID: "omp-session-1",
		TurnID:    "turn-1",
		Provider:  "openai-compatible-gateway",
		Model:     "legal-router",
		Request:   agentledger.JSONObject{"messages": []any{agentledger.JSONObject{"role": "user", "content": "find payment clause"}}},
		Response:  agentledger.JSONObject{"tool_calls": []any{agentledger.JSONObject{"name": "contract.search", "arguments": agentledger.JSONObject{"clause": "payment"}}}},
		Usage:     agentledger.JSONObject{"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
		TotalUSD:  0.003,
	}); err != nil {
		panic(err)
	}
	if err := bridge.RecordToolProposal(agentledger.OmpToolProposal{
		SessionID: "omp-session-1",
		TurnID:    "turn-1",
		ToolName:  "contract.search",
		Arguments: agentledger.JSONObject{"clause": "payment"},
		Provider:  "openai-compatible-gateway",
		Model:     "legal-router",
		Reason:    "model proposed a contract search",
	}); err != nil {
		panic(err)
	}
	if _, err := bridge.RecordToolExecution(agentledger.OmpToolExecution{
		SessionID:    "omp-session-1",
		TurnID:       "turn-1",
		ToolName:     "contract.search",
		Arguments:    agentledger.JSONObject{"clause": "payment"},
		Result:       agentledger.JSONObject{"matches": []any{"Section 9.2"}, "external_id": "search-001"},
		LedgerStatus: "SUCCEEDED",
	}); err != nil {
		panic(err)
	}
	if _, err := bridge.RecordStateChange(agentledger.OmpStateChange{
		SessionID:      "omp-session-1",
		TurnID:         "turn-1",
		Reason:         "persist normalized runtime-adjacent state",
		Patch:          agentledger.JSONObject{"memory_version": 1},
		BeforeSnapshot: agentledger.JSONObject{"memory_version": 0},
		AfterSnapshot:  agentledger.JSONObject{"memory_version": 1},
		Diff:           agentledger.JSONObject{"memory_version": []any{0, 1}},
	}); err != nil {
		panic(err)
	}
	if _, err := bridge.RecordTurnCompleted(agentledger.OmpTurn{
		SessionID:  "omp-session-1",
		TurnID:     "turn-1",
		StatePatch: agentledger.JSONObject{"last_tool": "contract.search"},
	}); err != nil {
		panic(err)
	}

	eventTypes := []string{}
	for _, event := range rt.Store.Events(runID) {
		eventTypes = append(eventTypes, event.Type)
	}
	finalState, err := rt.Store.FinalState(runID)
	if err != nil {
		panic(err)
	}
	body, _ := json.MarshalIndent(agentledger.JSONObject{
		"run_id":      runID,
		"events":      eventTypes,
		"tool_ledger": rt.Store.Ledger(runID),
		"final_state": finalState,
	}, "", "  ")
	fmt.Println(string(body))
}
