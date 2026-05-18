package agentledger

import (
	"context"
	"errors"
	"fmt"
)

const (
	ApprovalPending  = "PENDING"
	ApprovalApproved = "APPROVED"
	ApprovalDenied   = "DENIED"
)

type PermissionDeniedError struct{ Reason string }

func (e PermissionDeniedError) Error() string { return e.Reason }

type ApprovalRequiredError struct {
	ApprovalID string
	Reason     string
}

func (e ApprovalRequiredError) Error() string { return e.Reason }

type BudgetExceededError struct{ Reason string }

func (e BudgetExceededError) Error() string { return e.Reason }

type SandboxUnavailableError struct{ Reason string }

func (e SandboxUnavailableError) Error() string { return e.Reason }

type ToolFunc func(context.Context, JSONObject) (any, error)

type ToolSpec struct {
	Name                string     `json:"name"`
	Version             string     `json:"version"`
	Description         string     `json:"description,omitempty"`
	SideEffect          string     `json:"side_effect"`
	RiskLevel           string     `json:"risk_level"`
	IdempotencyRequired bool       `json:"idempotency_required"`
	ApprovalRequired    bool       `json:"approval_required"`
	SandboxRequired     bool       `json:"sandbox_required"`
	SandboxExecutor     string     `json:"sandbox_executor,omitempty"`
	SandboxPolicy       JSONObject `json:"sandbox_policy,omitempty"`
	InputSchema         JSONObject `json:"input_schema,omitempty"`
	OutputSchema        JSONObject `json:"output_schema,omitempty"`
	Func                ToolFunc   `json:"-"`
}

type ToolRegistry struct {
	tools map[string]ToolSpec
}

func NewToolRegistry() *ToolRegistry {
	return &ToolRegistry{tools: map[string]ToolSpec{}}
}

func (r *ToolRegistry) Register(spec ToolSpec) error {
	if spec.Name == "" {
		return errors.New("tool name is required")
	}
	if spec.Version == "" {
		spec.Version = "v1"
	}
	if spec.SideEffect == "" {
		spec.SideEffect = "none"
	}
	if spec.RiskLevel == "" {
		spec.RiskLevel = "low"
	}
	if spec.SandboxPolicy == nil {
		spec.SandboxPolicy = JSONObject{}
	}
	if spec.Func == nil {
		return fmt.Errorf("tool %s has no function", spec.Name)
	}
	r.tools[spec.Name] = spec
	return nil
}

func (r *ToolRegistry) Get(name string) (ToolSpec, error) {
	spec, ok := r.tools[name]
	if !ok {
		return ToolSpec{}, fmt.Errorf("tool not registered: %s", name)
	}
	return spec, nil
}

type RolePolicy struct {
	AllowTools map[string]bool
	DenyTools  map[string]bool
	AllowRisk  map[string]bool
	DenyRisk   map[string]bool
}

type PolicyEngine struct {
	Roles         map[string]RolePolicy
	DefaultByRisk map[string]string
}

func NewPolicyEngine() *PolicyEngine {
	return &PolicyEngine{Roles: map[string]RolePolicy{}, DefaultByRisk: map[string]string{}}
}

func (p *PolicyEngine) AllowTool(role, tool string) {
	policy := p.role(role)
	policy.AllowTools[tool] = true
	p.Roles[role] = policy
}

func (p *PolicyEngine) DenyTool(role, tool string) {
	policy := p.role(role)
	policy.DenyTools[tool] = true
	p.Roles[role] = policy
}

func (p *PolicyEngine) AllowRisk(role, risk string) {
	policy := p.role(role)
	policy.AllowRisk[risk] = true
	p.Roles[role] = policy
}

