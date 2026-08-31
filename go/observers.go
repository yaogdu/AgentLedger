package agentledger

import (
	"fmt"
	"strings"
)

const (
	TemporalObserverSchemaVersion  = "agentledger.temporal.observer.v1"
	DSHObserverSchemaVersion       = "agentledger.dsh.observer.v1"
	A2AObserverSchemaVersion       = "agentledger.a2a.observer.v1"
	FrameworkObserverSchemaVersion = "agentledger.framework.observer.v1"
	MCPObserverSchemaVersion       = "agentledger.mcp.observer.v1"
)

type normalizedEvidenceObserver struct {
	bridge *ExecutionEvidenceBridge
	kind   string
	schema string
	runID  string
}

type TemporalEvidenceObserver struct{ observer *normalizedEvidenceObserver }
type DSHEvidenceObserver struct{ observer *normalizedEvidenceObserver }
type A2AEvidenceObserver struct{ observer *normalizedEvidenceObserver }
type FrameworkEvidenceObserver struct{ observer *normalizedEvidenceObserver }
type MCPEvidenceObserver struct{ observer *normalizedEvidenceObserver }

func NewTemporalEvidenceObserver(runtime *Runtime, appName string, runID ...string) *TemporalEvidenceObserver {
	return &TemporalEvidenceObserver{observer: newEvidenceObserver(runtime, appName, "temporal", TemporalObserverSchemaVersion, firstOptional(runID), "temporal")}
}

func NewDSHEvidenceObserver(runtime *Runtime, appName string, runID ...string) *DSHEvidenceObserver {
	return &DSHEvidenceObserver{observer: newEvidenceObserver(runtime, appName, "dsh", DSHObserverSchemaVersion, firstOptional(runID), "dsh")}
}

func NewA2AEvidenceObserver(runtime *Runtime, appName string, runID ...string) *A2AEvidenceObserver {
	return &A2AEvidenceObserver{observer: newEvidenceObserver(runtime, appName, "a2a", A2AObserverSchemaVersion, firstOptional(runID), "a2a")}
}

func NewFrameworkEvidenceObserver(runtime *Runtime, appName string, source ...string) *FrameworkEvidenceObserver {
	observerSource := firstOptional(source)
	if observerSource == "" {
		observerSource = "framework"
	}
	return &FrameworkEvidenceObserver{observer: newEvidenceObserver(runtime, appName, "framework", FrameworkObserverSchemaVersion, "", observerSource)}
}

func NewMCPEvidenceObserver(runtime *Runtime, appName string, runID ...string) *MCPEvidenceObserver {
	return &MCPEvidenceObserver{observer: newEvidenceObserver(runtime, appName, "mcp", MCPObserverSchemaVersion, firstOptional(runID), "mcp")}
}

func newEvidenceObserver(runtime *Runtime, appName, kind, schema, runID string, source ...string) *normalizedEvidenceObserver {
	bridgeSource := firstOptional(source)
	if bridgeSource == "" {
		bridgeSource = kind
	}
	return &normalizedEvidenceObserver{
		bridge: NewExecutionEvidenceBridge(runtime, appName, bridgeSource),
		kind:   kind,
		schema: schema,
		runID:  runID,
	}
}

func (o *TemporalEvidenceObserver) Observe(event JSONObject) (any, error) {
	return o.observer.observe(event)
}
func (o *DSHEvidenceObserver) Observe(event JSONObject) (any, error) {
	return o.observer.observe(event)
}
func (o *A2AEvidenceObserver) Observe(event JSONObject) (any, error) {
	return o.observer.observe(event)
}
func (o *FrameworkEvidenceObserver) Observe(event JSONObject) (any, error) {
	return o.observer.observe(event)
}
func (o *MCPEvidenceObserver) Observe(event JSONObject) (any, error) {
	return o.observer.observe(event)
}

