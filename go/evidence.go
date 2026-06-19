package agentledger

import (
	"encoding/json"
	"fmt"
	"strings"
)

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
	FailureEnvelopes    []JSONObject      `json:"failure_envelopes"`
	FailureLifecycle    JSONObject        `json:"failure_lifecycle"`
	FailureCausalGraph  JSONObject        `json:"failure_causal_graph"`
	FailureReplayPlan   JSONObject        `json:"failure_replay_plan"`
	FailureAlerts       JSONObject        `json:"failure_alerts"`
	FailureExport       JSONObject        `json:"failure_export"`
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
	envelopes := failureEnvelopes(runID, run.Status, store.Steps(runID), store.Ledger(runID), store.ApprovalRequests(runID), failureEvents)
	lifecycle := failureLifecycle(runID, run.Status, envelopes)
	graph := failureCausalGraph(runID, run.Status, envelopes, store.Steps(runID), store.Ledger(runID), store.ApprovalRequests(runID), store.Events(runID), store.CostRecords(runID))
	replayPlan := failureReplayPlan(runID, envelopes, store.Ledger(runID), store.Events(runID))
	alerts := failureAlerts(runID, envelopes, replayPlan, store.CostRecords(runID))
	summary := JSONObject{
		"failed_step_count":               len(failedSteps),
		"pending_verification_count":      len(pendingLedger),
		"pending_approval_count":          len(pendingApprovals),
		"failure_event_count":             len(failureEvents),
		"failure_envelope_count":          len(envelopes),
		"failure_lifecycle_event_count":   len(lifecycle["events"].([]JSONObject)),
		"failure_alert_count":             alerts["alert_count"],
		"unsafe_replay_side_effect_count": replayPlan["unsafe_side_effect_count"],
		"terminal_failure_count":          countEnvelopeStatus(envelopes, "terminal"),
		"recoverable_failure_count":       countRecoverableFailures(envelopes),
	}
	export := failureExport(runID, run.Status, summary, envelopes, lifecycle, graph, replayPlan, alerts)
	return FailureAttributionReport{RunID: runID, RunStatus: run.Status, FailedSteps: failedSteps, PendingVerification: pendingLedger, PendingApprovals: pendingApprovals, FailureEvents: failureEvents, FailureEnvelopes: envelopes, FailureLifecycle: lifecycle, FailureCausalGraph: graph, FailureReplayPlan: replayPlan, FailureAlerts: alerts, FailureExport: export, Summary: summary}, nil
}

