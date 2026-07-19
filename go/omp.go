package agentledger

import (
	"fmt"
	"strings"
)

const OMPAdapterSchemaVersion = "agentledger.omp.adapter.v1"

type OmpSession struct {
	SessionID    string
	InitialState JSONObject
	Metadata     JSONObject
	RunID        string
}

type OmpTurn struct {
	SessionID  string
	TurnID     string
	AgentRole  string
	StatePatch JSONObject
	Metadata   JSONObject
}

type OmpModelCall struct {
	SessionID string
	TurnID    string
	Provider  string
	Model     string
	Request   JSONObject
	Response  JSONObject
	Usage     JSONObject
	TotalUSD  float64
	Metadata  JSONObject
}

type OmpToolProposal struct {
	SessionID    string
	TurnID       string
	ToolName     string
	Arguments    JSONObject
	Provider     string
	Model        string
	ModelCallRef string
	Confidence   *float64
	Reason       string
	Metadata     JSONObject
}

type OmpToolExecution struct {
	SessionID      string
	TurnID         string
	ToolName       string
	Arguments      JSONObject
	Result         any
	ToolCallID     string
	ToolVersion    string
	IdempotencyKey string
	LedgerStatus   string
	ErrorType      string
	ErrorMessage   string
	ExternalID     string
	CausalToken    string
	Metadata       JSONObject
}

type OmpFailure struct {
	SessionID  string
	TurnID     string
	ErrorType  string
	Message    string
	Retryable  *bool
	Status     string
	Terminal   *bool
	Category   string
	Provider   string
	Model      string
	Request    JSONObject
	Usage      JSONObject
	TotalUSD   float64
	Metadata   JSONObject
	ApprovalID string
}

type OmpStateChange struct {
	SessionID      string
	TurnID         string
	Reason         string
	Patch          JSONObject
	Label          string
	CommitStatus   string
	BeforeSnapshot any
	AfterSnapshot  any
	Diff           any
	Metadata       JSONObject
}

type ompBridgeSession struct {
	RunID         string
	SessionID     string
	InitialStepID string
}

type ompActiveTurn struct {
	RunID        string
	SessionID    string
	StepID       string
	LeaseToken   string
	Attempt      int
	StateVersion int
	AgentRole    string
}

type OmpLedgerBridge struct {
	Runtime      *Runtime
	AppName      string
	WorkerID     string
	LeaseSeconds int
	sessions     map[string]*ompBridgeSession
	activeTurns  map[string]*ompActiveTurn
}

func NewOmpLedgerBridge(runtime *Runtime, appName string) *OmpLedgerBridge {
	if runtime == nil {
		runtime = NewRuntime(nil)
	}
	if appName == "" {
		appName = "omp"
	}
	return &OmpLedgerBridge{
		Runtime:      runtime,
		AppName:      appName,
		WorkerID:     "omp:" + appName,
		LeaseSeconds: 60,
		sessions:     map[string]*ompBridgeSession{},
		activeTurns:  map[string]*ompActiveTurn{},
	}
}

func (b *OmpLedgerBridge) RecordSessionStarted(session OmpSession) (string, error) {
	if existing := b.sessions[session.SessionID]; existing != nil {
		return existing.RunID, nil
	}
	bridgeSession, err := b.ensureSession(session)
	if err != nil {
		return "", err
	}
	run, err := b.Runtime.Store.Run(bridgeSession.RunID)
	if err != nil {
		return "", err
	}
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: bridgeSession.RunID, SessionID: bridgeSession.SessionID, Type: "omp_session_started", StateVersion: run.StateVersion,
		Payload: compactJSON(JSONObject{"schema_version": OMPAdapterSchemaVersion, "adapter": "omp-ledger-bridge", "app_name": b.AppName, "external_session_id": session.SessionID, "metadata": cloneJSONObject(session.Metadata)}),
	})
	return bridgeSession.RunID, err
}

