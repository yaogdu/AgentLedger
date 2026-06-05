package agentledger

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRuntimeCreatesDurableRunEvidenceAndReplay(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.json")
	rt, err := NewLocalRuntime(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := rt.RegisterTool(ToolSpec{Name: "docs.echo", Version: "v1", SideEffect: "none", Func: func(ctx context.Context, args JSONObject) (any, error) {
		return JSONObject{"echo": args["text"]}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{"input": "hello"})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-a", "Researcher", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "docs.echo", JSONObject{"text": state["input"]})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("tool_result", result)
	})
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("expected run_once to complete")
	}

	reopened, err := NewJSONStore(path)
	if err != nil {
		t.Fatal(err)
	}
	state, err := reopened.FinalState(runID)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := state["tool_result"].(map[string]any); !ok {
		t.Fatalf("expected durable tool_result in state, got %#v", state)
	}
	bundle, err := ExportEvidence(reopened, runID)
	if err != nil {
		t.Fatal(err)
	}
	if bundle.SchemaVersion != "agentledger.evidence.v1" || bundle.BundleHash == "" {
		t.Fatalf("invalid evidence bundle: %#v", bundle)
	}
	if got := int(bundle.Summary["event_count"].(int)); got == 0 {
		t.Fatal("expected evidence events")
	}
	replay, err := Replay(reopened, runID)
	if err != nil {
		t.Fatal(err)
	}
	if !replay.ReplaySafe || replay.EventCount != len(bundle.Events) || replay.ToolCallCount != 2 {
		t.Fatalf("unexpected replay summary: %#v", replay)
	}
}

func TestLocalBlobStoreRoundTripsJSON(t *testing.T) {
	blobs, err := NewLocalBlobStore(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	value := JSONObject{"hello": "world", "nested": JSONObject{"n": 1}}
	digest, ref, err := blobs.PutJSON(value)
	if err != nil {
		t.Fatal(err)
	}
	digest2, ref2, err := blobs.PutJSON(value)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(digest, "sha256:") || !strings.HasPrefix(ref, "blob://sha256/") || digest != digest2 || ref != ref2 {
		t.Fatalf("unexpected digest/ref: %s %s / %s %s", digest, ref, digest2, ref2)
	}
	read, err := blobs.GetJSON(ref)
	if err != nil {
		t.Fatal(err)
	}
	encodedRead, _ := json.Marshal(read)
	encodedValue, _ := json.Marshal(value)
	if string(encodedRead) != string(encodedValue) {
		t.Fatalf("roundtrip mismatch: %s != %s", encodedRead, encodedValue)
	}
	if _, err := blobs.GetJSON("unsupported://blob"); err == nil {
		t.Fatal("expected unsupported ref to fail")
	}
}

func TestToolSchemaValidationRejectsInvalidInputAndOutput(t *testing.T) {
	inputSchema := JSONObject{"type": "object", "required": []any{"text"}, "additionalProperties": false, "properties": JSONObject{"text": JSONObject{"type": "string", "minLength": 1}}}
	outputSchema := JSONObject{"type": "object", "required": []any{"echo"}, "additionalProperties": false, "properties": JSONObject{"echo": JSONObject{"type": "string"}}}
	calls := 0
	rt := NewRuntime(NewMemoryStore())
	if err := rt.RegisterTool(ToolSpec{Name: "docs.echo", InputSchema: inputSchema, OutputSchema: outputSchema, Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"echo": args["text"]}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "SchemaAgent", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "docs.echo", JSONObject{})
		return err
	})
	if err == nil || ok || calls != 0 {
		t.Fatalf("expected invalid input before execution, ok=%v err=%v calls=%d", ok, err, calls)
	}
	runID, _, err = rt.CreateRun(JSONObject{"text": "hello"})
	if err != nil {
		t.Fatal(err)
	}
	ok, err = rt.RunOnce(context.Background(), runID, "worker", "SchemaAgent", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "docs.echo", JSONObject{"text": state["text"]})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("result", result)
	})
	if err != nil || !ok || calls != 1 {
		t.Fatalf("expected valid schema call, ok=%v err=%v calls=%d", ok, err, calls)
	}
}

