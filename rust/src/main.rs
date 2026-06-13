use std::env;
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

use agentledger::{
    adversarial_review, builtin_golden_evidence, builtin_golden_names, check_backup_readiness,
    cost_attribution, ddl_for, debug_html, debug_summary, diff_evidence, diff_states,
    divergence_report, evaluate_evidence, evaluate_evidence_regression, export_evidence,
    failure_attribution, golden_regression, latest_schema_version, migrations_for, otlp_trace_json,
    optional_adapter_capabilities, DockerSandboxAdapter, DockerSandboxExecutor, MySQLAdapter, ObjectClient, OtlpClient, OtlpTransport, PostgresAdapter, S3BlobStoreAdapter, SqlExecutor, plan_retention, replay, run_failure_injection_suite, scan_boundary_source, shadow_report,
    simple_run, time_travel, time_travel_html, trace_jsonl, trace_spans, AgentContext,
    BudgetLimits, FunctionAdapter, InMemoryMCPContextServer, InMemoryMCPToolServer, LocalBlobStore,
    LocalWorker, MCPContextAdapter, MCPToolAdapter, MemoryStore, MethodFrameworkAdapter, Runtime,
    RuntimeScheduler, SandboxExecutor, State, ToolSpec, Value, WorkerService,
};

const FIXTURE_CHECKS: &[(&str, &[&str])] = &[
    (
        "runtime_baseline.v1.json",
        &[
            "agentledger.conformance.runtime_baseline.v1",
            "durable_run_evidence_replay",
            "tool_ledger_idempotent_retry",
            "lease_recovery_fences_stale_worker",
            "cancellation_fences_worker",
        ],
    ),
    (
        "local_persistence.v1.json",
        &[
            "agentledger.conformance.local_persistence.v1",
            "local_store_round_trips_completed_run",
            "local_store_preserves_evidence_replay_chain",
            "local_store_uses_atomic_snapshot_write",
        ],
    ),
    (
        "local_blob_store.v1.json",
        &[
            "agentledger.conformance.local_blob_store.v1",
            "blob_roundtrip_json_value",
            "blob_content_address_is_stable",
            "blob_bad_ref_is_rejected",
        ],
    ),
    (
        "tool_schema_validation.v1.json",
        &[
            "agentledger.conformance.tool_schema_validation.v1",
            "invalid_tool_input_rejected_before_execution",
            "valid_tool_input_and_output_pass",
            "invalid_tool_output_rejected",
        ],
    ),
    (
        "worker_service.v1.json",
        &[
            "agentledger.conformance.worker_service.v1",
            "local_worker_runs_until_terminal",
            "worker_service_stops_after_idle_poll",
            "worker_loop_recovers_expired_leases",
        ],
    ),
    (
        "policy_approval_sandbox.v1.json",
        &[
            "agentledger.conformance.policy_approval_sandbox.v1",
            "policy_denies_unapproved_high_risk_tool",
            "approval_pauses_and_resumes_step",
            "sandbox_required_tool_fails_closed",
        ],
    ),
    (
        "cost_failure_attribution.v1.json",
        &[
            "agentledger.conformance.cost_failure_attribution.v1",
            "tool_and_model_cost_attributed_to_run_step_role",
            "budget_exhaustion_blocks_execution",
            "failure_attribution_classifies_agent_tool_model_runtime",
        ],
    ),
    (
        "media_stream_artifacts.v1.json",
        &[
            "agentledger.conformance.media_stream_artifacts.v1",
            "media_artifact_ref_is_indexed_in_evidence",
            "stream_checkpoint_ref_is_indexed_in_evidence",
        ],
    ),
    (
        "evidence_consumers.v1.json",
        &[
            "agentledger.conformance.evidence_consumers.v1",
            "trace_spans_from_evidence",
            "evidence_diff_detects_state_and_event_changes",
            "divergence_report_lists_changed_dimensions",
            "static_debug_summary_is_exportable",
        ],
    ),
    (
        "static_debug_html.v1.json",
        &[
            "agentledger.conformance.static_debug_html.v1",
            "static_debug_html_contains_run_events_and_state",
        ],
    ),
    (
        "ops_readiness.v1.json",
        &[
            "agentledger.conformance.ops_readiness.v1",
            "retention_plan_is_non_destructive_and_counts_evidence",
            "backup_readiness_reports_required_checks",
        ],
    ),
    (
        "storage_schema.v1.json",
        &[
            "agentledger.conformance.storage_schema.v1",
            "latest_schema_version_and_ddl_are_available",
        ],
    ),
    (
        "mcp_adapters.v1.json",
        &[
            "agentledger.conformance.mcp_adapters.v1",
            "in_memory_mcp_tool_server_lists_and_calls_tools",
            "mcp_tool_descriptor_maps_to_tool_spec",
            "in_memory_mcp_context_server_reads_resources",
        ],
    ),
    (
        "framework_adapters.v1.json",
        &[
            "agentledger.conformance.framework_adapters.v1",
            "function_adapter_maps_run_spec_and_invokes_agent",
            "method_framework_adapter_uses_first_available_method_and_writes_output",
        ],
    ),
    (
        "otlp_trace_export.v1.json",
        &[
            "agentledger.conformance.otlp_trace_export.v1",
            "otlp_json_contains_resource_scope_and_spans",
        ],
    ),
    (
        "simple_api.v1.json",
        &[
            "agentledger.conformance.simple_api.v1",
            "simple_run_returns_output_and_state",
        ],
    ),
    (
        "boundary_lint.v1.json",
        &[
            "agentledger.conformance.boundary_lint.v1",
            "direct_shell_and_http_calls_are_reported",
            "ignored_lines_are_not_reported",
        ],
    ),
    (
        "scheduler.v1.json",
        &[
            "agentledger.conformance.scheduler.v1",
            "scheduler_status_reports_run_steps_and_cost",
            "scheduler_recover_and_cancel_delegate_to_store",
        ],
    ),
    (
        "adversarial_review.v1.json",
        &[
            "agentledger.conformance.adversarial_review.v1",
            "clean_evidence_passes_blocker_review",
            "pending_high_risk_approval_blocks_review",
            "max_total_usd_limit_blocks_review",
        ],
    ),
    (
        "evidence_regression.v1.json",
        &[
            "agentledger.conformance.evidence_regression.v1",
            "evidence_health_checks_pass_for_clean_bundle",
            "regression_detects_final_state_and_event_type_changes",
            "regression_cost_delta_limit_blocks",
        ],
    ),
    (
        "failure_injection.v1.json",
        &[
            "agentledger.conformance.failure_injection.v1",
            "retry_exhaustion_marks_run_failed",
            "lease_fencing_rejects_stale_commit",
            "cancellation_fencing_rejects_late_commit",
            "side_effect_idempotency_executes_once_across_retry",
        ],
    ),
    (
        "shadow.v1.json",
        &[
            "agentledger.conformance.shadow.v1",
            "shadow_state_diff_reports_changed_keys",
            "shadow_report_carries_source_shadow_and_ok",
        ],
    ),
    (
        "repro.v1.json",
        &[
            "agentledger.conformance.repro.v1",
            "builtin_golden_names_are_available",
            "minimal_success_golden_is_valid_evidence",
            "golden_regression_detects_changed_final_state",
        ],
    ),
    (
        "time_travel.v1.json",
        &[
            "agentledger.conformance.time_travel.v1",
            "timeline_reconstructs_state_at_selected_seq",
            "timeline_marks_state_changed_frames",
            "time_travel_report_exports_static_html",
        ],
    ),
    (
        "optional_adapters.v1.json",
        &[
            "agentledger.conformance.optional_adapters.v1",
            "optional_backend_capabilities_are_discoverable",
            "postgres",
            "mysql",
            "langgraph",
            "langfuse",
            "shadow-runner",
        ],
    ),
    (
        "official_adapters.v1.json",
        &[
            "agentledger.conformance.official_adapters.v1",
            "postgres_adapter_plans_and_applies_migrations_with_injected_client",
            "mysql_adapter_plans_and_applies_migrations_with_injected_client",
            "s3_blob_adapter_round_trips_json_with_injected_client",
            "otlp_transport_posts_json_with_injected_client",
            "docker_sandbox_adapter_builds_manifest_without_daemon",
            "docker_sandbox_executor_runs_command_style_tool_with_injected_binary",
        ],
    ),
];