func (o *normalizedEvidenceObserver) observe(event JSONObject) (result any, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			if recoveredErr, ok := recovered.(error); ok {
				err = recoveredErr
			} else {
				err = fmt.Errorf("%s evidence event invalid: %v", o.kind, recovered)
			}
			result = nil
		}
	}()
	if event == nil {
		return nil, fmt.Errorf("%s evidence event must be an object", o.kind)
	}
	if value, ok := event["metadata"]; ok && value != nil && eventObject(value) == nil {
		return nil, fmt.Errorf("%s evidence metadata must be an object", o.kind)
	}
	eventType, err := observerEventType(event, o.kind)
	if err != nil {
		return nil, err
	}
	sessionID, err := o.sessionID(event)
	if err != nil {
		return nil, err
	}
	if err := o.ensureBoundSession(event, sessionID); err != nil {
		return nil, err
	}

	switch o.kind {
	case "temporal":
		return o.observeTemporal(event, eventType, sessionID)
	case "dsh":
		return o.observeDSH(event, eventType, sessionID)
	case "a2a":
		return o.observeA2A(event, eventType, sessionID)
	case "framework":
		return o.observeFramework(event, eventType, sessionID)
	case "mcp":
		return o.observeMCP(event, eventType, sessionID)
	default:
		return nil, fmt.Errorf("unsupported evidence observer: %s", o.kind)
	}
}

func (o *normalizedEvidenceObserver) observeTemporal(event JSONObject, eventType, sessionID string) (any, error) {
	switch {
	case in(eventType, "workflow_started", "workflow_execution_started"):
		return o.bridge.RecordSessionStarted(o.session(event, sessionID))
	case in(eventType, "activity_started", "activity_task_started"):
		return o.bridge.RecordTurnStarted(o.turn(event, sessionID, o.required(event, "activity_id", "turn_id"), "TemporalActivityAgent"))
	case in(eventType, "model_call", "model_call_completed"):
		return nil, o.bridge.RecordModelCall(o.modelCall(event, sessionID, o.required(event, "activity_id", "turn_id")))
	case in(eventType, "tool_proposal", "tool_call_proposed"):
		return nil, o.bridge.RecordToolProposal(o.toolProposal(event, sessionID, o.required(event, "activity_id", "turn_id")))
	case in(eventType, "tool_execution", "tool_call_completed", "tool_call_failed"):
		return o.bridge.RecordToolExecution(o.toolExecution(event, sessionID, o.required(event, "activity_id", "turn_id")))
	case in(eventType, "state_change", "state_change_recorded"):
		version, err := o.bridge.RecordStateChange(o.stateChange(event, sessionID, o.optional(event, "activity_id", "turn_id")))
		return version, err
	case in(eventType, "artifact_recorded", "artifact_created", "media_artifact_recorded"):
		return o.bridge.RecordArtifact(o.artifact(event, sessionID, o.optional(event, "activity_id", "turn_id")))
	case in(eventType, "activity_completed", "activity_task_completed"):
		turn := o.turn(event, sessionID, o.required(event, "activity_id", "turn_id"), "TemporalActivityAgent")
		turn.StatePatch = o.dict(event, "state_patch")
		version, err := o.bridge.RecordTurnCompleted(turn)
		return version, err
	case in(eventType, "activity_failed", "activity_task_failed"):
		return nil, o.bridge.RecordFailure(o.failure(event, sessionID, o.required(event, "activity_id", "turn_id"), "TemporalActivityFailure"))
	case in(eventType, "activity_scheduled", "activity_task_scheduled", "workflow_completed", "workflow_execution_completed", "workflow_failed", "workflow_execution_failed"):
		return o.receipt(event, sessionID, o.optional(event, "causal_token", "activity_id", "workflow_run_id"), JSONObject{
			"receipt_type": eventType, "workflow_id": o.optional(event, "workflow_id"),
			"workflow_run_id": o.optional(event, "workflow_run_id"), "activity_id": o.optional(event, "activity_id"),
			"attempt": event["attempt"], "status": firstText(o.optional(event, "status", "state"), statusFor(eventType)),
			"metadata": o.metadata(event),
		})
	}
	return nil, o.unsupported(eventType)
}