func failureEnvelopes(runID, runStatus string, steps []Step, ledger []ToolLedgerEntry, approvals []ApprovalRequest, events []Event) []JSONObject {
	out := []JSONObject{}
	for _, step := range steps {
		if step.Status == "failed" || step.Status == "retry_scheduled" {
			status, recoverability, retryability, severity := "terminal", "terminal", "not_retryable", "risk"
			if step.Status == "retry_scheduled" {
				status, recoverability, retryability, severity = "recovery_scheduled", "auto_retry", "retryable", "warn"
			}
			out = append(out, failureEnvelope(runID, "step", step.StepID, failureCategory(step.LastErrorType+" "+step.LastError, "agent"), status, severity, recoverability, retryability, "agent", firstText(step.LastError, step.LastErrorType, "step failure"), JSONObject{"step_id": step.StepID, "occurred_at": step.UpdatedAt}, []JSONObject{{"kind": "step", "value": step.StepID}}))
		}
	}
	for _, entry := range ledger {
		if entry.Status == "PENDING_VERIFICATION" || entry.Status == "FAILED" || entry.Status == "ERROR" {
			status, recoverability, retryability, severity := "unknown_side_effect", "manual_verification", "unknown", "warn"
			if entry.Status == "FAILED" || entry.Status == "ERROR" {
				status, recoverability, retryability, severity = "terminal", "terminal", "not_retryable", "risk"
			}
			out = append(out, failureEnvelope(runID, "tool_ledger", firstText(entry.LedgerID, entry.ToolName, entry.StepID), "tool", status, severity, recoverability, retryability, "tool", firstText(entry.ErrorType, "tool side effect requires verification"), JSONObject{"step_id": entry.StepID, "tool_name": entry.ToolName, "occurred_at": entry.UpdatedAt}, []JSONObject{{"kind": "step", "value": entry.StepID}, {"kind": "tool", "value": entry.ToolName}}))
		}
	}
	for _, approval := range approvals {
		if approval.Status == ApprovalPending || approval.Status == ApprovalDenied {
			status, category, severity := "waiting_human", "approval", "warn"
			if approval.Status == ApprovalDenied {
				status, category, severity = "blocked", "policy", "risk"
			}
			out = append(out, failureEnvelope(runID, "approval", firstText(approval.ApprovalID, approval.ToolName, approval.StepID), category, status, severity, "human_required", "unknown", "policy", firstText(approval.DecisionReason, approval.Reason, "approval required"), JSONObject{"step_id": approval.StepID, "tool_name": approval.ToolName, "approval_id": approval.ApprovalID, "occurred_at": approval.UpdatedAt}, []JSONObject{{"kind": "step", "value": approval.StepID}, {"kind": "tool", "value": approval.ToolName}, {"kind": "approval", "value": approval.ApprovalID}}))
		}
	}
	for _, event := range events {
		status := eventFailureStatus(event.Type, runStatus)
		category := eventFailureCategory(event)
		out = append(out, failureEnvelope(runID, "event", fmt.Sprintf("%d", event.Seq), category, status, severityForFailureStatus(status), eventRecoverability(event.Type, runStatus), eventRetryability(event.Type), ownerForFailureCategory(category), firstText(stringValue(event.Payload["error"]), stringValue(event.Payload["reason"]), event.Type), JSONObject{"step_id": event.StepID, "event_seq": event.Seq, "event_type": event.Type, "occurred_at": event.Timestamp}, []JSONObject{{"kind": "event", "value": fmt.Sprintf("%d", event.Seq)}, {"kind": "step", "value": event.StepID}}))
	}
	return dedupeJSONObjectList(out, "failure_id")
}

func failureEnvelope(runID, sourceKind, sourceID, category, status, severity, recoverability, retryability, owner, message string, extra JSONObject, refs []JSONObject) JSONObject {
	env := JSONObject{"schema_version": "agentledger.failure.envelope.v1", "failure_id": "failure-" + slug(runID+"-"+sourceKind+"-"+sourceID), "run_id": runID, "source_kind": sourceKind, "source_id": sourceID, "category": category, "status": status, "severity": severity, "recoverability": recoverability, "retryability": retryability, "owner": owner, "message": message, "causal_refs": refs, "evidence_refs": refs}
	for key, value := range extra {
		if value != nil && value != "" {
			env[key] = value
		}
	}
	return env
}

func failureLifecycle(runID, runStatus string, envelopes []JSONObject) JSONObject {
	events := []JSONObject{}
	for _, env := range envelopes {
		events = append(events, lifecycleRow(runID, env, "failure_detected", env["message"], env["severity"]))
		events = append(events, lifecycleRow(runID, env, "failure_classified", env["category"], env["severity"]))
		status := fmt.Sprint(env["status"])
		recoverability := fmt.Sprint(env["recoverability"])
		if status == "recovery_scheduled" || status == "waiting_human" || status == "unknown_side_effect" || recoverability == "auto_retry" || recoverability == "human_required" || recoverability == "manual_verification" {
			events = append(events, lifecycleRow(runID, env, "failure_recovery_scheduled", "recovery scheduled", "warn"))
		}
		if status == "terminal" || status == "blocked" || recoverability == "terminal" {
			events = append(events, lifecycleRow(runID, env, "failure_terminal", env["message"], "risk"))
		}
	}
	return JSONObject{"schema_version": "agentledger.failure.lifecycle.v1", "run_id": runID, "run_status": runStatus, "events": events, "terminal": countLifecycle(events, "failure_terminal") > 0, "recoverable": countLifecycle(events, "failure_recovery_scheduled") > 0}
}