func (p *PolicyEngine) CheckTool(role, toolName, riskLevel string) (bool, string) {
	if p == nil {
		p = NewPolicyEngine()
	}
	if policy, ok := p.Roles[role]; ok {
		if policy.DenyTools[toolName] {
			return false, fmt.Sprintf("tool %s explicitly denied for role %s", toolName, role)
		}
		if policy.AllowTools[toolName] {
			return true, "allowed by role policy"
		}
		if policy.DenyRisk[riskLevel] {
			return false, fmt.Sprintf("risk level %s denied for role %s", riskLevel, role)
		}
		if policy.AllowRisk[riskLevel] {
			return true, fmt.Sprintf("risk level %s allowed for role %s", riskLevel, role)
		}
		if len(policy.AllowTools) > 0 || len(policy.AllowRisk) > 0 {
			return false, fmt.Sprintf("tool %s not allowed for role %s", toolName, role)
		}
	}
	if decision := p.DefaultByRisk[riskLevel]; decision == "allow" {
		return true, fmt.Sprintf("risk level %s allowed by default policy", riskLevel)
	} else if decision == "deny" {
		return false, fmt.Sprintf("risk level %s denied by default policy", riskLevel)
	}
	if isHighRisk(riskLevel) {
		return false, "high-risk tool denied by default"
	}
	return true, "default allow for low/medium risk in local runtime"
}

func (p *PolicyEngine) role(role string) RolePolicy {
	policy, ok := p.Roles[role]
	if !ok {
		policy = RolePolicy{}
	}
	if policy.AllowTools == nil {
		policy.AllowTools = map[string]bool{}
	}
	if policy.DenyTools == nil {
		policy.DenyTools = map[string]bool{}
	}
	if policy.AllowRisk == nil {
		policy.AllowRisk = map[string]bool{}
	}
	if policy.DenyRisk == nil {
		policy.DenyRisk = map[string]bool{}
	}
	return policy
}

func isHighRisk(risk string) bool {
	switch risk {
	case "high", "destructive", "sensitive", "financial_or_legal":
		return true
	default:
		return false
	}
}

type BudgetLimits struct {
	MaxToolCalls   int
	MaxModelTokens int
	MaxTotalUSD    float64
}

type BudgetController struct {
	Limits BudgetLimits
}

func NewBudgetController(limits BudgetLimits) *BudgetController {
	return &BudgetController{Limits: limits}
}

func (b *BudgetController) BeforeToolCall(store *JSONStore, runID string) error {
	if b == nil || b.Limits.MaxToolCalls <= 0 {
		return nil
	}
	used := int(store.CostSummary(runID).ToolCalls)
	if used >= b.Limits.MaxToolCalls {
		return BudgetExceededError{Reason: fmt.Sprintf("tool call budget exceeded: %d/%d", used, b.Limits.MaxToolCalls)}
	}
	return nil
}

func (b *BudgetController) BeforeModelCall(store *JSONStore, runID string, estimatedTokens int) error {
	if b == nil {
		return nil
	}
	if b.Limits.MaxModelTokens > 0 {
		used := int(store.CostSummary(runID).ModelTokens)
		if used+estimatedTokens > b.Limits.MaxModelTokens {
			return BudgetExceededError{Reason: fmt.Sprintf("model token budget exceeded: %d+%d/%d", used, estimatedTokens, b.Limits.MaxModelTokens)}
		}
	}
	if b.Limits.MaxTotalUSD > 0 && store.CostSummary(runID).TotalUSD > b.Limits.MaxTotalUSD {
		return BudgetExceededError{Reason: fmt.Sprintf("cost budget exceeded: %.4f/%.4f USD", store.CostSummary(runID).TotalUSD, b.Limits.MaxTotalUSD)}
	}
	return nil
}

type SandboxPolicy struct {
	ToolName       string     `json:"tool_name"`
	RunID          string     `json:"run_id"`
	StepID         string     `json:"step_id"`
	Executor       string     `json:"executor"`
	IsolationLevel string     `json:"isolation_level"`
	Network        string     `json:"network"`
	Filesystem     string     `json:"filesystem"`
	TimeoutSeconds int        `json:"timeout_seconds"`
	Extra          JSONObject `json:"extra,omitempty"`
}