func (o *normalizedEvidenceObserver) observeDSH(event JSONObject, eventType, sessionID string) (any, error) {
	turnID := o.optional(event, "step_id", "turn_id")
	switch {
	case in(eventType, "run_started", "session_started", "execution_started"):
		return o.bridge.RecordSessionStarted(o.session(event, sessionID))
	case in(eventType, "step_started", "turn_started"):
		return o.bridge.RecordTurnStarted(o.turn(event, sessionID, o.required(event, "step_id", "turn_id"), "DSHAgent"))
	case in(eventType, "model_call", "model_call_completed"):
		return nil, o.bridge.RecordModelCall(o.modelCall(event, sessionID, o.required(event, "step_id", "turn_id")))
	case in(eventType, "tool_proposal", "tool_call_proposed"):
		return nil, o.bridge.RecordToolProposal(o.toolProposal(event, sessionID, o.required(event, "step_id", "turn_id")))
	case in(eventType, "tool_execution", "tool_call_completed", "tool_call_failed"):
		return o.bridge.RecordToolExecution(o.toolExecution(event, sessionID, o.required(event, "step_id", "turn_id")))
	case in(eventType, "state_change", "state_change_recorded"):
		version, err := o.bridge.RecordStateChange(o.stateChange(event, sessionID, turnID))
		return version, err
	case in(eventType, "artifact_recorded", "artifact_created", "media_artifact_recorded"):
		return o.bridge.RecordArtifact(o.artifact(event, sessionID, turnID))
	case in(eventType, "side_effect_receipt", "task_receipt", "execution_receipt"):
		return o.receipt(event, sessionID, o.optional(event, "causal_token", "receipt_id"), JSONObject{
			"receipt_type": eventType, "receipt_id": o.optional(event, "receipt_id"),
			"task_id": o.optional(event, "task_id"), "status": o.optional(event, "status", "state"),
			"external_id": o.optional(event, "external_id"), "artifact_refs": firstValue(event, "artifact_refs", "artifacts"),
			"metadata": o.metadata(event),
		})
	case in(eventType, "step_completed", "turn_completed"):
		turn := o.turn(event, sessionID, o.required(event, "step_id", "turn_id"), "DSHAgent")
		turn.StatePatch = o.dict(event, "state_patch")
		version, err := o.bridge.RecordTurnCompleted(turn)
		return version, err
	case in(eventType, "step_failed", "turn_failed"):
		return nil, o.bridge.RecordFailure(o.failure(event, sessionID, o.required(event, "step_id", "turn_id"), "DSHStepFailure"))
	}
	return nil, o.unsupported(eventType)
}

