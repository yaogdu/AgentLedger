package agentledger

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
)

var ErrNoRunnableStep = errors.New("agentledger: no runnable step")

type storeData struct {
	Runs             map[string]Run             `json:"runs"`
	Steps            map[string]Step            `json:"steps"`
	Events           map[string][]Event         `json:"events"`
	ToolLedger       map[string]ToolLedgerEntry `json:"tool_ledger"`
	ApprovalRequests map[string]ApprovalRequest `json:"approval_requests"`
	CostRecords      map[string][]CostRecord    `json:"cost_records"`
	Artifacts        map[string][]Artifact      `json:"artifacts"`
}

type JSONStore struct {
	mu   sync.Mutex
	path string
	data storeData
}

func NewMemoryStore() *JSONStore {
	return &JSONStore{data: emptyStoreData()}
}

func NewJSONStore(path string) (*JSONStore, error) {
	store := &JSONStore{path: path, data: emptyStoreData()}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, err
	}
	content, err := os.ReadFile(path)
	if err == nil && len(content) > 0 {
		if err := json.Unmarshal(content, &store.data); err != nil {
			return nil, err
		}
	} else if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	store.ensureMapsLocked()
	return store, nil
}

func emptyStoreData() storeData {
	return storeData{
		Runs:             map[string]Run{},
		Steps:            map[string]Step{},
		Events:           map[string][]Event{},
		ToolLedger:       map[string]ToolLedgerEntry{},
		ApprovalRequests: map[string]ApprovalRequest{},
		CostRecords:      map[string][]CostRecord{},
		Artifacts:        map[string][]Artifact{},
	}
}

func (s *JSONStore) ensureMapsLocked() {
	if s.data.Runs == nil {
		s.data.Runs = map[string]Run{}
	}
	if s.data.Steps == nil {
		s.data.Steps = map[string]Step{}
	}
	if s.data.Events == nil {
		s.data.Events = map[string][]Event{}
	}
	if s.data.ToolLedger == nil {
		s.data.ToolLedger = map[string]ToolLedgerEntry{}
	}
	if s.data.ApprovalRequests == nil {
		s.data.ApprovalRequests = map[string]ApprovalRequest{}
	}
	if s.data.CostRecords == nil {
		s.data.CostRecords = map[string][]CostRecord{}
	}
	if s.data.Artifacts == nil {
		s.data.Artifacts = map[string][]Artifact{}
	}
}

func (s *JSONStore) flushLocked() error {
	if s.path == "" {
		return nil
	}
	data, err := json.MarshalIndent(s.data, "", "  ")
	if err != nil {
		return err
	}
	tmp := s.path + ".tmp"
	file, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	if _, err := file.Write(data); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, s.path)
}

func (s *JSONStore) CreateRun(sessionID string, initialState JSONObject) (string, string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ensureMapsLocked()
	if sessionID == "" {
		sessionID = newID("sess")
	}
	runID := newID("run")
	stepID := newID("step")
	ts := nowSeconds()
	s.data.Runs[runID] = Run{RunID: runID, SessionID: sessionID, Status: "pending", State: cloneJSONObject(initialState), StateVersion: 0, CreatedAt: ts, UpdatedAt: ts}
	s.data.Steps[stepID] = Step{StepID: stepID, RunID: runID, SessionID: sessionID, Status: "pending", Attempt: 0, StateVersion: 0, CreatedAt: ts, UpdatedAt: ts}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: sessionID, Type: "run_created", Payload: JSONObject{"initial_state": cloneJSONObject(initialState)}}); err != nil {
		return "", "", err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: sessionID, StepID: stepID, Type: "step_created", Payload: JSONObject{"step_id": stepID}}); err != nil {
		return "", "", err
	}
	return runID, stepID, s.flushLocked()
}