func TestToolLedgerIdempotencyAcrossRetry(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(ToolSpec{Name: "github.create_pr", Version: "v1", SideEffect: "external", IdempotencyRequired: true, Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"external_id": "pr-123", "title": args["title"]}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{"title": "runtime parity"})
	if err != nil {
		t.Fatal(err)
	}
	agent := func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "github.create_pr", JSONObject{"title": state["title"]})
		if err != nil {
			return err
		}
		if agentCtx.Attempt == 1 {
			return ErrRetryable
		}
		return agentCtx.WriteState("pr", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-a", "Coder", 60, agent)
	if err != nil {
		t.Fatal(err)
	}
	if ok {
		t.Fatal("first attempt should schedule retry")
	}
	ok, err = rt.RunOnce(context.Background(), runID, "worker-b", "Coder", 60, agent)
	if err != nil {
		t.Fatal(err)
	}
	if !ok {
		t.Fatal("second attempt should complete")
	}
	if calls != 1 {
		t.Fatalf("tool should execute once and replay from ledger on retry, got calls=%d", calls)
	}
	ledger := rt.Store.Ledger(runID)
	if len(ledger) != 1 || ledger[0].Status != "SUCCEEDED" {
		t.Fatalf("unexpected ledger: %#v", ledger)
	}
}

func TestPolicyDeniesUnapprovedHighRiskTool(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(ToolSpec{Name: "repo.write", RiskLevel: "high", Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"ok": true}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Reviewer", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "repo.write", JSONObject{"path": "README.md"})
		return err
	})
	if err == nil || ok {
		t.Fatalf("expected denied tool to fail run, ok=%v err=%v", ok, err)
	}
	if calls != 0 {
		t.Fatalf("denied tool should not execute, calls=%d", calls)
	}
	if !eventPayloadContains(rt.Store.Events(runID), "tool_permission_decided", "allowed", false) {
		t.Fatal("expected denied permission decision event")
	}
}

