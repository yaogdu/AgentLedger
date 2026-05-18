package agentledger

import "fmt"

type EvidenceCheck struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail"`
}
type EvidenceCheckReport struct {
	Passed   bool            `json:"passed"`
	Checks   []EvidenceCheck `json:"checks"`
	Metadata JSONObject      `json:"metadata,omitempty"`
}

func EvaluateEvidence(bundle EvidenceBundle, maxTotalUSD *float64) EvidenceCheckReport {
	checks := []EvidenceCheck{
		{"no_failed_steps", !truthy(bundle.Summary["has_failed_steps"]), "all steps completed or remain non-failed"},
		{"no_pending_verification", !truthy(bundle.Summary["has_pending_verification"]) && !truthy(bundle.Summary["has_pending_ledger"]), "no side effect is waiting for human/external verification"},
		{"completed_steps_have_events", completedStepsHaveEvents(bundle.Steps, bundle.Events), "each completed step has a step_completed event"},
		{"managed_side_effects_are_ledgered", ledgerStatusesKnown(bundle.ToolLedger), "every ledger row has a known status"},
		{"media_artifacts_have_refs", mediaArtifactsHaveRefs(bundle.MediaArtifacts), "media artifacts have kind and durable refs"},
		{"stream_checkpoints_have_offsets", streamCheckpointsHaveOffsets(bundle.StreamCheckpoints), "stream checkpoints have stream, consumer, and offset"},
	}
	if maxTotalUSD != nil {
		checks = append(checks, EvidenceCheck{"max_total_usd", bundle.CostSummary.TotalUSD <= *maxTotalUSD, fmt.Sprintf("total_usd=%v, limit=%v", bundle.CostSummary.TotalUSD, *maxTotalUSD)})
	}
	return EvidenceCheckReport{Passed: evidenceChecksPassed(checks), Checks: checks}
}

func EvaluateEvidenceRegression(golden, current EvidenceBundle, maxTotalUSDDelta *float64) EvidenceCheckReport {
	diff := DiffEvidence(golden, current)
	changes := diff.Changes
	checks := []EvidenceCheck{
		{"final_state_regression", changedCount(changes["final_state"]) == 0, fmt.Sprintf("changed_final_state_keys=%d", changedCount(changes["final_state"]))},
		{"event_type_regression", changedCount(changes["event_types"]) == 0, fmt.Sprintf("changed_event_type_positions=%d", changedCount(changes["event_types"]))},
		{"tool_ledger_status_regression", changedCount(changes["tool_ledger"]) == 0, fmt.Sprintf("changed_ledger_status_positions=%d", changedCount(changes["tool_ledger"]))},
		{"media_artifact_regression", changedCount(changes["media_artifacts"]) == 0, fmt.Sprintf("changed_media_artifacts=%d", changedCount(changes["media_artifacts"]))},
		{"stream_checkpoint_regression", changedCount(changes["stream_checkpoints"]) == 0, fmt.Sprintf("changed_stream_checkpoints=%d", changedCount(changes["stream_checkpoints"]))},
	}
	if maxTotalUSDDelta != nil {
		delta := current.CostSummary.TotalUSD - golden.CostSummary.TotalUSD
		checks = append(checks, EvidenceCheck{"max_total_usd_delta", delta <= *maxTotalUSDDelta, fmt.Sprintf("total_usd_delta=%v, limit=%v", delta, *maxTotalUSDDelta)})
	}
	return EvidenceCheckReport{Passed: evidenceChecksPassed(checks), Checks: checks, Metadata: JSONObject{"diff": diff}}
}

func evidenceChecksPassed(checks []EvidenceCheck) bool {
	for _, c := range checks {
		if !c.Passed {
			return false
		}
	}
	return true
}
func changedCount(value any) int {
	if v, ok := value.(DictDiff); ok {
		return v.ChangedCount
	}
	if v, ok := value.(SequenceDiff); ok {
		return v.ChangedCount
	}
	if v, ok := value.(map[string]any); ok {
		if n, ok := v["changed_count"].(int); ok {
			return n
		}
	}
	return 0
}