func (s *JSONStore) ClaimStep(workerID, runID string, leaseSeconds int) (*StepClaim, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var candidate *Step
	for _, step := range s.data.Steps {
		if runID != "" && step.RunID != runID {
			continue
		}
		if step.Status != "pending" && step.Status != "retry_scheduled" {
			continue
		}
		copy := step
		if candidate == nil || copy.CreatedAt < candidate.CreatedAt || (copy.CreatedAt == candidate.CreatedAt && copy.StepID < candidate.StepID) {
			candidate = &copy
		}
	}
	if candidate == nil {
		return nil, ErrNoRunnableStep
	}
	now := nowSeconds()
	step := *candidate
	step.Status = "running"
	step.Owner = workerID
	step.LeaseToken = newID("lease")
	step.LeaseUntil = now + float64(leaseSeconds)
	step.Attempt++
	step.UpdatedAt = now
	s.data.Steps[step.StepID] = step
	run := s.data.Runs[step.RunID]
	run.Status = "running"
	run.UpdatedAt = now
	s.data.Runs[run.RunID] = run
	if _, err := s.appendEventLocked(AppendEventInput{
		RunID: step.RunID, SessionID: step.SessionID, StepID: step.StepID, Type: "step_claimed",
		Payload: JSONObject{"worker_id": workerID, "lease_token": step.LeaseToken, "attempt": step.Attempt, "lease_until": step.LeaseUntil},
	}); err != nil {
		return nil, err
	}
	if err := s.flushLocked(); err != nil {
		return nil, err
	}
	return &StepClaim{RunID: step.RunID, SessionID: step.SessionID, StepID: step.StepID, Attempt: step.Attempt, LeaseToken: step.LeaseToken, StateVersion: step.StateVersion, LeaseUntil: step.LeaseUntil}, nil
}

func (s *JSONStore) LoadState(runID string) (JSONObject, int, string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	run, ok := s.data.Runs[runID]
	if !ok {
		return nil, 0, "", fmt.Errorf("run not found: %s", runID)
	}
	return cloneJSONObject(run.State), run.StateVersion, run.SessionID, nil
}

func (s *JSONStore) Heartbeat(stepID, leaseToken string, leaseSeconds int) (float64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	step, err := s.validateLeaseLocked(stepID, leaseToken)
	if err != nil {
		return 0, err
	}
	now := nowSeconds()
	step.LeaseUntil = now + float64(leaseSeconds)
	step.UpdatedAt = now
	s.data.Steps[stepID] = step
	if _, err := s.appendEventLocked(AppendEventInput{RunID: step.RunID, SessionID: step.SessionID, StepID: step.StepID, Type: "lease_heartbeat", Payload: JSONObject{"lease_token": leaseToken, "lease_until": step.LeaseUntil}}); err != nil {
		return 0, err
	}
	return step.LeaseUntil, s.flushLocked()
}