func (o *normalizedEvidenceObserver) observeA2A(event JSONObject, eventType, sessionID string) (any, error) {
	taskID := o.optional(event, "task_id", "turn_id")
	switch {
	case eventType == "task_submitted":
		runID, err := o.bridge.RecordSessionStarted(o.session(event, sessionID))
		if err != nil {
			return nil, err
		}
		if _, err := o.receipt(event, sessionID, o.optional(event, "causal_token"), o.a2aReceipt(event, eventType)); err != nil {
			return nil, err
		}
		return runID, nil
	case eventType == "task_started":
		if _, err := o.bridge.RecordSessionStarted(o.session(event, sessionID)); err != nil {
			return nil, err
		}
		return o.bridge.RecordTurnStarted(o.turn(event, sessionID, o.required(event, "task_id", "turn_id"), firstText(o.optional(event, "agent_role", "to_agent"), "A2AAgent")))
	case in(eventType, "handoff_requested", "handoff_completed", "task_updated"):
		if _, err := o.bridge.RecordSessionStarted(o.session(event, sessionID)); err != nil {
			return nil, err
		}
		return o.receipt(event, sessionID, o.optional(event, "causal_token"), o.a2aReceipt(event, eventType))
	case eventType == "task_completed":
		if _, err := o.bridge.RecordSessionStarted(o.session(event, sessionID)); err != nil {
			return nil, err
		}
		if _, err := o.receipt(event, sessionID, o.optional(event, "causal_token"), o.a2aReceipt(event, eventType)); err != nil {
			return nil, err
		}
		turn := o.turn(event, sessionID, o.required(event, "task_id", "turn_id"), "A2AAgent")
		turn.StatePatch = o.dict(event, "state_patch")
		version, err := o.bridge.RecordTurnCompleted(turn)
		return version, err
	case eventType == "task_failed":
		if _, err := o.bridge.RecordSessionStarted(o.session(event, sessionID)); err != nil {
			return nil, err
		}
		if _, err := o.receipt(event, sessionID, o.optional(event, "causal_token"), o.a2aReceipt(event, eventType)); err != nil {
			return nil, err
		}
		return nil, o.bridge.RecordFailure(o.failure(event, sessionID, o.required(event, "task_id", "turn_id"), "A2ATaskFailure"))
	case in(eventType, "model_call", "model_call_completed"):
		return nil, o.bridge.RecordModelCall(o.modelCall(event, sessionID, o.required(event, "task_id", "turn_id")))
	case in(eventType, "tool_proposal", "tool_call_proposed"):
		return nil, o.bridge.RecordToolProposal(o.toolProposal(event, sessionID, o.required(event, "task_id", "turn_id")))
	case in(eventType, "tool_execution", "tool_call_completed", "tool_call_failed"):
		return o.bridge.RecordToolExecution(o.toolExecution(event, sessionID, o.required(event, "task_id", "turn_id")))
	case in(eventType, "state_change", "state_change_recorded"):
		version, err := o.bridge.RecordStateChange(o.stateChange(event, sessionID, taskID))
		return version, err
	case in(eventType, "artifact_recorded", "artifact_created", "media_artifact_recorded"):
		return o.bridge.RecordArtifact(o.artifact(event, sessionID, taskID))
	}
	return nil, o.unsupported(eventType)
}

func (o *normalizedEvidenceObserver) observeFramework(event JSONObject, eventType, sessionID string) (any, error) {
	turnID := o.optional(event, "node_id", "step_id", "turn_id")
	switch {
	case in(eventType, "session_started", "run_started", "graph_started", "agent_started"):
		return o.bridge.RecordSessionStarted(o.session(event, sessionID))
	case in(eventType, "node_started", "step_started", "turn_started"):
		return o.bridge.RecordTurnStarted(o.turn(event, sessionID, o.required(event, "turn_id", "node_id", "step_id"), firstText(o.optional(event, "agent_role", "node_name"), "FrameworkAgent")))
	case in(eventType, "model_call", "model_call_completed"):
		return nil, o.bridge.RecordModelCall(o.modelCall(event, sessionID, o.required(event, "turn_id", "node_id", "step_id")))
	case in(eventType, "tool_proposal", "tool_call_proposed", "tool_call_requested"):
		return nil, o.bridge.RecordToolProposal(o.toolProposal(event, sessionID, o.required(event, "turn_id", "node_id", "step_id")))
	case in(eventType, "tool_execution", "tool_call_completed", "tool_call_failed"):
		return o.bridge.RecordToolExecution(o.toolExecution(event, sessionID, o.required(event, "turn_id", "node_id", "step_id")))
	case in(eventType, "state_change", "state_change_recorded"):
		version, err := o.bridge.RecordStateChange(o.stateChange(event, sessionID, turnID))
		return version, err
	case in(eventType, "artifact_recorded", "artifact_created", "media_artifact_recorded"):
		return o.bridge.RecordArtifact(o.artifact(event, sessionID, turnID))
	case in(eventType, "checkpoint_saved", "checkpoint_recorded", "handoff_requested", "handoff_completed"):
		return o.receipt(event, sessionID, o.optional(event, "causal_token", "checkpoint_id", "handoff_id"), JSONObject{
			"receipt_type": eventType, "checkpoint_id": o.optional(event, "checkpoint_id"),
			"checkpoint_ns": o.optional(event, "checkpoint_ns"), "parent_checkpoint_id": o.optional(event, "parent_checkpoint_id"),
			"thread_id": o.optional(event, "thread_id"), "handoff_id": o.optional(event, "handoff_id"),
			"from_agent": o.optional(event, "from_agent"), "to_agent": o.optional(event, "to_agent"),
			"artifact_refs": firstValue(event, "artifact_refs", "artifacts"), "status": o.optional(event, "status", "state"),
			"metadata": o.metadata(event),
		})
	case in(eventType, "node_completed", "step_completed", "turn_completed"):
		turn := o.turn(event, sessionID, o.required(event, "turn_id", "node_id", "step_id"), "FrameworkAgent")
		turn.StatePatch = o.dict(event, "state_patch")
		version, err := o.bridge.RecordTurnCompleted(turn)
		return version, err
	case in(eventType, "run_completed", "graph_completed", "agent_completed"):
		return o.receipt(event, sessionID, o.optional(event, "causal_token", "run_id", "thread_id"), JSONObject{"receipt_type": eventType, "status": firstText(o.optional(event, "status", "state"), "completed"), "metadata": o.metadata(event)})
	case in(eventType, "node_failed", "step_failed", "turn_failed"):
		return nil, o.bridge.RecordFailure(o.failure(event, sessionID, o.required(event, "turn_id", "node_id", "step_id"), "FrameworkStepFailure"))
	}
	return nil, o.unsupported(eventType)
}

