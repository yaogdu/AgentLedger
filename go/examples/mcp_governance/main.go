package main

import (
	"context"
	"encoding/json"
	"fmt"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

func main() {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	rt.SetSandbox(agentledger.LocalSandboxExecutor{})
	externalActions := []agentledger.JSONObject{}
	server := agentledger.NewInMemoryMCPToolServer()
	server.AddTool(agentledger.JSONObject{
		"name": "mcp.github.create_pr",
		"inputSchema": agentledger.JSONObject{
			"type":     "object",
			"required": []any{"title"},
			"properties": agentledger.JSONObject{
				"title": agentledger.JSONObject{"type": "string", "minLength": 1},
			},
			"additionalProperties": true,
		},
		"annotations": agentledger.JSONObject{
			"side_effect":          "external_write",
			"risk_level":           "high",
			"idempotency_required": true,
			"approval_required":    true,
			"sandbox_required":     true,
			"sandbox_policy": agentledger.JSONObject{
				"network":    "deny",
				"filesystem": "read-only",
			},
		},
	}, func(name string, args agentledger.JSONObject) (any, error) {
		action := map[string]any{
			"external_id": fmt.Sprintf("PR-%d", len(externalActions)+1),
			"title":       args["title"],
		}
		externalActions = append(externalActions, agentledger.JSONObject(action))
		return action, nil
	})
	adapter := agentledger.MCPToolAdapter{ClientCall: server.CallTool}
	for _, descriptor := range server.ListTools() {
		if err := rt.RegisterTool(adapter.ToolSpecFromDescriptor(descriptor)); err != nil {
			panic(err)
		}
	}

	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "mcp.github.create_pr", agentledger.JSONObject{
			"title":              "Update runtime docs",
			"_logical_operation": "docs-pr",
		})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("pull_request", result)
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		panic(err)
	}
	firstOK, err := rt.RunOnce(context.Background(), runID, "worker-before-approval", "MCPAgent", 60, agent)
	if err != nil {
		panic(err)
	}
	approval := rt.Store.ApprovalRequests(runID)[0]
	if _, err := rt.Store.ApproveRequest(approval.ApprovalID, "maintainer", "demo approval"); err != nil {
		panic(err)
	}
	secondOK, err := rt.RunOnce(context.Background(), runID, "worker-after-approval", "MCPAgent", 60, agent)
	if err != nil {
		panic(err)
	}
	finalState, err := rt.Store.FinalState(runID)
	if err != nil {
		panic(err)
	}
	approvals := []agentledger.JSONObject{}
	for _, row := range rt.Store.ApprovalRequests(runID) {
		approvals = append(approvals, agentledger.JSONObject{
			"approval_id": row.ApprovalID,
			"tool_name":   row.ToolName,
			"risk_level":  row.RiskLevel,
			"status":      row.Status,
			"reason":      row.Reason,
		})
	}
	body, _ := json.MarshalIndent(agentledger.JSONObject{
		"run_id":                            runID,
		"first_attempt_waited_for_approval": !firstOK,
		"second_attempt_ok":                 secondOK,
		"approvals":                         approvals,
		"external_action_count":             len(externalActions),
		"final_state":                       finalState,
	}, "", "  ")
	fmt.Println(string(body))
}