func (s *JSONStore) RecoverExpiredLeases() (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := nowSeconds()
	recovered := 0
	ids := make([]string, 0, len(s.data.Steps))
	for id := range s.data.Steps {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, stepID := range ids {
		step := s.data.Steps[stepID]
		if step.Status != "running" || step.LeaseUntil == 0 || step.LeaseUntil >= now {
			continue
		}
		previousOwner := step.Owner
		step.Status = "retry_scheduled"
		step.Owner = ""
		step.LeaseToken = ""
		step.LeaseUntil = 0
		step.UpdatedAt = now
		s.data.Steps[stepID] = step
		run := s.data.Runs[step.RunID]
		run.Status = "retry_scheduled"
		run.UpdatedAt = now
		s.data.Runs[run.RunID] = run
		recovered++
		if _, err := s.appendEventLocked(AppendEventInput{RunID: step.RunID, SessionID: step.SessionID, StepID: step.StepID, Type: "lease_expired", Payload: JSONObject{"previous_owner": previousOwner, "attempt": step.Attempt}}); err != nil {
			return recovered, err
		}
		if _, err := s.appendEventLocked(AppendEventInput{RunID: step.RunID, SessionID: step.SessionID, StepID: step.StepID, Type: "step_retry_scheduled", Payload: JSONObject{"step_id": step.StepID, "reason": "lease_expired"}}); err != nil {
			return recovered, err
		}
	}
	return recovered, s.flushLocked()
}

func (s *JSONStore) CancelRun(runID, reason string) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	run, ok := s.data.Runs[runID]
	if !ok {
		return 0, fmt.Errorf("run not found: %s", runID)
	}
	if run.Status == "completed" || run.Status == "failed" || run.Status == "cancelled" {
		return 0, nil
	}
	now := nowSeconds()
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: run.SessionID, Type: "run_cancel_requested", Payload: JSONObject{"reason": reason}}); err != nil {
		return 0, err
	}
	cancelled := 0
	ids := make([]string, 0, len(s.data.Steps))
	for id := range s.data.Steps {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	for _, stepID := range ids {
		step := s.data.Steps[stepID]
		if step.RunID != runID || step.Status == "completed" || step.Status == "failed" || step.Status == "cancelled" {
			continue
		}
		step.Status = "cancelled"
		step.Owner = ""
		step.LeaseToken = ""
		step.LeaseUntil = 0
		step.CancelledAt = now
		step.UpdatedAt = now
		s.data.Steps[stepID] = step
		cancelled++
		if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: step.StepID, Type: "step_cancelled", Payload: JSONObject{"reason": reason}}); err != nil {
			return cancelled, err
		}
	}
	run.Status = "cancelled"
	run.UpdatedAt = now
	s.data.Runs[runID] = run
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: run.SessionID, Type: "run_cancelled", Payload: JSONObject{"reason": reason, "cancelled_steps": cancelled}}); err != nil {
		return cancelled, err
	}
	return cancelled, s.flushLocked()
}

func (s *JSONStore) CommitStatePatch(runID, stepID, leaseToken string, baseVersion int, patch JSONObject, checkpointID string) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	step, err := s.validateLeaseLocked(stepID, leaseToken)
	if err != nil {
		return 0, err
	}
	run, ok := s.data.Runs[runID]
	if !ok {
		return 0, fmt.Errorf("run not found: %s", runID)
	}
	if run.StateVersion != baseVersion {
		return 0, fmt.Errorf("state version conflict: expected %d, got %d", baseVersion, run.StateVersion)
	}
	now := nowSeconds()
	newVersion := run.StateVersion + 1
	run.State = mergePatch(run.State, patch)
	run.StateVersion = newVersion
	run.Status = "completed"
	run.UpdatedAt = now
	s.data.Runs[runID] = run
	step.Status = "completed"
	step.StateVersion = newVersion
	step.CheckpointID = checkpointID
	step.UpdatedAt = now
	s.data.Steps[stepID] = step
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "state_patch_committed", Payload: JSONObject{"patch": cloneJSONObject(patch), "state_version": newVersion}, StateVersion: newVersion}); err != nil {
		return 0, err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "step_completed", Payload: JSONObject{"step_id": stepID}, StateVersion: newVersion}); err != nil {
		return 0, err
	}
	return newVersion, s.flushLocked()
}

func (s *JSONStore) MarkWaitingHuman(runID, stepID, reason, approvalID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	step, ok := s.data.Steps[stepID]
	if !ok {
		return fmt.Errorf("step not found: %s", stepID)
	}
	now := nowSeconds()
	step.Status = "waiting_human"
	step.Owner = ""
	step.LeaseToken = ""
	step.LeaseUntil = 0
	step.LastErrorType = "ApprovalRequired"
	step.LastError = reason
	step.UpdatedAt = now
	s.data.Steps[stepID] = step
	run := s.data.Runs[runID]
	run.Status = "waiting_human"
	run.UpdatedAt = now
	s.data.Runs[runID] = run
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "step_waiting_human", Payload: JSONObject{"reason": reason, "approval_id": approvalID}}); err != nil {
		return err
	}
	return s.flushLocked()
}