fn main() {
    if let Err(error) = run(env::args().skip(1).collect()) {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run(args: Vec<String>) -> Result<(), Box<dyn Error>> {
    match args.as_slice() {
        [] => { print_help(); Ok(()) }
        [command] if command == "--help" || command == "help" => { print_help(); Ok(()) }
        [command] if command == "version" => { println!("agentledger-rust 1.4.0"); Ok(()) }
        [command] if command == "doctor" => { println!("{{\n  \"language\": \"rust\",\n  \"version\": \"1.4.0\",\n  \"status\": \"ok\",\n  \"runtime_core_parity\": true\n}}"); Ok(()) }
        [command] if command == "quickstart" => run_quickstart(),
        [command] if command == "conformance" => run_conformance(),
        [command, action] if command == "contract" && action == "validate" => validate_contract(),
        [command, action] if command == "contract" && action == "export" => {
            print!("{}", fs::read_to_string(contract_path()?)?);
            Ok(())
        }
        _ => Err(format!("unknown command {}; run agentledger-rust --help", args.join(" ")).into()),
    }
}

fn print_help() {
    println!("AgentLedger Rust Runtime 1.4.0\n\nUsage:\n  agentledger-rust doctor\n  agentledger-rust version\n  agentledger-rust quickstart\n  agentledger-rust conformance\n  agentledger-rust contract validate\n  agentledger-rust contract export\n\nProject: https://github.com/yaogdu/AgentLedger");
}

fn run_quickstart() -> Result<(), Box<dyn Error>> {
    fn hello(_ctx: &mut AgentContext, input: State) -> agentledger::Result<Option<Value>> {
        let mut output = State::new();
        output.insert("message".to_string(), Value::String("hello from rust".to_string()));
        output.insert("input".to_string(), input.get("input").cloned().unwrap_or(Value::Null));
        Ok(Some(Value::Object(output)))
    }
    let result = simple_run(hello, state(&[("input", "world".into())]))?;
    println!("{{\n  \"run_id\": \"{}\",\n  \"output_present\": {}\n}}", result.run_id, result.output.is_some());
    Ok(())
}

fn run_conformance() -> Result<(), Box<dyn Error>> {
    let mut checks = validate_fixtures()?;
    checks.extend(run_semantic_smokes()?);
    println!(
        "{{\n  \"language\": \"rust\",\n  \"suite\": \"agentledger_runtime_core\",\n  \"passed\": true,\n  \"checks\": [{}]\n}}",
        checks
            .iter()
            .map(|check| format!("\"{check}\""))
            .collect::<Vec<_>>()
            .join(", ")
    );
    Ok(())
}

fn run_semantic_smokes() -> Result<Vec<String>, Box<dyn Error>> {
    run_runtime_smoke()?;
    run_local_persistence_smoke()?;
    run_local_blob_store_smoke()?;
    run_tool_schema_validation_smoke()?;
    run_worker_service_smoke()?;
    run_tool_ledger_smoke()?;
    run_policy_approval_sandbox_smoke()?;
    run_cost_failure_smoke()?;
    run_media_stream_smoke()?;
    run_evidence_consumers_smoke()?;
    run_static_debug_html_smoke()?;
    run_ops_readiness_smoke()?;
    run_storage_schema_smoke()?;
    run_mcp_adapters_smoke()?;
    run_framework_adapters_smoke()?;
    run_otlp_trace_export_smoke()?;
    run_simple_api_smoke()?;
    run_boundary_lint_smoke()?;
    run_scheduler_smoke()?;
    run_adversarial_review_smoke()?;
    run_evidence_regression_smoke()?;
    if !run_failure_injection_suite().passed {
        return Err("failure injection smoke failed".into());
    }
    run_shadow_smoke()?;
    run_repro_golden_smoke()?;
    run_time_travel_timeline_smoke()?;
    run_optional_adapters_smoke()?;
    run_official_adapters_smoke()?;
    Ok(vec![
        "runtime_smoke_evidence_replay".to_string(),
        "local_persistence_smoke".to_string(),
        "local_blob_store_smoke".to_string(),
        "tool_schema_validation_smoke".to_string(),
        "worker_service_smoke".to_string(),
        "tool_ledger_idempotent_retry".to_string(),
        "policy_approval_sandbox_smoke".to_string(),
        "cost_failure_attribution_smoke".to_string(),
        "media_stream_artifacts_smoke".to_string(),
        "evidence_consumers_smoke".to_string(),
        "static_debug_html_smoke".to_string(),
        "ops_readiness_smoke".to_string(),
        "storage_schema_smoke".to_string(),
        "mcp_adapters_smoke".to_string(),
        "framework_adapters_smoke".to_string(),
        "otlp_trace_export_smoke".to_string(),
        "simple_api_smoke".to_string(),
        "boundary_lint_smoke".to_string(),
        "scheduler_smoke".to_string(),
        "adversarial_review_smoke".to_string(),
        "evidence_regression_smoke".to_string(),
        "failure_injection_smoke".to_string(),
        "shadow_smoke".to_string(),
        "repro_golden_smoke".to_string(),
        "time_travel_timeline_smoke".to_string(),
        "optional_adapters_smoke".to_string(),
        "official_adapters_smoke".to_string(),
    ])
}

fn run_runtime_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(ToolSpec::new(
        "docs.echo",
        Box::new(|args| {
            let mut result = State::new();
            result.insert("echo".to_string(), args["text"].clone());
            Ok(Value::Object(result))
        }),
    ));
    let mut initial = State::new();
    initial.insert("input".to_string(), Value::String("hello".to_string()));
    let (run_id, _) = runtime.create_run(initial);
    let completed = runtime.run_once(
        &run_id,
        "conformance-rust",
        "ConformanceAgent",
        60.0,
        |ctx, state| {
            let mut result = State::new();
            result.insert("echo".to_string(), state["input"].clone());
            ctx.write_state("tool_result", Value::Object(result));
            Ok(())
        },
    )?;
    if !completed {
        return Err("runtime smoke did not complete".into());
    }
    if !runtime
        .store
        .final_state(&run_id)?
        .contains_key("tool_result")
    {
        return Err("runtime smoke missing final state".into());
    }
    let bundle = export_evidence(&runtime.store, &run_id)?;
    let summary = replay(&runtime.store, &run_id)?;
    if bundle.schema_version != "agentledger.evidence.v1"
        || !summary.replay_safe
        || summary.event_count != bundle.events.len()
    {
        return Err("runtime smoke evidence/replay mismatch".into());
    }
    Ok(())
}

fn run_local_persistence_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "docs.persist",
            Box::new(|args| {
                Ok(Value::Object(state(&[
                    ("external_id", "persist-1".into()),
                    ("echo", args["text"].clone()),
                ])))
            }),
        )
        .side_effect("external")
        .idempotency_required(true),
    );
    let (run_id, _) = runtime.create_run(state(&[("input", "persist".into())]));
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-persist", "PersistenceAgent")?;
    let result = runtime.call_tool(&ctx, "docs.persist", state(&[("text", "persist".into())]))?;
    ctx.write_state("tool_result", result);
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let path = std::env::temp_dir().join(format!("agentledger-rust-{}.store", run_id));
    runtime.store.save_to_path(&path)?;
    let reopened = MemoryStore::load_from_path(&path)?;
    let _ = fs::remove_file(&path);
    if !reopened.final_state(&run_id)?.contains_key("tool_result") {
        return Err("local persistence smoke missing reopened final state".into());
    }
    let bundle = export_evidence(&reopened, &run_id)?;
    let summary = replay(&reopened, &run_id)?;
    if bundle.bundle_hash.is_empty()
        || !summary.replay_safe
        || summary.event_count != bundle.events.len()
        || reopened.ledger(&run_id).len() != 1
        || summary.tool_call_count == 0
    {
        return Err("local persistence evidence/replay mismatch".into());
    }
    Ok(())
}

