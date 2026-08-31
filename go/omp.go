package agentledger

import (
	"fmt"
	"strings"
)

const OMPAdapterSchemaVersion = "agentledger.omp.adapter.v1"
const ExecutionEvidenceSchemaVersion = "agentledger.execution.evidence.v1"

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

type ExecutionSession = OmpSession
type ExecutionTurn = OmpTurn
type ExecutionModelCall = OmpModelCall
type ExecutionToolProposal = OmpToolProposal
type ExecutionToolExecution = OmpToolExecution
type ExecutionFailure = OmpFailure
type ExecutionStateChange = OmpStateChange

type ExecutionArtifact struct {
	SessionID      string
	TurnID         string
	Name           string
	Kind           string
	URI            string
	ContentRef     string
	ExternalID     string
	Metadata       JSONObject
	Lineage        JSONObject
	DerivedOutputs JSONObject
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
	Runtime          *Runtime
	AppName          string
	WorkerID         string
	LeaseSeconds     int
	sessions         map[string]*ompBridgeSession
	activeTurns      map[string]*ompActiveTurn
	schemaVersion    string
	adapterName      string
	source           string
	eventPrefix      string
	checkpointPrefix string
	defaultRole      string
}

func NewOmpLedgerBridge(runtime *Runtime, appName string) *OmpLedgerBridge {
	return newLedgerBridge(runtime, appName, "omp", OMPAdapterSchemaVersion, "omp-ledger-bridge", "omp", "omp", "OMPAgent")
}

type ExecutionEvidenceBridge struct {
	*OmpLedgerBridge
}

func NewExecutionEvidenceBridge(runtime *Runtime, appName, source string) *ExecutionEvidenceBridge {
	if source == "" {
		source = "external"
	}
	return &ExecutionEvidenceBridge{
		OmpLedgerBridge: newLedgerBridge(runtime, appName, source, ExecutionEvidenceSchemaVersion, "execution-evidence-bridge", "execution", "execution", "Agent"),
	}
}

func newLedgerBridge(runtime *Runtime, appName, source, schemaVersion, adapterName, eventPrefix, checkpointPrefix, defaultRole string) *OmpLedgerBridge {
	if runtime == nil {
		runtime = NewRuntime(nil)
	}
	if appName == "" {
		appName = source
	}
	return &OmpLedgerBridge{
		Runtime:          runtime,
		AppName:          appName,
		WorkerID:         source + ":" + appName,
		LeaseSeconds:     60,
		sessions:         map[string]*ompBridgeSession{},
		activeTurns:      map[string]*ompActiveTurn{},
		schemaVersion:    schemaVersion,
		adapterName:      adapterName,
		source:           source,
		eventPrefix:      eventPrefix,
		checkpointPrefix: checkpointPrefix,
		defaultRole:      defaultRole,
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
		RunID: bridgeSession.RunID, SessionID: bridgeSession.SessionID, Type: b.eventType("session_started"), StateVersion: run.StateVersion,
		Payload: b.decoratePayload(compactJSON(JSONObject{"external_session_id": session.SessionID, "metadata": cloneJSONObject(session.Metadata)})),
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
	workerID := firstText(b.WorkerID, b.source+":"+b.AppName)
	claim, err := b.Runtime.Store.ClaimStep(workerID, session.RunID, leaseSeconds)
	if err != nil {
		return "", err
	}
	role := firstText(turn.AgentRole, b.defaultRole)
	active := &ompActiveTurn{RunID: claim.RunID, SessionID: claim.SessionID, StepID: claim.StepID, LeaseToken: claim.LeaseToken, Attempt: claim.Attempt, StateVersion: claim.StateVersion, AgentRole: role}
	b.activeTurns[key] = active
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: b.eventType("turn_started"), AgentRole: role, StateVersion: active.StateVersion,
		Payload: b.decoratePayload(compactJSON(JSONObject{"external_session_id": turn.SessionID, "external_turn_id": turn.TurnID, "metadata": cloneJSONObject(turn.Metadata)})),
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
	nextVersion, err := b.Runtime.Store.CommitStatePatch(active.RunID, active.StepID, active.LeaseToken, active.StateVersion, cloneJSONObject(turn.StatePatch), fmt.Sprintf("%s:%s:%d", b.checkpointPrefix, turn.TurnID, active.Attempt))
	if err != nil {
		return 0, err
	}
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: b.eventType("turn_completed"), AgentRole: active.AgentRole, StateVersion: nextVersion,
		Payload: b.decoratePayload(compactJSON(JSONObject{"external_session_id": turn.SessionID, "external_turn_id": turn.TurnID, "metadata": cloneJSONObject(turn.Metadata)})),
	})
	delete(b.activeTurns, b.turnKey(turn.SessionID, turn.TurnID))
	return nextVersion, err
}

