package agentledger

type ReviewCheck struct {
	Name     string `json:"name"`
	Passed   bool   `json:"passed"`
	Severity string `json:"severity"`
	Detail   string `json:"detail"`
}

type AdversarialReviewReport struct {
	Passed   bool          `json:"passed"`
	RunID    string        `json:"run_id,omitempty"`
	Checks   []ReviewCheck `json:"checks"`
	Metadata JSONObject    `json:"metadata"`
}

func AdversarialReview(bundle EvidenceBundle, maxTotalUSD *float64) AdversarialReviewReport {
	checks := []ReviewCheck{
		{"no_failed_steps", !truthy(bundle.Summary["has_failed_steps"]), "blocker", "no step is in failed status"},
		{"no_pending_verification", !truthy(bundle.Summary["has_pending_verification"]) && !truthy(bundle.Summary["has_pending_ledger"]), "blocker", "no side effect is pending verification"},
		{"no_pending_approvals", !truthy(bundle.Summary["has_pending_approvals"]) && !truthy(bundle.Summary["has_pending_approval"]), "blocker", "no approval request is still pending"},
		{"completed_steps_have_completion_events", completedStepsHaveEvents(bundle.Steps, bundle.Events), "blocker", "completed steps have step_completed events"},
		{"ledger_statuses_known", ledgerStatusesKnown(bundle.ToolLedger), "blocker", "Tool Ledger rows use known statuses"},
		{"event_sequence_contiguous", eventSequenceContiguous(bundle.Events), "blocker", "event sequence has no gaps"},
		{"artifacts_have_blob_refs", artifactsHaveBlobRefs(bundle.Artifacts), "warning", "artifacts have blob refs and hashes"},
		{"media_artifacts_have_refs", mediaArtifactsHaveRefs(bundle.MediaArtifacts), "blocker", "media artifacts have kind and durable refs"},
		{"stream_checkpoints_have_offsets", streamCheckpointsHaveOffsets(bundle.StreamCheckpoints), "blocker", "stream checkpoints have stream, consumer, and offset"},
		{"high_risk_approvals_decided", highRiskApprovalsDecided(bundle.Approvals), "blocker", "high-risk approval requests are decided"},
		{"no_blocking_failure_events", noBlockingFailureEvents(bundle.Events), "warning", "no blocking failure events are present"},
	}
	if maxTotalUSD != nil {
		checks = append(checks, ReviewCheck{"max_total_usd", bundle.CostSummary.TotalUSD <= *maxTotalUSD, "blocker", "cost limit check"})
	}
	passed := true
	for _, check := range checks {
		if check.Severity == "blocker" && !check.Passed {
			passed = false
		}
	}
	return AdversarialReviewReport{Passed: passed, RunID: bundle.Run.RunID, Checks: checks, Metadata: JSONObject{"event_count": len(bundle.Events), "step_count": len(bundle.Steps), "tool_ledger_count": len(bundle.ToolLedger), "approval_count": len(bundle.Approvals), "artifact_count": len(bundle.Artifacts), "media_artifact_count": len(bundle.MediaArtifacts), "stream_checkpoint_count": len(bundle.StreamCheckpoints), "cost_summary": bundle.CostSummary}}
}

func truthy(v any) bool { b, _ := v.(bool); return b }
func completedStepsHaveEvents(steps []Step, events []Event) bool {
	done := map[string]bool{}
	for _, e := range events {
		if e.Type == "step_completed" {
			done[e.StepID] = true
		}
	}
	for _, s := range steps {
		if s.Status == "completed" && !done[s.StepID] {
			return false
		}
	}
	return true
}
func ledgerStatusesKnown(rows []ToolLedgerEntry) bool {
	known := map[string]bool{"SUCCEEDED": true, "FAILED_NO_EFFECT": true, "PENDING_VERIFICATION": true, "COMPENSATED": true, "RUNNING": true, "RESERVED": true}
	for _, row := range rows {
		if !known[row.Status] {
			return false
		}
	}
	return true
}
func eventSequenceContiguous(events []Event) bool {
	for i, e := range events {
		if e.Seq != i+1 {
			return false
		}
	}
	return true
}
func artifactsHaveBlobRefs(rows []Artifact) bool {
	for _, row := range rows {
		if row.BlobRef == "" || row.BlobHash == "" {
			return false
		}
	}
	return true
}
func mediaArtifactsHaveRefs(rows []JSONObject) bool {
	for _, row := range rows {
		if row["kind"] == nil || (row["uri"] == nil && row["content_ref"] == nil && row["blob_ref"] == nil) {
			return false
		}
	}
	return true
}
func streamCheckpointsHaveOffsets(rows []JSONObject) bool {
	for _, row := range rows {
		if row["stream_id"] == nil || row["consumer_id"] == nil || row["offset"] == nil {
			return false
		}
	}
	return true
}
func highRiskApprovalsDecided(rows []ApprovalRequest) bool {
	high := map[string]bool{"high": true, "destructive": true, "sensitive": true}
	for _, row := range rows {
		if high[row.RiskLevel] && row.Status != "APPROVED" && row.Status != "DENIED" {
			return false
		}
	}
	return true
}
func noBlockingFailureEvents(events []Event) bool {
	bad := map[string]bool{"error_raised": true, "step_failed": true, "tool_call_failed": true, "tool_call_blocked": true}
	for _, e := range events {
		if bad[e.Type] {
			return false
		}
	}
	return true
}