fn run_local_blob_store_smoke() -> Result<(), Box<dyn Error>> {
    let root = std::env::temp_dir().join(format!("agentledger-rust-blobs-{}", std::process::id()));
    let blobs = LocalBlobStore::open(&root)?;
    let value = Value::Object(state(&[
        ("hello", "world".into()),
        ("nested", Value::Object(state(&[("n", 1_i64.into())]))),
    ]));
    let first = blobs.put_json(&value)?;
    let second = blobs.put_json(&value)?;
    if !first.0.starts_with("sha256:") || !first.1.starts_with("blob://sha256/") {
        return Err("local blob store invalid digest/ref".into());
    }
    if first != second {
        return Err("local blob store ref was not stable".into());
    }
    if blobs.get_json(&first.1)? != value {
        return Err("local blob store roundtrip mismatch".into());
    }
    if blobs.get_json("unsupported://blob").is_ok() {
        return Err("local blob store accepted unsupported ref".into());
    }
    let _ = fs::remove_dir_all(root);
    Ok(())
}

fn run_tool_schema_validation_smoke() -> Result<(), Box<dyn Error>> {
    let input_schema = Value::Object(state(&[
        ("type", "object".into()),
        (
            "required",
            Value::Array(vec![Value::String("text".to_string())]),
        ),
        ("additionalProperties", false.into()),
        (
            "properties",
            Value::Object(state(&[(
                "text",
                Value::Object(state(&[
                    ("type", "string".into()),
                    ("minLength", 1_i64.into()),
                ])),
            )])),
        ),
    ]));
    let output_schema = Value::Object(state(&[
        ("type", "object".into()),
        (
            "required",
            Value::Array(vec![Value::String("echo".to_string())]),
        ),
        ("additionalProperties", false.into()),
        (
            "properties",
            Value::Object(state(&[(
                "echo",
                Value::Object(state(&[("type", "string".into())])),
            )])),
        ),
    ]));
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "docs.echo",
            Box::new(|args| Ok(Value::Object(state(&[("echo", args["text"].clone())])))),
        )
        .input_schema(input_schema.clone())
        .output_schema(output_schema.clone()),
    );
    let (bad_run, _) = runtime.create_run(State::new());
    let ctx = claim_context(&mut runtime, &bad_run, "worker-schema", "SchemaAgent")?;
    if runtime.call_tool(&ctx, "docs.echo", State::new()).is_ok() {
        return Err("tool schema input validation smoke accepted invalid input".into());
    }
    if runtime
        .store
        .events(&bad_run)
        .iter()
        .any(|event| event.event_type == "tool_call_completed")
    {
        return Err("tool schema input validation recorded completion".into());
    }
    let (good_run, _) = runtime.create_run(state(&[("text", "hello".into())]));
    let mut ctx = claim_context(&mut runtime, &good_run, "worker-schema", "SchemaAgent")?;
    let result = runtime.call_tool(&ctx, "docs.echo", state(&[("text", "hello".into())]))?;
    ctx.write_state("result", result);
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let mut bad_output = Runtime::new();
    bad_output.register_tool(
        ToolSpec::new(
            "docs.bad",
            Box::new(|_| Ok(Value::Object(state(&[("bad", true.into())])))),
        )
        .output_schema(output_schema),
    );
    let (bad_out_run, _) = bad_output.create_run(State::new());
    let ctx = claim_context(
        &mut bad_output,
        &bad_out_run,
        "worker-schema",
        "SchemaAgent",
    )?;
    if bad_output.call_tool(&ctx, "docs.bad", State::new()).is_ok() {
        return Err("tool schema output validation smoke accepted invalid output".into());
    }
    if bad_output
        .store
        .events(&bad_out_run)
        .iter()
        .any(|event| event.event_type == "tool_call_completed")
    {
        return Err("tool schema output validation recorded completion".into());
    }
    Ok(())
}

fn worker_smoke_agent(ctx: &mut AgentContext, _state: State) -> agentledger::Result<()> {
    ctx.write_state("done", Value::Bool(true));
    Ok(())
}

fn run_worker_service_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "worker".into())]));
    let worker = LocalWorker::new("worker-service", "WorkerAgent");
    let summary = worker.run_until_idle(&mut runtime, &run_id, 3, worker_smoke_agent)?;
    if summary.attempts != 1
        || summary.succeeded_attempts != 1
        || summary.final_status.as_deref() != Some("completed")
        || summary.stopped_reason != "terminal_status"
    {
        return Err("worker terminal smoke mismatch".into());
    }
    let mut service = WorkerService::new(LocalWorker::new("worker-service", "WorkerAgent"));
    let terminal = service.serve(&mut runtime, Some(&run_id), 3, Some(1), worker_smoke_agent)?;
    if terminal.stopped_reason != "terminal_status" {
        return Err("worker service terminal smoke mismatch".into());
    }
    let mut empty = WorkerService::new(LocalWorker::new("worker-service", "WorkerAgent"));
    let idle = empty.serve(&mut runtime, None, 3, Some(1), worker_smoke_agent)?;
    if idle.stopped_reason != "idle" || idle.idle_polls != 1 || idle.attempts != 0 {
        return Err("worker service idle smoke mismatch".into());
    }
    Ok(())
}