func (b *OmpLedgerBridge) RecordTurnStarted(turn OmpTurn) (string, error) {
	key := b.turnKey(turn.SessionID, turn.TurnID)
	if active := b.activeTurns[key]; active != nil {
		return active.StepID, nil
	}
	session, err := b.ensureSession(OmpSession{SessionID: turn.SessionID})
	if err != nil {
		return "", err
	}
	if session.InitialStepID == "" && b.nextRunnableStepID(session.RunID) == "" {
		if _, err := b.Runtime.Store.CreateExternalStep(session.RunID); err != nil {
			return "", err
		}
	} else {
		session.InitialStepID = ""
	}
	leaseSeconds := b.LeaseSeconds
	if leaseSeconds == 0 {
		leaseSeconds = 60
	}
	workerID := firstText(b.WorkerID, "omp:"+b.AppName)
	claim, err := b.Runtime.Store.ClaimStep(workerID, session.RunID, leaseSeconds)
	if err != nil {
		return "", err
	}
	role := firstText(turn.AgentRole, "OMPAgent")
	active := &ompActiveTurn{RunID: claim.RunID, SessionID: claim.SessionID, StepID: claim.StepID, LeaseToken: claim.LeaseToken, Attempt: claim.Attempt, StateVersion: claim.StateVersion, AgentRole: role}
	b.activeTurns[key] = active
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "omp_turn_started", AgentRole: role, StateVersion: active.StateVersion,
		Payload: compactJSON(JSONObject{"schema_version": OMPAdapterSchemaVersion, "adapter": "omp-ledger-bridge", "app_name": b.AppName, "external_session_id": turn.SessionID, "external_turn_id": turn.TurnID, "metadata": cloneJSONObject(turn.Metadata)}),
	})
	if err != nil {
		return "", err
	}
	return active.StepID, nil
}

func (b *OmpLedgerBridge) RecordTurnCompleted(turn OmpTurn) (int, error) {
	active, err := b.requireTurn(turn.SessionID, turn.TurnID)
	if err != nil {
		return 0, err
	}
	nextVersion, err := b.Runtime.Store.CommitStatePatch(active.RunID, active.StepID, active.LeaseToken, active.StateVersion, cloneJSONObject(turn.StatePatch), fmt.Sprintf("omp:%s:%d", turn.TurnID, active.Attempt))
	if err != nil {
		return 0, err
	}
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "omp_turn_completed", AgentRole: active.AgentRole, StateVersion: nextVersion,
		Payload: compactJSON(JSONObject{"schema_version": OMPAdapterSchemaVersion, "adapter": "omp-ledger-bridge", "app_name": b.AppName, "external_session_id": turn.SessionID, "external_turn_id": turn.TurnID, "metadata": cloneJSONObject(turn.Metadata)}),
	})
	delete(b.activeTurns, b.turnKey(turn.SessionID, turn.TurnID))
	return nextVersion, err
}

func (b *OmpLedgerBridge) RecordModelCall(record OmpModelCall) error {
	ctx, err := b.contextFor(record.SessionID, record.TurnID)
	if err != nil {
		return err
	}
	return ctx.RecordModelCallEvidence(ModelCallEvidence{Provider: record.Provider, Model: record.Model, Request: cloneJSONObject(record.Request), Response: cloneJSONObject(record.Response), Usage: cloneJSONObject(record.Usage), TotalUSD: record.TotalUSD, Metadata: cloneJSONObject(record.Metadata)})
}

func (b *OmpLedgerBridge) RecordToolProposal(proposal OmpToolProposal) error {
	ctx, err := b.contextFor(proposal.SessionID, proposal.TurnID)
	if err != nil {
		return err
	}
	return ctx.RecordToolCallProposal(ToolCallProposal{ToolName: proposal.ToolName, Arguments: cloneJSONObject(proposal.Arguments), Provider: proposal.Provider, Model: proposal.Model, ModelCallRef: proposal.ModelCallRef, Confidence: proposal.Confidence, Reason: proposal.Reason, Metadata: cloneJSONObject(proposal.Metadata)})
}