func (o *normalizedEvidenceObserver) observeMCP(event JSONObject, eventType, sessionID string) (any, error) {
	turnID := o.optional(event, "turn_id", "request_id")
	switch {
	case in(eventType, "session_started", "connection_started"):
		return o.bridge.RecordSessionStarted(o.session(event, sessionID))
	case in(eventType, "request_started", "turn_started"):
		return o.bridge.RecordTurnStarted(o.turn(event, sessionID, o.required(event, "turn_id", "request_id"), "MCPAgent"))
	case in(eventType, "tool_call_proposed", "tool_call_requested"):
		proposal := o.toolProposal(event, sessionID, o.required(event, "turn_id", "request_id"))
		proposal.Provider = firstText(o.optional(event, "server_name", "provider"), proposal.Provider)
		return nil, o.bridge.RecordToolProposal(proposal)
	case in(eventType, "tool_call_completed", "tool_call_failed", "tool_execution"):
		return o.bridge.RecordToolExecution(o.toolExecution(event, sessionID, o.required(event, "turn_id", "request_id")))
	case in(eventType, "resource_read", "resource_read_completed", "resource_read_failed", "prompt_get", "prompt_get_completed", "prompt_get_failed"):
		return o.receipt(event, sessionID, o.optional(event, "causal_token", "request_id"), JSONObject{
			"receipt_type": eventType, "request_id": o.optional(event, "request_id"),
			"resource_uri": o.optional(event, "resource_uri", "uri"), "prompt_name": o.optional(event, "prompt_name"),
			"mime_type": o.optional(event, "mime_type"), "content_ref": o.optional(event, "content_ref"),
			"status": o.optional(event, "status", "state"), "error": o.optional(event, "error"), "metadata": o.metadata(event),
		})
	case in(eventType, "state_change", "state_change_recorded"):
		version, err := o.bridge.RecordStateChange(o.stateChange(event, sessionID, turnID))
		return version, err
	case in(eventType, "artifact_recorded", "artifact_created", "media_artifact_recorded"):
		return o.bridge.RecordArtifact(o.artifact(event, sessionID, turnID))
	case in(eventType, "request_completed", "turn_completed"):
		turn := o.turn(event, sessionID, o.required(event, "turn_id", "request_id"), "MCPAgent")
		turn.StatePatch = o.dict(event, "state_patch")
		version, err := o.bridge.RecordTurnCompleted(turn)
		return version, err
	}
	return nil, o.unsupported(eventType)
}

func (o *normalizedEvidenceObserver) session(event JSONObject, sessionID string) ExecutionSession {
	return ExecutionSession{SessionID: sessionID, InitialState: o.dict(event, "initial_state"), Metadata: o.metadata(event), RunID: o.runtimeRunID(event)}
}