type SandboxResult struct {
	OK       bool       `json:"ok"`
	Output   any        `json:"output,omitempty"`
	Error    string     `json:"error,omitempty"`
	Metadata JSONObject `json:"metadata,omitempty"`
}

type SandboxExecutor interface {
	RunTool(context.Context, ToolSpec, JSONObject, SandboxPolicy) SandboxResult
}

type DisabledSandboxExecutor struct{}

func (DisabledSandboxExecutor) RunTool(ctx context.Context, spec ToolSpec, args JSONObject, policy SandboxPolicy) SandboxResult {
	return SandboxResult{OK: false, Error: fmt.Sprintf("sandbox executor %q is disabled", policy.Executor), Metadata: JSONObject{"executor": policy.Executor, "isolation_level": "none", "fail_closed": true}}
}

type LocalSandboxExecutor struct{}

func (LocalSandboxExecutor) RunTool(ctx context.Context, spec ToolSpec, args JSONObject, policy SandboxPolicy) SandboxResult {
	result, err := spec.Func(ctx, cloneJSONObject(args))
	if err != nil {
		return SandboxResult{OK: false, Error: err.Error(), Metadata: JSONObject{"executor": "local", "isolation_level": "none"}}
	}
	return SandboxResult{OK: true, Output: result, Metadata: JSONObject{"executor": "local", "isolation_level": "none"}}
}

type ToolGateway struct {
	Store    *JSONStore
	Registry *ToolRegistry
	Policy   *PolicyEngine
	Budget   *BudgetController
	Sandbox  SandboxExecutor
}

func NewToolGateway(store *JSONStore, registry *ToolRegistry, policy *PolicyEngine, budget *BudgetController, sandbox SandboxExecutor) *ToolGateway {
	if policy == nil {
		policy = NewPolicyEngine()
	}
	if budget == nil {
		budget = NewBudgetController(BudgetLimits{})
	}
	return &ToolGateway{Store: store, Registry: registry, Policy: policy, Budget: budget, Sandbox: sandbox}
}