func (b *OmpLedgerBridge) RecordToolExecution(execution OmpToolExecution) (JSONObject, error) {
	active, err := b.requireTurn(execution.SessionID, execution.TurnID)
	if err != nil {
		return nil, err
	}
	toolCallID := firstText(execution.ToolCallID, newID("toolcall"))
	toolVersion := firstText(execution.ToolVersion, "external")
	request := compactJSON(JSONObject{"schema_version": OMPAdapterSchemaVersion, "tool": execution.ToolName, "args": cloneJSONObject(execution.Arguments), "tool_call_id": toolCallID, "metadata": cloneJSONObject(execution.Metadata)})
	requestHash, err := sha256JSON(request)
	if err != nil {
		return nil, err
	}
	requestRef := mustJSON(request)
	idempotencyKey := firstText(execution.IdempotencyKey, fmt.Sprintf("omp:%s:%s:%s:%s", execution.SessionID, execution.TurnID, execution.ToolName, toolCallID))
	causalToken := firstText(execution.CausalToken, fmt.Sprintf("omp:%s:%s:%s", execution.SessionID, execution.TurnID, toolCallID))
	if _, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "tool_call_requested", AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: requestHash, PayloadRef: requestRef, Payload: request}); err != nil {
		return nil, err
	}
	existing, err := b.Runtime.Store.ReserveLedger(LedgerReservation{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, ToolName: execution.ToolName, ToolVersion: toolVersion, ToolCallID: toolCallID, IdempotencyKey: idempotencyKey, CausalToken: causalToken, RequestHash: requestHash, RequestRef: requestRef})
	if err != nil {
		return nil, err
	}
	if existing != nil {
		if existing.Status == "SUCCEEDED" {
			_, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "tool_call_completed", AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: existing.ResponseHash, PayloadRef: existing.ResponseRef, Payload: JSONObject{"tool": execution.ToolName, "replayed_from_ledger": true, "idempotency_key": idempotencyKey, "tool_call_id": toolCallID}})
			return JSONObject{"ledger_status": "SUCCEEDED", "replayed_from_ledger": true, "idempotency_key": idempotencyKey, "tool_call_id": toolCallID}, err
		}
		if existing.Status == "PENDING_VERIFICATION" {
			return nil, fmt.Errorf("tool side effect pending verification")
		}
		if existing.Status == "RESERVED" || existing.Status == "RUNNING" {
			return nil, fmt.Errorf("tool side effect already in progress")
		}
	}
	ledgerStatus, err := normalizeOmpLedgerStatus(execution.LedgerStatus, firstText(execution.ErrorMessage, execution.ErrorType))
	if err != nil {
		return nil, err
	}
	responseHash, responseRef := "", ""
	if execution.Result != nil {
		hash, err := sha256JSON(execution.Result)
		if err != nil {
			return nil, err
		}
		responseHash = "sha256:" + hash
		responseRef = mustJSON(execution.Result)
	}
	if err := b.Runtime.Store.UpdateLedger(LedgerUpdate{IdempotencyKey: idempotencyKey, Status: ledgerStatus, ExternalID: firstText(execution.ExternalID, externalIDFromResult(execution.Result)), ResponseHash: responseHash, ResponseRef: responseRef, ErrorType: execution.ErrorType, Response: execution.Result}); err != nil {
		return nil, err
	}
	eventType := "tool_call_failed"
	if ledgerStatus == "SUCCEEDED" || ledgerStatus == "COMPENSATED" {
		eventType = "tool_call_completed"
	}
	if _, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: eventType, AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: responseHash, PayloadRef: responseRef, Payload: compactJSON(JSONObject{"tool": execution.ToolName, "tool_call_id": toolCallID, "idempotency_key": idempotencyKey, "ledger_status": ledgerStatus, "error": execution.ErrorMessage, "error_type": execution.ErrorType})}); err != nil {
		return nil, err
	}
	if ledgerStatus != "RESERVED" && ledgerStatus != "RUNNING" {
		if _, err := b.Runtime.Store.RecordCost(CostRecordInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Category: "tool", Name: execution.ToolName, Amount: 1, Unit: "call", Metadata: JSONObject{"external_runtime": "omp", "ledger_status": ledgerStatus}}); err != nil {
			return nil, err
		}
	}
	return JSONObject{"ledger_status": ledgerStatus, "idempotency_key": idempotencyKey, "tool_call_id": toolCallID}, nil
}

func (b *OmpLedgerBridge) RecordFailure(failure OmpFailure) error {
	active, err := b.requireTurn(failure.SessionID, failure.TurnID)
	if err != nil {
		return err
	}
	if failure.Category == "model" {
		ctx, err := b.contextFor(failure.SessionID, failure.TurnID)
		if err != nil {
			return err
		}
		if err := ctx.RecordModelFailure(ModelFailureEvidence{Provider: firstText(failure.Provider, "custom"), Model: firstText(failure.Model, "unknown"), ErrorType: failure.ErrorType, Message: failure.Message, Retryable: failure.Retryable, Request: cloneJSONObject(failure.Request), Usage: cloneJSONObject(failure.Usage), TotalUSD: failure.TotalUSD, Metadata: cloneJSONObject(failure.Metadata)}); err != nil {
			return err
		}
	}
	if failure.Terminal != nil && !*failure.Terminal {
		return nil
	}
	status := strings.ToLower(firstText(failure.Status, "failed"))
	if status == "waiting_human" || status == "approval_required" {
		err = b.Runtime.Store.MarkWaitingHuman(active.RunID, active.StepID, failure.Message, failure.ApprovalID)
	} else if status == "retry_scheduled" || status == "retry" || (failure.Retryable != nil && *failure.Retryable) {
		err = b.Runtime.Store.MarkRetry(active.RunID, active.StepID, failure.ErrorType, failure.Message)
	} else {
		err = b.Runtime.Store.MarkFailed(active.RunID, active.StepID, failure.ErrorType, failure.Message)
	}
	delete(b.activeTurns, b.turnKey(failure.SessionID, failure.TurnID))
	return err
}