fn run_tool_ledger_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "github.create_pr",
            Box::new(|args| {
                Ok(Value::Object(state(&[
                    ("external_id", "pr-123".into()),
                    ("title", args["title"].clone()),
                ])))
            }),
        )
        .side_effect("external")
        .idempotency_required(true),
    );
    let (run_id, _) = runtime.create_run(state(&[("title", "runtime parity".into())]));
    let ctx = claim_context(&mut runtime, &run_id, "worker-a", "Coder")?;
    let first = runtime.call_tool(
        &ctx,
        "github.create_pr",
        state(&[("title", "runtime parity".into())]),
    )?;
    runtime
        .store
        .mark_retry(&run_id, &ctx.step_id, "RetryableAgentError", "retryable");
    let ctx2 = claim_context(&mut runtime, &run_id, "worker-b", "Coder")?;
    let second = runtime.call_tool(
        &ctx2,
        "github.create_pr",
        state(&[("title", "runtime parity".into())]),
    )?;
    if first != second || runtime.store.ledger(&run_id).len() != 1 {
        return Err("tool ledger smoke mismatch".into());
    }
    Ok(())
}

fn run_policy_approval_sandbox_smoke() -> Result<(), Box<dyn Error>> {
    run_policy_smoke()?;
    run_approval_smoke()?;
    run_sandbox_smoke()
}

fn run_policy_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new("repo.write", Box::new(|_| Ok(Value::Bool(true)))).risk_level("high"),
    );
    let (run_id, _) = runtime.create_run(State::new());
    let ctx = claim_context(&mut runtime, &run_id, "worker", "Reviewer")?;
    let err = runtime
        .call_tool(&ctx, "repo.write", state(&[("path", "README.md".into())]))
        .unwrap_err();
    if !err.0.contains("high-risk")
        || !runtime.store.events(&run_id).iter().any(|event| {
            event.event_type == "tool_permission_decided"
                && event.payload.get("allowed") == Some(&Value::Bool(false))
        })
    {
        return Err("policy smoke mismatch".into());
    }
    Ok(())
}

fn run_approval_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new(
            "github.create_pr",
            Box::new(|_| Ok(Value::Object(state(&[("external_id", "pr-42".into())])))),
        )
        .risk_level("high")
        .approval_required(true)
        .side_effect("external")
        .idempotency_required(true),
    );
    let (run_id, _) = runtime.create_run(State::new());
    let ctx = claim_context(&mut runtime, &run_id, "worker-a", "Coder")?;
    let err = runtime
        .call_tool(&ctx, "github.create_pr", state(&[("title", "safe".into())]))
        .unwrap_err();
    let approval_id = err.0.trim_start_matches("approval required:").to_string();
    runtime
        .store
        .mark_waiting_human(&run_id, &ctx.step_id, &err.0, &approval_id);
    runtime
        .store
        .approve_request(&approval_id, "alice", "reviewed")?;
    let ctx2 = claim_context(&mut runtime, &run_id, "worker-b", "Coder")?;
    let result = runtime.call_tool(
        &ctx2,
        "github.create_pr",
        state(&[("title", "safe".into())]),
    )?;
    if !matches!(result, Value::Object(_)) {
        return Err("approval smoke mismatch".into());
    }
    Ok(())
}

fn run_sandbox_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.register_tool(
        ToolSpec::new("shell.exec", Box::new(|_| Ok(Value::Bool(true)))).sandbox_required(true),
    );
    let (run_id, _) = runtime.create_run(State::new());
    let ctx = claim_context(&mut runtime, &run_id, "worker", "Executor")?;
    let err = runtime
        .call_tool(
            &ctx,
            "shell.exec",
            state(&[("argv", Value::Object(State::new()))]),
        )
        .unwrap_err();
    let events = runtime.store.events(&run_id);
    if !err.0.contains("sandbox executor")
        || !events
            .iter()
            .any(|event| event.event_type == "sandbox_started")
        || !events
            .iter()
            .any(|event| event.event_type == "tool_call_failed")
    {
        return Err("sandbox smoke mismatch".into());
    }
    Ok(())
}

fn run_cost_failure_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    runtime.set_budget(BudgetLimits {
        max_tool_calls: Some(1.0),
        max_model_tokens: None,
        max_total_usd: None,
    });
    runtime.register_tool(ToolSpec::new(
        "docs.echo",
        Box::new(|args| Ok(Value::Object(state(&[("echo", args["text"].clone())])))),
    ));
    let (run_id, _) = runtime.create_run(State::new());
    let ctx = claim_context(&mut runtime, &run_id, "worker", "Researcher")?;
    runtime.record_model_call(&ctx, "gpt-test", 10.0, 5.0, 0.01)?;
    runtime.call_tool(&ctx, "docs.echo", state(&[("text", "first".into())]))?;
    let err = runtime
        .call_tool(&ctx, "docs.echo", state(&[("text", "second".into())]))
        .unwrap_err();
    runtime
        .store
        .mark_failed(&run_id, &ctx.step_id, "BudgetExceededError", &err.0);
    let summary = runtime.store.cost_summary(&run_id);
    let cost = cost_attribution(&runtime.store, &run_id);
    let failure = failure_attribution(&runtime.store, &run_id)?;
    if summary.tool_calls != 1.0
        || summary.model_tokens != 15.0
        || summary.total_usd != 0.01
        || cost.by_agent["Researcher"].tool_calls != 1.0
        || failure.summary["failed_step_count"] != Value::Number(1.0)
        || !failure
            .failure_events
            .iter()
            .any(|event| event.event_type == "budget_check_failed")
    {
        return Err("cost/failure smoke mismatch".into());
    }
    Ok(())
}

fn run_media_stream_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(State::new());
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-media", "MediaAgent")?;
    let frame = runtime.create_media_artifact(
        &ctx,
        "frame-0001",
        "frame",
        agentledger::MediaArtifactOptions {
            uri: Some("s3://media/demo/frame-0001.jpg".to_string()),
            media_metadata: state(&[("mime_type", "image/jpeg".into())]),
            lineage: State::new(),
            derived_outputs: State::new(),
            metadata: State::new(),
            content_ref: None,
        },
    )?;
    let checkpoint = runtime.create_stream_checkpoint(
        &ctx,
        "camera-checkpoint",
        agentledger::StreamCheckpointOptions {
            stream_id: "camera-1".to_string(),
            consumer_id: "vision-agent".to_string(),
            offset: Value::Number(7.0),
            watermark: None,
            chunk: Some(agentledger::StreamChunkRef {
                stream_id: "camera-1".to_string(),
                chunk_id: "chunk-7".to_string(),
                offset: Value::Number(7.0),
                content_ref: None,
                content_hash: None,
                sequence: None,
                event_time: None,
                metadata: State::new(),
            }),
            partial_result_ref: None,
            backpressure: State::new(),
            metadata: State::new(),
        },
    )?;
    let mut artifacts = State::new();
    artifacts.insert("frame".to_string(), Value::String(frame));
    artifacts.insert("checkpoint".to_string(), Value::String(checkpoint));
    ctx.write_state("artifacts", Value::Object(artifacts));
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let bundle = export_evidence(&runtime.store, &run_id)?;
    let summary = replay(&runtime.store, &run_id)?;
    if bundle.artifacts.len() != 2
        || bundle.media_artifacts.len() != 1
        || bundle.stream_checkpoints.len() != 1
        || summary.media_artifact_count != 1
        || summary.stream_checkpoint_count != 1
    {
        return Err("media/stream smoke mismatch".into());
    }
    Ok(())
}

