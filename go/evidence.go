package agentledger

import "encoding/json"

type EvidenceBundle struct {
	SchemaVersion     string            `json:"schema_version"`
	BundleHash        string            `json:"bundle_hash"`
	Run               Run               `json:"run"`
	Steps             []Step            `json:"steps"`
	Events            []Event           `json:"events"`
	ToolLedger        []ToolLedgerEntry `json:"tool_ledger"`
	Approvals         []ApprovalRequest `json:"approvals"`
	Artifacts         []Artifact        `json:"artifacts"`
	MediaArtifacts    []JSONObject      `json:"media_artifacts"`
	StreamCheckpoints []JSONObject      `json:"stream_checkpoints"`
	CostRecords       []CostRecord      `json:"cost_records"`
	CostSummary       CostSummary       `json:"cost_summary"`
	Summary           JSONObject        `json:"summary"`
	FinalState        JSONObject        `json:"final_state"`
}

func ExportEvidence(store *JSONStore, runID string) (EvidenceBundle, error) {
	run, err := store.Run(runID)
	if err != nil {
		return EvidenceBundle{}, err
	}
	steps := store.Steps(runID)
	events := store.Events(runID)
	ledger := store.Ledger(runID)
	approvals := store.ApprovalRequests(runID)
	artifacts := store.Artifacts(runID)
	mediaArtifacts := mediaArtifactsFrom(artifacts)
	streamCheckpoints := streamCheckpointsFrom(artifacts)
	costRecords := store.CostRecords(runID)
	costSummary := store.CostSummary(runID)
	finalState, err := store.FinalState(runID)
	if err != nil {
		return EvidenceBundle{}, err
	}
	summary := JSONObject{
		"event_count":             len(events),
		"step_count":              len(steps),
		"tool_ledger_count":       len(ledger),
		"approval_count":          len(approvals),
		"artifact_count":          len(artifacts),
		"media_artifact_count":    len(mediaArtifacts),
		"stream_checkpoint_count": len(streamCheckpoints),
		"cost_record_count":       len(costRecords),
		"has_failed_steps":        hasStepStatus(steps, "failed"),
		"has_pending_ledger":      hasLedgerStatus(ledger, "PENDING_VERIFICATION"),
		"has_pending_approval":    hasApprovalStatus(approvals, ApprovalPending),
	}
	bundle := EvidenceBundle{
		SchemaVersion:     "agentledger.evidence.v1",
		Run:               run,
		Steps:             steps,
		Events:            events,
		ToolLedger:        ledger,
		Approvals:         approvals,
		Artifacts:         artifacts,
		MediaArtifacts:    mediaArtifacts,
		StreamCheckpoints: streamCheckpoints,
		CostRecords:       costRecords,
		CostSummary:       costSummary,
		Summary:           summary,
		FinalState:        finalState,
	}
	hash, err := sha256JSON(bundleWithoutHash(bundle))
	if err != nil {
		return EvidenceBundle{}, err
	}
	bundle.BundleHash = hash
	return bundle, nil
}

func mediaArtifactsFrom(artifacts []Artifact) []JSONObject {
	out := []JSONObject{}
	for _, artifact := range artifacts {
		metadata, ok := artifact.Metadata["agentledger_media"].(map[string]any)
		if !ok {
			if asObject, ok := artifact.Metadata["agentledger_media"].(JSONObject); ok {
				metadata = map[string]any(asObject)
			} else {
				continue
			}
		}
		out = append(out, compactJSON(JSONObject{
			"artifact_id": artifact.ArtifactID,
			"name":        artifact.Name,
			"blob_hash":   artifact.BlobHash,
			"blob_ref":    artifact.BlobRef,
			"kind":        metadata["kind"],
			"uri":         metadata["uri"],
			"content_ref": metadata["content_ref"],
			"metadata":    metadata["metadata"],
			"lineage":     metadata["lineage"],
		}))
	}
	return out
}

func streamCheckpointsFrom(artifacts []Artifact) []JSONObject {
	out := []JSONObject{}
	for _, artifact := range artifacts {
		metadata, ok := artifact.Metadata["agentledger_stream"].(map[string]any)
		if !ok {
			if asObject, ok := artifact.Metadata["agentledger_stream"].(JSONObject); ok {
				metadata = map[string]any(asObject)
			} else {
				continue
			}
		}
		out = append(out, compactJSON(JSONObject{
			"artifact_id":        artifact.ArtifactID,
			"name":               artifact.Name,
			"blob_hash":          artifact.BlobHash,
			"blob_ref":           artifact.BlobRef,
			"stream_id":          metadata["stream_id"],
			"consumer_id":        metadata["consumer_id"],
			"offset":             metadata["offset"],
			"watermark":          metadata["watermark"],
			"chunk":              metadata["chunk"],
			"partial_result_ref": metadata["partial_result_ref"],
			"backpressure":       metadata["backpressure"],
		}))
	}
	return out
}

func (b EvidenceBundle) JSON() ([]byte, error) {
	return json.MarshalIndent(b, "", "  ")
}

func bundleWithoutHash(bundle EvidenceBundle) EvidenceBundle {
	bundle.BundleHash = ""
	return bundle
}

