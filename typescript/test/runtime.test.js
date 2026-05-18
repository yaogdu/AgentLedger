import assert from 'node:assert/strict';
import { mkdtemp, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import test from 'node:test';
import { JSONStore, LocalBlobStore, LocalWorker, RetryableAgentError, Runtime, WorkerService, exportEvidence, replay, costAttribution, failureAttribution } from '../src/index.js';

test('runtime creates durable run, evidence, and replay summary', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'agentledger-ts-'));
  const path = join(dir, 'state.json');
  const rt = await Runtime.local(path);
  rt.registerTool({ name: 'docs.echo', func: async (args) => ({ echo: args.text }) });
  const { runId } = await rt.createRun({ input: 'hello' });
  const ok = await rt.runOnce({
    runId,
    workerId: 'worker-a',
    agentRole: 'Researcher',
    agent: async (ctx, state) => {
      const result = await ctx.callTool('docs.echo', { text: state.input });
      await ctx.writeState('tool_result', result);
    },
  });
  assert.equal(ok, true);
  await readFile(path, 'utf8');
  const reopened = await JSONStore.open(path);
  assert.deepEqual(reopened.finalState(runId).tool_result, { echo: 'hello' });
  const bundle = exportEvidence(reopened, runId);
  assert.equal(bundle.schema_version, 'agentledger.evidence.v1');
  assert.ok(bundle.bundle_hash);
  const summary = replay(reopened, runId);
  assert.equal(summary.replay_safe, true);
  assert.equal(summary.event_count, bundle.events.length);
  assert.equal(summary.tool_call_count, 2);
});

test('local blob store roundtrips JSON-compatible values', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'agentledger-ts-blobs-'));
  const blobs = await LocalBlobStore.open(dir);
  const value = { hello: 'world', nested: { n: 1 } };
  const first = await blobs.putJSON(value);
  const second = await blobs.putJSON(value);
  assert.ok(first.digest.startsWith('sha256:'));
  assert.ok(first.ref.startsWith('blob://sha256/'));
  assert.deepEqual(first, second);
  assert.deepEqual(await blobs.getJSON(first.ref), value);
  await assert.rejects(() => blobs.getJSON('unsupported://blob'), /unsupported blob ref/);
});

test('tool schema validation rejects invalid input before execution', async () => {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({
    name: 'docs.echo',
    inputSchema: { type: 'object', required: ['text'], additionalProperties: false, properties: { text: { type: 'string', minLength: 1 } } },
    outputSchema: { type: 'object', required: ['echo'], additionalProperties: false, properties: { echo: { type: 'string' } } },
    func: async (args) => { calls += 1; return { echo: args.text }; },
  });
  const { runId } = await rt.createRun({});
  await assert.rejects(() => rt.runOnce({ runId, agentRole: 'SchemaAgent', agent: (ctx) => ctx.callTool('docs.echo', {}) }), /required/);
  assert.equal(calls, 0);
  assert.equal(rt.store.events(runId).some((event) => event.type === 'tool_call_failed' && event.payload.phase === 'input_validation'), true);
});

test('tool ledger idempotency reuses side effect response across retry', async () => {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({
    name: 'github.create_pr',
    sideEffect: 'external',
    idempotencyRequired: true,
    func: async (args) => {
      calls += 1;
      return { external_id: 'pr-123', title: args.title };
    },
  });
  const { runId } = await rt.createRun({ title: 'runtime parity' });
  const agent = async (ctx, state) => {
    const result = await ctx.callTool('github.create_pr', { title: state.title });
    if (ctx.attempt === 1) throw new RetryableAgentError('crash after side effect');
    await ctx.writeState('pr', result);
  };
  assert.equal(await rt.runOnce({ runId, agent }), false);
  assert.equal(await rt.runOnce({ runId, workerId: 'worker-b', agent }), true);
  assert.equal(calls, 1);
  assert.equal(rt.store.ledger(runId).length, 1);
  assert.equal(rt.store.ledger(runId)[0].status, 'SUCCEEDED');
});

test('policy denies unapproved high-risk tool before execution', async () => {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'repo.write', riskLevel: 'high', func: async () => { calls += 1; return { ok: true }; } });
  const { runId } = await rt.createRun({});
  await assert.rejects(() => rt.runOnce({ runId, agentRole: 'Reviewer', agent: (ctx) => ctx.callTool('repo.write', { path: 'README.md' }) }), /high-risk tool denied/);
  assert.equal(calls, 0);
  assert.equal(rt.store.events(runId).some((event) => event.type === 'tool_permission_decided' && event.payload.allowed === false), true);
  assert.equal(rt.store.steps(runId)[0].status, 'failed');
});