fn run_static_debug_html_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "debug".into())]));
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-debug", "DebugAgent")?;
    ctx.write_state("answer", "debug".into());
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let html = debug_html(&export_evidence(&runtime.store, &run_id)?);
    for token in [
        "<!doctype html>",
        "AgentLedger Debug Report",
        "Run",
        "Events",
        "Final State",
        "run_created",
    ] {
        if !html.contains(token) {
            return Err(format!("static debug html smoke missing {token}").into());
        }
    }
    Ok(())
}

fn run_ops_readiness_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "ops".into())]));
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-ops", "OpsAgent")?;
    runtime.create_media_artifact(
        &ctx,
        "frame-ops",
        "frame",
        agentledger::MediaArtifactOptions {
            uri: Some("file://frame.png".to_string()),
            media_metadata: State::new(),
            lineage: State::new(),
            derived_outputs: State::new(),
            metadata: State::new(),
            content_ref: None,
        },
    )?;
    ctx.write_state("answer", "ops".into());
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let bundle = export_evidence(&runtime.store, &run_id)?;
    let plan = plan_retention(&bundle);
    if plan.destructive
        || plan.event_count != bundle.events.len()
        || plan.media_artifact_count != 1
        || !plan
            .actions
            .iter()
            .any(|item| item == "export evidence bundle before destructive retention")
        || !plan
            .actions
            .iter()
            .any(|item| item == "snapshot final state and manifest")
    {
        return Err("ops retention plan smoke mismatch".into());
    }
    let report = check_backup_readiness(&bundle);
    for name in [
        "run_metadata_exists",
        "payload_refs_resolvable",
        "evidence_exportable",
        "media_stream_evidence_shape",
    ] {
        if !report
            .checks
            .iter()
            .any(|check| check.name == name && check.passed)
        {
            return Err(format!("ops backup readiness missing {name}").into());
        }
    }
    Ok(())
}

fn run_storage_schema_smoke() -> Result<(), Box<dyn Error>> {
    for dialect in ["sqlite", "postgres", "mysql"] {
        if latest_schema_version(dialect)? != Some("0001".to_string()) {
            return Err(format!("storage schema version mismatch for {dialect}").into());
        }
        let migrations = migrations_for(dialect)?;
        if migrations.len() != 1
            || migrations[0].name != "initial_runtime_metadata"
            || !migrations[0].checksum().starts_with("sha256:")
        {
            return Err(format!("storage schema migrations mismatch for {dialect}").into());
        }
        let ddl = ddl_for(dialect)?;
        for token in [
            "schema_migrations",
            "CREATE TABLE IF NOT EXISTS runs",
            "CREATE TABLE IF NOT EXISTS events",
            "CREATE TABLE IF NOT EXISTS tool_ledger",
        ] {
            if !ddl.contains(token) {
                return Err(format!("storage schema ddl for {dialect} missing {token}").into());
            }
        }
    }
    Ok(())
}

fn mcp_echo(name: &str, args: State) -> agentledger::Result<Value> {
    Ok(Value::Object(state(&[
        ("name", name.into()),
        ("echo", args.get("text").cloned().unwrap_or_default()),
    ])))
}

fn mcp_resource(uri: &str) -> agentledger::Result<Value> {
    Ok(Value::Object(state(&[("uri", uri.into())])))
}

fn run_mcp_adapters_smoke() -> Result<(), Box<dyn Error>> {
    let mut server = InMemoryMCPToolServer::new();
    server.add_tool(
        state(&[
            ("name", "docs.echo".into()),
            (
                "annotations",
                Value::Object(state(&[("side_effect", "none".into())])),
            ),
        ]),
        mcp_echo,
    );
    server.add_tool(state(&[("name", "web.search".into())]), mcp_echo);
    let tools = server.list_tools();
    if tools.len() != 2 || tools[0].get("name") != Some(&Value::String("docs.echo".to_string())) {
        return Err("mcp tool server list mismatch".into());
    }
    if server.call_tool("missing", State::new()).is_ok() {
        return Err("mcp missing tool should fail".into());
    }
    let spec = (MCPToolAdapter {
        client_call: mcp_echo,
    })
    .tool_spec_from_descriptor(&state(&[
        ("name", "github.create_pr".into()),
        (
            "annotations",
            Value::Object(state(&[
                ("side_effect", "external".into()),
                ("risk_level", "high".into()),
            ])),
        ),
    ]));
    if spec.name != "github.create_pr"
        || spec.side_effect != "external"
        || spec.risk_level != "high"
        || !spec.idempotency_required
    {
        return Err("mcp tool adapter spec mismatch".into());
    }
    let mut ctx_server = InMemoryMCPContextServer::new();
    ctx_server.add_resource("docs://readme", "README", "application/json", mcp_resource);
    let resources = ctx_server.list_resources();
    if resources.len() != 1
        || resources[0].get("mimeType") != Some(&Value::String("application/json".to_string()))
    {
        return Err("mcp context list mismatch".into());
    }
    if !ctx_server
        .read_resource("docs://readme")?
        .contains_key("content")
    {
        return Err("mcp context read mismatch".into());
    }
    let read_spec = (MCPContextAdapter {
        resource_read: mcp_resource,
    })
    .read_tool_spec("", "");
    if read_spec.name != "mcp.context.read" || read_spec.side_effect != "none" {
        return Err("mcp context adapter spec mismatch".into());
    }
    Ok(())
}

fn framework_function(_ctx: &mut AgentContext, state: State) -> agentledger::Result<Option<Value>> {
    Ok(Some(Value::Object(crate::state(&[
        ("kind", "function".into()),
        ("input", state.get("input").cloned().unwrap_or_default()),
    ]))))
}

fn framework_method(state: State) -> agentledger::Result<Value> {
    Ok(Value::Object(crate::state(&[
        ("kind", "method".into()),
        ("input", state.get("input").cloned().unwrap_or_default()),
    ])))
}

