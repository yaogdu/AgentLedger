package main

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"testing"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

func TestLedgerResolveClearsPendingVerification(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	rt, err := agentledger.NewLocalRuntime(path)
	if err != nil {
		t.Fatal(err)
	}
	fail := true
	calls := 0
	tool := func() agentledger.ToolSpec {
		return agentledger.ToolSpec{
			Name:                "payments.charge",
			Version:             "v1",
			SideEffect:          "external",
			IdempotencyRequired: true,
			Func: func(context.Context, agentledger.JSONObject) (any, error) {
				calls++
				if fail {
					return nil, errors.New("provider timeout")
				}
				return agentledger.JSONObject{"external_id": "charge-2"}, nil
			},
		}
	}
	if err := rt.RegisterTool(tool()); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "payments.charge", agentledger.JSONObject{"amount": 10})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("charge", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-cli", "BillingAgent", 60, agent)
	if err != nil || ok {
		t.Fatalf("expected retry scheduling, got ok=%v err=%v", ok, err)
	}
	if got := rt.Store.Steps(runID)[0].Status; got != "retry_scheduled" {
		t.Fatalf("expected retry_scheduled step, got %s", got)
	}

	store, err := agentledger.NewJSONStore(path)
	if err != nil {
		t.Fatal(err)
	}
	ledger := store.Ledger(runID)
	if len(ledger) != 1 || ledger[0].Status != "PENDING_VERIFICATION" {
		t.Fatalf("expected one pending ledger row, got %#v", ledger)
	}
	summary, err := debugSummaryForStore(store, path, runID)
	if err != nil {
		t.Fatal(err)
	}
	if summary["next_action"] != "manual_verification_required" {
		t.Fatalf("unexpected next_action: %#v", summary["next_action"])
	}
	resolutions := summary["pending_ledger_resolutions"].([]agentledger.JSONObject)
	commands := resolutions[0]["suggested_commands"].([]string)
	if !strings.Contains(commands[1], "ledger-resolve") {
		t.Fatalf("missing resolve suggestion: %#v", commands)
	}
	if err := resolveLedger(path, runID, ledger[0].IdempotencyKey, []string{"--status", "failed-no-effect", "--reason", "checked"}); err != nil {
		t.Fatal(err)
	}
	reopened, err := agentledger.NewJSONStore(path)
	if err != nil {
		t.Fatal(err)
	}
	row := reopened.Ledger(runID)[0]
	if row.Status != "FAILED_NO_EFFECT" || row.ErrorType != "ManualNoEffect" {
		t.Fatalf("unexpected resolved ledger row: %#v", row)
	}
	if err := resolveLedger(path, runID, ledger[0].IdempotencyKey, []string{"--status", "failed-no-effect"}); err == nil {
		t.Fatal("duplicate ledger resolve should fail")
	}
	fail = false
	rt2, err := agentledger.NewLocalRuntime(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := rt2.RegisterTool(tool()); err != nil {
		t.Fatal(err)
	}
	ok, err = rt2.RunOnce(context.Background(), runID, "worker-cli-2", "BillingAgent", 60, agent)
	if err != nil || !ok {
		t.Fatalf("expected retry to complete, got ok=%v err=%v", ok, err)
	}
	if calls != 2 {
		t.Fatalf("expected tool to execute twice, got %d", calls)
	}
	if got := rt2.Store.Ledger(runID)[0].Status; got != "SUCCEEDED" {
		t.Fatalf("expected succeeded ledger, got %s", got)
	}
	state, err := rt2.Store.FinalState(runID)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(fmt.Sprint(state["charge"]), "charge-2") {
		t.Fatalf("unexpected final state: %#v", state)
	}
}

func TestLedgerResolveSucceededReplaysManualResponse(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	rt, err := agentledger.NewLocalRuntime(path)
	if err != nil {
		t.Fatal(err)
	}
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{
		Name:                "payments.charge",
		Version:             "v1",
		SideEffect:          "external",
		IdempotencyRequired: true,
		Func: func(context.Context, agentledger.JSONObject) (any, error) {
			calls++
			return nil, errors.New("provider timeout")
		},
	}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "payments.charge", agentledger.JSONObject{"amount": 10})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("charge", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-cli", "BillingAgent", 60, agent)
	if err != nil || ok {
		t.Fatalf("expected retry scheduling, got ok=%v err=%v", ok, err)
	}
	key := rt.Store.Ledger(runID)[0].IdempotencyKey
	if err := resolveLedger(path, runID, key, []string{"--status", "succeeded", "--external-id", "charge-1"}); err != nil {
		t.Fatal(err)
	}
	rt2, err := agentledger.NewLocalRuntime(path)
	if err != nil {
		t.Fatal(err)
	}
	resolved := rt2.Store.Ledger(runID)[0]
	if resolved.ResponseHash == "" || resolved.ResponseRef == "" {
		t.Fatalf("manual success missing response hash/ref: %#v", resolved)
	}
	if err := rt2.RegisterTool(agentledger.ToolSpec{
		Name:                "payments.charge",
		Version:             "v1",
		SideEffect:          "external",
		IdempotencyRequired: true,
		Func: func(context.Context, agentledger.JSONObject) (any, error) {
			calls++
			return nil, errors.New("should replay")
		},
	}); err != nil {
		t.Fatal(err)
	}
	ok, err = rt2.RunOnce(context.Background(), runID, "worker-cli-2", "BillingAgent", 60, agent)
	if err != nil || !ok {
		t.Fatalf("expected replay to complete, got ok=%v err=%v", ok, err)
	}
	if calls != 1 {
		t.Fatalf("expected manual response replay, got calls=%d", calls)
	}
	state, err := rt2.Store.FinalState(runID)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(fmt.Sprint(state["charge"]), "charge-1") {
		t.Fatalf("unexpected final state: %#v", state)
	}
}
