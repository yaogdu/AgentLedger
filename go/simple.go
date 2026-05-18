package agentledger

import "context"

type SimpleAgentFunc func(context.Context, *AgentContext, JSONObject) (any, error)

type RunResult struct {
	RunID     string     `json:"run_id"`
	SessionID string     `json:"session_id"`
	OK        bool       `json:"ok"`
	Output    any        `json:"output,omitempty"`
	State     JSONObject `json:"state"`
	Runtime   *Runtime   `json:"-"`
}

func SimpleRun(ctx context.Context, agent SimpleAgentFunc, initialState JSONObject) (RunResult, error) {
	rt := NewRuntime(NewMemoryStore())
	return SimpleRunWithRuntime(ctx, rt, agent, initialState)
}

func SimpleRunWithRuntime(ctx context.Context, rt *Runtime, agent SimpleAgentFunc, initialState JSONObject) (RunResult, error) {
	if rt == nil {
		rt = NewRuntime(NewMemoryStore())
	}
	runID, _, err := rt.CreateRun(initialState)
	if err != nil {
		return RunResult{}, err
	}
	ok, err := rt.RunOnce(ctx, runID, "worker-simple", "Agent", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		output, err := agent(ctx, agentCtx, state)
		if err != nil {
			return err
		}
		if output != nil {
			if _, err := agentCtx.Store.AppendEvent(AppendEventInput{RunID: agentCtx.RunID, SessionID: agentCtx.SessionID, StepID: agentCtx.StepID, Type: "agent_result_returned", Payload: JSONObject{"agent": "agent"}, AgentRole: agentCtx.AgentRole, StateVersion: agentCtx.StateVersion}); err != nil {
				return err
			}
			return agentCtx.WriteState("output", output)
		}
		return nil
	})
	if err != nil {
		return RunResult{}, err
	}
	state, err := rt.Store.FinalState(runID)
	if err != nil {
		return RunResult{}, err
	}
	run, err := rt.Store.Run(runID)
	if err != nil {
		return RunResult{}, err
	}
	return RunResult{RunID: runID, SessionID: run.SessionID, OK: ok, Output: state["output"], State: state, Runtime: rt}, nil
}
