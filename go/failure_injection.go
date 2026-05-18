package agentledger

import (
	"context"
	"fmt"
)

type FailureInjectionCheck struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
	RunID  string `json:"run_id,omitempty"`
}
type FailureInjectionReport struct {
	Passed bool                    `json:"passed"`
	Checks []FailureInjectionCheck `json:"checks"`
}

func RunFailureInjectionSuite() FailureInjectionReport {
	checks := []FailureInjectionCheck{failureRetryExhaustion(), failureLeaseFencing(), failureCancellationFencing(), failureSideEffectIdempotency()}
	passed := true
	for _, check := range checks {
		if !check.Passed {
			passed = false
		}
	}
	return FailureInjectionReport{Passed: passed, Checks: checks}
}

func failureRetryExhaustion() FailureInjectionCheck {
	rt := NewRuntime(NewMemoryStore())
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		return FailureInjectionCheck{"retry_exhaustion", false, err.Error(), ""}
	}
	_, _ = rt.RunOnce(context.Background(), runID, "retry-1", "FailureInjector", 60, func(context.Context, *AgentContext, JSONObject) error { return ErrRetryable })
	_, _ = rt.RunOnce(context.Background(), runID, "retry-2", "FailureInjector", 60, func(context.Context, *AgentContext, JSONObject) error { return fmt.Errorf("final failure") })
	run, _ := rt.Store.Run(runID)
	passed := run.Status == "failed"
	return FailureInjectionCheck{"retry_exhaustion", passed, "run_status=" + run.Status, runID}
}
func failureLeaseFencing() FailureInjectionCheck {
	store := NewMemoryStore()
	runID, stepID, _ := store.CreateRun(newID("sess"), JSONObject{})
	claim, _ := store.ClaimStep("stale-worker", runID, 0)
	recovered, _ := store.RecoverExpiredLeases()
	staleRejected := false
	if _, err := store.CommitStatePatch(runID, stepID, claim.LeaseToken, 0, JSONObject{"stale": true}, ""); err != nil {
		staleRejected = true
	}
	newClaim, _ := store.ClaimStep("fresh-worker", runID, 60)
	passed := recovered == 1 && staleRejected && newClaim != nil && newClaim.Attempt == 2
	return FailureInjectionCheck{"lease_fencing", passed, fmt.Sprintf("recovered_steps=%d stale_rejected=%v", recovered, staleRejected), runID}
}
func failureCancellationFencing() FailureInjectionCheck {
	store := NewMemoryStore()
	runID, stepID, _ := store.CreateRun(newID("sess"), JSONObject{})
	claim, _ := store.ClaimStep("stale-worker", runID, 60)
	cancelled, _ := store.CancelRun(runID, "failure injection")
	staleRejected := false
	if _, err := store.CommitStatePatch(runID, stepID, claim.LeaseToken, 0, JSONObject{"late": true}, ""); err != nil {
		staleRejected = true
	}
	newClaim, _ := store.ClaimStep("fresh-worker", runID, 60)
	run, _ := store.Run(runID)
	passed := cancelled == 1 && staleRejected && newClaim == nil && run.Status == "cancelled"
	return FailureInjectionCheck{"cancellation_fencing", passed, fmt.Sprintf("cancelled_steps=%d stale_rejected=%v", cancelled, staleRejected), runID}
}
func failureSideEffectIdempotency() FailureInjectionCheck {
	rt := NewRuntime(NewMemoryStore())
	calls := 0
	_ = rt.RegisterTool(ToolSpec{Name: "external.create", Version: "v1", SideEffect: "external", Func: func(_ context.Context, _ JSONObject) (any, error) { calls++; return JSONObject{"id": "EXT-1"}, nil }})
	runID, _, _ := rt.CreateRun(JSONObject{})
	agent := func(_ context.Context, ctx *AgentContext, _ JSONObject) error {
		_, err := ctx.CallTool(context.Background(), "external.create", JSONObject{"title": "once"})
		return err
	}
	_, _ = rt.RunOnce(context.Background(), runID, "worker-1", "FailureInjector", 60, agent)
	_, _ = rt.RunOnce(context.Background(), runID, "worker-2", "FailureInjector", 60, agent)
	passed := calls == 1
	return FailureInjectionCheck{"side_effect_idempotency", passed, fmt.Sprintf("external_call_count=%d", calls), runID}
}