func (b *OmpLedgerBridge) RecordStateChange(change OmpStateChange) (int, error) {
	session, err := b.ensureSession(OmpSession{SessionID: change.SessionID})
	if err != nil {
		return 0, err
	}
	active := b.activeTurns[b.turnKey(change.SessionID, change.TurnID)]
	artifactRefs := JSONObject{}
	label := firstText(change.Label, "state")
	if change.BeforeSnapshot != nil {
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), "omp-"+label+"-before", change.BeforeSnapshot, JSONObject{"schema_version": OMPAdapterSchemaVersion, "kind": "before_snapshot", "external_session_id": change.SessionID}, active)
		if err != nil {
			return 0, err
		}
		artifactRefs["before_artifact_id"] = id
	}
	if change.AfterSnapshot != nil {
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), "omp-"+label+"-after", change.AfterSnapshot, JSONObject{"schema_version": OMPAdapterSchemaVersion, "kind": "after_snapshot", "external_session_id": change.SessionID}, active)
		if err != nil {
			return 0, err
		}
		artifactRefs["after_artifact_id"] = id
	}
	if change.Diff != nil {
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), "omp-"+label+"-diff", change.Diff, JSONObject{"schema_version": OMPAdapterSchemaVersion, "kind": "diff", "external_session_id": change.SessionID}, active)
		if err != nil {
			return 0, err
		}
		artifactRefs["diff_artifact_id"] = id
	}
	version := b.runStateVersion(session.RunID)
	if len(change.Patch) > 0 && (change.CommitStatus == "" || strings.EqualFold(change.CommitStatus, "committed") || strings.EqualFold(change.CommitStatus, "applied")) {
		version, err = b.Runtime.Store.ApplySystemStatePatch(session.RunID, cloneJSONObject(change.Patch), change.Reason)
		if err != nil {
			return 0, err
		}
		if active != nil {
			active.StateVersion = version
		}
	}
	agentRole := ""
	stepID := ""
	if active != nil {
		agentRole = active.AgentRole
		stepID = active.StepID
	}
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: session.RunID, SessionID: session.SessionID, StepID: stepID, Type: "omp_state_change_recorded", AgentRole: agentRole, StateVersion: version,
		Payload: compactJSON(JSONObject{"schema_version": OMPAdapterSchemaVersion, "adapter": "omp-ledger-bridge", "app_name": b.AppName, "external_session_id": change.SessionID, "external_turn_id": change.TurnID, "reason": change.Reason, "commit_status": firstText(change.CommitStatus, "committed"), "patch": cloneJSONObject(change.Patch), "artifacts": artifactRefs, "metadata": cloneJSONObject(change.Metadata)}),
	})
	return version, err
}

func (b *OmpLedgerBridge) ensureSession(session OmpSession) (*ompBridgeSession, error) {
	if existing := b.sessions[session.SessionID]; existing != nil {
		return existing, nil
	}
	var bridgeSession *ompBridgeSession
	if session.RunID != "" {
		run, err := b.Runtime.Store.Run(session.RunID)
		if err != nil {
			return nil, err
		}
		bridgeSession = &ompBridgeSession{RunID: session.RunID, SessionID: run.SessionID}
		for _, step := range b.Runtime.Store.Steps(session.RunID) {
			if step.Status == "pending" || step.Status == "retry_scheduled" {
				bridgeSession.InitialStepID = step.StepID
				break
			}
		}
	} else {
		runID, stepID, err := b.Runtime.CreateRun(cloneJSONObject(session.InitialState))
		if err != nil {
			return nil, err
		}
		run, err := b.Runtime.Store.Run(runID)
		if err != nil {
			return nil, err
		}
		bridgeSession = &ompBridgeSession{RunID: runID, SessionID: run.SessionID, InitialStepID: stepID}
	}
	b.sessions[session.SessionID] = bridgeSession
	return bridgeSession, nil
}