func TestApprovalPausesAndResumesStep(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(ToolSpec{Name: "github.create_pr", RiskLevel: "high", ApprovalRequired: true, SideEffect: "external", IdempotencyRequired: true, Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"external_id": "pr-42"}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	agent := func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "github.create_pr", JSONObject{"title": "safe"})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("pr", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-a", "Coder", 60, agent)
	if err != nil || ok {
		t.Fatalf("expected approval pause without error, ok=%v err=%v", ok, err)
	}
	if calls != 0 {
		t.Fatalf("approval-required tool should not execute before approval, calls=%d", calls)
	}
	approvals := rt.Store.ApprovalRequests(runID)
	if len(approvals) != 1 || approvals[0].Status != ApprovalPending {
		t.Fatalf("expected one pending approval, got %#v", approvals)
	}
	steps := rt.Store.Steps(runID)
	if len(steps) != 1 || steps[0].Status != "waiting_human" {
		t.Fatalf("expected waiting_human step, got %#v", steps)
	}
	if _, err := rt.Store.ApproveRequest(approvals[0].ApprovalID, "alice", "reviewed"); err != nil {
		t.Fatal(err)
	}
	ok, err = rt.RunOnce(context.Background(), runID, "worker-b", "Coder", 60, agent)
	if err != nil || !ok {
		t.Fatalf("expected approved step to resume, ok=%v err=%v", ok, err)
	}
	if calls != 1 {
		t.Fatalf("approved tool should execute once, calls=%d", calls)
	}

	runID2, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err = rt.RunOnce(context.Background(), runID2, "worker-c", "Coder", 60, agent)
	if err != nil || ok {
		t.Fatalf("expected second approval pause, ok=%v err=%v", ok, err)
	}
	approvals2 := rt.Store.ApprovalRequests(runID2)
	if _, err := rt.Store.DenyRequest(approvals2[0].ApprovalID, "bob", "not allowed"); err != nil {
		t.Fatal(err)
	}
	if status := rt.Store.Steps(runID2)[0].Status; status != "failed" {
		t.Fatalf("denied approval should fail step, got %s", status)
	}
}

func TestMCPToolAdapterMapsGovernanceAnnotations(t *testing.T) {
	adapter := MCPToolAdapter{ClientCall: func(name string, args JSONObject) (any, error) {
		return JSONObject{"ok": true}, nil
	}}
	spec := adapter.ToolSpecFromDescriptor(JSONObject{
		"name": "mcp.github.create_pr",
		"inputSchema": JSONObject{
			"type":     "object",
			"required": []any{"title"},
		},
		"annotations": JSONObject{
			"side_effect":          "external_write",
			"risk_level":           "high",
			"idempotency_required": true,
			"approval_required":    true,
			"sandbox_required":     true,
			"sandbox_executor":     "docker",
			"sandbox_policy": JSONObject{
				"network":    "deny",
				"filesystem": "read-only",
			},
		},
	})
	if spec.SideEffect != "external_write" || spec.RiskLevel != "high" || !spec.IdempotencyRequired || !spec.ApprovalRequired || !spec.SandboxRequired {
		t.Fatalf("governance annotations not mapped: %#v", spec)
	}
	if spec.SandboxExecutor != "docker" || spec.SandboxPolicy["network"] != "deny" || spec.SandboxPolicy["filesystem"] != "read-only" {
		t.Fatalf("sandbox annotations not mapped: %#v", spec)
	}
	if spec.InputSchema["type"] != "object" {
		t.Fatalf("input schema not mapped: %#v", spec.InputSchema)
	}
}

func TestSandboxRequiredToolFailsClosed(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(ToolSpec{Name: "shell.exec", RiskLevel: "low", SandboxRequired: true, Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"ok": true}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Executor", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "shell.exec", JSONObject{"argv": []any{"echo", "hi"}})
		return err
	})
	if err == nil || ok {
		t.Fatalf("expected sandbox fail-closed error, ok=%v err=%v", ok, err)
	}
	if calls != 0 {
		t.Fatalf("sandbox-required tool should not execute without sandbox, calls=%d", calls)
	}
	if !eventTypeExists(rt.Store.Events(runID), "sandbox_started") || !eventTypeExists(rt.Store.Events(runID), "tool_call_failed") {
		t.Fatal("expected sandbox and tool failure events")
	}
}

func TestDockerSandboxExecutorRequiresExplicitExecution(t *testing.T) {
	executor := DockerSandboxExecutor{}
	result := executor.RunTool(context.Background(), ToolSpec{Name: "shell.exec"}, JSONObject{"_sandbox_command": []any{"echo", "hi"}}, SandboxPolicy{Executor: "docker", Network: "deny", TimeoutSeconds: 1})
	if result.OK || result.Metadata["error_type"] != "SandboxAdapterNotInstalled" {
		t.Fatalf("expected docker executor to fail closed without explicit execution, got %#v", result)
	}
}