func (g *ToolGateway) Call(ctx context.Context, agentCtx *AgentContext, toolName string, args JSONObject) (any, error) {
	spec, err := g.Registry.Get(toolName)
	if err != nil {
		return nil, err
	}
	request := JSONObject{"tool": toolName, "args": cloneJSONObject(args)}
	requestHash, err := sha256JSON(request)
	if err != nil {
		return nil, err
	}
	requestRef := mustJSON(request)
	causal := mustJSON(JSONObject{
		"run_id":        agentCtx.RunID,
		"step_id":       agentCtx.StepID,
		"attempt":       agentCtx.Attempt,
		"state_version": agentCtx.StateVersion,
		"lease_token":   agentCtx.LeaseToken,
	})
	idempotencyKey := fmt.Sprintf("%s:%s:%s:%s", agentCtx.RunID, agentCtx.StepID, toolName, requestHash)
	approvalKey := idempotencyKey
	managedSideEffect := spec.SideEffect != "none" || spec.IdempotencyRequired

	_, err = g.Store.AppendEvent(AppendEventInput{
		RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_requested",
		AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal,
		PayloadHash: requestHash, PayloadRef: requestRef, Payload: request,
	})
	if err != nil {
		return nil, err
	}
	if err := ValidateToolSchema(spec.InputSchema, args, "$arg"); err != nil {
		_, appendErr := g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_failed", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"tool": toolName, "error": err.Error(), "phase": "input_validation"}})
		if appendErr != nil {
			return nil, appendErr
		}
		return nil, err
	}

	allowed, reason := g.Policy.CheckTool(agentCtx.AgentRole, toolName, spec.RiskLevel)
	if approval := g.Store.ApprovalForKey(approvalKey); approval != nil {
		switch approval.Status {
		case ApprovalDenied:
			reason = fmt.Sprintf("approval denied for tool %s", toolName)
			if err := g.recordPermission(agentCtx, toolName, false, reason, causal); err != nil {
				return nil, err
			}
			return nil, PermissionDeniedError{Reason: reason}
		case ApprovalApproved:
			allowed = true
			reason = fmt.Sprintf("approved by %s", nonempty(approval.ApprovedBy, "operator"))
		}
	} else if spec.ApprovalRequired {
		approval, err := g.Store.RequestApproval(ApprovalRequestInput{
			ApprovalKey: approvalKey,
			RunID:       agentCtx.RunID,
			SessionID:   agentCtx.SessionID,
			StepID:      agentCtx.StepID,
			ToolName:    toolName,
			RiskLevel:   spec.RiskLevel,
			Reason:      "tool requires approval",
			RequestHash: requestHash,
			RequestRef:  requestRef,
			RequestedBy: agentCtx.AgentRole,
		})
		if err != nil {
			return nil, err
		}
		if err := g.recordPermission(agentCtx, toolName, false, "approval required", causal); err != nil {
			return nil, err
		}
		_, err = g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_approval_required", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"tool": toolName, "approval_id": approval.ApprovalID, "approval_key": approvalKey, "risk_level": spec.RiskLevel}})
		if err != nil {
			return nil, err
		}
		return nil, ApprovalRequiredError{ApprovalID: approval.ApprovalID, Reason: fmt.Sprintf("approval required for tool %s", toolName)}
	}
	if err := g.recordPermission(agentCtx, toolName, allowed, reason, causal); err != nil {
		return nil, err
	}
	if !allowed {
		return nil, PermissionDeniedError{Reason: reason}
	}
	if err := g.Budget.BeforeToolCall(g.Store, agentCtx.RunID); err != nil {
		_, appendErr := g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "budget_check_failed", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"category": "tool", "tool": toolName, "error": err.Error()}})
		if appendErr != nil {
			return nil, appendErr
		}
		return nil, err
	}

	if managedSideEffect {
		existing, err := g.Store.ReserveLedger(LedgerReservation{
			RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, ToolName: toolName,
			ToolVersion: spec.Version, ToolCallID: newID("toolcall"), IdempotencyKey: idempotencyKey,
			CausalToken: causal, RequestHash: requestHash, RequestRef: requestRef,
		})
		if err != nil {
			return nil, err
		}
		if existing != nil {
			switch existing.Status {
			case "SUCCEEDED":
				_, err := g.Store.AppendEvent(AppendEventInput{
					RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_completed",
					AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal,
					PayloadHash: existing.ResponseHash, PayloadRef: existing.ResponseRef,
					Payload: JSONObject{"tool": toolName, "idempotency_key": idempotencyKey, "replayed_from_ledger": true},
				})
				if err != nil {
					return nil, err
				}
				_, err = g.Store.RecordCost(CostRecordInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Category: "tool", Name: toolName, Amount: 1, Unit: "call", Metadata: JSONObject{"replayed_from_ledger": true}})
				return existing.Response, err
			case "PENDING_VERIFICATION":
				return nil, errors.New("tool side effect pending verification")
			default:
				return nil, errors.New("tool side effect already in progress")
			}
		}
		if err := g.Store.UpdateLedger(LedgerUpdate{IdempotencyKey: idempotencyKey, Status: "RUNNING"}); err != nil {
			return nil, err
		}
	}

	result, err := g.executeTool(ctx, agentCtx, spec, args, causal)
	if err != nil {
		if managedSideEffect {
			_ = g.Store.UpdateLedger(LedgerUpdate{IdempotencyKey: idempotencyKey, Status: "PENDING_VERIFICATION", ErrorType: fmt.Sprintf("%T", err)})
		}
		_, appendErr := g.Store.AppendEvent(AppendEventInput{
			RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_failed",
			AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal,
			Payload: JSONObject{"tool": toolName, "error": err.Error()},
		})
		if appendErr != nil {
			return nil, appendErr
		}
		return nil, err
	}
	if err := ValidateToolSchema(spec.OutputSchema, result, "$result"); err != nil {
		if managedSideEffect {
			_ = g.Store.UpdateLedger(LedgerUpdate{IdempotencyKey: idempotencyKey, Status: "PENDING_VERIFICATION", ErrorType: "ToolOutputValidationError"})
		}
		_, appendErr := g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_failed", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"tool": toolName, "error": err.Error(), "phase": "output_validation"}})
		if appendErr != nil {
			return nil, appendErr
		}
		return nil, err
	}
	responseHash, err := sha256JSON(result)
	if err != nil {
		return nil, err
	}
	responseRef := mustJSON(result)
	if managedSideEffect {
		externalID := ""
		if asMap, ok := result.(map[string]any); ok {
			if value, ok := asMap["external_id"].(string); ok {
				externalID = value
			}
		}
		if err := g.Store.UpdateLedger(LedgerUpdate{IdempotencyKey: idempotencyKey, Status: "SUCCEEDED", ExternalID: externalID, ResponseHash: responseHash, ResponseRef: responseRef, Response: result}); err != nil {
			return nil, err
		}
	}
	_, err = g.Store.AppendEvent(AppendEventInput{
		RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_call_completed",
		AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal,
		PayloadHash: responseHash, PayloadRef: responseRef,
		Payload: JSONObject{"tool": toolName, "idempotency_key": idempotencyKey},
	})
	if err != nil {
		return nil, err
	}
	_, err = g.Store.RecordCost(CostRecordInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Category: "tool", Name: toolName, Amount: 1, Unit: "call", Metadata: JSONObject{"side_effect": spec.SideEffect, "sandboxed": spec.SandboxRequired, "sandbox_executor": spec.SandboxExecutor}})
	if err != nil {
		return nil, err
	}
	return result, nil
}

