package main

import (
	"context"
	"encoding/json"
	"fmt"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

func main() {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	externalTickets := []agentledger.JSONObject{}
	actualToolExecutions := 0

	if err := rt.RegisterTool(agentledger.ToolSpec{
		Name:                "ticket.create",
		Version:             "v1",
		SideEffect:          "external_write",
		IdempotencyRequired: true,
		InputSchema: agentledger.JSONObject{
			"type":     "object",
			"required": []any{"title"},
		},
		Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
			actualToolExecutions++
			ticket := map[string]any{
				"external_id": fmt.Sprintf("TICKET-%d", len(externalTickets)+1),
				"title":       args["title"],
			}
			externalTickets = append(externalTickets, agentledger.JSONObject(ticket))
			return ticket, nil
		},
	}); err != nil {
		panic(err)
	}

	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		ticket, err := agentCtx.CallTool(ctx, "ticket.create", agentledger.JSONObject{
			"title":              "Investigate failed payment",
			"_logical_operation": "open-payment-ticket",
		})
		if err != nil {
			return err
		}
		if agentCtx.Attempt == 1 {
			return agentledger.ErrRetryable
		}
		if err := agentCtx.WriteState("ticket", ticket); err != nil {
			return err
		}
		return agentCtx.WriteState("recovered", true)
	}

	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		panic(err)
	}
	firstOK, err := rt.RunOnce(context.Background(), runID, "worker-before-crash", "SupportAgent", 60, agent)
	if err != nil {
		panic(err)
	}
	secondOK, err := rt.RunOnce(context.Background(), runID, "worker-after-restart", "SupportAgent", 60, agent)
	if err != nil {
		panic(err)
	}
	replay, err := agentledger.Replay(rt.Store, runID)
	if err != nil {
		panic(err)
	}
	finalState, err := rt.Store.FinalState(runID)
	if err != nil {
		panic(err)
	}
	ledger := []agentledger.JSONObject{}
	for _, row := range rt.Store.Ledger(runID) {
		ledger = append(ledger, agentledger.JSONObject{
			"tool_name":       row.ToolName,
			"status":          row.Status,
			"external_id":     row.ExternalID,
			"idempotency_key": row.IdempotencyKey,
		})
	}
	body, _ := json.MarshalIndent(agentledger.JSONObject{
		"run_id":                 runID,
		"first_attempt_ok":       firstOK,
		"second_attempt_ok":      secondOK,
		"external_ticket_count":  len(externalTickets),
		"actual_tool_executions": actualToolExecutions,
		"tool_ledger":            ledger,
		"final_state":            finalState,
		"replay": agentledger.JSONObject{
			"safe":            replay.ReplaySafe,
			"event_count":     replay.EventCount,
			"tool_call_count": replay.ToolCallCount,
		},
	}, "", "  ")
	fmt.Println(string(body))
}