func TestDockerSandboxExecutorRunsCommandStyleToolWithInjectedBinary(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	rt.SetSandbox(DockerSandboxExecutor{Binary: "/bin/echo", Image: "fake-image", AllowCommandExecution: true})
	if err := rt.RegisterTool(ToolSpec{Name: "cmd.echo", SandboxRequired: true, SandboxExecutor: "docker", Func: func(ctx context.Context, args JSONObject) (any, error) {
		t.Fatalf("sandboxed command-style tool should execute through docker executor, not direct func")
		return nil, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-docker", "Executor", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "cmd.echo", JSONObject{"_sandbox_command": []any{"echo", "hi"}})
		if err != nil {
			return err
		}
		output := result.(JSONObject)
		stdout := output["stdout"].(string)
		if !strings.Contains(stdout, "run") || !strings.Contains(stdout, "fake-image") {
			t.Fatalf("expected docker argv in fake binary stdout, got %q", stdout)
		}
		return agentCtx.WriteState("sandbox_result", output)
	})
	if err != nil || !ok {
		t.Fatalf("docker sandbox run mismatch ok=%v err=%v", ok, err)
	}
	events := rt.Store.Events(runID)
	if !eventTypeExists(events, "sandbox_completed") || !eventTypeExists(events, "tool_call_completed") {
		t.Fatalf("missing sandbox/tool events: %#v", events)
	}
}

type fakeSQLExecutor struct {
	queries []string
	args    [][]any
}

func (f *fakeSQLExecutor) Exec(ctx context.Context, query string, args ...any) error {
	f.queries = append(f.queries, query)
	f.args = append(f.args, args)
	return nil
}

func TestPostgresAdapterUsesInjectedSQLExecutor(t *testing.T) {
	client := &fakeSQLExecutor{}
	adapter := NewPostgresAdapter("", client)
	if err := adapter.ApplyMigrations(context.Background()); err != nil {
		t.Fatal(err)
	}
	if adapter.Schema != "agentledger" {
		t.Fatalf("expected default schema, got %s", adapter.Schema)
	}
	if len(client.queries) < 2 {
		t.Fatalf("expected DDL plus migration insert queries, got %#v", client.queries)
	}
	if !strings.Contains(client.queries[0], "CREATE TABLE IF NOT EXISTS runs") {
		t.Fatalf("expected postgres DDL first, got %s", client.queries[0])
	}
	if !strings.Contains(client.queries[1], "INSERT INTO schema_migrations") || len(client.args[1]) != 3 {
		t.Fatalf("expected schema migration insert with args, got query=%s args=%#v", client.queries[1], client.args[1])
	}
}

func TestMySQLAdapterUsesInjectedSQLExecutor(t *testing.T) {
	client := &fakeSQLExecutor{}
	adapter := NewMySQLAdapter("", client)
	plan, err := adapter.MigrationPlan()
	if err != nil {
		t.Fatalf("migration plan failed: %v", err)
	}
	if len(plan) != 1 || plan[0].Dialect != "mysql" {
		t.Fatalf("unexpected migration plan: %#v", plan)
	}
	if err := adapter.ApplyMigrations(context.Background()); err != nil {
		t.Fatalf("apply migrations failed: %v", err)
	}
	if adapter.Database != "agentledger" {
		t.Fatalf("expected default database, got %s", adapter.Database)
	}
	if len(client.queries) < 2 {
		t.Fatalf("expected DDL plus migration insert queries, got %#v", client.queries)
	}
	if !strings.Contains(client.queries[0], "CREATE TABLE IF NOT EXISTS runs") {
		t.Fatalf("expected mysql DDL first, got %s", client.queries[0])
	}
	if !strings.Contains(client.queries[1], "ON DUPLICATE KEY UPDATE") || len(client.args[1]) != 3 {
		t.Fatalf("expected mysql migration insert with args, got query=%s args=%#v", client.queries[1], client.args[1])
	}
}

type fakeObjectClient struct {
	objects map[string][]byte
	puts    []ObjectPutInput
}

func (f *fakeObjectClient) PutObject(ctx context.Context, input ObjectPutInput) error {
	if f.objects == nil {
		f.objects = map[string][]byte{}
	}
	f.puts = append(f.puts, input)
	f.objects[input.Bucket+"/"+input.Key] = append([]byte(nil), input.Body...)
	return nil
}

func (f *fakeObjectClient) GetObject(ctx context.Context, bucket string, key string) (ObjectGetOutput, error) {
	body, ok := f.objects[bucket+"/"+key]
	if !ok {
		return ObjectGetOutput{}, errors.New("object not found")
	}
	return ObjectGetOutput{Body: append([]byte(nil), body...)}, nil
}

func TestS3BlobStoreUsesInjectedObjectClient(t *testing.T) {
	client := &fakeObjectClient{}
	blobs := NewS3BlobStore("agentledger-test", "", client)
	digest, ref, err := blobs.PutJSON(context.Background(), JSONObject{"hello": "world"})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(digest, "sha256:") || !strings.HasPrefix(ref, "s3://agentledger-test/agentledger/blobs/sha256/") {
		t.Fatalf("unexpected digest/ref: %s %s", digest, ref)
	}
	if len(client.puts) != 1 || client.puts[0].ContentType != "application/json" || client.puts[0].Metadata["agentledger-digest"] != digest {
		t.Fatalf("unexpected put object call: %#v", client.puts)
	}
	value, err := blobs.GetJSON(context.Background(), ref)
	if err != nil {
		t.Fatal(err)
	}
	if value.(map[string]any)["hello"] != "world" {
		t.Fatalf("unexpected roundtrip value: %#v", value)
	}
	if _, err := blobs.GetJSON(context.Background(), "s3://agentledger-test/../bad.json"); err == nil {
		t.Fatal("expected unsafe s3 ref to be rejected")
	}
}

func TestCostBudgetAndFailureAttribution(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	rt.SetBudget(BudgetLimits{MaxToolCalls: 1})
	calls := 0
	if err := rt.RegisterTool(ToolSpec{Name: "docs.echo", Func: func(ctx context.Context, args JSONObject) (any, error) {
		calls++
		return JSONObject{"echo": args["text"]}, nil
	}}); err != nil {
		t.Fatal(err)
	}
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Researcher", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		if err := agentCtx.RecordModelCall("gpt-test", 10, 5, 0.01); err != nil {
			return err
		}
		if _, err := agentCtx.CallTool(ctx, "docs.echo", JSONObject{"text": "first"}); err != nil {
			return err
		}
		_, err := agentCtx.CallTool(ctx, "docs.echo", JSONObject{"text": "second"})
		return err
	})
	if err == nil || ok {
		t.Fatalf("expected budget error, ok=%v err=%v", ok, err)
	}
	if calls != 1 {
		t.Fatalf("second tool call should be blocked by budget, calls=%d", calls)
	}
	summary := rt.Store.CostSummary(runID)
	if summary.ToolCalls != 1 || summary.ModelTokens != 15 || summary.TotalUSD != 0.01 {
		t.Fatalf("unexpected cost summary: %#v", summary)
	}
	report := CostAttribution(rt.Store, runID)
	if report.ByAgent["Researcher"].ToolCalls != 1 || report.ByAgent["Researcher"].ModelTokens != 15 {
		t.Fatalf("unexpected cost attribution: %#v", report)
	}
	failure, err := FailureAttribution(rt.Store, runID)
	if err != nil {
		t.Fatal(err)
	}
	if failure.Summary["failed_step_count"].(int) != 1 || !eventTypeExists(failure.FailureEvents, "budget_check_failed") || !eventTypeExists(failure.FailureEvents, "failure_classified") {
		t.Fatalf("unexpected failure attribution: %#v", failure)
	}
}

