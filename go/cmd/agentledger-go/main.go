package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	agentledger "github.com/yaogdu/AgentLedger/go"
)

type checkResult struct {
	Language string   `json:"language"`
	Suite    string   `json:"suite"`
	Passed   bool     `json:"passed"`
	Checks   []string `json:"checks"`
}

type fixtureCheck struct {
	File   string
	Tokens []string
}

var fixtureChecks = []fixtureCheck{
	{File: "runtime_baseline.v1.json", Tokens: []string{
		"agentledger.conformance.runtime_baseline.v1",
		"durable_run_evidence_replay",
		"tool_ledger_idempotent_retry",
		"lease_recovery_fences_stale_worker",
		"cancellation_fences_worker",
	}},
	{File: "local_persistence.v1.json", Tokens: []string{
		"agentledger.conformance.local_persistence.v1",
		"local_store_round_trips_completed_run",
		"local_store_preserves_evidence_replay_chain",
		"local_store_uses_atomic_snapshot_write",
	}},
	{File: "local_blob_store.v1.json", Tokens: []string{
		"agentledger.conformance.local_blob_store.v1",
		"blob_roundtrip_json_value",
		"blob_content_address_is_stable",
		"blob_bad_ref_is_rejected",
	}},
	{File: "tool_schema_validation.v1.json", Tokens: []string{
		"agentledger.conformance.tool_schema_validation.v1",
		"invalid_tool_input_rejected_before_execution",
		"valid_tool_input_and_output_pass",
		"invalid_tool_output_rejected",
	}},
	{File: "worker_service.v1.json", Tokens: []string{
		"agentledger.conformance.worker_service.v1",
		"local_worker_runs_until_terminal",
		"worker_service_stops_after_idle_poll",
		"worker_loop_recovers_expired_leases",
	}},
	{File: "policy_approval_sandbox.v1.json", Tokens: []string{
		"agentledger.conformance.policy_approval_sandbox.v1",
		"policy_denies_unapproved_high_risk_tool",
		"approval_pauses_and_resumes_step",
		"sandbox_required_tool_fails_closed",
	}},
	{File: "cost_failure_attribution.v1.json", Tokens: []string{
		"agentledger.conformance.cost_failure_attribution.v1",
		"tool_and_model_cost_attributed_to_run_step_role",
		"budget_exhaustion_blocks_execution",
		"failure_attribution_classifies_agent_tool_model_runtime",
	}},
	{File: "media_stream_artifacts.v1.json", Tokens: []string{
		"agentledger.conformance.media_stream_artifacts.v1",
		"media_artifact_ref_is_indexed_in_evidence",
		"stream_checkpoint_ref_is_indexed_in_evidence",
	}},
	{File: "evidence_consumers.v1.json", Tokens: []string{
		"agentledger.conformance.evidence_consumers.v1",
		"trace_spans_from_evidence",
		"evidence_diff_detects_state_and_event_changes",
		"divergence_report_lists_changed_dimensions",
		"static_debug_summary_is_exportable",
	}},
	{File: "static_debug_html.v1.json", Tokens: []string{
		"agentledger.conformance.static_debug_html.v1",
		"static_debug_html_contains_run_events_and_state",
	}},
	{File: "ops_readiness.v1.json", Tokens: []string{
		"agentledger.conformance.ops_readiness.v1",
		"retention_plan_is_non_destructive_and_counts_evidence",
		"backup_readiness_reports_required_checks",
	}},
	{File: "storage_schema.v1.json", Tokens: []string{
		"agentledger.conformance.storage_schema.v1",
		"latest_schema_version_and_ddl_are_available",
	}},
	{File: "mcp_adapters.v1.json", Tokens: []string{
		"agentledger.conformance.mcp_adapters.v1",
		"in_memory_mcp_tool_server_lists_and_calls_tools",
		"mcp_tool_descriptor_maps_to_tool_spec",
		"in_memory_mcp_context_server_reads_resources",
	}},
	{File: "framework_adapters.v1.json", Tokens: []string{
		"agentledger.conformance.framework_adapters.v1",
		"function_adapter_maps_run_spec_and_invokes_agent",
		"method_framework_adapter_uses_first_available_method_and_writes_output",
	}},
	{File: "otlp_trace_export.v1.json", Tokens: []string{
		"agentledger.conformance.otlp_trace_export.v1",
		"otlp_json_contains_resource_scope_and_spans",
	}},
	{File: "simple_api.v1.json", Tokens: []string{
		"agentledger.conformance.simple_api.v1",
		"simple_run_returns_output_and_state",
	}},
	{File: "boundary_lint.v1.json", Tokens: []string{
		"agentledger.conformance.boundary_lint.v1",
		"direct_shell_and_http_calls_are_reported",
		"ignored_lines_are_not_reported",
	}},
	{File: "scheduler.v1.json", Tokens: []string{
		"agentledger.conformance.scheduler.v1",
		"scheduler_status_reports_run_steps_and_cost",
		"scheduler_recover_and_cancel_delegate_to_store",
	}},
	{File: "adversarial_review.v1.json", Tokens: []string{
		"agentledger.conformance.adversarial_review.v1",
		"clean_evidence_passes_blocker_review",
		"pending_high_risk_approval_blocks_review",
		"max_total_usd_limit_blocks_review",
	}},
	{File: "evidence_regression.v1.json", Tokens: []string{
		"agentledger.conformance.evidence_regression.v1",
		"evidence_health_checks_pass_for_clean_bundle",
		"regression_detects_final_state_and_event_type_changes",
		"regression_cost_delta_limit_blocks",
	}},
	{File: "failure_injection.v1.json", Tokens: []string{
		"agentledger.conformance.failure_injection.v1",
		"retry_exhaustion_marks_run_failed",
		"lease_fencing_rejects_stale_commit",
		"cancellation_fencing_rejects_late_commit",
		"side_effect_idempotency_executes_once_across_retry",
	}},
	{File: "shadow.v1.json", Tokens: []string{
		"agentledger.conformance.shadow.v1",
		"shadow_state_diff_reports_changed_keys",
		"shadow_report_carries_source_shadow_and_ok",
	}},
	{File: "repro.v1.json", Tokens: []string{
		"agentledger.conformance.repro.v1",
		"builtin_golden_names_are_available",
		"minimal_success_golden_is_valid_evidence",
		"golden_regression_detects_changed_final_state",
	}},
	{File: "time_travel.v1.json", Tokens: []string{
		"agentledger.conformance.time_travel.v1",
		"timeline_reconstructs_state_at_selected_seq",
		"timeline_marks_state_changed_frames",
		"time_travel_report_exports_static_html",
	}},
	{File: "optional_adapters.v1.json", Tokens: []string{
		"agentledger.conformance.optional_adapters.v1",
		"optional_backend_capabilities_are_discoverable",
		"postgres",
		"mysql",
		"langgraph",
		"langfuse",
		"shadow-runner",
	}},
	{File: "official_adapters.v1.json", Tokens: []string{
		"agentledger.conformance.official_adapters.v1",
		"postgres_adapter_plans_and_applies_migrations_with_injected_client",
		"mysql_adapter_plans_and_applies_migrations_with_injected_client",
		"s3_blob_adapter_round_trips_json_with_injected_client",
		"otlp_transport_posts_json_with_injected_client",
		"docker_sandbox_adapter_builds_manifest_without_daemon",
		"docker_sandbox_executor_runs_command_style_tool_with_injected_binary",
	}},
}

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 || (len(args) == 1 && (args[0] == "--help" || args[0] == "help")) {
		printHelp()
		return nil
	}
	if len(args) == 1 && args[0] == "version" {
		fmt.Println("agentledger-go 1.4.0")
		return nil
	}
	if len(args) == 1 && args[0] == "doctor" {
		fmt.Println(`{"language":"go","version":"1.4.0","status":"ok","runtime_core_parity":true}`)
		return nil
	}
	if len(args) == 1 && args[0] == "quickstart" {
		return runQuickstart()
	}
	if len(args) == 1 && args[0] == "conformance" {
		return runConformance()
	}
	if len(args) == 2 && args[0] == "contract" && args[1] == "validate" {
		return validateContract()
	}
	if len(args) == 2 && args[0] == "contract" && args[1] == "export" {
		root, err := findRepoRoot()
		if err != nil {
			return err
		}
		body, err := os.ReadFile(filepath.Join(root, "contracts", "agentledger.runtime.v1.json"))
		if err != nil {
			return err
		}
		fmt.Print(string(body))
		return nil
	}
	return fmt.Errorf("unknown command %q; run agentledger-go --help", strings.Join(args, " "))
}