func (s *JSONStore) MarkRetry(runID, stepID, errorType, message string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	step, ok := s.data.Steps[stepID]
	if !ok {
		return fmt.Errorf("step not found: %s", stepID)
	}
	now := nowSeconds()
	step.Status = "retry_scheduled"
	step.Owner = ""
	step.LeaseToken = ""
	step.LeaseUntil = 0
	step.LastErrorType = errorType
	step.LastError = message
	step.UpdatedAt = now
	s.data.Steps[stepID] = step
	run := s.data.Runs[runID]
	run.Status = "retry_scheduled"
	run.UpdatedAt = now
	s.data.Runs[runID] = run
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "failure_classified", Payload: JSONObject{"error": message, "error_type": errorType, "retryable": true, "source": "agent"}}); err != nil {
		return err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "error_raised", Payload: JSONObject{"error": message, "error_type": errorType}}); err != nil {
		return err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "step_retry_scheduled", Payload: JSONObject{"step_id": stepID, "attempt": step.Attempt}}); err != nil {
		return err
	}
	return s.flushLocked()
}

func (s *JSONStore) MarkFailed(runID, stepID, errorType, message string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	step, ok := s.data.Steps[stepID]
	if !ok {
		return fmt.Errorf("step not found: %s", stepID)
	}
	now := nowSeconds()
	step.Status = "failed"
	step.Owner = ""
	step.LeaseToken = ""
	step.LeaseUntil = 0
	step.LastErrorType = errorType
	step.LastError = message
	step.UpdatedAt = now
	s.data.Steps[stepID] = step
	run := s.data.Runs[runID]
	run.Status = "failed"
	run.UpdatedAt = now
	s.data.Runs[runID] = run
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "failure_classified", Payload: JSONObject{"error": message, "error_type": errorType, "retryable": false, "source": failureSource(errorType)}}); err != nil {
		return err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "error_raised", Payload: JSONObject{"error": message, "error_type": errorType}}); err != nil {
		return err
	}
	if _, err := s.appendEventLocked(AppendEventInput{RunID: runID, SessionID: step.SessionID, StepID: stepID, Type: "step_failed", Payload: JSONObject{"step_id": stepID, "error_type": errorType}}); err != nil {
		return err
	}
	return s.flushLocked()
}

func (s *JSONStore) AppendEvent(input AppendEventInput) (Event, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	event, err := s.appendEventLocked(input)
	if err != nil {
		return Event{}, err
	}
	return event, s.flushLocked()
}

func (s *JSONStore) appendEventLocked(input AppendEventInput) (Event, error) {
	payload := cloneJSONObject(input.Payload)
	payloadHash := input.PayloadHash
	if payloadHash == "" {
		hash, err := sha256JSON(payload)
		if err != nil {
			return Event{}, err
		}
		payloadHash = hash
	}
	payloadRef := input.PayloadRef
	if payloadRef == "" {
		payloadRef = mustJSON(payload)
	}
	events := s.data.Events[input.RunID]
	event := Event{
		EventID:      newID("evt"),
		RunID:        input.RunID,
		SessionID:    input.SessionID,
		StepID:       input.StepID,
		Seq:          len(events) + 1,
		Type:         input.Type,
		Timestamp:    nowSeconds(),
		AgentRole:    input.AgentRole,
		StateVersion: input.StateVersion,
		CausalToken:  input.CausalToken,
		PayloadHash:  payloadHash,
		PayloadRef:   payloadRef,
		Payload:      payload,
	}
	s.data.Events[input.RunID] = append(events, event)
	return event, nil
}