func TestMediaAndStreamArtifactsParity(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-media", "MediaAgent", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		frameID, err := agentCtx.CreateMediaArtifact("frame-0001", "frame", MediaArtifactOptions{
			URI:           "s3://media/demo/frame-0001.jpg",
			MediaMetadata: JSONObject{"mime_type": "image/jpeg", "frame_index": 1},
			Lineage:       JSONObject{"source_blob_refs": []any{"s3://media/demo/input.mp4"}, "tool_call_ids": []any{"video.extract_frames"}},
		})
		if err != nil {
			return err
		}
		checkpointID, err := agentCtx.CreateStreamCheckpoint("camera-checkpoint", StreamCheckpointOptions{
			StreamID:     "camera-1",
			ConsumerID:   "vision-agent",
			Offset:       7,
			Watermark:    1.5,
			Chunk:        StreamChunkRef{StreamID: "camera-1", ChunkID: "chunk-7", Offset: 7, ContentRef: "blob://sha256/chunk-7.json", Sequence: 7},
			Backpressure: JSONObject{"recommended_pause_ms": 100},
		})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("artifacts", JSONObject{"frame": frameID, "checkpoint": checkpointID})
	})
	if err != nil || !ok {
		t.Fatalf("expected media run to complete, ok=%v err=%v", ok, err)
	}
	bundle, err := ExportEvidence(rt.Store, runID)
	if err != nil {
		t.Fatal(err)
	}
	if len(bundle.Artifacts) != 2 || len(bundle.MediaArtifacts) != 1 || len(bundle.StreamCheckpoints) != 1 {
		t.Fatalf("unexpected artifact evidence: %#v", bundle.Summary)
	}
	if bundle.MediaArtifacts[0]["kind"] != "frame" || bundle.StreamCheckpoints[0]["stream_id"] != "camera-1" {
		t.Fatalf("unexpected media/stream rows: %#v %#v", bundle.MediaArtifacts, bundle.StreamCheckpoints)
	}
	summary, err := Replay(rt.Store, runID)
	if err != nil {
		t.Fatal(err)
	}
	if summary.ArtifactCount != 2 || summary.MediaArtifactCount != 1 || summary.StreamCheckpointCount != 1 {
		t.Fatalf("unexpected replay artifact counts: %#v", summary)
	}
}

