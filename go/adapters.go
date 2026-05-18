package agentledger

import "context"

type FrameworkAgentFunc func(context.Context, *AgentContext, JSONObject) (any, error)

type FunctionAdapter struct {
	Func FrameworkAgentFunc
	Role string
	Name string
}

func NewFunctionAdapter(fn FrameworkAgentFunc, role string) FunctionAdapter {
	if role == "" {
		role = "Agent"
	}
	return FunctionAdapter{Func: fn, Role: role, Name: "function"}
}

func (a FunctionAdapter) MapRunSpec() JSONObject {
	return JSONObject{"adapter": a.Name, "role": a.Role}
}

func (a FunctionAdapter) AsAgent(outputKey string) AgentFunc {
	return func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := a.Func(ctx, agentCtx, state)
		if err != nil {
			return err
		}
		if outputKey != "" && result != nil {
			return agentCtx.WriteState(outputKey, result)
		}
		return nil
	}
}

type MethodHandler func(JSONObject) (any, error)

type MethodFrameworkAdapter struct {
	TargetName       string
	Role             string
	MethodCandidates []string
	Methods          map[string]MethodHandler
	OutputKey        string
}

func NewMethodFrameworkAdapter(targetName, role string, candidates []string, methods map[string]MethodHandler, outputKey string) MethodFrameworkAdapter {
	if role == "" {
		role = "FrameworkAgent"
	}
	if outputKey == "" {
		outputKey = "output"
	}
	return MethodFrameworkAdapter{TargetName: targetName, Role: role, MethodCandidates: candidates, Methods: methods, OutputKey: outputKey}
}

func (a MethodFrameworkAdapter) MapRunSpec() JSONObject {
	return JSONObject{"adapter": "method-framework", "role": a.Role, "target": a.TargetName, "methods": a.MethodCandidates}
}

func (a MethodFrameworkAdapter) AsAgent() AgentFunc {
	return func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		for _, name := range a.MethodCandidates {
			method := a.Methods[name]
			if method == nil {
				continue
			}
			result, err := method(state)
			if err != nil {
				return err
			}
			if a.OutputKey != "" {
				return agentCtx.WriteState(a.OutputKey, result)
			}
			return nil
		}
		return agentCtx.WriteState("adapter_error", "no method candidate matched")
	}
}