func (s *JSONStore) ReserveLedger(input LedgerReservation) (*ToolLedgerEntry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.data.ToolLedger[input.IdempotencyKey]; ok {
		copy := cloneLedger(existing)
		return &copy, nil
	}
	ts := nowSeconds()
	s.data.ToolLedger[input.IdempotencyKey] = ToolLedgerEntry{
		LedgerID:       newID("ledger"),
		RunID:          input.RunID,
		SessionID:      input.SessionID,
		StepID:         input.StepID,
		ToolName:       input.ToolName,
		ToolVersion:    input.ToolVersion,
		ToolCallID:     input.ToolCallID,
		IdempotencyKey: input.IdempotencyKey,
		CausalToken:    input.CausalToken,
		RequestHash:    input.RequestHash,
		RequestRef:     input.RequestRef,
		Status:         "RESERVED",
		CreatedAt:      ts,
		UpdatedAt:      ts,
	}
	return nil, s.flushLocked()
}

func (s *JSONStore) UpdateLedger(update LedgerUpdate) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.data.ToolLedger[update.IdempotencyKey]
	if !ok {
		return fmt.Errorf("ledger entry not found: %s", update.IdempotencyKey)
	}
	entry.Status = update.Status
	entry.ExternalID = update.ExternalID
	entry.ResponseHash = update.ResponseHash
	entry.ResponseRef = update.ResponseRef
	entry.ErrorType = update.ErrorType
	entry.Response = cloneAny(update.Response)
	entry.UpdatedAt = nowSeconds()
	s.data.ToolLedger[update.IdempotencyKey] = entry
	return s.flushLocked()
}

func (s *JSONStore) RequestApproval(input ApprovalRequestInput) (ApprovalRequest, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if existing, ok := s.data.ApprovalRequests[input.ApprovalKey]; ok {
		return existing, nil
	}
	ts := nowSeconds()
	approval := ApprovalRequest{
		ApprovalID:  newID("approval"),
		ApprovalKey: input.ApprovalKey,
		RunID:       input.RunID,
		SessionID:   input.SessionID,
		StepID:      input.StepID,
		ToolName:    input.ToolName,
		RiskLevel:   input.RiskLevel,
		Status:      "PENDING",
		Reason:      input.Reason,
		RequestHash: input.RequestHash,
		RequestRef:  input.RequestRef,
		RequestedBy: input.RequestedBy,
		CreatedAt:   ts,
		UpdatedAt:   ts,
	}
	s.data.ApprovalRequests[input.ApprovalKey] = approval
	return approval, s.flushLocked()
}

func (s *JSONStore) ApprovalForKey(approvalKey string) *ApprovalRequest {
	s.mu.Lock()
	defer s.mu.Unlock()
	if approval, ok := s.data.ApprovalRequests[approvalKey]; ok {
		copy := approval
		return &copy
	}
	return nil
}

func (s *JSONStore) ApprovalRequests(runID string) []ApprovalRequest {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := []ApprovalRequest{}
	for _, approval := range s.data.ApprovalRequests {
		if runID == "" || approval.RunID == runID {
			out = append(out, approval)
		}
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt < out[j].CreatedAt || (out[i].CreatedAt == out[j].CreatedAt && out[i].ApprovalID < out[j].ApprovalID)
	})
	return out
}

func (s *JSONStore) ApproveRequest(approvalID, approver, reason string) (ApprovalRequest, error) {
	return s.decideApproval(approvalID, "APPROVED", approver, reason)
}

func (s *JSONStore) DenyRequest(approvalID, approver, reason string) (ApprovalRequest, error) {
	return s.decideApproval(approvalID, "DENIED", approver, reason)
}