func (b *OmpLedgerBridge) requireTurn(sessionID, turnID string) (*ompActiveTurn, error) {
	active := b.activeTurns[b.turnKey(sessionID, turnID)]
	if active == nil {
		return nil, fmt.Errorf("OMP turn not active: %s/%s", sessionID, turnID)
	}
	return active, nil
}

func (b *OmpLedgerBridge) contextFor(sessionID, turnID string) (*AgentContext, error) {
	active, err := b.requireTurn(sessionID, turnID)
	if err != nil {
		return nil, err
	}
	return &AgentContext{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, AgentRole: active.AgentRole, LeaseToken: active.LeaseToken, Attempt: active.Attempt, StateVersion: active.StateVersion, Store: b.Runtime.Store, Gateway: b.Runtime.Gateway, Budget: b.Runtime.Budget, PendingPatch: JSONObject{}}, nil
}

func (b *OmpLedgerBridge) storeArtifact(runID, stepID, name string, content any, metadata JSONObject, active *ompActiveTurn) (string, error) {
	artifact, err := b.Runtime.Store.CreateArtifact(runID, stepID, name, content, metadata)
	if err != nil {
		return "", err
	}
	sessionID := ""
	agentRole := ""
	stateVersion := b.runStateVersion(runID)
	if active != nil {
		sessionID = active.SessionID
		agentRole = active.AgentRole
		stateVersion = active.StateVersion
	} else if run, err := b.Runtime.Store.Run(runID); err == nil {
		sessionID = run.SessionID
	}
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{RunID: runID, SessionID: sessionID, StepID: stepID, Type: "artifact_created", AgentRole: agentRole, StateVersion: stateVersion, PayloadHash: artifact.BlobHash, PayloadRef: artifact.BlobRef, Payload: JSONObject{"artifact_id": artifact.ArtifactID, "name": name}})
	return artifact.ArtifactID, err
}

func (b *OmpLedgerBridge) runStateVersion(runID string) int {
	run, err := b.Runtime.Store.Run(runID)
	if err != nil {
		return 0
	}
	return run.StateVersion
}

func (b *OmpLedgerBridge) nextRunnableStepID(runID string) string {
	for _, step := range b.Runtime.Store.Steps(runID) {
		if step.Status == "pending" || step.Status == "retry_scheduled" {
			return step.StepID
		}
	}
	return ""
}

func (b *OmpLedgerBridge) turnKey(sessionID, turnID string) string {
	return sessionID + "\x1f" + turnID
}

func normalizeOmpLedgerStatus(value, errorMessage string) (string, error) {
	if value == "" {
		if errorMessage == "" {
			return "SUCCEEDED", nil
		}
		return "PENDING_VERIFICATION", nil
	}
	aliases := map[string]string{
		"SUCCESS":              "SUCCEEDED",
		"SUCCEEDED":            "SUCCEEDED",
		"COMPLETED":            "SUCCEEDED",
		"OK":                   "SUCCEEDED",
		"FAILED":               "PENDING_VERIFICATION",
		"FAILED_NO_EFFECT":     "FAILED_NO_EFFECT",
		"NO_EFFECT":            "FAILED_NO_EFFECT",
		"PENDING_VERIFICATION": "PENDING_VERIFICATION",
		"UNKNOWN":              "PENDING_VERIFICATION",
		"COMPENSATED":          "COMPENSATED",
		"RUNNING":              "RUNNING",
		"RESERVED":             "RESERVED",
	}
	status := strings.ToUpper(strings.TrimSpace(value))
	if mapped, ok := aliases[status]; ok {
		status = mapped
	}
	switch status {
	case "SUCCEEDED", "COMPENSATED", "FAILED_NO_EFFECT", "PENDING_VERIFICATION", "RESERVED", "RUNNING":
		return status, nil
	default:
		return "", fmt.Errorf("unsupported Tool Ledger status: %s", value)
	}
}

func externalIDFromResult(result any) string {
	if item, ok := result.(map[string]any); ok {
		if value, ok := item["external_id"]; ok && value != nil {
			return fmt.Sprint(value)
		}
	}
	if item, ok := result.(JSONObject); ok {
		if value, ok := item["external_id"]; ok && value != nil {
			return fmt.Sprint(value)
		}
	}
	return ""
}

func stepIDOrEmpty(active *ompActiveTurn) string {
	if active == nil {
		return ""
	}
	return active.StepID
}