func printHelp() {
	fmt.Println(`AgentLedger Go Runtime 1.4.0

Usage:
  agentledger-go doctor
  agentledger-go version
  agentledger-go quickstart
  agentledger-go conformance
  agentledger-go contract validate
  agentledger-go contract export

Project: https://github.com/yaogdu/AgentLedger`)
}

func runQuickstart() error {
	result, err := agentledger.SimpleRun(context.Background(), func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"message": "hello from go", "input": state["input"]}, nil
	}, agentledger.JSONObject{"input": "world"})
	if err != nil {
		return err
	}
	encoded, err := json.MarshalIndent(agentledger.JSONObject{"run_id": result.RunID, "output": result.Output, "state": result.State}, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(encoded))
	return nil
}

func runConformance() error {
	checks, err := validateFixtures()
	if err != nil {
		return err
	}
	semanticChecks, err := runSemanticSmokes()
	if err != nil {
		return err
	}
	checks = append([]string{"contract_validate"}, checks...)
	checks = append(checks, semanticChecks...)
	result := checkResult{Language: "go", Suite: "agentledger_runtime_core", Passed: true, Checks: checks}
	encoded, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(encoded))
	return nil
}

func runSemanticSmokes() ([]string, error) {
	checks := []string{}
	if err := runRuntimeSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "runtime_smoke_evidence_replay")
	if err := runLocalPersistenceSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "local_persistence_smoke")
	if err := runLocalBlobStoreSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "local_blob_store_smoke")
	if err := runToolSchemaValidationSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "tool_schema_validation_smoke")
	if err := runWorkerServiceSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "worker_service_smoke")
	if err := runToolLedgerSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "tool_ledger_idempotent_retry")
	if err := runPolicyApprovalSandboxSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "policy_approval_sandbox_smoke")
	if err := runCostFailureSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "cost_failure_attribution_smoke")
	if err := runMediaStreamSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "media_stream_artifacts_smoke")
	if err := runEvidenceConsumersSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "evidence_consumers_smoke")
	if err := runStaticDebugHTMLSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "static_debug_html_smoke")
	if err := runOpsReadinessSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "ops_readiness_smoke")
	if err := runStorageSchemaSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "storage_schema_smoke")
	if err := runMCPAdaptersSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "mcp_adapters_smoke")
	if err := runFrameworkAdaptersSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "framework_adapters_smoke")
	if err := runOTLPTraceExportSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "otlp_trace_export_smoke")
	if err := runSimpleAPISmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "simple_api_smoke")
	if err := runBoundaryLintSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "boundary_lint_smoke")
	if err := runSchedulerSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "scheduler_smoke")
	if err := runAdversarialReviewSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "adversarial_review_smoke")
	if err := runEvidenceRegressionSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "evidence_regression_smoke")
	if !agentledger.RunFailureInjectionSuite().Passed {
		return nil, fmt.Errorf("failure injection smoke failed")
	}
	checks = append(checks, "failure_injection_smoke")
	if err := runShadowSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "shadow_smoke")
	if err := runReproGoldenSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "repro_golden_smoke")
	if err := runTimeTravelTimelineSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "time_travel_timeline_smoke")
	if err := runOptionalAdaptersSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "optional_adapters_smoke")
	if err := runOfficialAdaptersSmoke(); err != nil {
		return nil, err
	}
	checks = append(checks, "official_adapters_smoke")
	return checks, nil
}

func runRuntimeSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	if err := rt.RegisterTool(agentledger.ToolSpec{
		Name:       "docs.echo",
		Version:    "v1",
		SideEffect: "none",
		Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
			return agentledger.JSONObject{"echo": args["text"]}, nil
		},
	}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "hello"})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "conformance-go", "ConformanceAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{"text": state["input"]})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("tool_result", result)
	})
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("runtime smoke did not complete")
	}
	finalState, err := rt.Store.FinalState(runID)
	if err != nil {
		return err
	}
	if _, ok := finalState["tool_result"]; !ok {
		return fmt.Errorf("runtime smoke missing final state")
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	summary, err := agentledger.Replay(rt.Store, runID)
	if err != nil {
		return err
	}
	if bundle.SchemaVersion != "agentledger.evidence.v1" || !summary.ReplaySafe || summary.EventCount != len(bundle.Events) {
		return fmt.Errorf("runtime smoke evidence/replay mismatch")
	}
	return nil
}