func lifecycleRow(runID string, env JSONObject, stage string, message any, severity any) JSONObject {
	return JSONObject{"schema_version": "agentledger.failure.lifecycle.v1", "stage": stage, "run_id": runID, "failure_id": env["failure_id"], "category": env["category"], "recoverability": env["recoverability"], "retryability": env["retryability"], "owner": env["owner"], "message": fmt.Sprint(message), "severity": fmt.Sprint(severity), "causal_refs": env["causal_refs"]}
}

func failureCausalGraph(runID, runStatus string, envelopes []JSONObject, steps []Step, ledger []ToolLedgerEntry, approvals []ApprovalRequest, events []Event, costs []CostRecord) JSONObject {
	nodes := []JSONObject{{"id": "run:" + slug(runID), "kind": "run", "status": runStatus}}
	edges := []JSONObject{}
	for _, step := range steps {
		nodes = append(nodes, JSONObject{"id": "step:" + slug(step.StepID), "kind": "step", "status": step.Status})
		edges = append(edges, JSONObject{"source": "run:" + slug(runID), "target": "step:" + slug(step.StepID), "kind": "contains_step"})
	}
	for _, event := range events {
		nodes = append(nodes, JSONObject{"id": fmt.Sprintf("event:%d", event.Seq), "kind": "event", "event_type": event.Type})
		edges = append(edges, JSONObject{"source": "run:" + slug(runID), "target": fmt.Sprintf("event:%d", event.Seq), "kind": "emitted_event"})
	}
	for _, entry := range ledger {
		nodes = append(nodes, JSONObject{"id": "tool:" + slug(entry.ToolName), "kind": "tool", "status": entry.Status})
	}
	for _, approval := range approvals {
		nodes = append(nodes, JSONObject{"id": "approval:" + slug(approval.ApprovalID), "kind": "approval", "status": approval.Status})
	}
	for _, cost := range costs {
		nodes = append(nodes, JSONObject{"id": "cost:" + slug(cost.CostID), "kind": "cost", "category": cost.Category, "amount": cost.Amount, "unit": cost.Unit})
	}
	for _, env := range envelopes {
		id := "failure:" + slug(fmt.Sprint(env["failure_id"]))
		nodes = append(nodes, JSONObject{"id": id, "kind": "failure", "category": env["category"], "status": env["status"], "owner": env["owner"]})
		edges = append(edges, JSONObject{"source": "run:" + slug(runID), "target": id, "kind": "has_failure"})
	}
	nodes = dedupeJSONObjectList(nodes, "id")
	return JSONObject{"schema_version": "agentledger.failure.causal_graph.v1", "run_id": runID, "nodes": nodes, "edges": edges, "summary": JSONObject{"node_count": len(nodes), "edge_count": len(edges), "failure_node_count": countNodeKind(nodes, "failure")}}
}

func failureReplayPlan(runID string, envelopes []JSONObject, ledger []ToolLedgerEntry, events []Event) JSONObject {
	actions := []JSONObject{}
	unsafe := 0
	manual := 0
	for _, env := range envelopes {
		status := fmt.Sprint(env["status"])
		recoverability := fmt.Sprint(env["recoverability"])
		action := JSONObject{"failure_id": env["failure_id"], "category": env["category"], "status": status, "replay_action": "reuse_recorded_evidence", "replay_safe": true, "requires_manual_verification": false, "reason": "recorded runtime evidence can be inspected without calling external systems"}
		if status == "unknown_side_effect" || recoverability == "manual_verification" {
			action["replay_action"], action["replay_safe"], action["requires_manual_verification"], action["reason"] = "manual_verify_side_effect", false, true, "Tool Ledger recorded an unknown side-effect state"
			unsafe++
			manual++
		} else if status == "waiting_human" {
			action["replay_action"] = "resume_after_approval"
		} else if status == "recovery_scheduled" {
			action["replay_action"] = "retry_from_checkpoint"
		} else if status == "terminal" || status == "blocked" {
			action["replay_action"] = "terminal_stop"
		}
		actions = append(actions, action)
	}
	return JSONObject{"schema_version": "agentledger.failure.replay_plan.v1", "run_id": runID, "mode": "evidence_only", "safe_to_replay": unsafe == 0, "unsafe_side_effect_count": unsafe, "manual_verification_count": manual, "recorded_tool_call_count": len(ledger), "recorded_event_count": len(events), "actions": actions}
}

