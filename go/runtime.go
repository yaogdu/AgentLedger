package agentledger

import (
	"context"
	"errors"
	"fmt"
)

var ErrRetryable = errors.New("agentledger: retryable agent error")

type AgentFunc func(context.Context, *AgentContext, JSONObject) error

type Runtime struct {
	Store    *JSONStore
	Registry *ToolRegistry
	Policy   *PolicyEngine
	Budget   *BudgetController
	Sandbox  SandboxExecutor
	Gateway  *ToolGateway
}

func NewRuntime(store *JSONStore) *Runtime {
	if store == nil {
		store = NewMemoryStore()
	}
	registry := NewToolRegistry()
	policy := NewPolicyEngine()
	budget := NewBudgetController(BudgetLimits{})
	runtime := &Runtime{Store: store, Registry: registry, Policy: policy, Budget: budget}
	runtime.Gateway = NewToolGateway(store, registry, policy, budget, nil)
	return runtime
}

func NewLocalRuntime(path string) (*Runtime, error) {
	store, err := NewJSONStore(path)
	if err != nil {
		return nil, err
	}
	return NewRuntime(store), nil
}

func (r *Runtime) SetBudget(limits BudgetLimits) {
	r.Budget = NewBudgetController(limits)
	r.Gateway.Budget = r.Budget
}

func (r *Runtime) SetSandbox(executor SandboxExecutor) {
	r.Sandbox = executor
	r.Gateway.Sandbox = executor
}

func (r *Runtime) RegisterTool(spec ToolSpec) error {
	return r.Registry.Register(spec)
}

func (r *Runtime) CreateRun(initialState JSONObject) (string, string, error) {
	return r.Store.CreateRun("", initialState)
}

func (r *Runtime) RunOnce(ctx context.Context, runID, workerID, agentRole string, leaseSeconds int, agent AgentFunc) (bool, error) {
	if workerID == "" {
		workerID = "worker-go"
	}
	if agentRole == "" {
		agentRole = "Agent"
	}
	if leaseSeconds == 0 {
		leaseSeconds = 60
	}
	claim, err := r.Store.ClaimStep(workerID, runID, leaseSeconds)
	if err != nil {
		if errors.Is(err, ErrNoRunnableStep) {
			return false, nil
		}
		return false, err
	}
	state, version, sessionID, err := r.Store.LoadState(claim.RunID)
	if err != nil {
		return false, err
	}
	agentCtx := &AgentContext{
		RunID:        claim.RunID,
		SessionID:    sessionID,
		StepID:       claim.StepID,
		AgentRole:    agentRole,
		LeaseToken:   claim.LeaseToken,
		Attempt:      claim.Attempt,
		StateVersion: version,
		Store:        r.Store,
		Gateway:      r.Gateway,
		Budget:       r.Budget,
		PendingPatch: JSONObject{},
	}
	_, err = r.Store.AppendEvent(AppendEventInput{
		RunID: claim.RunID, SessionID: sessionID, StepID: claim.StepID, Type: "agent_started",
		AgentRole: agentRole, StateVersion: version,
		Payload: JSONObject{"agent_role": agentRole, "attempt": claim.Attempt, "execution_mode": "normal"},
	})
	if err != nil {
		return false, err
	}
	if err := agent(ctx, agentCtx, cloneJSONObject(state)); err != nil {
		var approvalErr ApprovalRequiredError
		if errors.As(err, &approvalErr) {
			return false, r.Store.MarkWaitingHuman(claim.RunID, claim.StepID, approvalErr.Error(), approvalErr.ApprovalID)
		}
		if errors.Is(err, ErrRetryable) {
			return false, r.Store.MarkRetry(claim.RunID, claim.StepID, "RetryableAgentError", err.Error())
		}
		markErr := r.Store.MarkFailed(claim.RunID, claim.StepID, errorTypeName(err), err.Error())
		if markErr != nil {
			return false, markErr
		}
		return false, err
	}
	_, err = r.Store.CommitStatePatch(claim.RunID, claim.StepID, claim.LeaseToken, version, agentCtx.PendingPatch, fmt.Sprintf("ckpt:%s:%s:%d", claim.RunID, claim.StepID, claim.Attempt))
	if err != nil {
		return false, err
	}
	return true, nil
}