func runLocalPersistenceSmoke() error {
	path := filepath.Join(os.TempDir(), fmt.Sprintf("agentledger-go-%d.json", os.Getpid()))
	defer os.Remove(path)
	rt, err := agentledger.NewLocalRuntime(path)
	if err != nil {
		return err
	}
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "docs.persist", Version: "v1", SideEffect: "external", IdempotencyRequired: true, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"external_id": "persist-1", "echo": args["text"]}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "persist"})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-persist", "PersistenceAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "docs.persist", agentledger.JSONObject{"text": state["input"]})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("tool_result", result)
	})
	if err != nil || !ok {
		return fmt.Errorf("local persistence smoke expected completion, ok=%v err=%v", ok, err)
	}
	reopened, err := agentledger.NewJSONStore(path)
	if err != nil {
		return err
	}
	state, err := reopened.FinalState(runID)
	if err != nil {
		return err
	}
	if _, ok := state["tool_result"]; !ok {
		return fmt.Errorf("local persistence smoke missing reopened final state")
	}
	bundle, err := agentledger.ExportEvidence(reopened, runID)
	if err != nil {
		return err
	}
	summary, err := agentledger.Replay(reopened, runID)
	if err != nil {
		return err
	}
	if bundle.BundleHash == "" || !summary.ReplaySafe || summary.EventCount != len(bundle.Events) || len(reopened.Ledger(runID)) != 1 || summary.ToolCallCount == 0 {
		return fmt.Errorf("local persistence evidence/replay mismatch")
	}
	return nil
}

func runLocalBlobStoreSmoke() error {
	root := filepath.Join(os.TempDir(), fmt.Sprintf("agentledger-go-blobs-%d", os.Getpid()))
	defer os.RemoveAll(root)
	blobs, err := agentledger.NewLocalBlobStore(root)
	if err != nil {
		return err
	}
	value := agentledger.JSONObject{"hello": "world", "nested": agentledger.JSONObject{"n": 1}}
	digest, ref, err := blobs.PutJSON(value)
	if err != nil {
		return err
	}
	if !strings.HasPrefix(digest, "sha256:") || !strings.HasPrefix(ref, "blob://sha256/") {
		return fmt.Errorf("local blob store returned invalid digest/ref")
	}
	digest2, ref2, err := blobs.PutJSON(value)
	if err != nil {
		return err
	}
	if digest != digest2 || ref != ref2 {
		return fmt.Errorf("local blob store ref was not stable")
	}
	read, err := blobs.GetJSON(ref)
	if err != nil {
		return err
	}
	encodedRead, _ := json.Marshal(read)
	encodedValue, _ := json.Marshal(value)
	if string(encodedRead) != string(encodedValue) {
		return fmt.Errorf("local blob store roundtrip mismatch")
	}
	if _, err := blobs.GetJSON("file:///etc/passwd"); err == nil {
		return fmt.Errorf("local blob store accepted unsupported ref")
	}
	return nil
}

func runToolSchemaValidationSmoke() error {
	inputSchema := agentledger.JSONObject{"type": "object", "required": []any{"text"}, "additionalProperties": false, "properties": agentledger.JSONObject{"text": agentledger.JSONObject{"type": "string", "minLength": 1}}}
	outputSchema := agentledger.JSONObject{"type": "object", "required": []any{"echo"}, "additionalProperties": false, "properties": agentledger.JSONObject{"echo": agentledger.JSONObject{"type": "string"}}}
	calls := 0
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "docs.echo", InputSchema: inputSchema, OutputSchema: outputSchema, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"echo": args["text"]}, nil
	}}); err != nil {
		return err
	}
	badRun, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), badRun, "worker-schema", "SchemaAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{})
		return err
	})
	if err == nil || ok || calls != 0 {
		return fmt.Errorf("tool schema input validation smoke failed: ok=%v err=%v calls=%d", ok, err, calls)
	}
	goodRun, _, err := rt.CreateRun(agentledger.JSONObject{"text": "hello"})
	if err != nil {
		return err
	}
	ok, err = rt.RunOnce(context.Background(), goodRun, "worker-schema", "SchemaAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{"text": state["text"]})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("result", result)
	})
	if err != nil || !ok || calls != 1 {
		return fmt.Errorf("tool schema valid call smoke failed: ok=%v err=%v calls=%d", ok, err, calls)
	}
	badOutput := agentledger.NewRuntime(agentledger.NewMemoryStore())
	if err := badOutput.RegisterTool(agentledger.ToolSpec{Name: "docs.bad", OutputSchema: outputSchema, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"bad": true}, nil
	}}); err != nil {
		return err
	}
	badOutRun, _, err := badOutput.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err = badOutput.RunOnce(context.Background(), badOutRun, "worker-schema", "SchemaAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "docs.bad", agentledger.JSONObject{})
		return err
	})
	if err == nil || ok || eventTypeExists(badOutput.Store.Events(badOutRun), "tool_call_completed") {
		return fmt.Errorf("tool schema output validation smoke failed: ok=%v err=%v", ok, err)
	}
	return nil
}

func runWorkerServiceSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "worker"})
	if err != nil {
		return err
	}
	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		return agentCtx.WriteState("done", true)
	}
	worker := agentledger.NewLocalWorker(rt, "worker-service", "WorkerAgent")
	summary, err := worker.RunUntilIdle(context.Background(), runID, 3, agent)
	if err != nil || summary.Attempts != 1 || summary.SucceededAttempts != 1 || summary.FinalStatus != "completed" || summary.StoppedReason != "terminal_status" {
		return fmt.Errorf("worker terminal smoke mismatch: %#v err=%v", summary, err)
	}
	service := agentledger.NewWorkerService(agentledger.NewLocalWorker(rt, "worker-service", "WorkerAgent"))
	idle, err := service.Serve(context.Background(), runID, 3, 1, agent)
	if err != nil || idle.IdlePolls != 0 || idle.StoppedReason != "terminal_status" {
		return fmt.Errorf("worker service terminal smoke mismatch: %#v err=%v", idle, err)
	}
	idleRun, _, err := rt.CreateRun(agentledger.JSONObject{"idle": true})
	if err != nil {
		return err
	}
	if _, err := rt.Store.CancelRun(idleRun, "make-idle"); err != nil {
		return err
	}
	idle, err = service.Serve(context.Background(), idleRun, 3, 1, agent)
	if err != nil || idle.StoppedReason != "terminal_status" {
		return fmt.Errorf("worker service idle/terminal smoke mismatch: %#v err=%v", idle, err)
	}
	return nil
}

func runToolLedgerSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "github.create_pr", Version: "v1", SideEffect: "external", IdempotencyRequired: true, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"external_id": "pr-123", "title": args["title"]}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"title": "runtime parity"})
	if err != nil {
		return err
	}
	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "github.create_pr", agentledger.JSONObject{"title": state["title"]})
		if err != nil {
			return err
		}
		if agentCtx.Attempt == 1 {
			return agentledger.ErrRetryable
		}
		return agentCtx.WriteState("pr", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-a", "Coder", 60, agent)
	if err != nil || ok {
		return fmt.Errorf("expected retryable first attempt, ok=%v err=%v", ok, err)
	}
	ok, err = rt.RunOnce(context.Background(), runID, "worker-b", "Coder", 60, agent)
	if err != nil || !ok {
		return fmt.Errorf("expected retry replay completion, ok=%v err=%v", ok, err)
	}
	ledger := rt.Store.Ledger(runID)
	if calls != 1 || len(ledger) != 1 || ledger[0].Status != "SUCCEEDED" {
		return fmt.Errorf("unexpected tool ledger smoke: calls=%d ledger=%#v", calls, ledger)
	}
	return nil
}

func runPolicyApprovalSandboxSmoke() error {
	if err := runPolicySmoke(); err != nil {
		return err
	}
	if err := runApprovalSmoke(); err != nil {
		return err
	}
	return runSandboxSmoke()
}

func runPolicySmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "repo.write", RiskLevel: "high", Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"ok": true}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Reviewer", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "repo.write", agentledger.JSONObject{"path": "README.md"})
		return err
	})
	if err == nil || ok || calls != 0 || !eventPayloadContains(rt.Store.Events(runID), "tool_permission_decided", "allowed", false) {
		return fmt.Errorf("policy smoke failed: ok=%v err=%v calls=%d", ok, err, calls)
	}
	return nil
}

func runApprovalSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "github.create_pr", RiskLevel: "high", ApprovalRequired: true, SideEffect: "external", IdempotencyRequired: true, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"external_id": "pr-42"}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	agent := func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		result, err := agentCtx.CallTool(ctx, "github.create_pr", agentledger.JSONObject{"title": "safe"})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("pr", result)
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-a", "Coder", 60, agent)
	if err != nil || ok || calls != 0 {
		return fmt.Errorf("approval smoke expected pause, ok=%v err=%v calls=%d", ok, err, calls)
	}
	approvals := rt.Store.ApprovalRequests(runID)
	if len(approvals) != 1 || approvals[0].Status != agentledger.ApprovalPending || rt.Store.Steps(runID)[0].Status != "waiting_human" {
		return fmt.Errorf("approval smoke missing pending approval")
	}
	if _, err := rt.Store.ApproveRequest(approvals[0].ApprovalID, "alice", "reviewed"); err != nil {
		return err
	}
	ok, err = rt.RunOnce(context.Background(), runID, "worker-b", "Coder", 60, agent)
	if err != nil || !ok || calls != 1 {
		return fmt.Errorf("approval smoke expected resume, ok=%v err=%v calls=%d", ok, err, calls)
	}
	return nil
}

func runSandboxSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "shell.exec", RiskLevel: "low", SandboxRequired: true, Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"ok": true}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Executor", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		_, err := agentCtx.CallTool(ctx, "shell.exec", agentledger.JSONObject{"argv": []any{"echo", "hi"}})
		return err
	})
	if err == nil || ok || calls != 0 || !eventTypeExists(rt.Store.Events(runID), "sandbox_started") || !eventTypeExists(rt.Store.Events(runID), "tool_call_failed") {
		return fmt.Errorf("sandbox smoke failed: ok=%v err=%v calls=%d", ok, err, calls)
	}
	return nil
}

func runCostFailureSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	rt.SetBudget(agentledger.BudgetLimits{MaxToolCalls: 1})
	calls := 0
	if err := rt.RegisterTool(agentledger.ToolSpec{Name: "docs.echo", Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
		calls++
		return agentledger.JSONObject{"echo": args["text"]}, nil
	}}); err != nil {
		return err
	}
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker", "Researcher", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		if err := agentCtx.RecordModelCall("gpt-test", 10, 5, 0.01); err != nil {
			return err
		}
		if _, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{"text": "first"}); err != nil {
			return err
		}
		_, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{"text": "second"})
		return err
	})
	if err == nil || ok || calls != 1 {
		return fmt.Errorf("cost/failure smoke expected budget failure, ok=%v err=%v calls=%d", ok, err, calls)
	}
	summary := rt.Store.CostSummary(runID)
	failure, failureErr := agentledger.FailureAttribution(rt.Store, runID)
	if failureErr != nil {
		return failureErr
	}
	if summary.ToolCalls != 1 || summary.ModelTokens != 15 || summary.TotalUSD != 0.01 || failure.Summary["failed_step_count"].(int) != 1 || !eventTypeExists(failure.FailureEvents, "budget_check_failed") {
		return fmt.Errorf("cost/failure smoke attribution mismatch")
	}
	return nil
}

func runMediaStreamSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-media", "MediaAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		frameID, err := agentCtx.CreateMediaArtifact("frame-0001", "frame", agentledger.MediaArtifactOptions{URI: "s3://media/demo/frame-0001.jpg", MediaMetadata: agentledger.JSONObject{"mime_type": "image/jpeg"}})
		if err != nil {
			return err
		}
		checkpointID, err := agentCtx.CreateStreamCheckpoint("camera-checkpoint", agentledger.StreamCheckpointOptions{StreamID: "camera-1", ConsumerID: "vision-agent", Offset: 7, Chunk: agentledger.StreamChunkRef{StreamID: "camera-1", ChunkID: "chunk-7", Offset: 7}})
		if err != nil {
			return err
		}
		return agentCtx.WriteState("artifacts", agentledger.JSONObject{"frame": frameID, "checkpoint": checkpointID})
	})
	if err != nil || !ok {
		return fmt.Errorf("media smoke expected completion, ok=%v err=%v", ok, err)
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	summary, err := agentledger.Replay(rt.Store, runID)
	if err != nil {
		return err
	}
	if len(bundle.Artifacts) != 2 || len(bundle.MediaArtifacts) != 1 || len(bundle.StreamCheckpoints) != 1 || summary.MediaArtifactCount != 1 || summary.StreamCheckpointCount != 1 {
		return fmt.Errorf("media smoke evidence/replay mismatch")
	}
	return nil
}

func runStaticDebugHTMLSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "debug"})
	if err != nil {
		return err
	}
	if _, err := rt.RunOnce(context.Background(), runID, "worker-debug", "DebugAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		return agentCtx.WriteState("answer", "debug")
	}); err != nil {
		return err
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	html := agentledger.DebugHTML(bundle)
	for _, token := range []string{"<!doctype html>", "AgentLedger Debug Report", "Run", "Events", "Final State", "run_created"} {
		if !strings.Contains(html, token) {
			return fmt.Errorf("static debug html smoke missing %s", token)
		}
	}
	return nil
}

func runOpsReadinessSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "ops"})
	if err != nil {
		return err
	}
	if _, err := rt.RunOnce(context.Background(), runID, "worker-ops", "OpsAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		if _, err := agentCtx.CreateMediaArtifact("frame-ops", "frame", agentledger.MediaArtifactOptions{URI: "file://frame.png"}); err != nil {
			return err
		}
		return agentCtx.WriteState("answer", "ops")
	}); err != nil {
		return err
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	plan := agentledger.PlanRetention(bundle)
	if plan.Destructive || plan.EventCount != len(bundle.Events) || plan.MediaArtifactCount != 1 || !stringSliceContains(plan.Actions, "export evidence bundle before destructive retention") || !stringSliceContains(plan.Actions, "snapshot final state and manifest") {
		return fmt.Errorf("ops retention plan smoke mismatch")
	}
	report := agentledger.CheckBackupReadiness(bundle)
	if !report.Passed || !backupCheckExists(report.Checks, "run_metadata_exists") || !backupCheckExists(report.Checks, "payload_refs_resolvable") || !backupCheckExists(report.Checks, "evidence_exportable") || !backupCheckExists(report.Checks, "media_stream_evidence_shape") {
		return fmt.Errorf("ops backup readiness smoke mismatch")
	}
	return nil
}

func backupCheckExists(checks []agentledger.BackupCheck, name string) bool {
	for _, check := range checks {
		if check.Name == name && check.Passed {
			return true
		}
	}
	return false
}

func runStorageSchemaSmoke() error {
	for _, dialect := range []string{"sqlite", "postgres", "mysql"} {
		version, err := agentledger.LatestSchemaVersion(dialect)
		if err != nil || version != "0001" {
			return fmt.Errorf("storage schema version mismatch for %s", dialect)
		}
		migrations, err := agentledger.MigrationsFor(dialect)
		if err != nil || len(migrations) != 1 || migrations[0].Name != "initial_runtime_metadata" || !strings.HasPrefix(migrations[0].Checksum(), "sha256:") {
			return fmt.Errorf("storage schema migrations mismatch for %s", dialect)
		}
		ddl, err := agentledger.DDLFor(dialect)
		if err != nil {
			return err
		}
		for _, token := range []string{"schema_migrations", "CREATE TABLE IF NOT EXISTS runs", "CREATE TABLE IF NOT EXISTS events", "CREATE TABLE IF NOT EXISTS tool_ledger"} {
			if !strings.Contains(ddl, token) {
				return fmt.Errorf("storage schema ddl for %s missing %s", dialect, token)
			}
		}
	}
	return nil
}

func runMCPAdaptersSmoke() error {
	server := agentledger.NewInMemoryMCPToolServer()
	server.AddTool(agentledger.JSONObject{"name": "docs.echo", "annotations": agentledger.JSONObject{"side_effect": "none"}}, func(name string, args agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"name": name, "echo": args["text"]}, nil
	})
	server.AddTool(agentledger.JSONObject{"name": "web.search"}, func(name string, args agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"ok": true}, nil
	})
	tools := server.ListTools()
	if len(tools) != 2 || tools[0]["name"] != "docs.echo" {
		return fmt.Errorf("mcp tool server list mismatch")
	}
	if _, err := server.CallTool("missing", agentledger.JSONObject{}); err == nil {
		return fmt.Errorf("mcp missing tool should fail")
	}
	adapter := agentledger.MCPToolAdapter{ClientCall: server.CallTool}
	spec := adapter.ToolSpecFromDescriptor(agentledger.JSONObject{"name": "github.create_pr", "annotations": agentledger.JSONObject{"side_effect": "external", "risk_level": "high"}})
	if spec.Name != "github.create_pr" || spec.SideEffect != "external" || spec.RiskLevel != "high" || !spec.IdempotencyRequired {
		return fmt.Errorf("mcp tool adapter spec mismatch")
	}
	ctxServer := agentledger.NewInMemoryMCPContextServer()
	ctxServer.AddResource("docs://readme", "README", "application/json", func(uri string) (any, error) { return agentledger.JSONObject{"uri": uri}, nil })
	resources := ctxServer.ListResources()
	if len(resources) != 1 || resources[0]["mimeType"] != "application/json" {
		return fmt.Errorf("mcp context list mismatch")
	}
	read, err := ctxServer.ReadResource("docs://readme")
	if err != nil || read["content"] == nil {
		return fmt.Errorf("mcp context read mismatch")
	}
	readSpec := (agentledger.MCPContextAdapter{ResourceRead: func(uri string) (any, error) { return ctxServer.ReadResource(uri) }}).ReadToolSpec("", "")
	if readSpec.Name != "mcp.context.read" || readSpec.SideEffect != "none" {
		return fmt.Errorf("mcp context adapter spec mismatch")
	}
	return nil
}

func finalStateHasNoOutput(store *agentledger.JSONStore, runID string) bool {
	state, err := store.FinalState(runID)
	return err != nil || state["output"] == nil
}

func runFrameworkAdaptersSmoke() error {
	functionAdapter := agentledger.NewFunctionAdapter(func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"kind": "function", "input": state["input"]}, nil
	}, "Agent")
	if functionAdapter.MapRunSpec()["adapter"] != "function" {
		return fmt.Errorf("function adapter run spec mismatch")
	}
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, _ := rt.CreateRun(agentledger.JSONObject{"input": "adapter"})
	if ok, err := rt.RunOnce(context.Background(), runID, "worker-adapter", functionAdapter.Role, 60, functionAdapter.AsAgent("output")); err != nil || !ok {
		return fmt.Errorf("function adapter run mismatch")
	}
	if finalStateHasNoOutput(rt.Store, runID) {
		return fmt.Errorf("function adapter missing output")
	}
	methodAdapter := agentledger.NewMethodFrameworkAdapter("Target", "FrameworkAgent", []string{"ainvoke", "invoke"}, map[string]agentledger.MethodHandler{"invoke": func(state agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"kind": "method", "input": state["input"]}, nil
	}}, "output")
	if methodAdapter.MapRunSpec()["adapter"] != "method-framework" {
		return fmt.Errorf("method adapter run spec mismatch")
	}
	rt2 := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID2, _, _ := rt2.CreateRun(agentledger.JSONObject{"input": "method"})
	if ok, err := rt2.RunOnce(context.Background(), runID2, "worker-method", methodAdapter.Role, 60, methodAdapter.AsAgent()); err != nil || !ok {
		return fmt.Errorf("method adapter run mismatch")
	}
	if finalStateHasNoOutput(rt2.Store, runID2) {
		return fmt.Errorf("method adapter missing output")
	}
	return nil
}

func runOTLPTraceExportSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "otlp"})
	if err != nil {
		return err
	}
	if _, err := rt.RunOnce(context.Background(), runID, "worker-otlp", "TraceAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		return agentCtx.WriteState("answer", "otlp")
	}); err != nil {
		return err
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	otlp := agentledger.OTLPTraceJSON(bundle, agentledger.OTLPResource{ServiceName: "agentledger-test", ServiceVersion: "1.0.0"})
	encoded, _ := json.Marshal(otlp)
	body := string(encoded)
	for _, token := range []string{"resourceSpans", "service.name", "scopeSpans", "traceId", "spanId", "agentledger.original_trace_id", "agentledger.run_id"} {
		if !strings.Contains(body, token) {
			return fmt.Errorf("otlp trace smoke missing %s", token)
		}
	}
	return nil
}

func runSimpleAPISmoke() error {
	result, err := agentledger.SimpleRun(context.Background(), func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) (any, error) {
		return agentledger.JSONObject{"message": "hello", "input": state["input"]}, nil
	}, agentledger.JSONObject{"input": "world"})
	if err != nil {
		return err
	}
	if !result.OK || result.Output == nil || result.State["output"] == nil || result.SessionID == "" {
		return fmt.Errorf("simple api smoke result mismatch")
	}
	if !eventTypeExists(result.Runtime.Store.Events(result.RunID), "agent_result_returned") {
		return fmt.Errorf("simple api smoke missing result event")
	}
	return nil
}

func runEvidenceConsumersSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "left"})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "worker-evidence", "EvidenceAgent", 60, func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
		if _, err := agentCtx.CreateMediaArtifact("frame-0001", "frame", agentledger.MediaArtifactOptions{URI: "file://frame.png", Lineage: agentledger.JSONObject{"source": "camera"}}); err != nil {
			return err
		}
		if _, err := agentCtx.CreateStreamCheckpoint("audio-checkpoint", agentledger.StreamCheckpointOptions{StreamID: "audio-stream", ConsumerID: "asr", Offset: 1, Watermark: "00:00:01", Chunk: agentledger.StreamChunkRef{StreamID: "audio-stream", ChunkID: "c1", Offset: 1}}); err != nil {
			return err
		}
		return agentCtx.WriteState("answer", "left")
	})
	if err != nil || !ok {
		return fmt.Errorf("evidence consumer smoke expected completion, ok=%v err=%v", ok, err)
	}
	left, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	right := left
	right.Run.RunID = left.Run.RunID + "-shadow"
	right.BundleHash = "different"
	right.FinalState = agentledger.JSONObject{"answer": "right"}
	right.Events = append(append([]agentledger.Event{}, left.Events...), agentledger.Event{Seq: len(left.Events) + 1, Type: "shadow_event"})
	right.MediaArtifacts = []agentledger.JSONObject{}
	right.StreamCheckpoints = []agentledger.JSONObject{}
	spans := agentledger.TraceSpans(left)
	if len(spans) == 0 || spans[0].SpanID != "evt-000001" || spans[0].Attributes["agentledger.run_id"] != runID {
		return fmt.Errorf("trace span event smoke mismatch")
	}
	jsonl, err := agentledger.TraceJSONL(left)
	if err != nil || !strings.Contains(jsonl, "evt-000001") || !spanNameExists(spans, "media_artifact") || !spanNameExists(spans, "stream_checkpoint") {
		return fmt.Errorf("trace span artifact smoke mismatch")
	}
	diff := agentledger.DiffEvidence(left, right)
	if diff.Same || !dimensionChangedForMain(diff.Changes["final_state"]) || !dimensionChangedForMain(diff.Changes["event_types"]) || !dimensionChangedForMain(diff.Changes["media_artifacts"]) || !dimensionChangedForMain(diff.Changes["stream_checkpoints"]) {
		return fmt.Errorf("evidence diff smoke mismatch")
	}
	divergence := agentledger.DivergenceEvidence(left, right)
	for _, dimension := range []string{"events", "state", "media_artifacts", "stream_checkpoints"} {
		if !stringSliceContains(divergence.ChangedDimensions, dimension) {
			return fmt.Errorf("divergence smoke missing %s", dimension)
		}
	}
	debug := agentledger.DebugSummary(left)
	if debug["run_id"] != runID || debug["event_count"] != len(left.Events) {
		return fmt.Errorf("debug summary smoke mismatch")
	}
	return nil
}

func spanNameExists(spans []agentledger.TraceSpan, name string) bool {
	for _, span := range spans {
		if span.Name == name {
			return true
		}
	}
	return false
}