func failureAlerts(runID string, envelopes []JSONObject, replayPlan JSONObject, costs []CostRecord) JSONObject {
	alerts := []JSONObject{}
	if countEnvelopeStatus(envelopes, "terminal") > 0 {
		alerts = append(alerts, JSONObject{"schema_version": "agentledger.failure.alerts.v1", "run_id": runID, "kind": "terminal_failure", "severity": "risk", "message": "terminal failure recorded"})
	}
	if countEnvelopeStatus(envelopes, "unknown_side_effect") > 0 {
		alerts = append(alerts, JSONObject{"schema_version": "agentledger.failure.alerts.v1", "run_id": runID, "kind": "unknown_side_effect", "severity": "risk", "message": "tool side-effect state requires manual verification"})
	}
	if fmt.Sprint(replayPlan["unsafe_side_effect_count"]) != "0" {
		alerts = append(alerts, JSONObject{"schema_version": "agentledger.failure.alerts.v1", "run_id": runID, "kind": "unsafe_replay_blocked", "severity": "risk", "message": "failure replay plan blocks unsafe automatic replay"})
	}
	return JSONObject{"schema_version": "agentledger.failure.alerts.v1", "run_id": runID, "alerts": alerts, "alert_count": len(alerts)}
}

func failureExport(runID, runStatus string, summary JSONObject, envelopes []JSONObject, lifecycle, graph, replayPlan, alerts JSONObject) JSONObject {
	return JSONObject{"schema_version": "agentledger.failure.export.v1", "run_id": runID, "run_status": runStatus, "summary": summary, "failure_envelopes": envelopes, "failure_lifecycle": lifecycle, "failure_causal_graph": graph, "failure_replay_plan": replayPlan, "failure_alerts": alerts, "external_mappings": JSONObject{"opentelemetry": JSONObject{"span_event_count": len(lifecycle["events"].([]JSONObject))}, "langfuse": JSONObject{"trace_id": runID, "observation_count": len(envelopes)}, "langsmith": JSONObject{"run_id": runID, "feedback_count": len(envelopes)}, "temporal": JSONObject{"workflow_id": runID, "failure_count": len(envelopes), "safe_to_replay": replayPlan["safe_to_replay"]}}}
}

func isFailureEvent(kind string) bool {
	switch kind {
	case "failure_classified", "error_raised", "step_failed", "step_retry_scheduled", "step_waiting_human", "lease_expired", "run_cancel_requested", "run_cancelled", "model_call_failed", "tool_call_failed", "tool_approval_required", "budget_check_failed":
		return true
	default:
		return false
	}
}

func failureCategory(text, fallback string) string {
	lower := strings.ToLower(text)
	for _, category := range []string{"sandbox", "budget", "policy", "model", "tool", "runtime"} {
		if strings.Contains(lower, category) {
			return category
		}
	}
	if strings.Contains(lower, "approval") || strings.Contains(lower, "permission") || strings.Contains(lower, "denied") {
		return "policy"
	}
	if strings.Contains(lower, "lease") || strings.Contains(lower, "worker") {
		return "runtime"
	}
	if strings.Contains(lower, "cancel") {
		return "cancellation"
	}
	if fallback == "" {
		return "agent"
	}
	return fallback
}