func TestLeaseRecoveryFencesPreviousOwner(t *testing.T) {
	store := NewMemoryStore()
	runID, stepID, err := store.CreateRun("", JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	claim, err := store.ClaimStep("stale-worker", runID, 0)
	if err != nil {
		t.Fatal(err)
	}
	recovered, err := store.RecoverExpiredLeases()
	if err != nil {
		t.Fatal(err)
	}
	if recovered != 1 {
		t.Fatalf("expected one recovered lease, got %d", recovered)
	}
	if _, err := store.CommitStatePatch(runID, stepID, claim.LeaseToken, 0, JSONObject{"late": true}, ""); err == nil {
		t.Fatal("expected stale lease commit to be rejected")
	}
	if _, err := store.ClaimStep("new-worker", runID, 60); err != nil {
		t.Fatalf("expected recovered step to be claimable: %v", err)
	}
}

func TestCancellationFencesWorker(t *testing.T) {
	store := NewMemoryStore()
	runID, stepID, err := store.CreateRun("", JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	claim, err := store.ClaimStep("worker", runID, 60)
	if err != nil {
		t.Fatal(err)
	}
	cancelled, err := store.CancelRun(runID, "operator requested")
	if err != nil {
		t.Fatal(err)
	}
	if cancelled != 1 {
		t.Fatalf("expected one cancelled step, got %d", cancelled)
	}
	if _, err := store.CommitStatePatch(runID, stepID, claim.LeaseToken, 0, JSONObject{"late": true}, ""); err == nil {
		t.Fatal("expected cancelled worker to be fenced")
	}
}

func TestContractFixtureReadable(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("..", "contracts", "agentledger.runtime.v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	var contract struct {
		ContractVersion string `json:"contract_version"`
		LanguageTargets []struct {
			Language string `json:"language"`
			Status   string `json:"status"`
		} `json:"language_targets"`
	}
	if err := json.Unmarshal(content, &contract); err != nil {
		t.Fatal(err)
	}
	if contract.ContractVersion != "1.0" {
		t.Fatalf("unexpected contract version: %s", contract.ContractVersion)
	}
	foundGo := false
	for _, target := range contract.LanguageTargets {
		if target.Language == "go" {
			foundGo = true
		}
	}
	if !foundGo {
		t.Fatal("contract fixture should include the Go language target")
	}
}

func TestRunOncePropagatesNonRetryableError(t *testing.T) {
	rt := NewRuntime(NewMemoryStore())
	runID, _, err := rt.CreateRun(JSONObject{})
	if err != nil {
		t.Fatal(err)
	}
	boom := errors.New("boom")
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Agent", 60, func(ctx context.Context, agentCtx *AgentContext, state JSONObject) error {
		return boom
	})
	if ok || !errors.Is(err, boom) {
		t.Fatalf("expected non-retryable error to propagate, ok=%v err=%v", ok, err)
	}
	steps := rt.Store.Steps(runID)
	if len(steps) != 1 || steps[0].Status != "failed" {
		t.Fatalf("expected failed step, got %#v", steps)
	}
}