func stringSliceContains(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func dimensionChangedForMain(value any) bool {
	data, _ := json.Marshal(value)
	var decoded map[string]any
	if err := json.Unmarshal(data, &decoded); err != nil {
		return false
	}
	count, _ := decoded["changed_count"].(float64)
	return count > 0
}

func eventTypeExists(events []agentledger.Event, typ string) bool {
	for _, event := range events {
		if event.Type == typ {
			return true
		}
	}
	return false
}

func eventPayloadContains(events []agentledger.Event, typ, key string, expected any) bool {
	for _, event := range events {
		if event.Type == typ && event.Payload[key] == expected {
			return true
		}
	}
	return false
}

func validateContract() error {
	root, err := findRepoRoot()
	if err != nil {
		return err
	}
	body, err := os.ReadFile(filepath.Join(root, "contracts", "agentledger.runtime.v1.json"))
	if err != nil {
		return err
	}
	text := string(body)
	for _, token := range []string{"\"contract_version\": \"1.0\"", "\"language\": \"go\"", "\"status\": \"preview\"", "media_stream_artifacts.v1.json"} {
		if !strings.Contains(text, token) {
			return fmt.Errorf("contract missing %s", token)
		}
	}
	return nil
}

func validateFixtures() ([]string, error) {
	if err := validateContract(); err != nil {
		return nil, err
	}
	root, err := findRepoRoot()
	if err != nil {
		return nil, err
	}
	checks := make([]string, 0, len(fixtureChecks))
	for _, fixture := range fixtureChecks {
		body, err := os.ReadFile(filepath.Join(root, "contracts", "conformance", fixture.File))
		if err != nil {
			return nil, err
		}
		text := string(body)
		for _, token := range fixture.Tokens {
			if !strings.Contains(text, token) {
				return nil, fmt.Errorf("fixture %s missing %s", fixture.File, token)
			}
		}
		checks = append(checks, fixture.File)
	}
	return checks, nil
}

func findRepoRoot() (string, error) {
	if env := os.Getenv("AGENTLEDGER_REPO_ROOT"); env != "" {
		return env, nil
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		candidate := filepath.Join(wd, "contracts", "agentledger.runtime.v1.json")
		if _, err := os.Stat(candidate); err == nil {
			return wd, nil
		}
		parent := filepath.Dir(wd)
		if parent == wd {
			break
		}
		wd = parent
	}
	return "", fmt.Errorf("could not find AgentLedger repository root")
}

func runBoundaryLintSmoke() error {
	report := agentledger.ScanBoundarySource("agent.py", "import os\nimport requests\nos.system('echo unsafe')\nrequests.post('https://example.com')\n", nil)
	if report.Passed || report.FindingCount != 2 {
		return fmt.Errorf("boundary lint finding count mismatch")
	}
	if report.Findings[0].RuleID != "direct-shell-os-system" || report.Findings[1].RuleID != "direct-http-requests" {
		return fmt.Errorf("boundary lint rule mismatch")
	}
	ignored := agentledger.ScanBoundarySource("agent.py", "import os\n# agentledger: ignore-next-line\nos.system('echo intentional')\n", nil)
	if !ignored.Passed || ignored.FindingCount != 0 {
		return fmt.Errorf("boundary lint ignore mismatch")
	}
	return nil
}

func runSchedulerSmoke() error {
	store := agentledger.NewMemoryStore()
	rt := agentledger.NewRuntime(store)
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "scheduler"})
	if err != nil {
		return err
	}
	scheduler := agentledger.NewRuntimeScheduler(store)
	status, err := scheduler.Status(runID)
	if err != nil {
		return err
	}
	if status.RunID != runID || status.RunStatus != "pending" || len(status.Steps) != 1 {
		return fmt.Errorf("scheduler status mismatch")
	}
	claim, err := store.ClaimStep("scheduler-stale", runID, 0)
	if err != nil || claim == nil {
		return fmt.Errorf("scheduler claim failed")
	}
	recovery, err := scheduler.RecoverExpiredLeases()
	if err != nil {
		return err
	}
	if recovery.RecoveredSteps != 1 {
		return fmt.Errorf("scheduler recovered steps mismatch")
	}
	cancelled, err := scheduler.CancelRun(runID, "scheduler smoke")
	if err != nil {
		return err
	}
	if cancelled != 1 {
		return fmt.Errorf("scheduler cancelled steps mismatch")
	}
	status, err = scheduler.Status(runID)
	if err != nil {
		return err
	}
	if status.RunStatus != "cancelled" || status.Steps[0].Status != "cancelled" {
		return fmt.Errorf("scheduler cancelled status mismatch")
	}
	return nil
}

func runAdversarialReviewSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "review"})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "review-worker", "ReviewAgent", 60, func(_ context.Context, ctx *agentledger.AgentContext, state agentledger.JSONObject) error {
		return ctx.WriteState("answer", "ok")
	})
	if err != nil || !ok {
		return fmt.Errorf("review run failed")
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	report := agentledger.AdversarialReview(bundle, nil)
	if !report.Passed {
		return fmt.Errorf("clean adversarial review should pass")
	}
	pending := bundle
	pending.Summary["has_pending_approvals"] = true
	pending.Approvals = append(pending.Approvals, agentledger.ApprovalRequest{RiskLevel: "high", Status: "PENDING"})
	blocked := agentledger.AdversarialReview(pending, nil)
	if blocked.Passed {
		return fmt.Errorf("pending high-risk approval should block")
	}
	limit := 0.5
	costly := bundle
	costly.CostSummary.TotalUSD = 1.0
	costReport := agentledger.AdversarialReview(costly, &limit)
	if costReport.Passed {
		return fmt.Errorf("cost limit should block")
	}
	return nil
}

func runEvidenceRegressionSmoke() error {
	rt := agentledger.NewRuntime(agentledger.NewMemoryStore())
	runID, _, err := rt.CreateRun(agentledger.JSONObject{"input": "eval"})
	if err != nil {
		return err
	}
	ok, err := rt.RunOnce(context.Background(), runID, "eval-worker", "EvalAgent", 60, func(_ context.Context, ctx *agentledger.AgentContext, state agentledger.JSONObject) error {
		return ctx.WriteState("answer", "ok")
	})
	if err != nil || !ok {
		return fmt.Errorf("eval run failed")
	}
	bundle, err := agentledger.ExportEvidence(rt.Store, runID)
	if err != nil {
		return err
	}
	if !agentledger.EvaluateEvidence(bundle, nil).Passed {
		return fmt.Errorf("clean evidence health check should pass")
	}
	changed := bundle
	changed.FinalState = agentledger.JSONObject{"answer": "changed"}
	changed.Events = append(changed.Events, agentledger.Event{Seq: len(changed.Events) + 1, Type: "extra_event"})
	if agentledger.EvaluateEvidenceRegression(bundle, changed, nil).Passed {
		return fmt.Errorf("regression changes should fail")
	}
	costly := bundle
	costly.CostSummary.TotalUSD = 1.0
	limit := 0.5
	if agentledger.EvaluateEvidenceRegression(bundle, costly, &limit).Passed {
		return fmt.Errorf("cost delta should fail")
	}
	return nil
}

func runShadowSmoke() error {
	diff := agentledger.DiffStates(agentledger.JSONObject{"answer": "old", "stable": true}, agentledger.JSONObject{"answer": "new", "stable": true, "extra": 1})
	if diff["changed_count"] != 2 {
		return fmt.Errorf("shadow diff changed_count mismatch")
	}
	report := agentledger.NewShadowReport("run_source", "run_shadow", true, agentledger.JSONObject{"answer": "old"}, agentledger.JSONObject{"answer": "new"})
	if report.SourceRunID != "run_source" || report.ShadowRunID != "run_shadow" || !report.OK {
		return fmt.Errorf("shadow report mismatch")
	}
	return nil
}

func runReproGoldenSmoke() error {
	names := strings.Join(agentledger.BuiltinGoldenNames(), ",")
	if names != "media-stream-checkpoint,minimal-success,tool-ledger-success" {
		return fmt.Errorf("builtin golden names mismatch: %s", names)
	}
	bundle, err := agentledger.BuiltinGoldenEvidence("minimal-success")
	if err != nil {
		return err
	}
	if bundle.SchemaVersion != "agentledger.evidence.v1" || bundle.FinalState["answer"] != "ok" {
		return fmt.Errorf("minimal golden evidence mismatch")
	}
	changed := bundle
	changed.FinalState = agentledger.JSONObject{"answer": "changed"}
	if agentledger.GoldenRegression(bundle, changed).Passed {
		return fmt.Errorf("golden regression should detect final state change")
	}
	return nil
}