test('approval pauses and resumes step', async () => {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({
    name: 'github.create_pr',
    riskLevel: 'high',
    approvalRequired: true,
    sideEffect: 'external',
    idempotencyRequired: true,
    func: async () => { calls += 1; return { external_id: 'pr-42' }; },
  });
  const { runId } = await rt.createRun({});
  const agent = async (ctx) => {
    const result = await ctx.callTool('github.create_pr', { title: 'safe' });
    await ctx.writeState('pr', result);
  };
  assert.equal(await rt.runOnce({ runId, workerId: 'worker-a', agentRole: 'Coder', agent }), false);
  assert.equal(calls, 0);
  const approvals = rt.store.approvalRequests(runId);
  assert.equal(approvals.length, 1);
  assert.equal(approvals[0].status, 'PENDING');
  assert.equal(rt.store.steps(runId)[0].status, 'waiting_human');
  await rt.store.approveRequest(approvals[0].approval_id, { approver: 'alice', reason: 'reviewed' });
  assert.equal(await rt.runOnce({ runId, workerId: 'worker-b', agentRole: 'Coder', agent }), true);
  assert.equal(calls, 1);

  const { runId: deniedRun } = await rt.createRun({});
  assert.equal(await rt.runOnce({ runId: deniedRun, workerId: 'worker-c', agentRole: 'Coder', agent }), false);
  await rt.store.denyRequest(rt.store.approvalRequests(deniedRun)[0].approval_id, { approver: 'bob', reason: 'not allowed' });
  assert.equal(rt.store.steps(deniedRun)[0].status, 'failed');
});

test('sandbox-required tool fails closed without executor', async () => {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'shell.exec', sandboxRequired: true, func: async () => { calls += 1; return { ok: true }; } });
  const { runId } = await rt.createRun({});
  await assert.rejects(() => rt.runOnce({ runId, agentRole: 'Executor', agent: (ctx) => ctx.callTool('shell.exec', { argv: ['echo', 'hi'] }) }), /sandbox executor/);
  assert.equal(calls, 0);
  assert.equal(rt.store.events(runId).some((event) => event.type === 'sandbox_started'), true);
  assert.equal(rt.store.events(runId).some((event) => event.type === 'tool_call_failed'), true);
});

test('cost budget and failure attribution are recorded', async () => {
  const rt = new Runtime(JSONStore.memory());
  rt.setBudget({ maxToolCalls: 1 });
  let calls = 0;
  rt.registerTool({ name: 'docs.echo', func: async (args) => { calls += 1; return { echo: args.text }; } });
  const { runId } = await rt.createRun({});
  await assert.rejects(() => rt.runOnce({
    runId,
    agentRole: 'Researcher',
    agent: async (ctx) => {
      await ctx.recordModelCall({ model: 'gpt-test', inputTokens: 10, outputTokens: 5, totalUsd: 0.01 });
      await ctx.callTool('docs.echo', { text: 'first' });
      await ctx.callTool('docs.echo', { text: 'second' });
    },
  }), /tool call budget exceeded/);
  assert.equal(calls, 1);
  const summary = rt.store.costSummary(runId);
  assert.equal(summary.tool_calls, 1);
  assert.equal(summary.model_tokens, 15);
  assert.equal(summary.total_usd, 0.01);
  const cost = costAttribution(rt.store, runId);
  assert.equal(cost.by_agent.Researcher.tool_calls, 1);
  assert.equal(cost.by_agent.Researcher.model_tokens, 15);
  const failure = failureAttribution(rt.store, runId);
  assert.equal(failure.summary.failed_step_count, 1);
  assert.equal(failure.failure_events.some((event) => event.type === 'budget_check_failed'), true);
  assert.equal(failure.failure_events.some((event) => event.type === 'failure_classified'), true);
});