fn run_framework_adapters_smoke() -> Result<(), Box<dyn Error>> {
    let function_adapter = FunctionAdapter::new(framework_function, "Agent");
    if function_adapter.map_run_spec().get("adapter")
        != Some(&Value::String("function".to_string()))
    {
        return Err("function adapter run spec mismatch".into());
    }
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "adapter".into())]));
    let mut ctx = claim_context(
        &mut runtime,
        &run_id,
        "worker-adapter",
        &function_adapter.role,
    )?;
    function_adapter.run(&mut ctx, runtime.store.final_state(&run_id)?, "output")?;
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    if !runtime.store.final_state(&run_id)?.contains_key("output") {
        return Err("function adapter missing output".into());
    }
    let mut methods = std::collections::HashMap::new();
    methods.insert(
        "invoke".to_string(),
        framework_method as agentledger::MethodHandler,
    );
    let method_adapter = MethodFrameworkAdapter::new(
        "Target",
        "FrameworkAgent",
        vec!["ainvoke".to_string(), "invoke".to_string()],
        methods,
        "output",
    );
    if method_adapter.map_run_spec().get("adapter")
        != Some(&Value::String("method-framework".to_string()))
    {
        return Err("method adapter run spec mismatch".into());
    }
    let mut runtime2 = Runtime::new();
    let (run_id2, _) = runtime2.create_run(state(&[("input", "method".into())]));
    let mut ctx2 = claim_context(
        &mut runtime2,
        &run_id2,
        "worker-method",
        &method_adapter.role,
    )?;
    method_adapter.run(&mut ctx2, runtime2.store.final_state(&run_id2)?)?;
    runtime2.store.commit_state_patch(
        &ctx2.run_id,
        &ctx2.step_id,
        &ctx2.lease_token,
        ctx2.state_version,
        ctx2.pending_patch,
    )?;
    if !runtime2.store.final_state(&run_id2)?.contains_key("output") {
        return Err("method adapter missing output".into());
    }
    Ok(())
}

fn run_otlp_trace_export_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "otlp".into())]));
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-otlp", "TraceAgent")?;
    ctx.write_state("answer", "otlp".into());
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let bundle = export_evidence(&runtime.store, &run_id)?;
    let otlp = otlp_trace_json(&bundle, "agentledger-test", Some("1.0.0"));
    let body = format!("{:?}", otlp);
    for token in [
        "resourceSpans",
        "service.name",
        "scopeSpans",
        "traceId",
        "spanId",
        "agentledger.original_trace_id",
        "agentledger.run_id",
    ] {
        if !body.contains(token) {
            return Err(format!("otlp trace smoke missing {token}").into());
        }
    }
    Ok(())
}

fn simple_agent(_ctx: &mut AgentContext, state: State) -> agentledger::Result<Option<Value>> {
    Ok(Some(Value::Object(crate::state(&[
        ("message", "hello".into()),
        ("input", state.get("input").cloned().unwrap_or_default()),
    ]))))
}

fn run_simple_api_smoke() -> Result<(), Box<dyn Error>> {
    let result = simple_run(simple_agent, state(&[("input", "world".into())]))?;
    if !result.ok
        || result.output.is_none()
        || !result.state.contains_key("output")
        || result.session_id.is_empty()
    {
        return Err("simple api smoke result mismatch".into());
    }
    Ok(())
}

fn run_evidence_consumers_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", "left".into())]));
    let mut ctx = claim_context(&mut runtime, &run_id, "worker-evidence", "EvidenceAgent")?;
    runtime.create_media_artifact(
        &ctx,
        "frame-0001",
        "frame",
        agentledger::MediaArtifactOptions {
            uri: Some("file://frame.png".to_string()),
            media_metadata: State::new(),
            lineage: state(&[("source", "camera".into())]),
            derived_outputs: State::new(),
            metadata: State::new(),
            content_ref: None,
        },
    )?;
    runtime.create_stream_checkpoint(
        &ctx,
        "audio-checkpoint",
        agentledger::StreamCheckpointOptions {
            stream_id: "audio-stream".to_string(),
            consumer_id: "asr".to_string(),
            offset: Value::Number(1.0),
            watermark: Some(Value::String("00:00:01".to_string())),
            chunk: Some(agentledger::StreamChunkRef {
                stream_id: "audio-stream".to_string(),
                chunk_id: "c1".to_string(),
                offset: Value::Number(1.0),
                content_ref: None,
                content_hash: None,
                sequence: None,
                event_time: None,
                metadata: State::new(),
            }),
            partial_result_ref: None,
            backpressure: State::new(),
            metadata: State::new(),
        },
    )?;
    ctx.write_state("answer", "left".into());
    runtime.store.commit_state_patch(
        &ctx.run_id,
        &ctx.step_id,
        &ctx.lease_token,
        ctx.state_version,
        ctx.pending_patch,
    )?;
    let left = export_evidence(&runtime.store, &run_id)?;
    let mut right = left.clone();
    right.run.run_id = format!("{}-shadow", left.run.run_id);
    right.bundle_hash = "different".to_string();
    right.final_state = state(&[("answer", "right".into())]);
    let mut shadow = left.events.last().cloned().ok_or("missing events")?;
    shadow.seq = left.events.len() as u64 + 1;
    shadow.event_type = "shadow_event".to_string();
    right.events.push(shadow);
    right.media_artifacts.clear();
    right.stream_checkpoints.clear();
    let spans = trace_spans(&left);
    if spans.is_empty()
        || spans[0].span_id != "evt-000001"
        || !spans.iter().any(|span| span.name == "media_artifact")
        || !spans.iter().any(|span| span.name == "stream_checkpoint")
        || !trace_jsonl(&left).contains("evt-000001")
    {
        return Err("trace span smoke mismatch".into());
    }
    let diff = diff_evidence(&left, &right);
    if diff.same
        || diff.final_state_changed_count == 0
        || diff.event_types_changed_count == 0
        || diff.media_artifacts_changed_count == 0
        || diff.stream_checkpoints_changed_count == 0
    {
        return Err("evidence diff smoke mismatch".into());
    }
    let divergence = divergence_report(&left, &right);
    for dimension in ["events", "state", "media_artifacts", "stream_checkpoints"] {
        if !divergence
            .changed_dimensions
            .iter()
            .any(|item| item == dimension)
        {
            return Err(format!("divergence smoke missing {dimension}").into());
        }
    }
    let debug = debug_summary(&left);
    if debug.get("run_id") != Some(&Value::String(run_id.clone()))
        || debug.get("event_count") != Some(&Value::Number(left.events.len() as f64))
    {
        return Err("debug summary smoke mismatch".into());
    }
    Ok(())
}

fn claim_context(
    runtime: &mut Runtime,
    run_id: &str,
    worker: &str,
    role: &str,
) -> Result<AgentContext, Box<dyn Error>> {
    let claim = runtime.store.claim_step(worker, run_id, 60.0)?;
    let (_state, version, session_id) = runtime.store.load_state(run_id)?;
    let mut payload = State::new();
    payload.insert("agent_role".to_string(), Value::String(role.to_string()));
    runtime.store.append_event(
        run_id,
        Some(&session_id),
        Some(&claim.step_id),
        "agent_started",
        payload,
        Some(role),
        Some(version),
        None,
    );
    Ok(AgentContext {
        run_id: run_id.to_string(),
        session_id,
        step_id: claim.step_id,
        agent_role: role.to_string(),
        lease_token: claim.lease_token,
        attempt: claim.attempt,
        state_version: version,
        pending_patch: State::new(),
    })
}

fn state(items: &[(&str, Value)]) -> State {
    items
        .iter()
        .map(|(key, value)| ((*key).to_string(), value.clone()))
        .collect()
}