func (s *JSONStore) decideApproval(approvalID, status, approver, reason string) (ApprovalRequest, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var key string
	var approval ApprovalRequest
	for k, candidate := range s.data.ApprovalRequests {
		if candidate.ApprovalID == approvalID {
			key = k
			approval = candidate
			break
		}
	}
	if key == "" {
		return ApprovalRequest{}, fmt.Errorf("approval not found: %s", approvalID)
	}
	ts := nowSeconds()
	approval.Status = status
	approval.ApprovedBy = approver
	approval.DecisionReason = reason
	approval.UpdatedAt = ts
	s.data.ApprovalRequests[key] = approval
	if _, err := s.appendEventLocked(AppendEventInput{RunID: approval.RunID, SessionID: approval.SessionID, StepID: approval.StepID, Type: "tool_approval_decided", Payload: JSONObject{"approval_id": approvalID, "tool": approval.ToolName, "status": status, "approver": approver, "reason": reason}}); err != nil {
		return ApprovalRequest{}, err
	}
	step := s.data.Steps[approval.StepID]
	if step.Status == "waiting_human" {
		if status == "APPROVED" {
			step.Status = "pending"
			step.Owner = ""
			step.LeaseToken = ""
			step.LeaseUntil = 0
			step.UpdatedAt = ts
			s.data.Steps[approval.StepID] = step
			run := s.data.Runs[approval.RunID]
			run.Status = "pending"
			run.UpdatedAt = ts
			s.data.Runs[approval.RunID] = run
			if _, err := s.appendEventLocked(AppendEventInput{RunID: approval.RunID, SessionID: approval.SessionID, StepID: approval.StepID, Type: "step_retry_scheduled", Payload: JSONObject{"step_id": approval.StepID, "reason": "approval_granted"}}); err != nil {
				return ApprovalRequest{}, err
			}
		} else if status == "DENIED" {
			step.Status = "failed"
			step.Owner = ""
			step.LeaseToken = ""
			step.LeaseUntil = 0
			step.LastErrorType = "ApprovalDenied"
			step.LastError = reason
			step.UpdatedAt = ts
			s.data.Steps[approval.StepID] = step
			run := s.data.Runs[approval.RunID]
			run.Status = "failed"
			run.UpdatedAt = ts
			s.data.Runs[approval.RunID] = run
			if _, err := s.appendEventLocked(AppendEventInput{RunID: approval.RunID, SessionID: approval.SessionID, StepID: approval.StepID, Type: "failure_classified", Payload: JSONObject{"error": reason, "error_type": "ApprovalDenied", "retryable": false, "source": "approval"}}); err != nil {
				return ApprovalRequest{}, err
			}
			if _, err := s.appendEventLocked(AppendEventInput{RunID: approval.RunID, SessionID: approval.SessionID, StepID: approval.StepID, Type: "step_failed", Payload: JSONObject{"step_id": approval.StepID, "error_type": "ApprovalDenied"}}); err != nil {
				return ApprovalRequest{}, err
			}
		}
	}
	return approval, s.flushLocked()
}

func (s *JSONStore) RecordCost(input CostRecordInput) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	costID := newID("cost")
	ts := nowSeconds()
	record := CostRecord{CostID: costID, RunID: input.RunID, SessionID: input.SessionID, StepID: input.StepID, Category: input.Category, Name: input.Name, Amount: input.Amount, Unit: input.Unit, Metadata: cloneJSONObject(input.Metadata), CreatedAt: ts}
	s.data.CostRecords[input.RunID] = append(s.data.CostRecords[input.RunID], record)
	if _, err := s.appendEventLocked(AppendEventInput{RunID: input.RunID, SessionID: input.SessionID, StepID: input.StepID, Type: "cost_recorded", Payload: JSONObject{"cost_id": costID, "category": input.Category, "name": input.Name, "amount": input.Amount, "unit": input.Unit, "metadata": cloneJSONObject(input.Metadata)}}); err != nil {
		return "", err
	}
	return costID, s.flushLocked()
}

func (s *JSONStore) CostRecords(runID string) []CostRecord {
	s.mu.Lock()
	defer s.mu.Unlock()
	records := append([]CostRecord(nil), s.data.CostRecords[runID]...)
	for i := range records {
		records[i].Metadata = cloneJSONObject(records[i].Metadata)
	}
	return records
}