func (o *normalizedEvidenceObserver) turn(event JSONObject, sessionID, turnID, role string) ExecutionTurn {
	return ExecutionTurn{SessionID: sessionID, TurnID: turnID, AgentRole: role, Metadata: o.metadata(event)}
}

func (o *normalizedEvidenceObserver) modelCall(event JSONObject, sessionID, turnID string) ExecutionModelCall {
	return ExecutionModelCall{SessionID: sessionID, TurnID: turnID, Provider: o.required(event, "provider"), Model: o.required(event, "model"), Request: o.dict(event, "request"), Response: o.dict(event, "response"), Usage: o.dict(event, "usage"), TotalUSD: observerNumberValue(firstValue(event, "total_usd", "totalUsd")), Metadata: o.metadata(event)}
}

func (o *normalizedEvidenceObserver) toolProposal(event JSONObject, sessionID, turnID string) ExecutionToolProposal {
	confidence := numberPointer(firstValue(event, "confidence"))
	return ExecutionToolProposal{SessionID: sessionID, TurnID: turnID, ToolName: o.required(event, "tool_name", "tool"), Arguments: o.dict(event, "arguments", "args"), Provider: o.optional(event, "provider"), Model: o.optional(event, "model"), ModelCallRef: o.optional(event, "model_call_ref"), Confidence: confidence, Reason: o.optional(event, "reason"), Metadata: o.metadata(event)}
}

func (o *normalizedEvidenceObserver) toolExecution(event JSONObject, sessionID, turnID string) ExecutionToolExecution {
	return ExecutionToolExecution{SessionID: sessionID, TurnID: turnID, ToolName: o.required(event, "tool_name", "tool"), Arguments: o.dict(event, "arguments", "args"), Result: firstValue(event, "result"), ToolCallID: o.optional(event, "tool_call_id"), ToolVersion: firstText(o.optional(event, "tool_version"), "external"), IdempotencyKey: o.optional(event, "idempotency_key"), LedgerStatus: o.optional(event, "ledger_status", "status"), ErrorType: o.optional(event, "error_type"), ErrorMessage: o.optional(event, "error_message", "error"), ExternalID: o.optional(event, "external_id"), CausalToken: o.optional(event, "causal_token"), Metadata: o.metadata(event)}
}

func (o *normalizedEvidenceObserver) failure(event JSONObject, sessionID, turnID, defaultType string) ExecutionFailure {
	retryable := boolPointer(firstValue(event, "retryable"))
	status := o.optional(event, "status")
	if status == "" {
		status = statusForBool(retryable)
	}
	return ExecutionFailure{SessionID: sessionID, TurnID: turnID, ErrorType: firstText(o.optional(event, "error_type", "failure_type"), defaultType), Message: o.required(event, "message", "error"), Retryable: retryable, Status: status, Terminal: boolPointerDefault(event, "terminal", true), Category: firstText(o.optional(event, "category"), "runtime"), Provider: o.optional(event, "provider"), Model: o.optional(event, "model"), Request: o.dict(event, "request"), Usage: o.dict(event, "usage"), TotalUSD: observerNumberValue(firstValue(event, "total_usd", "totalUsd")), Metadata: o.metadata(event), ApprovalID: o.optional(event, "approval_id")}
}

func (o *normalizedEvidenceObserver) stateChange(event JSONObject, sessionID, turnID string) ExecutionStateChange {
	return ExecutionStateChange{SessionID: sessionID, TurnID: turnID, Reason: o.required(event, "reason"), Patch: o.dict(event, "patch"), Label: firstText(o.optional(event, "label"), "state"), CommitStatus: firstText(o.optional(event, "commit_status"), "committed"), BeforeSnapshot: firstValue(event, "before_snapshot"), AfterSnapshot: firstValue(event, "after_snapshot"), Diff: firstValue(event, "diff"), Metadata: o.metadata(event)}
}