func (g *ToolGateway) recordPermission(agentCtx *AgentContext, toolName string, allowed bool, reason, causal string) error {
	_, err := g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "tool_permission_decided", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"tool": toolName, "allowed": allowed, "reason": reason}})
	return err
}

func (g *ToolGateway) executeTool(ctx context.Context, agentCtx *AgentContext, spec ToolSpec, args JSONObject, causal string) (any, error) {
	if !spec.SandboxRequired {
		return spec.Func(ctx, cloneJSONObject(args))
	}
	executorName := nonempty(spec.SandboxExecutor, "default")
	policy := SandboxPolicy{ToolName: spec.Name, RunID: agentCtx.RunID, StepID: agentCtx.StepID, Executor: executorName, IsolationLevel: "unknown", Network: "deny", Filesystem: "read-only", TimeoutSeconds: 30, Extra: cloneJSONObject(spec.SandboxPolicy)}
	if network, ok := spec.SandboxPolicy["network"].(string); ok {
		policy.Network = network
	}
	if fs, ok := spec.SandboxPolicy["filesystem"].(string); ok {
		policy.Filesystem = fs
	}
	if timeout, ok := spec.SandboxPolicy["timeout_seconds"].(float64); ok {
		policy.TimeoutSeconds = int(timeout)
	}
	_, err := g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "sandbox_started", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"tool_name": policy.ToolName, "executor": policy.Executor, "network": policy.Network, "filesystem": policy.Filesystem, "timeout_seconds": policy.TimeoutSeconds}})
	if err != nil {
		return nil, err
	}
	executor := g.Sandbox
	if executor == nil {
		executor = DisabledSandboxExecutor{}
	}
	result := executor.RunTool(ctx, spec, cloneJSONObject(args), policy)
	_, err = g.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "sandbox_completed", AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion, CausalToken: causal, Payload: JSONObject{"ok": result.OK, "error": result.Error, "metadata": result.Metadata}})
	if err != nil {
		return nil, err
	}
	if !result.OK {
		return nil, SandboxUnavailableError{Reason: nonempty(result.Error, "sandboxed tool failed")}
	}
	return result.Output, nil
}