test('media and stream artifacts are indexed in evidence and replay', async () => {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({});
  const ok = await rt.runOnce({
    runId,
    workerId: 'worker-media',
    agentRole: 'MediaAgent',
    agent: async (ctx) => {
      const frame = await ctx.createMediaArtifact('frame-0001', 'frame', {
        uri: 's3://media/demo/frame-0001.jpg',
        mediaMetadata: { mime_type: 'image/jpeg', frame_index: 1 },
        lineage: { source_blob_refs: ['s3://media/demo/input.mp4'], tool_call_ids: ['video.extract_frames'] },
      });
      const checkpoint = await ctx.createStreamCheckpoint('camera-checkpoint', {
        streamId: 'camera-1',
        consumerId: 'vision-agent',
        offset: 7,
        watermark: 1.5,
        chunk: { streamId: 'camera-1', chunkId: 'chunk-7', offset: 7, contentRef: 'blob://sha256/chunk-7.json', sequence: 7 },
        backpressure: { recommended_pause_ms: 100 },
      });
      await ctx.writeState('artifacts', { frame, checkpoint });
    },
  });
  assert.equal(ok, true);
  const bundle = exportEvidence(rt.store, runId);
  assert.equal(bundle.summary.artifact_count, 2);
  assert.equal(bundle.summary.media_artifact_count, 1);
  assert.equal(bundle.summary.stream_checkpoint_count, 1);
  assert.equal(bundle.media_artifacts[0].kind, 'frame');
  assert.equal(bundle.stream_checkpoints[0].stream_id, 'camera-1');
  const summary = replay(rt.store, runId);
  assert.equal(summary.artifact_count, 2);
  assert.equal(summary.media_artifact_count, 1);
  assert.equal(summary.stream_checkpoint_count, 1);
});

test('lease recovery fences previous owner', async () => {
  const store = JSONStore.memory();
  const { runId, stepId } = await store.createRun({});
  const claim = await store.claimStep({ workerId: 'stale-worker', runId, leaseSeconds: 0 });
  assert.equal(await store.recoverExpiredLeases(), 1);
  await assert.rejects(() => store.commitStatePatch({ runId, stepId, leaseToken: claim.lease_token, baseVersion: 0, patch: { late: true } }), /invalid or stale lease token/);
  const next = await store.claimStep({ workerId: 'new-worker', runId, leaseSeconds: 60 });
  assert.equal(next.step_id, stepId);
});

test('cancellation fences worker', async () => {
  const store = JSONStore.memory();
  const { runId, stepId } = await store.createRun({});
  const claim = await store.claimStep({ workerId: 'worker', runId, leaseSeconds: 60 });
  assert.equal(await store.cancelRun(runId, 'operator requested'), 1);
  await assert.rejects(() => store.commitStatePatch({ runId, stepId, leaseToken: claim.lease_token, baseVersion: 0, patch: { late: true } }), /invalid or stale lease token/);
});

test('contract fixture is readable and includes TypeScript target', async () => {
  const contract = JSON.parse(await readFile(new URL('../../contracts/agentledger.runtime.v1.json', import.meta.url), 'utf8'));
  assert.equal(contract.contract_version, '1.0');
  assert.ok(contract.language_targets.some((target) => target.language === 'typescript'));
});

test('shared runtime baseline fixture covers preview scenarios', async () => {
  const fixture = JSON.parse(await readFile(new URL('../../contracts/conformance/runtime_baseline.v1.json', import.meta.url), 'utf8'));
  assert.equal(fixture.schema_version, 'agentledger.conformance.runtime_baseline.v1');
  assert.equal(fixture.contract_version, '1.0');
  const names = new Set(fixture.required_scenarios.map((scenario) => scenario.name));
  for (const name of ['durable_run_evidence_replay', 'tool_ledger_idempotent_retry', 'lease_recovery_fences_stale_worker', 'cancellation_fences_worker']) assert.equal(names.has(name), true, `missing shared fixture scenario ${name}`);
  for (const scenario of fixture.required_scenarios) assert.ok(scenario.required_assertions.length > 0, `scenario ${scenario.name} should define assertions`);
});