func hasStepStatus(steps []Step, status string) bool {
	for _, step := range steps {
		if step.Status == status {
			return true
		}
	}
	return false
}

func hasLedgerStatus(entries []ToolLedgerEntry, status string) bool {
	for _, entry := range entries {
		if entry.Status == status {
			return true
		}
	}
	return false
}

func hasApprovalStatus(entries []ApprovalRequest, status string) bool {
	for _, entry := range entries {
		if entry.Status == status {
			return true
		}
	}
	return false
}

type CostAttributionReport struct {
	RunID      string                        `json:"run_id"`
	Total      CostSummary                   `json:"total"`
	ByAgent    map[string]CostSummary        `json:"by_agent"`
	ByStep     map[string]CostSummary        `json:"by_step"`
	ByCategory map[string]map[string]float64 `json:"by_category"`
	ByName     map[string]CostSummary        `json:"by_name"`
}

func CostAttribution(store *JSONStore, runID string) CostAttributionReport {
	stepRoles := map[string]string{}
	for _, event := range store.Events(runID) {
		if event.StepID != "" && event.AgentRole != "" {
			stepRoles[event.StepID] = event.AgentRole
		}
	}
	report := CostAttributionReport{RunID: runID, Total: CostSummary{ByCategory: map[string]float64{}}, ByAgent: map[string]CostSummary{}, ByStep: map[string]CostSummary{}, ByCategory: map[string]map[string]float64{}, ByName: map[string]CostSummary{}}
	for _, record := range store.CostRecords(runID) {
		addCost(&report.Total, record)
		agent := stepRoles[record.StepID]
		if agent == "" {
			agent = "<unknown>"
		}
		agentSummary := report.ByAgent[agent]
		addCost(&agentSummary, record)
		report.ByAgent[agent] = agentSummary
		stepKey := record.StepID
		if stepKey == "" {
			stepKey = "<run>"
		}
		stepSummary := report.ByStep[stepKey]
		addCost(&stepSummary, record)
		report.ByStep[stepKey] = stepSummary
		nameSummary := report.ByName[record.Name]
		addCost(&nameSummary, record)
		report.ByName[record.Name] = nameSummary
		bucket := report.ByCategory[record.Category]
		if bucket == nil {
			bucket = map[string]float64{}
		}
		bucket[record.Unit] += record.Amount
		report.ByCategory[record.Category] = bucket
	}
	return report
}

func addCost(summary *CostSummary, record CostRecord) {
	if summary.ByCategory == nil {
		summary.ByCategory = map[string]float64{}
	}
	if (record.Category == "tool" || record.Category == "tool_shadow") && record.Unit == "call" {
		summary.ToolCalls += record.Amount
	}
	if record.Category == "model" && record.Unit == "token" {
		summary.ModelTokens += record.Amount
	}
	if record.Unit == "usd" {
		summary.TotalUSD += record.Amount
	}
	summary.ByCategory[record.Category+":"+record.Unit] += record.Amount
}

type FailureAttributionReport struct {
	RunID               string            `json:"run_id"`
	RunStatus           string            `json:"run_status"`
	FailedSteps         []Step            `json:"failed_steps"`
	PendingVerification []ToolLedgerEntry `json:"pending_verification"`
	PendingApprovals    []ApprovalRequest `json:"pending_approvals"`
	FailureEvents       []Event           `json:"failure_events"`
	Summary             JSONObject        `json:"summary"`
}

func FailureAttribution(store *JSONStore, runID string) (FailureAttributionReport, error) {
	run, err := store.Run(runID)
	if err != nil {
		return FailureAttributionReport{}, err
	}
	failedSteps := []Step{}
	for _, step := range store.Steps(runID) {
		if step.Status == "failed" {
			failedSteps = append(failedSteps, step)
		}
	}
	pendingLedger := []ToolLedgerEntry{}
	for _, entry := range store.Ledger(runID) {
		if entry.Status == "PENDING_VERIFICATION" {
			pendingLedger = append(pendingLedger, entry)
		}
	}
	pendingApprovals := []ApprovalRequest{}
	for _, approval := range store.ApprovalRequests(runID) {
		if approval.Status == ApprovalPending {
			pendingApprovals = append(pendingApprovals, approval)
		}
	}
	failureEvents := []Event{}
	for _, event := range store.Events(runID) {
		if isFailureEvent(event.Type) {
			failureEvents = append(failureEvents, event)
		}
	}
	return FailureAttributionReport{RunID: runID, RunStatus: run.Status, FailedSteps: failedSteps, PendingVerification: pendingLedger, PendingApprovals: pendingApprovals, FailureEvents: failureEvents, Summary: JSONObject{"failed_step_count": len(failedSteps), "pending_verification_count": len(pendingLedger), "pending_approval_count": len(pendingApprovals), "failure_event_count": len(failureEvents)}}, nil
}

func isFailureEvent(kind string) bool {
	switch kind {
	case "failure_classified", "error_raised", "step_failed", "step_retry_scheduled", "step_waiting_human", "lease_expired", "run_cancel_requested", "run_cancelled", "tool_call_failed", "tool_approval_required", "budget_check_failed":
		return true
	default:
		return false
	}
}