func nonempty(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func ValidateToolSchema(schema JSONObject, value any, path string) error {
	if len(schema) == 0 {
		return nil
	}
	if path == "" {
		path = "$"
	}
	if expected, ok := schema["const"]; ok && fmt.Sprintf("%#v", expected) != fmt.Sprintf("%#v", value) {
		return fmt.Errorf("%s expected const %v", path, expected)
	}
	if enum, ok := asSlice(schema["enum"]); ok {
		matched := false
		for _, item := range enum {
			if fmt.Sprintf("%#v", item) == fmt.Sprintf("%#v", value) {
				matched = true
				break
			}
		}
		if !matched {
			return fmt.Errorf("%s value not in enum", path)
		}
	}
	if typ, ok := schema["type"].(string); ok {
		switch typ {
		case "object":
			object, ok := asJSONObject(value)
			if !ok {
				return fmt.Errorf("%s expected object", path)
			}
			if required, ok := asStringSlice(schema["required"]); ok {
				for _, key := range required {
					if _, exists := object[key]; !exists {
						return fmt.Errorf("%s.%s is required", path, key)
					}
				}
			}
			properties, _ := asJSONObject(schema["properties"])
			for key, propertySchema := range properties {
				if child, exists := object[key]; exists {
					childSchema, ok := asJSONObject(propertySchema)
					if !ok {
						return fmt.Errorf("%s.%s schema must be object", path, key)
					}
					if err := ValidateToolSchema(childSchema, child, path+"."+key); err != nil {
						return err
					}
				}
			}
			if additional, ok := schema["additionalProperties"].(bool); ok && !additional {
				for key := range object {
					if _, allowed := properties[key]; !allowed {
						return fmt.Errorf("%s.%s is not allowed", path, key)
					}
				}
			}
		case "string":
			text, ok := value.(string)
			if !ok {
				return fmt.Errorf("%s expected string", path)
			}
			if min, ok := asFloat(schema["minLength"]); ok && float64(len(text)) < min {
				return fmt.Errorf("%s shorter than minLength", path)
			}
			if max, ok := asFloat(schema["maxLength"]); ok && float64(len(text)) > max {
				return fmt.Errorf("%s longer than maxLength", path)
			}
		case "number", "integer":
			number, ok := asFloat(value)
			if !ok {
				return fmt.Errorf("%s expected number", path)
			}
			if typ == "integer" && number != float64(int(number)) {
				return fmt.Errorf("%s expected integer", path)
			}
			if min, ok := asFloat(schema["minimum"]); ok && number < min {
				return fmt.Errorf("%s below minimum", path)
			}
			if max, ok := asFloat(schema["maximum"]); ok && number > max {
				return fmt.Errorf("%s above maximum", path)
			}
		case "boolean":
			if _, ok := value.(bool); !ok {
				return fmt.Errorf("%s expected boolean", path)
			}
		}
	}
	return nil
}

func asJSONObject(value any) (JSONObject, bool) {
	switch item := value.(type) {
	case JSONObject:
		return item, true
	case map[string]any:
		return JSONObject(item), true
	default:
		return nil, false
	}
}

func asSlice(value any) ([]any, bool) {
	items, ok := value.([]any)
	return items, ok
}

func asStringSlice(value any) ([]string, bool) {
	items, ok := value.([]any)
	if !ok {
		return nil, false
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		text, ok := item.(string)
		if !ok {
			return nil, false
		}
		out = append(out, text)
	}
	return out, true
}

func asFloat(value any) (float64, bool) {
	switch item := value.(type) {
	case int:
		return float64(item), true
	case int64:
		return float64(item), true
	case float64:
		return item, true
	case float32:
		return float64(item), true
	default:
		return 0, false
	}
}