func (b *OmpLedgerBridge) RecordModelCall(record OmpModelCall) error {
	ctx, err := b.contextFor(record.SessionID, record.TurnID)
	if err != nil {
		return err
	}
	return ctx.RecordModelCallEvidence(ModelCallEvidence{Provider: record.Provider, Model: record.Model, Request: cloneJSONObject(record.Request), Response: cloneJSONObject(record.Response), Usage: cloneJSONObject(record.Usage), TotalUSD: record.TotalUSD, Metadata: b.bridgeMetadata(record.Metadata, record.SessionID, record.TurnID)})
}

func (b *OmpLedgerBridge) RecordToolProposal(proposal OmpToolProposal) error {
	ctx, err := b.contextFor(proposal.SessionID, proposal.TurnID)
	if err != nil {
		return err
	}
	return ctx.RecordToolCallProposal(ToolCallProposal{ToolName: proposal.ToolName, Arguments: cloneJSONObject(proposal.Arguments), Provider: proposal.Provider, Model: proposal.Model, ModelCallRef: proposal.ModelCallRef, Confidence: proposal.Confidence, Reason: proposal.Reason, Metadata: b.bridgeMetadata(proposal.Metadata, proposal.SessionID, proposal.TurnID)})
}

func (b *OmpLedgerBridge) RecordToolExecution(execution OmpToolExecution) (JSONObject, error) {
	active, err := b.requireTurn(execution.SessionID, execution.TurnID)
	if err != nil {
		return nil, err
	}
	toolCallID := firstText(execution.ToolCallID, newID("toolcall"))
	toolVersion := firstText(execution.ToolVersion, "external")
	request := compactJSON(JSONObject{"schema_version": b.schemaVersion, "source": b.source, "tool": execution.ToolName, "args": cloneJSONObject(execution.Arguments), "tool_call_id": toolCallID, "external_session_id": execution.SessionID, "external_turn_id": execution.TurnID, "metadata": b.bridgeMetadata(execution.Metadata, execution.SessionID, execution.TurnID)})
	requestHash, err := sha256JSON(request)
	if err != nil {
		return nil, err
	}
	requestRef := mustJSON(request)
	idempotencyKey := firstText(execution.IdempotencyKey, fmt.Sprintf("%s:%s:%s:%s:%s", b.source, execution.SessionID, execution.TurnID, execution.ToolName, toolCallID))
	causalToken := firstText(execution.CausalToken, fmt.Sprintf("%s:%s:%s:%s", b.source, execution.SessionID, execution.TurnID, toolCallID))
	if _, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "tool_call_requested", AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: requestHash, PayloadRef: requestRef, Payload: request}); err != nil {
		return nil, err
	}
	existing, err := b.Runtime.Store.ReserveLedger(LedgerReservation{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, ToolName: execution.ToolName, ToolVersion: toolVersion, ToolCallID: toolCallID, IdempotencyKey: idempotencyKey, CausalToken: causalToken, RequestHash: requestHash, RequestRef: requestRef})
	if err != nil {
		return nil, err
	}
	if existing != nil {
		if existing.Status == "SUCCEEDED" {
			_, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: "tool_call_completed", AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: existing.ResponseHash, PayloadRef: existing.ResponseRef, Payload: b.decoratePayload(JSONObject{"tool": execution.ToolName, "external_session_id": execution.SessionID, "external_turn_id": execution.TurnID, "replayed_from_ledger": true, "idempotency_key": idempotencyKey, "tool_call_id": toolCallID, "response_hash": existing.ResponseHash, "response_ref": existing.ResponseRef})})
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
	if _, err := b.Runtime.Store.AppendEvent(AppendEventInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Type: eventType, AgentRole: active.AgentRole, StateVersion: active.StateVersion, CausalToken: causalToken, PayloadHash: responseHash, PayloadRef: responseRef, Payload: b.decoratePayload(compactJSON(JSONObject{"external_session_id": execution.SessionID, "external_turn_id": execution.TurnID, "tool": execution.ToolName, "tool_call_id": toolCallID, "idempotency_key": idempotencyKey, "ledger_status": ledgerStatus, "error": execution.ErrorMessage, "error_type": execution.ErrorType, "response_hash": responseHash, "response_ref": responseRef}))}); err != nil {
		return nil, err
	}
	if ledgerStatus != "RESERVED" && ledgerStatus != "RUNNING" {
		if _, err := b.Runtime.Store.RecordCost(CostRecordInput{RunID: active.RunID, SessionID: active.SessionID, StepID: active.StepID, Category: "tool", Name: execution.ToolName, Amount: 1, Unit: "call", Metadata: JSONObject{"external_runtime": b.source, "ledger_status": ledgerStatus}}); err != nil {
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
		if err := ctx.RecordModelFailure(ModelFailureEvidence{Provider: firstText(failure.Provider, "custom"), Model: firstText(failure.Model, "unknown"), ErrorType: failure.ErrorType, Message: failure.Message, Retryable: failure.Retryable, Request: cloneJSONObject(failure.Request), Usage: cloneJSONObject(failure.Usage), TotalUSD: failure.TotalUSD, Metadata: b.bridgeMetadata(failure.Metadata, failure.SessionID, failure.TurnID)}); err != nil {
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
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), b.source+"-"+label+"-before", change.BeforeSnapshot, JSONObject{"schema_version": b.schemaVersion, "source": b.source, "kind": "before_snapshot", "external_session_id": change.SessionID}, active)
		if err != nil {
			return 0, err
		}
		artifactRefs["before_artifact_id"] = id
	}
	if change.AfterSnapshot != nil {
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), b.source+"-"+label+"-after", change.AfterSnapshot, JSONObject{"schema_version": b.schemaVersion, "source": b.source, "kind": "after_snapshot", "external_session_id": change.SessionID}, active)
		if err != nil {
			return 0, err
		}
		artifactRefs["after_artifact_id"] = id
	}
	if change.Diff != nil {
		id, err := b.storeArtifact(session.RunID, stepIDOrEmpty(active), b.source+"-"+label+"-diff", change.Diff, JSONObject{"schema_version": b.schemaVersion, "source": b.source, "kind": "diff", "external_session_id": change.SessionID}, active)
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
		RunID: session.RunID, SessionID: session.SessionID, StepID: stepID, Type: b.eventType("state_change_recorded"), AgentRole: agentRole, StateVersion: version,
		Payload: b.decoratePayload(compactJSON(JSONObject{"external_session_id": change.SessionID, "external_turn_id": change.TurnID, "reason": change.Reason, "commit_status": firstText(change.CommitStatus, "committed"), "patch": cloneJSONObject(change.Patch), "artifacts": artifactRefs, "metadata": cloneJSONObject(change.Metadata)})),
	})
	return version, err
}

