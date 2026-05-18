package main

import (
	"context"
	"encoding/json"
	"fmt"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

func main() {
	result, err := agentledger.SimpleRun(context.Background(), func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"message": "hello from go", "input": state["input"]}, nil
	}, agentledger.JSONObject{"input": "world"})
	if err != nil {
		panic(err)
	}
	body, _ := json.MarshalIndent(agentledger.JSONObject{"run_id": result.RunID, "output": result.Output, "state": result.State}, "", "  ")
	fmt.Println(string(body))
}