type AgentContext struct {
	RunID        string
	SessionID    string
	StepID       string
	AgentRole    string
	LeaseToken   string
	Attempt      int
	StateVersion int
	Store        *JSONStore
	Gateway      *ToolGateway
	Budget       *BudgetController
	PendingPatch JSONObject
}

func (c *AgentContext) WriteState(key string, value any) error {
	if c.PendingPatch == nil {
		c.PendingPatch = JSONObject{}
	}
	c.PendingPatch[key] = cloneAny(value)
	_, err := c.Store.AppendEvent(AppendEventInput{
		RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "state_patch_proposed",
		AgentRole: c.AgentRole, StateVersion: c.StateVersion,
		Payload: JSONObject{"key": key, "patch": cloneAny(value)},
	})
	return err
}

func (c *AgentContext) CreateArtifact(name string, content any, metadata JSONObject) (string, error) {
	artifact, err := c.Store.CreateArtifact(c.RunID, c.StepID, name, content, metadata)
	if err != nil {
		return "", err
	}
	_, err = c.Store.AppendEvent(AppendEventInput{
		RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "artifact_created",
		AgentRole: c.AgentRole, StateVersion: c.StateVersion,
		Payload:     JSONObject{"artifact_id": artifact.ArtifactID, "name": name},
		PayloadHash: artifact.BlobHash,
		PayloadRef:  artifact.BlobRef,
	})
	if err != nil {
		return "", err
	}
	return artifact.ArtifactID, nil
}

func (c *AgentContext) CreateMediaArtifact(name, kind string, options MediaArtifactOptions) (string, error) {
	if !mediaKinds[kind] {
		return "", fmt.Errorf("unsupported media kind %q", kind)
	}
	metadata := cloneJSONObject(options.MediaMetadata)
	if metadata == nil {
		metadata = JSONObject{}
	}
	metadata["schema_version"] = MediaSchemaVersion
	metadata["kind"] = kind
	content := compactJSON(JSONObject{
		"schema_version":  MediaSchemaVersion,
		"kind":            kind,
		"uri":             options.URI,
		"content_ref":     options.ContentRef,
		"metadata":        metadata,
		"lineage":         cloneJSONObject(options.Lineage),
		"derived_outputs": cloneJSONObject(options.DerivedOutputs),
	})
	artifactMetadata := cloneJSONObject(options.Metadata)
	artifactMetadata["agentledger_media"] = compactJSON(JSONObject{
		"schema_version": MediaSchemaVersion,
		"kind":           kind,
		"uri":            options.URI,
		"content_ref":    options.ContentRef,
		"metadata":       metadata,
		"lineage":        cloneJSONObject(options.Lineage),
	})
	return c.CreateArtifact(name, content, artifactMetadata)
}

func (c *AgentContext) CreateStreamCheckpoint(name string, options StreamCheckpointOptions) (string, error) {
	if options.StreamID == "" || options.ConsumerID == "" {
		return "", fmt.Errorf("stream_id and consumer_id are required")
	}
	chunk := options.Chunk
	if ref, ok := chunk.(StreamChunkRef); ok {
		chunk = ref.ToJSON()
	}
	content := compactJSON(JSONObject{
		"schema_version":     StreamSchemaVersion,
		"stream_id":          options.StreamID,
		"consumer_id":        options.ConsumerID,
		"offset":             options.Offset,
		"watermark":          options.Watermark,
		"chunk":              cloneAny(chunk),
		"partial_result_ref": options.PartialResultRef,
		"backpressure":       cloneJSONObject(options.Backpressure),
		"metadata":           cloneJSONObject(options.Metadata),
	})
	artifactMetadata := JSONObject{"agentledger_stream": compactJSON(JSONObject{
		"schema_version":     StreamSchemaVersion,
		"stream_id":          options.StreamID,
		"consumer_id":        options.ConsumerID,
		"offset":             options.Offset,
		"watermark":          options.Watermark,
		"chunk":              cloneAny(chunk),
		"partial_result_ref": options.PartialResultRef,
		"backpressure":       cloneJSONObject(options.Backpressure),
	})}
	return c.CreateArtifact(name, content, artifactMetadata)
}