func (b *OmpLedgerBridge) RecordExecutionEvent(sessionID, eventName string, payload JSONObject, turnID, agentRole, causalToken string) (Event, error) {
	session, err := b.ensureSession(OmpSession{SessionID: sessionID})
	if err != nil {
		return Event{}, err
	}
	active := (*ompActiveTurn)(nil)
	if turnID != "" {
		active = b.activeTurns[b.turnKey(sessionID, turnID)]
	}
	if payload == nil {
		payload = JSONObject{}
	}
	payload["event_name"] = eventName
	payload = b.decoratePayload(payload)
	role := agentRole
	stateVersion := b.runStateVersion(session.RunID)
	stepID := ""
	if active != nil {
		role = active.AgentRole
		stateVersion = active.StateVersion
		stepID = active.StepID
	}
	return b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: session.RunID, SessionID: session.SessionID, StepID: stepID,
		Type: b.eventType(eventName), AgentRole: role, StateVersion: stateVersion,
		CausalToken: causalToken, Payload: payload,
	})
}

func (b *OmpLedgerBridge) RecordArtifact(artifact ExecutionArtifact) (string, error) {
	if strings.TrimSpace(artifact.Name) == "" {
		return "", fmt.Errorf("%s artifact name must not be empty", b.source)
	}
	if artifact.URI == "" && artifact.ContentRef == "" && artifact.ExternalID == "" && len(artifact.DerivedOutputs) == 0 {
		return "", fmt.Errorf("%s artifact requires a uri, content_ref, external_id, or derived_outputs", b.source)
	}
	session, err := b.ensureSession(OmpSession{SessionID: artifact.SessionID})
	if err != nil {
		return "", err
	}
	active := (*ompActiveTurn)(nil)
	if artifact.TurnID != "" {
		active = b.activeTurns[b.turnKey(artifact.SessionID, artifact.TurnID)]
	}
	kind := firstText(artifact.Kind, "artifact")
	manifest := compactJSON(JSONObject{
		"schema_version":  b.schemaVersion,
		"source":          b.source,
		"kind":            kind,
		"uri":             artifact.URI,
		"content_ref":     artifact.ContentRef,
		"external_id":     artifact.ExternalID,
		"metadata":        cloneJSONObject(artifact.Metadata),
		"lineage":         cloneJSONObject(artifact.Lineage),
		"derived_outputs": cloneJSONObject(artifact.DerivedOutputs),
	})
	metadata := cloneJSONObject(artifact.Metadata)
	if metadata == nil {
		metadata = JSONObject{}
	}
	metadata["schema_version"] = b.schemaVersion
	metadata["source"] = b.source
	metadata["external_session_id"] = artifact.SessionID
	metadata["kind"] = kind
	if artifact.URI != "" {
		metadata["uri"] = artifact.URI
	}
	if artifact.ContentRef != "" {
		metadata["content_ref"] = artifact.ContentRef
	}
	if artifact.ExternalID != "" {
		metadata["external_id"] = artifact.ExternalID
	}
	if len(artifact.Lineage) > 0 {
		metadata["lineage"] = cloneJSONObject(artifact.Lineage)
	}
	if len(artifact.DerivedOutputs) > 0 {
		metadata["derived_outputs"] = cloneJSONObject(artifact.DerivedOutputs)
	}
	if mediaKinds[kind] {
		mediaMetadata := cloneJSONObject(artifact.Metadata)
		if mediaMetadata == nil {
			mediaMetadata = JSONObject{}
		}
		mediaMetadata["schema_version"] = MediaSchemaVersion
		mediaMetadata["kind"] = kind
		manifest = compactJSON(JSONObject{
			"schema_version":  MediaSchemaVersion,
			"kind":            kind,
			"uri":             artifact.URI,
			"content_ref":     artifact.ContentRef,
			"metadata":        mediaMetadata,
			"lineage":         cloneJSONObject(artifact.Lineage),
			"derived_outputs": cloneJSONObject(artifact.DerivedOutputs),
		})
		metadata["agentledger_media"] = compactJSON(JSONObject{
			"schema_version":  MediaSchemaVersion,
			"kind":            kind,
			"uri":             artifact.URI,
			"content_ref":     artifact.ContentRef,
			"metadata":        mediaMetadata,
			"lineage":         cloneJSONObject(artifact.Lineage),
			"derived_outputs": cloneJSONObject(artifact.DerivedOutputs),
		})
	}
	stored, err := b.Runtime.Store.CreateArtifact(session.RunID, stepIDOrEmpty(active), artifact.Name, manifest, metadata)
	if err != nil {
		return "", err
	}
	stateVersion := b.runStateVersion(session.RunID)
	role := ""
	if active != nil {
		stateVersion = active.StateVersion
		role = active.AgentRole
	}
	if _, err := b.Runtime.Store.AppendEvent(AppendEventInput{
		RunID: session.RunID, SessionID: session.SessionID, StepID: stepIDOrEmpty(active),
		Type: "artifact_created", AgentRole: role, StateVersion: stateVersion,
		PayloadHash: stored.BlobHash, PayloadRef: stored.BlobRef,
		Payload: b.decoratePayload(JSONObject{"artifact_id": stored.ArtifactID, "name": artifact.Name, "kind": kind, "external_session_id": artifact.SessionID, "external_turn_id": artifact.TurnID, "external_id": artifact.ExternalID}),
	}); err != nil {
		return "", err
	}
	return stored.ArtifactID, nil
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
		return nil, fmt.Errorf("%s turn not active: %s/%s", b.source, sessionID, turnID)
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
	_, err = b.Runtime.Store.AppendEvent(AppendEventInput{RunID: runID, SessionID: sessionID, StepID: stepID, Type: "artifact_created", AgentRole: agentRole, StateVersion: stateVersion, PayloadHash: artifact.BlobHash, PayloadRef: artifact.BlobRef, Payload: b.decoratePayload(JSONObject{"artifact_id": artifact.ArtifactID, "name": name})})
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

func (b *OmpLedgerBridge) eventType(suffix string) string {
	return b.eventPrefix + "_" + suffix
}

func (b *OmpLedgerBridge) decoratePayload(payload JSONObject) JSONObject {
	if payload == nil {
		payload = JSONObject{}
	}
	payload["schema_version"] = b.schemaVersion
	payload["adapter"] = b.adapterName
	payload["source"] = b.source
	payload["app_name"] = b.AppName
	return compactJSON(payload)
}

func (b *OmpLedgerBridge) bridgeMetadata(metadata JSONObject, sessionID, turnID string) JSONObject {
	result := cloneJSONObject(metadata)
	if result == nil {
		result = JSONObject{}
	}
	result["schema_version"] = b.schemaVersion
	result["adapter"] = b.adapterName
	result["source"] = b.source
	result["external_session_id"] = sessionID
	if turnID != "" {
		result["external_turn_id"] = turnID
	}
	return result
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