func runTimeTravelTimelineSmoke() error {
	bundle, err := agentledger.BuiltinGoldenEvidence("minimal-success")
	if err != nil {
		return err
	}
	report := agentledger.TimeTravel(bundle, 999, true)
	if report.StateAtSeq["answer"] != "ok" || report.EventCount != len(bundle.Events) {
		return fmt.Errorf("time travel state mismatch")
	}
	foundChange := false
	for _, frame := range report.Timeline {
		if frame.StateChanged {
			foundChange = true
		}
	}
	if !foundChange {
		return fmt.Errorf("time travel missing changed frame")
	}
	html := report.HTML()
	for _, token := range []string{"AgentLedger Time Travel Report", "State At Selected Point", "Selected Event"} {
		if !strings.Contains(html, token) {
			return fmt.Errorf("time travel html missing %s", token)
		}
	}
	return nil
}

func runOptionalAdaptersSmoke() error {
	caps := agentledger.OptionalAdapterCapabilities()
	seen := map[string]bool{}
	for _, cap := range caps {
		if cap.CoreImportsHeavySDKs || !cap.AdapterIsOptional || !cap.FailClosedWithout || len(cap.ContractSurface) == 0 {
			return fmt.Errorf("invalid optional adapter capability: %s", cap.Name)
		}
		seen[cap.Name] = true
	}
	for _, name := range []string{"postgres", "mysql", "s3", "docker", "langgraph", "mcp-transport", "langfuse", "shadow-runner"} {
		if !seen[name] {
			return fmt.Errorf("missing optional adapter capability: %s", name)
		}
	}
	return nil
}

type fakeSQLClient struct{ count int }

func (f *fakeSQLClient) Exec(ctx context.Context, sql string, args ...any) error {
	f.count++
	return nil
}

type fakeObjectClient struct {
	objects     map[string][]byte
	contentType string
}

func (f *fakeObjectClient) PutObject(ctx context.Context, in agentledger.ObjectPutInput) error {
	if f.objects == nil {
		f.objects = map[string][]byte{}
	}
	f.objects[in.Bucket+"/"+in.Key] = in.Body
	f.contentType = in.ContentType
	return nil
}
func (f *fakeObjectClient) GetObject(ctx context.Context, bucket, key string) (agentledger.ObjectGetOutput, error) {
	return agentledger.ObjectGetOutput{Body: f.objects[bucket+"/"+key]}, nil
}

type fakeOTLPClient struct{ contentType string }

func (f *fakeOTLPClient) PostJSON(ctx context.Context, endpoint string, payload []byte, contentType string) error {
	f.contentType = contentType
	return nil
}
func runOfficialAdaptersSmoke() error {
	sql := &fakeSQLClient{}
	pg := agentledger.NewPostgresAdapter("agentledger", sql)
	plan, err := pg.MigrationPlan()
	if err != nil || len(plan) == 0 || plan[0].Dialect != "postgres" {
		return fmt.Errorf("postgres adapter plan failed")
	}
	if err := pg.ApplyMigrations(context.Background()); err != nil || sql.count < 2 {
		return fmt.Errorf("postgres adapter apply failed: %v", err)
	}
	mySQLStart := sql.count
	my := agentledger.NewMySQLAdapter("agentledger", sql)
	myPlan, err := my.MigrationPlan()
	if err != nil || len(myPlan) == 0 || myPlan[0].Dialect != "mysql" {
		return fmt.Errorf("mysql adapter plan failed")
	}
	if err := my.ApplyMigrations(context.Background()); err != nil || sql.count < mySQLStart+2 {
		return fmt.Errorf("mysql adapter apply failed: %v", err)
	}
	obj := &fakeObjectClient{}
	s3 := agentledger.NewS3BlobStore("agentledger-test", "agentledger/blobs", obj)
	_, ref, err := s3.PutJSON(context.Background(), agentledger.JSONObject{"answer": "ok"})
	if err != nil || !strings.HasPrefix(ref, "s3://agentledger-test/agentledger/blobs/sha256/") || obj.contentType != "application/json" {
		return fmt.Errorf("s3 adapter put failed")
	}
	if value, err := s3.GetJSON(context.Background(), ref); err != nil || value == nil {
		return fmt.Errorf("s3 adapter get failed")
	}
	otlp := &fakeOTLPClient{}
	if err := (agentledger.OTLPTransport{Endpoint: "http://collector", Client: otlp}).Export(context.Background(), []byte(`{}`)); err != nil || otlp.contentType != "application/json" {
		return fmt.Errorf("otlp adapter failed")
	}
	manifest := (agentledger.DockerSandboxAdapter{}).Manifest(agentledger.SandboxPolicy{Network: "deny"}, []string{"echo", "ok"})
	if manifest["network"] != "none" || manifest["read_only_root"] != true || manifest["requires_explicit_execution"] != true {
		return fmt.Errorf("docker adapter manifest failed")
	}
	closed := (agentledger.DockerSandboxExecutor{}).RunTool(context.Background(), agentledger.ToolSpec{Name: "cmd.echo"}, agentledger.JSONObject{"_sandbox_command": []any{"echo", "ok"}}, agentledger.SandboxPolicy{Executor: "docker", Network: "deny", TimeoutSeconds: 1})
	if closed.OK || closed.Metadata["error_type"] != "SandboxAdapterNotInstalled" {
		return fmt.Errorf("docker executor should fail closed without explicit execution")
	}
	executed := (agentledger.DockerSandboxExecutor{Binary: "/bin/echo", Image: "fake-image", AllowCommandExecution: true}).RunTool(context.Background(), agentledger.ToolSpec{Name: "cmd.echo"}, agentledger.JSONObject{"_sandbox_command": []any{"echo", "ok"}}, agentledger.SandboxPolicy{Executor: "docker", Network: "deny", TimeoutSeconds: 1})
	if !executed.OK {
		return fmt.Errorf("docker executor injected binary failed: %s", executed.Error)
	}
	output, ok := executed.Output.(agentledger.JSONObject)
	if !ok || !strings.Contains(fmt.Sprint(output["stdout"]), "fake-image") {
		return fmt.Errorf("docker executor output mismatch: %#v", executed.Output)
	}
	return nil
}