fn validate_contract() -> Result<(), Box<dyn Error>> {
    let body = fs::read_to_string(contract_path()?)?;
    for token in [
        "\"contract_version\": \"1.0\"",
        "\"language\": \"rust\"",
        "\"status\": \"preview\"",
        "media_stream_artifacts.v1.json",
    ] {
        if !body.contains(token) {
            return Err(format!("contract missing {token}").into());
        }
    }
    Ok(())
}

fn validate_fixtures() -> Result<Vec<String>, Box<dyn Error>> {
    validate_contract()?;
    let root = find_repo_root()?;
    let mut checks = vec!["contract_validate".to_string()];
    for (file, tokens) in FIXTURE_CHECKS {
        let body = fs::read_to_string(root.join("contracts").join("conformance").join(file))?;
        for token in *tokens {
            if !body.contains(token) {
                return Err(format!("fixture {file} missing {token}").into());
            }
        }
        checks.push((*file).to_string());
    }
    Ok(checks)
}

fn contract_path() -> Result<PathBuf, Box<dyn Error>> {
    Ok(find_repo_root()?
        .join("contracts")
        .join("agentledger.runtime.v1.json"))
}

fn find_repo_root() -> Result<PathBuf, Box<dyn Error>> {
    if let Ok(root) = env::var("AGENTLEDGER_REPO_ROOT") {
        return Ok(PathBuf::from(root));
    }
    let mut current = env::current_dir()?;
    loop {
        if current
            .join("contracts")
            .join("agentledger.runtime.v1.json")
            .exists()
        {
            return Ok(current);
        }
        if !current.pop() {
            break;
        }
    }
    Err("could not find AgentLedger repository root".into())
}

#[allow(dead_code)]
fn _path_exists(path: &Path) -> bool {
    path.exists()
}

fn run_boundary_lint_smoke() -> Result<(), Box<dyn Error>> {
    let report = scan_boundary_source("agent.py", "import os\nimport requests\nos.system('echo unsafe')\nrequests.post('https://example.com')\n", None);
    if report.passed || report.finding_count != 2 {
        return Err("boundary lint finding count mismatch".into());
    }
    if report.findings[0].rule_id != "direct-shell-os-system"
        || report.findings[1].rule_id != "direct-http-requests"
    {
        return Err("boundary lint rule mismatch".into());
    }
    let ignored = scan_boundary_source(
        "agent.py",
        "import os\n# agentledger: ignore-next-line\nos.system('echo intentional')\n",
        None,
    );
    if !ignored.passed || ignored.finding_count != 0 {
        return Err("boundary lint ignore mismatch".into());
    }
    Ok(())
}

fn run_scheduler_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", Value::String("scheduler".into()))]));
    let status = RuntimeScheduler::status(&runtime.store, &run_id)?;
    if status.run_id != run_id || status.run_status != "pending" || status.steps.len() != 1 {
        return Err("scheduler status mismatch".into());
    }
    let _claim = runtime.store.claim_step("scheduler-stale", &run_id, 0.0)?;
    let recovery = RuntimeScheduler::recover_expired_leases(&mut runtime.store);
    if recovery.recovered_steps != 1 {
        return Err("scheduler recovered steps mismatch".into());
    }
    let cancelled = RuntimeScheduler::cancel_run(&mut runtime.store, &run_id, "scheduler smoke")?;
    if cancelled != 1 {
        return Err("scheduler cancelled steps mismatch".into());
    }
    let status = RuntimeScheduler::status(&runtime.store, &run_id)?;
    if status.run_status != "cancelled" || status.steps[0].status != "cancelled" {
        return Err("scheduler cancelled status mismatch".into());
    }
    Ok(())
}

fn run_adversarial_review_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", Value::String("review".into()))]));
    runtime.run_once(
        &run_id,
        "review-worker",
        "ReviewAgent",
        60.0,
        |ctx, _state| {
            ctx.write_state("answer", Value::String("ok".into()));
            Ok(())
        },
    )?;
    let bundle = export_evidence(&runtime.store, &run_id)?;
    if !adversarial_review(&bundle, None).passed {
        return Err("clean adversarial review should pass".into());
    }
    let mut pending = bundle.clone();
    pending.approvals.push(agentledger::ApprovalRequest {
        approval_id: "approval_pending".into(),
        approval_key: "key".into(),
        run_id: run_id.clone(),
        session_id: "session".into(),
        step_id: "step".into(),
        tool_name: "dangerous.tool".into(),
        risk_level: "high".into(),
        status: "PENDING".into(),
        reason: "test".into(),
        request_hash: "hash".into(),
        request_ref: "ref".into(),
        requested_by: "tester".into(),
        approved_by: None,
        decision_reason: None,
        created_at: 0.0,
        updated_at: 0.0,
    });
    if adversarial_review(&pending, None).passed {
        return Err("pending high-risk approval should block".into());
    }
    let mut costly = bundle.clone();
    costly.cost_summary.total_usd = 1.0;
    if adversarial_review(&costly, Some(0.5)).passed {
        return Err("cost limit should block".into());
    }
    Ok(())
}

fn run_evidence_regression_smoke() -> Result<(), Box<dyn Error>> {
    let mut runtime = Runtime::new();
    let (run_id, _) = runtime.create_run(state(&[("input", Value::String("eval".into()))]));
    runtime.run_once(&run_id, "eval-worker", "EvalAgent", 60.0, |ctx, _state| {
        ctx.write_state("answer", Value::String("ok".into()));
        Ok(())
    })?;
    let bundle = export_evidence(&runtime.store, &run_id)?;
    if !evaluate_evidence(&bundle, None).passed {
        return Err("clean evidence health check should pass".into());
    }
    let mut changed = bundle.clone();
    changed
        .final_state
        .insert("answer".into(), Value::String("changed".into()));
    changed.events.push(agentledger::Event {
        event_id: "event_extra".into(),
        run_id: run_id.clone(),
        session_id: None,
        step_id: None,
        seq: changed.events.len() as u64 + 1,
        event_type: "extra_event".into(),
        timestamp: 0.0,
        agent_role: None,
        state_version: None,
        causal_token: None,
        payload_hash: "".into(),
        payload_ref: "".into(),
        payload: State::new(),
    });
    if evaluate_evidence_regression(&bundle, &changed, None).passed {
        return Err("regression changes should fail".into());
    }
    let mut costly = bundle.clone();
    costly.cost_summary.total_usd = 1.0;
    if evaluate_evidence_regression(&bundle, &costly, Some(0.5)).passed {
        return Err("cost delta should fail".into());
    }
    Ok(())
}

fn run_shadow_smoke() -> Result<(), Box<dyn Error>> {
    let source = state(&[
        ("answer", Value::String("old".into())),
        ("stable", Value::Bool(true)),
    ]);
    let shadow = state(&[
        ("answer", Value::String("new".into())),
        ("stable", Value::Bool(true)),
        ("extra", Value::Number(1.0)),
    ]);
    let diff = diff_states(&source, &shadow);
    if diff.get("changed_count") != Some(&Value::Number(2.0)) {
        return Err("shadow diff changed_count mismatch".into());
    }
    let report = shadow_report("run_source", "run_shadow", true, &source, &shadow);
    if report.source_run_id != "run_source" || report.shadow_run_id != "run_shadow" || !report.ok {
        return Err("shadow report mismatch".into());
    }
    Ok(())
}