func (s *JSONStore) CostSummary(runID string) CostSummary {
	s.mu.Lock()
	defer s.mu.Unlock()
	summary := CostSummary{ByCategory: map[string]float64{}}
	for _, row := range s.data.CostRecords[runID] {
		if (row.Category == "tool" || row.Category == "tool_shadow") && row.Unit == "call" {
			summary.ToolCalls += row.Amount
		}
		if row.Category == "model" && row.Unit == "token" {
			summary.ModelTokens += row.Amount
		}
		if row.Unit == "usd" {
			summary.TotalUSD += row.Amount
		}
		key := fmt.Sprintf("%s:%s", row.Category, row.Unit)
		summary.ByCategory[key] += row.Amount
	}
	return summary
}

func (s *JSONStore) CreateArtifact(runID, stepID, name string, content any, metadata JSONObject) (Artifact, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	hash, err := sha256JSON(content)
	if err != nil {
		return Artifact{}, err
	}
	artifact := Artifact{
		ArtifactID: newID("art"),
		RunID:      runID,
		StepID:     stepID,
		Name:       name,
		BlobHash:   "sha256:" + hash,
		BlobRef:    mustJSON(content),
		Metadata:   cloneJSONObject(metadata),
		CreatedAt:  nowSeconds(),
	}
	s.data.Artifacts[runID] = append(s.data.Artifacts[runID], artifact)
	return artifact, s.flushLocked()
}

func (s *JSONStore) Artifacts(runID string) []Artifact {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := append([]Artifact(nil), s.data.Artifacts[runID]...)
	for i := range out {
		out[i].Metadata = cloneJSONObject(out[i].Metadata)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt < out[j].CreatedAt || (out[i].CreatedAt == out[j].CreatedAt && out[i].ArtifactID < out[j].ArtifactID)
	})
	return out
}

func (s *JSONStore) Run(runID string) (Run, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	run, ok := s.data.Runs[runID]
	if !ok {
		return Run{}, fmt.Errorf("run not found: %s", runID)
	}
	run.State = cloneJSONObject(run.State)
	return run, nil
}

func (s *JSONStore) Steps(runID string) []Step {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := []Step{}
	for _, step := range s.data.Steps {
		if step.RunID == runID {
			out = append(out, step)
		}
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt < out[j].CreatedAt || (out[i].CreatedAt == out[j].CreatedAt && out[i].StepID < out[j].StepID)
	})
	return out
}

func (s *JSONStore) Events(runID string) []Event {
	s.mu.Lock()
	defer s.mu.Unlock()
	events := append([]Event(nil), s.data.Events[runID]...)
	for i := range events {
		events[i].Payload = cloneJSONObject(events[i].Payload)
	}
	return events
}

func (s *JSONStore) Ledger(runID string) []ToolLedgerEntry {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := []ToolLedgerEntry{}
	for _, entry := range s.data.ToolLedger {
		if entry.RunID == runID {
			out = append(out, cloneLedger(entry))
		}
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt < out[j].CreatedAt || (out[i].CreatedAt == out[j].CreatedAt && out[i].LedgerID < out[j].LedgerID)
	})
	return out
}

func (s *JSONStore) FinalState(runID string) (JSONObject, error) {
	state, _, _, err := s.LoadState(runID)
	return state, err
}

func (s *JSONStore) validateLeaseLocked(stepID, leaseToken string) (Step, error) {
	step, ok := s.data.Steps[stepID]
	if !ok {
		return Step{}, fmt.Errorf("step not found: %s", stepID)
	}
	if step.Status != "running" || step.LeaseToken != leaseToken {
		return Step{}, errors.New("invalid or stale lease token")
	}
	if step.LeaseUntil != 0 && step.LeaseUntil < nowSeconds() {
		return Step{}, errors.New("lease expired")
	}
	return step, nil
}

func cloneLedger(entry ToolLedgerEntry) ToolLedgerEntry {
	entry.Response = cloneAny(entry.Response)
	return entry
}

func failureSource(errorType string) string {
	switch errorType {
	case "BudgetExceededError":
		return "budget"
	case "PermissionDeniedError", "ApprovalDenied":
		return "policy"
	case "SandboxUnavailableError":
		return "sandbox"
	default:
		return "agent"
	}
}