test('shared parity fixtures cover implemented scenarios', async () => {
  const fixtures = {
    'policy_approval_sandbox.v1.json': ['agentledger.conformance.policy_approval_sandbox.v1', 'policy_denies_unapproved_high_risk_tool', 'approval_pauses_and_resumes_step', 'sandbox_required_tool_fails_closed'],
    'cost_failure_attribution.v1.json': ['agentledger.conformance.cost_failure_attribution.v1', 'tool_and_model_cost_attributed_to_run_step_role', 'budget_exhaustion_blocks_execution', 'failure_attribution_classifies_agent_tool_model_runtime'],
    'local_persistence.v1.json': ['agentledger.conformance.local_persistence.v1', 'local_store_round_trips_completed_run', 'local_store_preserves_evidence_replay_chain', 'local_store_uses_atomic_snapshot_write'],
    'local_blob_store.v1.json': ['agentledger.conformance.local_blob_store.v1', 'blob_roundtrip_json_value', 'blob_content_address_is_stable', 'blob_bad_ref_is_rejected'],
    'tool_schema_validation.v1.json': ['agentledger.conformance.tool_schema_validation.v1', 'invalid_tool_input_rejected_before_execution', 'valid_tool_input_and_output_pass', 'invalid_tool_output_rejected'],
    'worker_service.v1.json': ['agentledger.conformance.worker_service.v1', 'local_worker_runs_until_terminal', 'worker_service_stops_after_idle_poll', 'worker_loop_recovers_expired_leases'],
    'media_stream_artifacts.v1.json': ['agentledger.conformance.media_stream_artifacts.v1', 'media_artifact_ref_is_indexed_in_evidence', 'stream_checkpoint_ref_is_indexed_in_evidence'],
    'evidence_consumers.v1.json': ['agentledger.conformance.evidence_consumers.v1', 'trace_spans_from_evidence', 'evidence_diff_detects_state_and_event_changes', 'divergence_report_lists_changed_dimensions', 'static_debug_summary_is_exportable'],
    'static_debug_html.v1.json': ['agentledger.conformance.static_debug_html.v1', 'static_debug_html_contains_run_events_and_state'],
    'ops_readiness.v1.json': ['agentledger.conformance.ops_readiness.v1', 'retention_plan_is_non_destructive_and_counts_evidence', 'backup_readiness_reports_required_checks'],
    'storage_schema.v1.json': ['agentledger.conformance.storage_schema.v1', 'latest_schema_version_and_ddl_are_available'],
    'mcp_adapters.v1.json': ['agentledger.conformance.mcp_adapters.v1', 'in_memory_mcp_tool_server_lists_and_calls_tools', 'mcp_tool_descriptor_maps_to_tool_spec', 'in_memory_mcp_context_server_reads_resources'],
    'framework_adapters.v1.json': ['agentledger.conformance.framework_adapters.v1', 'function_adapter_maps_run_spec_and_invokes_agent', 'method_framework_adapter_uses_first_available_method_and_writes_output'],
    'otlp_trace_export.v1.json': ['agentledger.conformance.otlp_trace_export.v1', 'otlp_json_contains_resource_scope_and_spans'],
    'simple_api.v1.json': ['agentledger.conformance.simple_api.v1', 'simple_run_returns_output_and_state'],
    'boundary_lint.v1.json': ['agentledger.conformance.boundary_lint.v1', 'direct_shell_and_http_calls_are_reported', 'ignored_lines_are_not_reported'],
    'scheduler.v1.json': ['agentledger.conformance.scheduler.v1', 'scheduler_status_reports_run_steps_and_cost', 'scheduler_recover_and_cancel_delegate_to_store'],
    'adversarial_review.v1.json': ['agentledger.conformance.adversarial_review.v1', 'clean_evidence_passes_blocker_review', 'pending_high_risk_approval_blocks_review', 'max_total_usd_limit_blocks_review'],
    'evidence_regression.v1.json': ['agentledger.conformance.evidence_regression.v1', 'evidence_health_checks_pass_for_clean_bundle', 'regression_detects_final_state_and_event_type_changes', 'regression_cost_delta_limit_blocks'],
    'failure_injection.v1.json': ['agentledger.conformance.failure_injection.v1', 'retry_exhaustion_marks_run_failed', 'lease_fencing_rejects_stale_commit', 'cancellation_fencing_rejects_late_commit', 'side_effect_idempotency_executes_once_across_retry'],
    'shadow.v1.json': ['agentledger.conformance.shadow.v1', 'shadow_state_diff_reports_changed_keys', 'shadow_report_carries_source_shadow_and_ok'],
    'repro.v1.json': ['agentledger.conformance.repro.v1', 'builtin_golden_names_are_available', 'minimal_success_golden_is_valid_evidence', 'golden_regression_detects_changed_final_state'],
    'time_travel.v1.json': ['agentledger.conformance.time_travel.v1', 'timeline_reconstructs_state_at_selected_seq', 'timeline_marks_state_changed_frames', 'time_travel_report_exports_static_html'],
  };
  for (const [file, required] of Object.entries(fixtures)) {
    const body = await readFile(new URL(`../../contracts/conformance/${file}`, import.meta.url), 'utf8');
    for (const token of required) assert.ok(body.includes(token), `fixture ${file} missing ${token}`);
  }
});
