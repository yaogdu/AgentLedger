package agentledger

import (
	"context"
	"fmt"
	"sort"
)

type GoldenCase struct {
	Name       string     `json:"name"`
	BundleHash string     `json:"bundle_hash,omitempty"`
	Metadata   JSONObject `json:"metadata"`
}

func BuiltinGoldenNames() []string {
	names := []string{"minimal-success", "tool-ledger-success", "media-stream-checkpoint"}
	sort.Strings(names)
	return names
}

func BuiltinGoldenEvidence(name string) (EvidenceBundle, error) {
	switch name {
	case "minimal-success":
		return goldenMinimalSuccess()
	case "tool-ledger-success":
		return goldenToolLedgerSuccess()
	case "media-stream-checkpoint":
		return goldenMediaStreamCheckpoint()
	default:
		return EvidenceBundle{}, fmt.Errorf("unknown built-in golden case: %s", name)
	}
}

func GoldenRegression(golden, current EvidenceBundle) EvidenceCheckReport {
	return EvaluateEvidenceRegression(golden, current, nil)
}

func goldenMinimalSuccess() (EvidenceBundle, error) {
	rt := NewRuntime(NewMemoryStore())
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		return EvidenceBundle{}, err
	}
	_, err = rt.RunOnce(context.Background(), runID, "golden-worker", "GoldenAgent", 60, func(_ context.Context, ctx *AgentContext, _ JSONObject) error { return ctx.WriteState("answer", "ok") })
	if err != nil {
		return EvidenceBundle{}, err
	}
	return ExportEvidence(rt.Store, runID)
}
func goldenToolLedgerSuccess() (EvidenceBundle, error) {
	rt := NewRuntime(NewMemoryStore())
	_ = rt.RegisterTool(ToolSpec{Name: "github.create_issue", Version: "v1", SideEffect: "external", Func: func(_ context.Context, _ JSONObject) (any, error) { return JSONObject{"issue_id": "ISSUE-1"}, nil }})
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		return EvidenceBundle{}, err
	}
	_, err = rt.RunOnce(context.Background(), runID, "golden-worker", "ExecutorAgent", 60, func(ctx context.Context, agentCtx *AgentContext, _ JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "github.create_issue", JSONObject{"title": "golden"})
		if err != nil {
			return err
		}
		if obj, ok := result.(JSONObject); ok {
			return agentCtx.WriteState("issue_id", obj["issue_id"])
		}
		return agentCtx.WriteState("issue_id", "ISSUE-1")
	})
	if err != nil {
		return EvidenceBundle{}, err
	}
	return ExportEvidence(rt.Store, runID)
}
func goldenMediaStreamCheckpoint() (EvidenceBundle, error) {
	rt := NewRuntime(NewMemoryStore())
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		return EvidenceBundle{}, err
	}
	_, err = rt.RunOnce(context.Background(), runID, "golden-worker", "MediaAgent", 60, func(_ context.Context, ctx *AgentContext, _ JSONObject) error {
		if _, err := ctx.CreateMediaArtifact("golden-video-frame", "frame", MediaArtifactOptions{URI: "file://golden-frame.jpg"}); err != nil {
			return err
		}
		if _, err := ctx.CreateStreamCheckpoint("golden-stream-checkpoint", StreamCheckpointOptions{StreamID: "stream-golden", ConsumerID: "consumer-golden", Offset: 42}); err != nil {
			return err
		}
		return ctx.WriteState("processed_offset", 42)
	})
	if err != nil {
		return EvidenceBundle{}, err
	}
	return ExportEvidence(rt.Store, runID)
}