fn run_repro_golden_smoke() -> Result<(), Box<dyn Error>> {
    if builtin_golden_names().join(",")
        != "media-stream-checkpoint,minimal-success,tool-ledger-success"
    {
        return Err("builtin golden names mismatch".into());
    }
    let bundle = builtin_golden_evidence("minimal-success")?;
    if bundle.schema_version != "agentledger.evidence.v1"
        || bundle.final_state.get("answer") != Some(&Value::String("ok".into()))
    {
        return Err("minimal golden evidence mismatch".into());
    }
    let mut changed = bundle.clone();
    changed
        .final_state
        .insert("answer".into(), Value::String("changed".into()));
    if golden_regression(&bundle, &changed).passed {
        return Err("golden regression should detect final state change".into());
    }
    Ok(())
}

fn run_time_travel_timeline_smoke() -> Result<(), Box<dyn Error>> {
    let bundle = builtin_golden_evidence("minimal-success")?;
    let report = time_travel(&bundle, Some(999), true);
    if report.state_at_seq.get("answer") != Some(&Value::String("ok".into()))
        || report.event_count != bundle.events.len()
    {
        return Err("time travel state mismatch".into());
    }
    if !report.timeline.iter().any(|frame| frame.state_changed) {
        return Err("time travel missing changed frame".into());
    }
    let html = time_travel_html(&report);
    for token in [
        "AgentLedger Time Travel Report",
        "State At Selected Point",
        "Selected Event",
    ] {
        if !html.contains(token) {
            return Err(format!("time travel html missing {token}").into());
        }
    }
    Ok(())
}

fn run_optional_adapters_smoke() -> Result<(), Box<dyn Error>> {
    let caps = optional_adapter_capabilities();
    let names: std::collections::HashSet<String> = caps.iter().map(|cap| cap.name.clone()).collect();
    for cap in &caps {
        if cap.core_imports_heavy_sdks || !cap.adapter_is_optional || !cap.fail_closed_without_adapter || cap.contract_surface.is_empty() {
            return Err(format!("invalid optional adapter capability: {}", cap.name).into());
        }
    }
    for name in ["postgres", "mysql", "s3", "docker", "langgraph", "mcp-transport", "langfuse", "shadow-runner"] {
        if !names.contains(name) {
            return Err(format!("missing optional adapter capability: {name}").into());
        }
    }
    Ok(())
}

#[derive(Default)]
struct FakeSql { count: usize }
impl SqlExecutor for FakeSql { fn exec(&mut self, _sql: &str, _params: &[Value]) -> agentledger::Result<()> { self.count += 1; Ok(()) } }
#[derive(Default)]
struct FakeObjects { objects: std::collections::HashMap<String, Vec<u8>>, content_type: String }
impl ObjectClient for FakeObjects {
    fn put_object(&mut self, bucket: &str, key: &str, body: &[u8], content_type: &str, _metadata: State) -> agentledger::Result<()> { self.objects.insert(format!("{bucket}/{key}"), body.to_vec()); self.content_type = content_type.to_string(); Ok(()) }
    fn get_object(&mut self, bucket: &str, key: &str) -> agentledger::Result<Vec<u8>> { Ok(self.objects.get(&format!("{bucket}/{key}")).cloned().unwrap_or_default()) }
}
#[derive(Default)]
struct FakeOtlp { content_type: String }
impl OtlpClient for FakeOtlp { fn post_json(&mut self, _endpoint: &str, _payload: &str, content_type: &str) -> agentledger::Result<()> { self.content_type = content_type.to_string(); Ok(()) } }
fn run_official_adapters_smoke() -> Result<(), Box<dyn Error>> {
    let mut pg = PostgresAdapter::new(FakeSql::default(), "agentledger");
    if pg.migration_plan()?[0].dialect != "postgres" { return Err("postgres adapter plan failed".into()); }
    pg.apply_migrations()?;
    if pg.client.count < 2 { return Err("postgres adapter apply failed".into()); }
    let mut mysql = MySQLAdapter::new(FakeSql::default(), "agentledger");
    if mysql.migration_plan()?[0].dialect != "mysql" { return Err("mysql adapter plan failed".into()); }
    mysql.apply_migrations()?;
    if mysql.client.count < 2 { return Err("mysql adapter apply failed".into()); }
    let mut s3 = S3BlobStoreAdapter::new(FakeObjects::default(), "agentledger-test", "agentledger/blobs");
    let value = Value::Object(state(&[("answer", "ok".into())]));
    let (_digest, reference) = s3.put_json(&value)?;
    if !reference.starts_with("s3://agentledger-test/agentledger/blobs/sha256/") || s3.client.content_type != "application/json" { return Err("s3 put failed".into()); }
    if s3.get_json(&reference)? != value { return Err("s3 roundtrip failed".into()); }
    let mut otlp = OtlpTransport { endpoint: "http://collector".to_string(), client: FakeOtlp::default() };
    otlp.export("{}")?;
    if otlp.client.content_type != "application/json" { return Err("otlp transport failed".into()); }
    let manifest = (DockerSandboxAdapter { image: String::new() }).manifest(&state(&[("network", "deny".into())]), vec!["echo".to_string(), "ok".to_string()]);
    if manifest.get("network") != Some(&Value::String("none".to_string())) || manifest.get("read_only_root") != Some(&Value::Bool(true)) { return Err("docker manifest failed".into()); }
    let closed = DockerSandboxExecutor::new("fake-image", false).with_binary("/bin/echo").run_tool(
        state(&[("_sandbox_command", Value::Array(vec!["echo".into(), "ok".into()]))]),
        &agentledger::SandboxPolicy {
            tool_name: "cmd.echo".to_string(),
            run_id: "run".to_string(),
            step_id: "step".to_string(),
            executor: "docker".to_string(),
            network: "deny".to_string(),
            filesystem: "read-only".to_string(),
            timeout_seconds: 1,
            extra: State::new(),
        },
    );
    if closed.ok || closed.metadata.get("error_type") != Some(&Value::String("SandboxAdapterNotInstalled".to_string())) { return Err("docker executor should fail closed without explicit execution".into()); }
    let executed = DockerSandboxExecutor::new("fake-image", true).with_binary("/bin/echo").run_tool(
        state(&[("_sandbox_command", Value::Array(vec!["echo".into(), "ok".into()]))]),
        &agentledger::SandboxPolicy {
            tool_name: "cmd.echo".to_string(),
            run_id: "run".to_string(),
            step_id: "step".to_string(),
            executor: "docker".to_string(),
            network: "deny".to_string(),
            filesystem: "read-only".to_string(),
            timeout_seconds: 1,
            extra: State::new(),
        },
    );
    let stdout = match executed.output { Value::Object(output) => match output.get("stdout") { Some(Value::String(value)) => value.clone(), _ => String::new() }, _ => String::new() };
    if !executed.ok || !stdout.contains("fake-image") { return Err("docker executor injected binary failed".into()); }
    Ok(())
}