func TestSharedRuntimeBaselineFixture(t *testing.T) {
	content, err := os.ReadFile(filepath.Join("..", "contracts", "conformance", "runtime_baseline.v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		SchemaVersion     string `json:"schema_version"`
		ContractVersion   string `json:"contract_version"`
		RequiredScenarios []struct {
			Name               string   `json:"name"`
			RequiredAssertions []string `json:"required_assertions"`
		} `json:"required_scenarios"`
	}
	if err := json.Unmarshal(content, &fixture); err != nil {
		t.Fatal(err)
	}
	if fixture.SchemaVersion != "agentledger.conformance.runtime_baseline.v1" || fixture.ContractVersion != "1.0" {
		t.Fatalf("unexpected fixture header: %#v", fixture)
	}
	want := map[string]bool{
		"durable_run_evidence_replay":        false,
		"tool_ledger_idempotent_retry":       false,
		"lease_recovery_fences_stale_worker": false,
		"cancellation_fences_worker":         false,
	}
	for _, scenario := range fixture.RequiredScenarios {
		if _, ok := want[scenario.Name]; ok {
			want[scenario.Name] = len(scenario.RequiredAssertions) > 0
		}
	}
	for name, ok := range want {
		if !ok {
			t.Fatalf("shared fixture missing required scenario %s", name)
		}
	}
}

func TestSharedParityFixtures(t *testing.T) {
	fixtures := map[string][]string{
		"policy_approval_sandbox.v1.json": {
			"agentledger.conformance.policy_approval_sandbox.v1",
			"policy_denies_unapproved_high_risk_tool",
			"approval_pauses_and_resumes_step",
			"sandbox_required_tool_fails_closed",
		},
		"cost_failure_attribution.v1.json": {
			"agentledger.conformance.cost_failure_attribution.v1",
			"tool_and_model_cost_attributed_to_run_step_role",
			"budget_exhaustion_blocks_execution",
			"failure_attribution_classifies_agent_tool_model_runtime",
		},
		"local_persistence.v1.json": {
			"agentledger.conformance.local_persistence.v1",
			"local_store_round_trips_completed_run",
			"local_store_preserves_evidence_replay_chain",
			"local_store_uses_atomic_snapshot_write",
		},
		"local_blob_store.v1.json": {
			"agentledger.conformance.local_blob_store.v1",
			"blob_roundtrip_json_value",
			"blob_content_address_is_stable",
			"blob_bad_ref_is_rejected",
		},
		"tool_schema_validation.v1.json": {
			"agentledger.conformance.tool_schema_validation.v1",
			"invalid_tool_input_rejected_before_execution",
			"valid_tool_input_and_output_pass",
			"invalid_tool_output_rejected",
		},
		"worker_service.v1.json": {
			"agentledger.conformance.worker_service.v1",
			"local_worker_runs_until_terminal",
			"worker_service_stops_after_idle_poll",
			"worker_loop_recovers_expired_leases",
		},
		"media_stream_artifacts.v1.json": {
			"agentledger.conformance.media_stream_artifacts.v1",
			"media_artifact_ref_is_indexed_in_evidence",
			"stream_checkpoint_ref_is_indexed_in_evidence",
		},
		"evidence_consumers.v1.json": {
			"agentledger.conformance.evidence_consumers.v1",
			"trace_spans_from_evidence",
			"evidence_diff_detects_state_and_event_changes",
			"divergence_report_lists_changed_dimensions",
			"static_debug_summary_is_exportable",
		},
		"static_debug_html.v1.json": {
			"agentledger.conformance.static_debug_html.v1",
			"static_debug_html_contains_run_events_and_state",
		},
		"ops_readiness.v1.json": {
			"agentledger.conformance.ops_readiness.v1",
			"retention_plan_is_non_destructive_and_counts_evidence",
			"backup_readiness_reports_required_checks",
		},
		"storage_schema.v1.json": {
			"agentledger.conformance.storage_schema.v1",
			"latest_schema_version_and_ddl_are_available",
		},
		"mcp_adapters.v1.json": {
			"agentledger.conformance.mcp_adapters.v1",
			"in_memory_mcp_tool_server_lists_and_calls_tools",
			"mcp_tool_descriptor_maps_to_tool_spec",
			"in_memory_mcp_context_server_reads_resources",
		},
		"framework_adapters.v1.json": {
			"agentledger.conformance.framework_adapters.v1",
			"function_adapter_maps_run_spec_and_invokes_agent",
			"method_framework_adapter_uses_first_available_method_and_writes_output",
		},
		"otlp_trace_export.v1.json": {
			"agentledger.conformance.otlp_trace_export.v1",
			"otlp_json_contains_resource_scope_and_spans",
		},
		"simple_api.v1.json": {
			"agentledger.conformance.simple_api.v1",
			"simple_run_returns_output_and_state",
		},
		"boundary_lint.v1.json": {
			"agentledger.conformance.boundary_lint.v1",
			"direct_shell_and_http_calls_are_reported",
			"ignored_lines_are_not_reported",
		},
		"scheduler.v1.json": {
			"agentledger.conformance.scheduler.v1",
			"scheduler_status_reports_run_steps_and_cost",
			"scheduler_recover_and_cancel_delegate_to_store",
		},
		"adversarial_review.v1.json": {
			"agentledger.conformance.adversarial_review.v1",
			"clean_evidence_passes_blocker_review",
			"pending_high_risk_approval_blocks_review",
			"max_total_usd_limit_blocks_review",
		},
		"evidence_regression.v1.json": {
			"agentledger.conformance.evidence_regression.v1",
			"evidence_health_checks_pass_for_clean_bundle",
			"regression_detects_final_state_and_event_type_changes",
			"regression_cost_delta_limit_blocks",
		},
		"failure_injection.v1.json": {
			"agentledger.conformance.failure_injection.v1",
			"retry_exhaustion_marks_run_failed",
			"lease_fencing_rejects_stale_commit",
			"cancellation_fencing_rejects_late_commit",
			"side_effect_idempotency_executes_once_across_retry",
		},
		"shadow.v1.json": {
			"agentledger.conformance.shadow.v1",
			"shadow_state_diff_reports_changed_keys",
			"shadow_report_carries_source_shadow_and_ok",
		},
		"repro.v1.json": {
			"agentledger.conformance.repro.v1",
			"builtin_golden_names_are_available",
			"minimal_success_golden_is_valid_evidence",
			"golden_regression_detects_changed_final_state",
		},
		"time_travel.v1.json": {
			"agentledger.conformance.time_travel.v1",
			"timeline_reconstructs_state_at_selected_seq",
			"timeline_marks_state_changed_frames",
			"time_travel_report_exports_static_html",
		},
	}
	for file, required := range fixtures {
		content, err := os.ReadFile(filepath.Join("..", "contracts", "conformance", file))
		if err != nil {
			t.Fatal(err)
		}
		body := string(content)
		for _, token := range required {
			if !strings.Contains(body, token) {
				t.Fatalf("fixture %s missing %s", file, token)
			}
		}
	}
}

func eventTypeExists(events []Event, typ string) bool {
	for _, event := range events {
		if event.Type == typ {
			return true
		}
	}
	return false
}

func eventPayloadContains(events []Event, typ, key string, want any) bool {
	for _, event := range events {
		if event.Type == typ && event.Payload[key] == want {
			return true
		}
	}
	return false
}