func (o *normalizedEvidenceObserver) artifact(event JSONObject, sessionID, turnID string) ExecutionArtifact {
	return ExecutionArtifact{SessionID: sessionID, TurnID: turnID, Name: o.required(event, "name", "artifact_name"), Kind: firstText(o.optional(event, "kind"), "artifact"), URI: o.optional(event, "uri"), ContentRef: o.optional(event, "content_ref"), ExternalID: o.optional(event, "external_id", "artifact_id"), Metadata: o.metadata(event), Lineage: o.dict(event, "lineage"), DerivedOutputs: o.dict(event, "derived_outputs")}
}

func (o *normalizedEvidenceObserver) receipt(event JSONObject, sessionID, causalToken string, payload JSONObject) (Event, error) {
	return o.bridge.RecordExecutionEvent(sessionID, "task_receipt_recorded", payload, o.optional(event, "turn_id", "step_id", "task_id", "request_id", "activity_id", "node_id"), "", causalToken)
}

func (o *normalizedEvidenceObserver) a2aReceipt(event JSONObject, eventType string) JSONObject {
	return JSONObject{"receipt_type": eventType, "context_id": o.optional(event, "context_id", "session_id"), "task_id": o.optional(event, "task_id", "turn_id"), "handoff_id": o.optional(event, "handoff_id"), "message_id": o.optional(event, "message_id"), "from_agent": o.optional(event, "from_agent"), "to_agent": o.optional(event, "to_agent"), "status": o.optional(event, "status", "state"), "artifact_refs": firstValue(event, "artifact_refs", "artifacts"), "metadata": o.metadata(event)}
}

func (o *normalizedEvidenceObserver) ensureBoundSession(event JSONObject, sessionID string) error {
	runID := o.runtimeRunID(event)
	if runID == "" {
		return nil
	}
	_, err := o.bridge.RecordSessionStarted(ExecutionSession{SessionID: sessionID, InitialState: o.dict(event, "initial_state"), Metadata: o.metadata(event), RunID: runID})
	return err
}

func (o *normalizedEvidenceObserver) runtimeRunID(event JSONObject) string {
	return firstText(o.optional(event, "runtime_run_id", "agentledger_run_id"), o.runID)
}

func (o *normalizedEvidenceObserver) sessionID(event JSONObject) (string, error) {
	switch o.kind {
	case "temporal":
		if value := o.optional(event, "session_id"); value != "" {
			return value, nil
		}
		workflowID, err := o.requiredResult(event, "workflow_id")
		if err != nil {
			return "", err
		}
		runID, err := o.requiredResult(event, "workflow_run_id")
		if err != nil {
			return "", err
		}
		return workflowID + ":" + runID, nil
	case "dsh":
		return o.requiredResult(event, "session_id", "execution_id", "run_id")
	case "a2a":
		return o.requiredResult(event, "context_id", "session_id")
	case "framework":
		return o.requiredResult(event, "session_id", "thread_id", "run_id")
	case "mcp":
		return o.requiredResult(event, "session_id", "connection_id")
	default:
		return "", fmt.Errorf("unsupported evidence observer: %s", o.kind)
	}
}

func (o *normalizedEvidenceObserver) metadata(event JSONObject) JSONObject {
	result := cloneJSONObject(eventObject(event["metadata"]))
	if result == nil {
		result = JSONObject{}
	}
	var keys []string
	switch o.kind {
	case "temporal":
		keys = []string{"workflow_id", "workflow_run_id", "activity_id", "attempt", "task_queue", "namespace"}
	case "dsh":
		keys = []string{"execution_id", "run_id", "session_id", "step_id", "turn_id", "attempt", "worker_id", "parent_id", "trace_id", "sandbox_id", "task_id", "receipt_id"}
	case "a2a":
		keys = []string{"context_id", "task_id", "handoff_id", "message_id", "from_agent", "to_agent"}
	case "framework":
		keys = []string{"session_id", "thread_id", "run_id", "turn_id", "node_id", "step_id", "node_name", "graph_id", "agent_id", "trace_id", "span_id", "checkpoint_id", "checkpoint_ns", "handoff_id", "from_agent", "to_agent", "attempt"}
	case "mcp":
		keys = []string{"session_id", "connection_id", "turn_id", "request_id", "server_name", "server_uri", "tool_name", "resource_uri", "prompt_name", "mime_type", "attempt"}
	}
	for _, key := range keys {
		if value, ok := event[key]; ok && value != nil {
			if o.kind == "temporal" && key == "attempt" {
				result["external_activity_attempt"] = value
			} else {
				result["external_"+key] = value
			}
		}
	}
	result["observer_schema_version"] = o.schema
	return result
}