func eventFailureCategory(event Event) string {
	switch event.Type {
	case "model_call_failed":
		return "model"
	case "tool_call_failed", "tool_call_blocked", "tool_approval_required":
		return "tool"
	case "run_cancel_requested", "run_cancelled", "step_cancelled":
		return "cancellation"
	case "lease_expired":
		return "runtime"
	case "step_retry_scheduled":
		return "retry"
	case "step_waiting_human":
		return "approval"
	default:
		return failureCategory(event.Type+" "+stringValue(event.Payload["error_type"])+" "+stringValue(event.Payload["error"])+" "+stringValue(event.Payload["reason"]), "agent")
	}
}

func eventFailureStatus(kind, runStatus string) string {
	switch kind {
	case "step_failed", "run_cancelled", "step_cancelled":
		return "terminal"
	case "tool_call_blocked":
		return "blocked"
	case "step_retry_scheduled", "lease_expired":
		return "recovery_scheduled"
	case "step_waiting_human", "tool_approval_required":
		return "waiting_human"
	case "failure_classified":
		return "classified"
	default:
		if runStatus == "failed" && kind == "error_raised" {
			return "terminal"
		}
		return "failed"
	}
}

func eventRecoverability(kind, runStatus string) string {
	if runStatus == "failed" && (kind == "step_failed" || kind == "run_cancelled" || kind == "step_cancelled") {
		return "terminal"
	}
	switch kind {
	case "step_retry_scheduled", "lease_expired":
		return "auto_retry"
	case "step_waiting_human", "tool_approval_required":
		return "human_required"
	case "tool_call_blocked":
		return "manual_intervention"
	default:
		return "unknown"
	}
}

func eventRetryability(kind string) string {
	if kind == "step_retry_scheduled" || kind == "lease_expired" {
		return "retryable"
	}
	if kind == "tool_call_blocked" || kind == "run_cancelled" || kind == "step_cancelled" {
		return "not_retryable"
	}
	return "unknown"
}

func severityForFailureStatus(status string) string {
	if status == "terminal" || status == "blocked" || status == "failed" {
		return "risk"
	}
	return "warn"
}

func ownerForFailureCategory(category string) string {
	switch category {
	case "tool", "model", "policy", "sandbox", "budget", "runtime":
		return category
	case "approval", "cancellation", "retry":
		return "runtime"
	default:
		return "agent"
	}
}

func firstText(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return "failure signal"
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	return fmt.Sprint(value)
}

func dedupeJSONObjectList(rows []JSONObject, key string) []JSONObject {
	out := []JSONObject{}
	seen := map[string]bool{}
	for _, row := range rows {
		value := fmt.Sprint(row[key])
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		out = append(out, row)
	}
	return out
}

func countEnvelopeStatus(envelopes []JSONObject, status string) int {
	count := 0
	for _, envelope := range envelopes {
		if fmt.Sprint(envelope["status"]) == status {
			count++
		}
	}
	return count
}

func countRecoverableFailures(envelopes []JSONObject) int {
	count := 0
	for _, envelope := range envelopes {
		switch fmt.Sprint(envelope["recoverability"]) {
		case "auto_retry", "recoverable", "manual_verification", "human_required":
			count++
		}
	}
	return count
}

func countLifecycle(rows []JSONObject, stage string) int {
	count := 0
	for _, row := range rows {
		if fmt.Sprint(row["stage"]) == stage {
			count++
		}
	}
	return count
}

func countNodeKind(rows []JSONObject, kind string) int {
	count := 0
	for _, row := range rows {
		if fmt.Sprint(row["kind"]) == kind {
			count++
		}
	}
	return count
}

func slug(value string) string {
	var builder strings.Builder
	previousDash := false
	for _, ch := range strings.ToLower(value) {
		if (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') {
			builder.WriteRune(ch)
			previousDash = false
			continue
		}
		if !previousDash {
			builder.WriteByte('-')
			previousDash = true
		}
	}
	out := strings.Trim(builder.String(), "-")
	if out == "" {
		return "unknown"
	}
	return out
}