func (r StreamChunkRef) ToJSON() JSONObject {
	return compactJSON(JSONObject{
		"schema_version": StreamSchemaVersion,
		"stream_id":      r.StreamID,
		"chunk_id":       r.ChunkID,
		"offset":         r.Offset,
		"content_ref":    r.ContentRef,
		"content_hash":   r.ContentHash,
		"sequence":       r.Sequence,
		"event_time":     r.EventTime,
		"metadata":       cloneJSONObject(r.Metadata),
	})
}

func (c *AgentContext) CallTool(ctx context.Context, name string, args JSONObject) (any, error) {
	return c.Gateway.Call(ctx, c, name, args)
}

func (c *AgentContext) RecordModelCall(model string, inputTokens, outputTokens int, totalUSD float64) error {
	return c.RecordModelCallEvidence(ModelCallEvidence{Provider: "custom", Model: model, Usage: JSONObject{"input_tokens": inputTokens, "output_tokens": outputTokens}, TotalUSD: totalUSD})
}

type ModelCallEvidence struct {
	Provider string
	Model    string
	Request  JSONObject
	Response JSONObject
	Usage    JSONObject
	TotalUSD float64
	Metadata JSONObject
}

type ModelFailureEvidence struct {
	Provider  string
	Model     string
	ErrorType string
	Message   string
	Retryable *bool
	Request   JSONObject
	Usage     JSONObject
	TotalUSD  float64
	Metadata  JSONObject
}

type ToolCallProposal struct {
	ToolName     string
	Arguments    JSONObject
	Provider     string
	Model        string
	ModelCallRef string
	Confidence   *float64
	Reason       string
	Metadata     JSONObject
}

func (c *AgentContext) RecordModelCallEvidence(record ModelCallEvidence) error {
	provider := firstText(record.Provider, "custom")
	model := firstText(record.Model, "unknown")
	usage := cloneJSONObject(record.Usage)
	tokens := usageTotalTokens(usage)
	if err := c.Budget.BeforeModelCall(c.Store, c.RunID, tokens); err != nil {
		_, appendErr := c.Store.AppendEvent(AppendEventInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "budget_check_failed", AgentRole: c.AgentRole, StateVersion: c.StateVersion, Payload: JSONObject{"category": "model", "provider": provider, "model": model, "error": err.Error()}})
		if appendErr != nil {
			return appendErr
		}
		return err
	}
	requestPayload := compactJSON(JSONObject{"schema_version": "agentledger.model.evidence.v1", "provider": provider, "model": model, "request": cloneJSONObject(record.Request), "metadata": cloneJSONObject(record.Metadata)})
	if _, err := c.Store.AppendEvent(AppendEventInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "model_call_requested", AgentRole: c.AgentRole, StateVersion: c.StateVersion, Payload: requestPayload}); err != nil {
		return err
	}
	responsePayload := compactJSON(JSONObject{"schema_version": "agentledger.model.evidence.v1", "provider": provider, "model": model, "response": cloneJSONObject(record.Response), "usage": usage, "total_usd": record.TotalUSD, "metadata": cloneJSONObject(record.Metadata)})
	if _, err := c.Store.AppendEvent(AppendEventInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "model_call_completed", AgentRole: c.AgentRole, StateVersion: c.StateVersion, Payload: responsePayload}); err != nil {
		return err
	}
	return c.recordModelCosts(provider, model, usage, record.TotalUSD)
}