func (o *normalizedEvidenceObserver) dict(event JSONObject, keys ...string) JSONObject {
	for _, key := range keys {
		if value, ok := event[key]; ok && value != nil {
			if result := eventObject(value); result != nil {
				return cloneJSONObject(result)
			}
			panic(fmt.Sprintf("%s evidence field %s must be an object", o.kind, key))
		}
	}
	return JSONObject{}
}

func (o *normalizedEvidenceObserver) optional(event JSONObject, keys ...string) string {
	for _, key := range keys {
		if value, ok := event[key]; ok && value != nil {
			text := fmt.Sprint(value)
			if strings.TrimSpace(text) != "" {
				return text
			}
		}
	}
	return ""
}

func (o *normalizedEvidenceObserver) required(event JSONObject, keys ...string) string {
	value, err := o.requiredResult(event, keys...)
	if err != nil {
		panic(err)
	}
	return value
}

func (o *normalizedEvidenceObserver) requiredResult(event JSONObject, keys ...string) (string, error) {
	value := o.optional(event, keys...)
	if value == "" {
		return "", fmt.Errorf("%s evidence event requires one of: %s", o.kind, strings.Join(keys, ", "))
	}
	return value, nil
}

func (o *normalizedEvidenceObserver) unsupported(eventType string) error {
	return fmt.Errorf("unsupported %s evidence event type: %s", o.kind, eventType)
}

func observerEventType(event JSONObject, kind string) (string, error) {
	value, ok := event["type"]
	if !ok {
		value = event["event_type"]
	}
	text := strings.TrimSpace(fmt.Sprint(value))
	if text == "" || text == "<nil>" {
		return "", fmt.Errorf("%s evidence event requires type", kind)
	}
	return strings.ToLower(strings.ReplaceAll(text, ".", "_")), nil
}

func eventObject(value any) JSONObject {
	switch item := value.(type) {
	case JSONObject:
		return item
	case map[string]any:
		return JSONObject(item)
	default:
		return nil
	}
}

func firstValue(event JSONObject, keys ...string) any {
	for _, key := range keys {
		if value, ok := event[key]; ok {
			return value
		}
	}
	return nil
}

func firstOptional(values []string) string {
	if len(values) == 0 {
		return ""
	}
	return values[0]
}

func numberPointer(value any) *float64 {
	if value == nil {
		return nil
	}
	number := numberValue(value)
	return &number
}

func observerNumberValue(value any) float64 {
	switch item := value.(type) {
	case float64:
		return item
	case float32:
		return float64(item)
	case int:
		return float64(item)
	case int64:
		return float64(item)
	case int32:
		return float64(item)
	case string:
		var result float64
		_, _ = fmt.Sscanf(item, "%f", &result)
		return result
	default:
		return 0
	}
}

func boolPointer(value any) *bool {
	if value == nil {
		return nil
	}
	item, ok := value.(bool)
	if !ok {
		return nil
	}
	return &item
}

func boolPointerDefault(event JSONObject, key string, fallback bool) *bool {
	if value, ok := event[key]; ok && value != nil {
		if item, ok := value.(bool); ok {
			return &item
		}
	}
	return &fallback
}

func statusForBool(retryable *bool) string {
	if retryable != nil && *retryable {
		return "retry_scheduled"
	}
	return "failed"
}

func statusFor(eventType string) string {
	if strings.Contains(eventType, "failed") {
		return "failed"
	}
	return "completed"
}

func in(value string, values ...string) bool {
	for _, item := range values {
		if value == item {
			return true
		}
	}
	return false
}