func (c *AgentContext) RecordModelFailure(record ModelFailureEvidence) error {
	provider := firstText(record.Provider, "custom")
	model := firstText(record.Model, "unknown")
	usage := cloneJSONObject(record.Usage)
	payload := compactJSON(JSONObject{"schema_version": "agentledger.model.evidence.v1", "provider": provider, "model": model, "error_type": firstText(record.ErrorType, "ModelCallFailed"), "error": record.Message, "usage": usage, "total_usd": record.TotalUSD, "metadata": cloneJSONObject(record.Metadata)})
	if record.Retryable != nil {
		payload["retryable"] = *record.Retryable
	}
	if len(record.Request) > 0 {
		payload["request"] = cloneJSONObject(record.Request)
	}
	if _, err := c.Store.AppendEvent(AppendEventInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "model_call_failed", AgentRole: c.AgentRole, StateVersion: c.StateVersion, Payload: payload}); err != nil {
		return err
	}
	return c.recordModelCosts(provider, model, usage, record.TotalUSD)
}

func (c *AgentContext) RecordToolCallProposal(proposal ToolCallProposal) error {
	payload := compactJSON(JSONObject{"schema_version": "agentledger.model.evidence.v1", "tool": proposal.ToolName, "args": cloneJSONObject(proposal.Arguments), "metadata": cloneJSONObject(proposal.Metadata)})
	if proposal.Provider != "" {
		payload["provider"] = proposal.Provider
	}
	if proposal.Model != "" {
		payload["model"] = proposal.Model
	}
	if proposal.ModelCallRef != "" {
		payload["model_call_ref"] = proposal.ModelCallRef
	}
	if proposal.Confidence != nil {
		payload["confidence"] = *proposal.Confidence
	}
	if proposal.Reason != "" {
		payload["reason"] = proposal.Reason
	}
	_, err := c.Store.AppendEvent(AppendEventInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Type: "tool_call_proposed", AgentRole: c.AgentRole, StateVersion: c.StateVersion, Payload: payload})
	return err
}

func (c *AgentContext) recordModelCosts(provider, model string, usage JSONObject, totalUSD float64) error {
	tokens := usageTotalTokens(usage)
	metadata := JSONObject{"provider": provider, "model": model, "usage": cloneJSONObject(usage)}
	if tokens > 0 {
		if _, err := c.Store.RecordCost(CostRecordInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Category: "model", Name: model, Amount: float64(tokens), Unit: "token", Metadata: metadata}); err != nil {
			return err
		}
	}
	if totalUSD > 0 {
		if _, err := c.Store.RecordCost(CostRecordInput{RunID: c.RunID, SessionID: c.SessionID, StepID: c.StepID, Category: "model", Name: model, Amount: totalUSD, Unit: "usd", Metadata: metadata}); err != nil {
			return err
		}
	}
	return nil
}

func usageTotalTokens(usage JSONObject) int {
	for _, key := range []string{"total_tokens", "totalTokens", "tokens"} {
		if value, ok := usage[key]; ok {
			return int(numberValue(value))
		}
	}
	return int(numberValue(usage["input_tokens"]) + numberValue(usage["prompt_tokens"]) + numberValue(usage["inputTokens"]) + numberValue(usage["output_tokens"]) + numberValue(usage["completion_tokens"]) + numberValue(usage["outputTokens"]))
}

func numberValue(value any) float64 {
	switch typed := value.(type) {
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case float64:
		return typed
	case float32:
		return float64(typed)
	default:
		return 0
	}
}

func (c *AgentContext) Heartbeat(leaseSeconds int) (float64, error) {
	return c.Store.Heartbeat(c.StepID, c.LeaseToken, leaseSeconds)
}

func errorTypeName(err error) string {
	var budgetErr BudgetExceededError
	if errors.As(err, &budgetErr) {
		return "BudgetExceededError"
	}
	var permissionErr PermissionDeniedError
	if errors.As(err, &permissionErr) {
		return "PermissionDeniedError"
	}
	var sandboxErr SandboxUnavailableError
	if errors.As(err, &sandboxErr) {
		return "SandboxUnavailableError"
	}
	return fmt.Sprintf("%T", err)
}

func compactJSON(in JSONObject) JSONObject {
	out := JSONObject{}
	for key, value := range in {
		if value == nil {
			continue
		}
		switch typed := value.(type) {
		case string:
			if typed == "" {
				continue
			}
		case JSONObject:
			if len(typed) == 0 {
				continue
			}
		case map[string]any:
			if len(typed) == 0 {
				continue
			}
		}
		out[key] = cloneAny(value)
	}
	return out
}
