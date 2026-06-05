#!/usr/bin/env node
import { existsSync, readFileSync, realpathSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { FunctionAdapter, InMemoryMCPContextServer, InMemoryMCPToolServer, JSONStore, LocalBlobStore, LocalWorker, MCPContextAdapter, MCPToolAdapter, MethodFrameworkAdapter, RetryableAgentError, Runtime, RuntimeScheduler, WorkerService, checkBackupReadiness, costAttribution, debugHTML, ddlFor, debugSummary, diffEvidence, divergenceReport, exportEvidence, failureAttribution, latestSchemaVersion, migrationsFor, otlpTraceJSON, planRetention, replay, simpleRun, traceJSONL, traceSpans, scanBoundarySource, adversarialReview, evaluateEvidence, evaluateEvidenceRegression, runFailureInjectionSuite, diffStates, shadowReport, builtinGoldenNames, builtinGoldenEvidence, goldenRegression, timeTravel, timeTravelHTML, optionalAdapterCapabilities, PostgresAdapter, MySQLAdapter, S3BlobStoreAdapter, OTLPTransport, DockerSandboxAdapter, DockerSandboxExecutor } from './index.js';

const FIXTURE_CHECKS = {
  'runtime_baseline.v1.json': [
    'agentledger.conformance.runtime_baseline.v1',
    'durable_run_evidence_replay',
    'tool_ledger_idempotent_retry',
    'lease_recovery_fences_stale_worker',
    'cancellation_fences_worker',
  ],
  'local_persistence.v1.json': [
    'agentledger.conformance.local_persistence.v1',
    'local_store_round_trips_completed_run',
    'local_store_preserves_evidence_replay_chain',
    'local_store_uses_atomic_snapshot_write',
  ],
  'local_blob_store.v1.json': [
    'agentledger.conformance.local_blob_store.v1',
    'blob_roundtrip_json_value',
    'blob_content_address_is_stable',
    'blob_bad_ref_is_rejected',
  ],
  'tool_schema_validation.v1.json': [
    'agentledger.conformance.tool_schema_validation.v1',
    'invalid_tool_input_rejected_before_execution',
    'valid_tool_input_and_output_pass',
    'invalid_tool_output_rejected',
  ],
  'worker_service.v1.json': [
    'agentledger.conformance.worker_service.v1',
    'local_worker_runs_until_terminal',
    'worker_service_stops_after_idle_poll',
    'worker_loop_recovers_expired_leases',
  ],
  'policy_approval_sandbox.v1.json': [
    'agentledger.conformance.policy_approval_sandbox.v1',
    'policy_denies_unapproved_high_risk_tool',
    'approval_pauses_and_resumes_step',
    'sandbox_required_tool_fails_closed',
  ],
  'cost_failure_attribution.v1.json': [
    'agentledger.conformance.cost_failure_attribution.v1',
    'tool_and_model_cost_attributed_to_run_step_role',
    'budget_exhaustion_blocks_execution',
    'failure_attribution_classifies_agent_tool_model_runtime',
  ],
  'media_stream_artifacts.v1.json': [
    'agentledger.conformance.media_stream_artifacts.v1',
    'media_artifact_ref_is_indexed_in_evidence',
    'stream_checkpoint_ref_is_indexed_in_evidence',
  ],
  'evidence_consumers.v1.json': [
    'agentledger.conformance.evidence_consumers.v1',
    'trace_spans_from_evidence',
    'evidence_diff_detects_state_and_event_changes',
    'divergence_report_lists_changed_dimensions',
    'static_debug_summary_is_exportable',
  ],
  'static_debug_html.v1.json': [
    'agentledger.conformance.static_debug_html.v1',
    'static_debug_html_contains_run_events_and_state',
  ],
  'ops_readiness.v1.json': [
    'agentledger.conformance.ops_readiness.v1',
    'retention_plan_is_non_destructive_and_counts_evidence',
    'backup_readiness_reports_required_checks',
  ],
  'storage_schema.v1.json': [
    'agentledger.conformance.storage_schema.v1',
    'latest_schema_version_and_ddl_are_available',
  ],
  'mcp_adapters.v1.json': [
    'agentledger.conformance.mcp_adapters.v1',
    'in_memory_mcp_tool_server_lists_and_calls_tools',
    'mcp_tool_descriptor_maps_to_tool_spec',
    'in_memory_mcp_context_server_reads_resources',
  ],
  'framework_adapters.v1.json': [
    'agentledger.conformance.framework_adapters.v1',
    'function_adapter_maps_run_spec_and_invokes_agent',
    'method_framework_adapter_uses_first_available_method_and_writes_output',
  ],
  'otlp_trace_export.v1.json': [
    'agentledger.conformance.otlp_trace_export.v1',
    'otlp_json_contains_resource_scope_and_spans',
  ],
  'simple_api.v1.json': [
    'agentledger.conformance.simple_api.v1',
    'simple_run_returns_output_and_state',
  ],
  'boundary_lint.v1.json': [
    'agentledger.conformance.boundary_lint.v1',
    'direct_shell_and_http_calls_are_reported',
    'ignored_lines_are_not_reported',
  ],
  'scheduler.v1.json': [
    'agentledger.conformance.scheduler.v1',
    'scheduler_status_reports_run_steps_and_cost',
    'scheduler_recover_and_cancel_delegate_to_store',
  ],
  'adversarial_review.v1.json': [
    'agentledger.conformance.adversarial_review.v1',
    'clean_evidence_passes_blocker_review',
    'pending_high_risk_approval_blocks_review',
    'max_total_usd_limit_blocks_review',
  ],
  'evidence_regression.v1.json': [
    'agentledger.conformance.evidence_regression.v1',
    'evidence_health_checks_pass_for_clean_bundle',
    'regression_detects_final_state_and_event_type_changes',
    'regression_cost_delta_limit_blocks',
  ],
  'failure_injection.v1.json': [
    'agentledger.conformance.failure_injection.v1',
    'retry_exhaustion_marks_run_failed',
    'lease_fencing_rejects_stale_commit',
    'cancellation_fencing_rejects_late_commit',
    'side_effect_idempotency_executes_once_across_retry',
  ],
  'shadow.v1.json': [
    'agentledger.conformance.shadow.v1',
    'shadow_state_diff_reports_changed_keys',
    'shadow_report_carries_source_shadow_and_ok',
  ],
  'repro.v1.json': [
    'agentledger.conformance.repro.v1',
    'builtin_golden_names_are_available',
    'minimal_success_golden_is_valid_evidence',
    'golden_regression_detects_changed_final_state',
  ],
  'time_travel.v1.json': [
    'agentledger.conformance.time_travel.v1',
    'timeline_reconstructs_state_at_selected_seq',
    'timeline_marks_state_changed_frames',
    'time_travel_report_exports_static_html',
  ],
  'optional_adapters.v1.json': [
    'agentledger.conformance.optional_adapters.v1',
    'optional_backend_capabilities_are_discoverable',
    'postgres',
    'mysql',
    'langgraph',
    'langfuse',
    'shadow-runner',
  ],
  'official_adapters.v1.json': [
    'agentledger.conformance.official_adapters.v1',
    'postgres_adapter_plans_and_applies_migrations_with_injected_client',
    'mysql_adapter_plans_and_applies_migrations_with_injected_client',
    's3_blob_adapter_round_trips_json_with_injected_client',
    'otlp_transport_posts_json_with_injected_client',
    'docker_sandbox_adapter_builds_manifest_without_daemon',
    'docker_sandbox_executor_runs_command_style_tool_with_injected_binary',
  ],
};

function findRepoRoot() {
  if (process.env.AGENTLEDGER_REPO_ROOT) return process.env.AGENTLEDGER_REPO_ROOT;
  let current = process.cwd();
  while (true) {
    if (existsSync(join(current, 'contracts', 'agentledger.runtime.v1.json'))) return current;
    const parent = dirname(current);
    if (parent === current) throw new Error('could not find AgentLedger repository root');
    current = parent;
  }
}

function contractPath() {
  return join(findRepoRoot(), 'contracts', 'agentledger.runtime.v1.json');
}

export function validateContract() {
  const body = readFileSync(contractPath(), 'utf8');
  for (const token of ['"contract_version": "1.0"', '"language": "typescript"', '"status": "preview"', 'media_stream_artifacts.v1.json']) {
    if (!body.includes(token)) throw new Error(`contract missing ${token}`);
  }
}

export function validateFixtures() {
  validateContract();
  const root = findRepoRoot();
  const checks = [];
  for (const [file, tokens] of Object.entries(FIXTURE_CHECKS)) {
    const body = readFileSync(join(root, 'contracts', 'conformance', file), 'utf8');
    for (const token of tokens) {
      if (!body.includes(token)) throw new Error(`fixture ${file} missing ${token}`);
    }
    checks.push(file);
  }
  return checks;
}

function usage() {
  return `AgentLedger TypeScript Runtime 1.2.4\n\nUsage:\n  agentledger-ts doctor\n  agentledger-ts version\n  agentledger-ts quickstart\n  agentledger-ts conformance\n  agentledger-ts contract validate\n  agentledger-ts contract export\n\nProject: https://github.com/yaogdu/AgentLedger`;
}

export async function runRuntimeSmoke() {
  const rt = new Runtime(JSONStore.memory());
  rt.registerTool({ name: 'docs.echo', version: 'v1', sideEffect: 'none', func: async (args) => ({ echo: args.text }) });
  const { runId } = await rt.createRun({ input: 'hello' });
  const ok = await rt.runOnce({
    runId,
    workerId: 'conformance-ts',
    agentRole: 'ConformanceAgent',
    agent: async (ctx, state) => {
      const result = await ctx.callTool('docs.echo', { text: state.input });
      await ctx.writeState('tool_result', result);
    },
  });
  if (!ok) throw new Error('runtime smoke did not complete');
  if (!rt.store.finalState(runId).tool_result) throw new Error('runtime smoke missing final state');
  const bundle = exportEvidence(rt.store, runId);
  const summary = replay(rt.store, runId);
  if (bundle.schema_version !== 'agentledger.evidence.v1' || !summary.replay_safe || summary.event_count !== bundle.events.length) throw new Error('runtime smoke evidence/replay mismatch');
}


export async function runSemanticSmokes() {
  await runRuntimeSmoke();
  await runLocalPersistenceSmoke();
  await runLocalBlobStoreSmoke();
  await runToolSchemaValidationSmoke();
  await runWorkerServiceSmoke();
  await runToolLedgerSmoke();
  await runPolicyApprovalSandboxSmoke();
  await runCostFailureSmoke();
  await runMediaStreamSmoke();
  await runEvidenceConsumersSmoke();
  await runStaticDebugHTMLSmoke();
  await runOpsReadinessSmoke();
  await runStorageSchemaSmoke();
  await runMCPAdaptersSmoke();
  await runFrameworkAdaptersSmoke();
  await runOTLPTraceExportSmoke();
  await runSimpleAPISmoke();
  await runBoundaryLintSmoke();
  await runSchedulerSmoke();
  await runAdversarialReviewSmoke();
  await runEvidenceRegressionSmoke();
  if (!(await runFailureInjectionSuite()).passed) throw new Error('failure injection smoke failed');
  runShadowSmoke();
  await runReproGoldenSmoke();
  await runTimeTravelTimelineSmoke();
  runOptionalAdaptersSmoke();
  await runOfficialAdaptersSmoke();
  return ['runtime_smoke_evidence_replay', 'local_persistence_smoke', 'local_blob_store_smoke', 'tool_schema_validation_smoke', 'worker_service_smoke', 'tool_ledger_idempotent_retry', 'policy_approval_sandbox_smoke', 'cost_failure_attribution_smoke', 'media_stream_artifacts_smoke', 'evidence_consumers_smoke', 'static_debug_html_smoke', 'ops_readiness_smoke', 'storage_schema_smoke', 'mcp_adapters_smoke', 'framework_adapters_smoke', 'otlp_trace_export_smoke', 'simple_api_smoke', 'boundary_lint_smoke', 'scheduler_smoke', 'adversarial_review_smoke', 'evidence_regression_smoke', 'failure_injection_smoke', 'shadow_smoke', 'repro_golden_smoke', 'time_travel_timeline_smoke', 'optional_adapters_smoke', 'official_adapters_smoke'];
}





async function runStaticDebugHTMLSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'debug' });
  await rt.runOnce({ runId, workerId: 'worker-debug', agentRole: 'DebugAgent', agent: async (ctx) => ctx.writeState('answer', 'debug') });
  const html = debugHTML(exportEvidence(rt.store, runId));
  for (const token of ['<!doctype html>', 'AgentLedger Debug Report', 'Run', 'Events', 'Final State', 'run_created']) if (!html.includes(token)) throw new Error(`static debug html smoke missing ${token}`);
}


async function runOpsReadinessSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'ops' });
  await rt.runOnce({ runId, workerId: 'worker-ops', agentRole: 'OpsAgent', agent: async (ctx) => {
    await ctx.createMediaArtifact('frame-ops', 'frame', { uri: 'file://frame.png' });
    await ctx.writeState('answer', 'ops');
  } });
  const bundle = exportEvidence(rt.store, runId);
  const plan = planRetention(bundle);
  if (plan.destructive || plan.event_count !== bundle.events.length || plan.media_artifact_count !== 1 || !plan.actions.includes('export evidence bundle before destructive retention') || !plan.actions.includes('snapshot final state and manifest')) throw new Error('ops retention plan smoke mismatch');
  const report = checkBackupReadiness(bundle);
  for (const name of ['run_metadata_exists', 'payload_refs_resolvable', 'evidence_exportable', 'media_stream_evidence_shape']) if (!report.checks.some((check) => check.name === name && check.passed)) throw new Error(`ops backup readiness missing ${name}`);
}


async function runStorageSchemaSmoke() {
  for (const dialect of ['sqlite', 'postgres']) {
    if (latestSchemaVersion(dialect) !== '0001') throw new Error(`storage schema version mismatch for ${dialect}`);
    const migrations = migrationsFor(dialect);
    if (migrations.length !== 1 || migrations[0].name !== 'initial_runtime_metadata' || !migrations[0].checksum.startsWith('sha256:')) throw new Error(`storage schema migrations mismatch for ${dialect}`);
    const ddl = ddlFor(dialect);
    for (const token of ['schema_migrations', 'CREATE TABLE IF NOT EXISTS runs', 'CREATE TABLE IF NOT EXISTS events', 'CREATE TABLE IF NOT EXISTS tool_ledger']) if (!ddl.includes(token)) throw new Error(`storage schema ddl for ${dialect} missing ${token}`);
  }
}


async function runMCPAdaptersSmoke() {
  const server = new InMemoryMCPToolServer();
  server.addTool({ name: 'docs.echo', annotations: { side_effect: 'none' } }, (name, args) => ({ name, echo: args.text }));
  server.addTool({ name: 'web.search' }, () => ({ ok: true }));
  const tools = server.listTools();
  if (tools.length !== 2 || tools[0].name !== 'docs.echo') throw new Error('mcp tool server list mismatch');
  let missing = false;
  try { server.callTool('missing', {}); } catch { missing = true; }
  if (!missing) throw new Error('mcp missing tool should fail');
  const spec = new MCPToolAdapter((name, args) => server.callTool(name, args)).toolSpecFromDescriptor({ name: 'github.create_pr', annotations: { side_effect: 'external', risk_level: 'high' } });
  if (spec.name !== 'github.create_pr' || spec.sideEffect !== 'external' || spec.riskLevel !== 'high' || !spec.idempotencyRequired) throw new Error('mcp tool adapter spec mismatch');
  const ctxServer = new InMemoryMCPContextServer();
  ctxServer.addResource({ uri: 'docs://readme', name: 'README', reader: (uri) => ({ uri }) });
  const resources = ctxServer.listResources();
  if (resources.length !== 1 || resources[0].mimeType !== 'application/json') throw new Error('mcp context list mismatch');
  const read = ctxServer.readResource('docs://readme');
  if (!read.content) throw new Error('mcp context read mismatch');
  const readSpec = new MCPContextAdapter((uri) => ctxServer.readResource(uri)).readToolSpec();
  if (readSpec.name !== 'mcp.context.read' || readSpec.sideEffect !== 'none') throw new Error('mcp context adapter spec mismatch');
}


async function runFrameworkAdaptersSmoke() {
  const functionAdapter = new FunctionAdapter(async (_ctx, state) => ({ kind: 'function', input: state.input }));
  if (functionAdapter.mapRunSpec().adapter !== 'function') throw new Error('function adapter run spec mismatch');
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'adapter' });
  await rt.runOnce({ runId, workerId: 'worker-adapter', agentRole: functionAdapter.role, agent: functionAdapter.asAgent() });
  if (!rt.store.finalState(runId).output) throw new Error('function adapter missing output');
  const methodAdapter = new MethodFrameworkAdapter({ invoke: (state) => ({ kind: 'method', input: state.input }) }, { methodCandidates: ['ainvoke', 'invoke'], outputKey: 'output' });
  if (methodAdapter.mapRunSpec().adapter !== 'method-framework') throw new Error('method adapter run spec mismatch');
  const rt2 = new Runtime(JSONStore.memory());
  const { runId: runId2 } = await rt2.createRun({ input: 'method' });
  await rt2.runOnce({ runId: runId2, workerId: 'worker-method', agentRole: methodAdapter.role, agent: methodAdapter.asAgent() });
  if (!rt2.store.finalState(runId2).output) throw new Error('method adapter missing output');
}

async function runOTLPTraceExportSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'otlp' });
  await rt.runOnce({ runId, workerId: 'worker-otlp', agentRole: 'TraceAgent', agent: async (ctx) => ctx.writeState('answer', 'otlp') });
  const bundle = exportEvidence(rt.store, runId);
  const otlp = otlpTraceJSON(bundle, { serviceName: 'agentledger-test', serviceVersion: '1.0.0' });
  const body = JSON.stringify(otlp);
  for (const token of ['resourceSpans', 'service.name', 'scopeSpans', 'traceId', 'spanId', 'agentledger.original_trace_id', 'agentledger.run_id']) if (!body.includes(token)) throw new Error(`otlp trace smoke missing ${token}`);
}

async function runSimpleAPISmoke() {
  const result = await simpleRun(async (_ctx, state) => ({ message: 'hello', input: state.input }), { initialState: { input: 'world' } });
  if (!result.ok || !result.output || !result.state.output || !result.session_id) throw new Error('simple api smoke result mismatch');
  if (!result.runtime.store.events(result.run_id).some((event) => event.type === 'agent_result_returned')) throw new Error('simple api smoke missing result event');
}

async function runEvidenceConsumersSmoke() {
  const rt = new Runtime(JSONStore.memory());
  rt.registerTool({ name: 'docs.echo', version: 'v1', sideEffect: 'none', func: async (args) => ({ echo: args.text }) });
  const { runId } = await rt.createRun({ input: 'left' });
  await rt.runOnce({ runId, agentRole: 'EvidenceAgent', agent: async (ctx, state) => {
    await ctx.callTool('docs.echo', { text: state.input });
    await ctx.createMediaArtifact('frame-0001', 'frame', { uri: 'file://frame.png', lineage: { source: 'camera' } });
    await ctx.createStreamCheckpoint('audio-checkpoint', { streamId: 'audio-stream', consumerId: 'asr', offset: 1, watermark: '00:00:01', chunk: { chunkId: 'c1', streamId: 'audio-stream', offset: 1 } });
    await ctx.writeState('answer', 'left');
  } });
  const left = exportEvidence(rt.store, runId);
  const right = JSON.parse(JSON.stringify(left));
  right.run = { ...right.run, run_id: `${left.run.run_id}-shadow` };
  right.bundle_hash = 'different';
  right.final_state = { ...right.final_state, answer: 'right' };
  right.events = [...right.events, { ...right.events[right.events.length - 1], seq: right.events.length + 1, type: 'shadow_event' }];
  right.media_artifacts = [];
  right.stream_checkpoints = [];
  const spans = traceSpans(left);
  if (!spans.some((span) => span.span_id === 'evt-000001' && span.attributes['agentledger.run_id'] === runId)) throw new Error('trace span event smoke mismatch');
  if (!spans.some((span) => span.name === 'media_artifact') || !spans.some((span) => span.name === 'stream_checkpoint') || !traceJSONL(left).includes('evt-000001')) throw new Error('trace span artifact smoke mismatch');
  const diff = diffEvidence(left, right);
  if (diff.same || diff.changes.final_state.changed_count < 1 || diff.changes.event_types.changed_count < 1 || diff.changes.media_artifacts.changed_count < 1 || diff.changes.stream_checkpoints.changed_count < 1) throw new Error('evidence diff smoke mismatch');
  const divergence = divergenceReport(left, right);
  for (const dimension of ['events', 'state', 'media_artifacts', 'stream_checkpoints']) if (!divergence.changed_dimensions.includes(dimension)) throw new Error(`divergence smoke missing ${dimension}`);
  const debug = debugSummary(left);
  if (debug.run_id !== runId || debug.event_count !== left.events.length || !debug.final_state.answer) throw new Error('debug summary smoke mismatch');
}

async function runLocalPersistenceSmoke() {
  const dir = await mkdtemp(join(tmpdir(), 'agentledger-ts-conformance-'));
  try {
    const path = join(dir, 'state.json');
    const rt = await Runtime.local(path);
    rt.registerTool({ name: 'docs.persist', version: 'v1', sideEffect: 'external', idempotencyRequired: true, func: async (args) => ({ external_id: 'persist-1', echo: args.text }) });
    const { runId } = await rt.createRun({ input: 'persist' });
    const ok = await rt.runOnce({
      runId,
      workerId: 'worker-persist',
      agentRole: 'PersistenceAgent',
      agent: async (ctx, state) => {
        const result = await ctx.callTool('docs.persist', { text: state.input });
        await ctx.writeState('tool_result', result);
      },
    });
    if (!ok) throw new Error('local persistence smoke did not complete');
    const reopened = await JSONStore.open(path);
    if (!reopened.finalState(runId).tool_result) throw new Error('local persistence smoke missing reopened final state');
    const bundle = exportEvidence(reopened, runId);
    const summary = replay(reopened, runId);
    if (!bundle.bundle_hash || !summary.replay_safe || summary.event_count !== bundle.events.length || reopened.ledger(runId).length !== 1 || summary.tool_call_count === 0) throw new Error('local persistence evidence/replay mismatch');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function runLocalBlobStoreSmoke() {
  const dir = await mkdtemp(join(tmpdir(), 'agentledger-ts-blobs-'));
  try {
    const blobs = await LocalBlobStore.open(dir);
    const value = { hello: 'world', nested: { n: 1 } };
    const first = await blobs.putJSON(value);
    const second = await blobs.putJSON(value);
    if (!first.digest.startsWith('sha256:') || !first.ref.startsWith('blob://sha256/')) throw new Error('local blob store invalid digest/ref');
    if (first.digest !== second.digest || first.ref !== second.ref) throw new Error('local blob store ref was not stable');
    assertDeepEqual(await blobs.getJSON(first.ref), value, 'local blob store roundtrip mismatch');
    let rejected = false;
    try {
      await blobs.getJSON('unsupported://blob');
    } catch {
      rejected = true;
    }
    if (!rejected) throw new Error('local blob store accepted unsupported ref');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function assertDeepEqual(left, right, message) {
  if (JSON.stringify(left) !== JSON.stringify(right)) throw new Error(message);
}

async function runToolSchemaValidationSmoke() {
  const inputSchema = { type: 'object', required: ['text'], additionalProperties: false, properties: { text: { type: 'string', minLength: 1 } } };
  const outputSchema = { type: 'object', required: ['echo'], additionalProperties: false, properties: { echo: { type: 'string' } } };
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'docs.echo', inputSchema, outputSchema, func: async (args) => { calls += 1; return { echo: args.text }; } });
  const { runId: badRun } = await rt.createRun({});
  let failed = false;
  try {
    await rt.runOnce({ runId: badRun, agentRole: 'SchemaAgent', agent: (ctx) => ctx.callTool('docs.echo', {}) });
  } catch (error) {
    failed = /required|expected/.test(error.message ?? String(error));
  }
  if (!failed || calls !== 0) throw new Error('tool schema input validation smoke mismatch');
  const { runId: goodRun } = await rt.createRun({ text: 'hello' });
  if (!(await rt.runOnce({ runId: goodRun, agentRole: 'SchemaAgent', agent: async (ctx, state) => {
    const result = await ctx.callTool('docs.echo', { text: state.text });
    await ctx.writeState('result', result);
  } })) || calls !== 1) throw new Error('tool schema valid call smoke mismatch');
  const badOutput = new Runtime(JSONStore.memory());
  badOutput.registerTool({ name: 'docs.bad', outputSchema, func: async () => ({ bad: true }) });
  const { runId: badOutRun } = await badOutput.createRun({});
  failed = false;
  try {
    await badOutput.runOnce({ runId: badOutRun, agentRole: 'SchemaAgent', agent: (ctx) => ctx.callTool('docs.bad', {}) });
  } catch (error) {
    failed = /required|not allowed|expected/.test(error.message ?? String(error));
  }
  if (!failed || badOutput.store.events(badOutRun).some((event) => event.type === 'tool_call_completed')) throw new Error('tool schema output validation smoke mismatch');
}

async function runWorkerServiceSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'worker' });
  const agent = async (ctx) => ctx.writeState('done', true);
  const worker = new LocalWorker(rt, { workerId: 'worker-service', agentRole: 'WorkerAgent' });
  const summary = await worker.runUntilIdle({ runId, maxIterations: 3, agent });
  if (summary.attempts !== 1 || summary.succeeded_attempts !== 1 || summary.final_status !== 'completed' || summary.stopped_reason !== 'terminal_status') throw new Error('worker terminal smoke mismatch');
  const service = new WorkerService(worker);
  const terminal = await service.serve({ runId, maxLoops: 3, maxIdlePolls: 1, agent });
  if (terminal.stopped_reason !== 'terminal_status') throw new Error('worker service terminal smoke mismatch');
  const empty = new WorkerService(worker);
  const idle = await empty.serve({ runId: null, maxLoops: 3, maxIdlePolls: 1, agent });
  if (idle.stopped_reason !== 'idle' || idle.idle_polls !== 1 || idle.attempts !== 0) throw new Error('worker service idle smoke mismatch');
}

async function runToolLedgerSmoke() {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'github.create_pr', sideEffect: 'external', idempotencyRequired: true, func: async (args) => { calls += 1; return { external_id: 'pr-123', title: args.title }; } });
  const { runId } = await rt.createRun({ title: 'runtime parity' });
  const agent = async (ctx, state) => {
    const result = await ctx.callTool('github.create_pr', { title: state.title });
    if (ctx.attempt === 1) throw new RetryableAgentError('crash after side effect');
    await ctx.writeState('pr', result);
  };
  if (await rt.runOnce({ runId, workerId: 'worker-a', agent })) throw new Error('tool ledger smoke first attempt should retry');
  if (!(await rt.runOnce({ runId, workerId: 'worker-b', agent }))) throw new Error('tool ledger smoke second attempt should complete');
  const ledger = rt.store.ledger(runId);
  if (calls !== 1 || ledger.length !== 1 || ledger[0].status !== 'SUCCEEDED') throw new Error('tool ledger smoke mismatch');
}

async function runPolicyApprovalSandboxSmoke() {
  await runPolicySmoke();
  await runApprovalSmoke();
  await runSandboxSmoke();
}

async function runPolicySmoke() {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'repo.write', riskLevel: 'high', func: async () => { calls += 1; return { ok: true }; } });
  const { runId } = await rt.createRun({});
  let failed = false;
  try {
    await rt.runOnce({ runId, agentRole: 'Reviewer', agent: (ctx) => ctx.callTool('repo.write', { path: 'README.md' }) });
  } catch (error) {
    failed = /high-risk tool denied/.test(error.message ?? String(error));
  }
  if (!failed || calls !== 0 || !rt.store.events(runId).some((event) => event.type === 'tool_permission_decided' && event.payload.allowed === false)) throw new Error('policy smoke mismatch');
}

async function runApprovalSmoke() {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'github.create_pr', riskLevel: 'high', approvalRequired: true, sideEffect: 'external', idempotencyRequired: true, func: async () => { calls += 1; return { external_id: 'pr-42' }; } });
  const { runId } = await rt.createRun({});
  const agent = async (ctx) => {
    const result = await ctx.callTool('github.create_pr', { title: 'safe' });
    await ctx.writeState('pr', result);
  };
  if (await rt.runOnce({ runId, workerId: 'worker-a', agentRole: 'Coder', agent })) throw new Error('approval smoke should pause');
  const approvals = rt.store.approvalRequests(runId);
  if (calls !== 0 || approvals.length !== 1 || approvals[0].status !== 'PENDING' || rt.store.steps(runId)[0].status !== 'waiting_human') throw new Error('approval smoke pending mismatch');
  await rt.store.approveRequest(approvals[0].approval_id, { approver: 'alice', reason: 'reviewed' });
  if (!(await rt.runOnce({ runId, workerId: 'worker-b', agentRole: 'Coder', agent })) || calls !== 1) throw new Error('approval smoke resume mismatch');
}

async function runSandboxSmoke() {
  const rt = new Runtime(JSONStore.memory());
  let calls = 0;
  rt.registerTool({ name: 'shell.exec', sandboxRequired: true, func: async () => { calls += 1; return { ok: true }; } });
  const { runId } = await rt.createRun({});
  let failed = false;
  try {
    await rt.runOnce({ runId, agentRole: 'Executor', agent: (ctx) => ctx.callTool('shell.exec', { argv: ['echo', 'hi'] }) });
  } catch (error) {
    failed = /sandbox executor/.test(error.message ?? String(error));
  }
  const events = rt.store.events(runId);
  if (!failed || calls !== 0 || !events.some((event) => event.type === 'sandbox_started') || !events.some((event) => event.type === 'tool_call_failed')) throw new Error('sandbox smoke mismatch');
}

async function runCostFailureSmoke() {
  const rt = new Runtime(JSONStore.memory());
  rt.setBudget({ maxToolCalls: 1 });
  let calls = 0;
  rt.registerTool({ name: 'docs.echo', func: async (args) => { calls += 1; return { echo: args.text }; } });
  const { runId } = await rt.createRun({});
  let failed = false;
  try {
    await rt.runOnce({ runId, agentRole: 'Researcher', agent: async (ctx) => {
      await ctx.recordModelCall({ model: 'gpt-test', inputTokens: 10, outputTokens: 5, totalUsd: 0.01 });
      await ctx.callTool('docs.echo', { text: 'first' });
      await ctx.callTool('docs.echo', { text: 'second' });
    } });
  } catch (error) {
    failed = /tool call budget exceeded/.test(error.message ?? String(error));
  }
  const summary = rt.store.costSummary(runId);
  const cost = costAttribution(rt.store, runId);
  const failure = failureAttribution(rt.store, runId);
  if (!failed || calls !== 1 || summary.tool_calls !== 1 || summary.model_tokens !== 15 || summary.total_usd !== 0.01 || cost.by_agent.Researcher.tool_calls !== 1 || failure.summary.failed_step_count !== 1 || !failure.failure_events.some((event) => event.type === 'budget_check_failed')) throw new Error('cost/failure smoke mismatch');
}

async function runMediaStreamSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({});
  const ok = await rt.runOnce({ runId, workerId: 'worker-media', agentRole: 'MediaAgent', agent: async (ctx) => {
    const frame = await ctx.createMediaArtifact('frame-0001', 'frame', { uri: 's3://media/demo/frame-0001.jpg', mediaMetadata: { mime_type: 'image/jpeg' } });
    const checkpoint = await ctx.createStreamCheckpoint('camera-checkpoint', { streamId: 'camera-1', consumerId: 'vision-agent', offset: 7, chunk: { streamId: 'camera-1', chunkId: 'chunk-7', offset: 7 } });
    await ctx.writeState('artifacts', { frame, checkpoint });
  } });
  const bundle = exportEvidence(rt.store, runId);
  const summary = replay(rt.store, runId);
  if (!ok || bundle.summary.artifact_count !== 2 || bundle.summary.media_artifact_count !== 1 || bundle.summary.stream_checkpoint_count !== 1 || summary.media_artifact_count !== 1 || summary.stream_checkpoint_count !== 1) throw new Error('media/stream smoke mismatch');
}

export async function main(args = process.argv.slice(2)) {
  if (args.length === 0 || (args.length === 1 && (args[0] === '--help' || args[0] === 'help'))) {
    console.log(usage());
    return 0;
  }
  if (args.length === 1 && args[0] === 'version') {
    console.log('agentledger-ts 1.2.4');
    return 0;
  }
  if (args.length === 1 && args[0] === 'doctor') {
    console.log(JSON.stringify({ language: 'typescript', version: '1.2.4', status: 'ok', runtime_core_parity: true }, null, 2));
    return 0;
  }
  if (args.length === 1 && args[0] === 'quickstart') {
    const result = await simpleRun(async (_ctx, state) => ({ message: 'hello from typescript', input: state.input }), { initialState: { input: 'world' } });
    console.log(JSON.stringify({ run_id: result.run_id, output: result.output, state: result.state }, null, 2));
    return 0;
  }
  if (args.length === 1 && args[0] === 'conformance') {
    const checks = validateFixtures();
    const semanticChecks = await runSemanticSmokes();
    console.log(JSON.stringify({ language: 'typescript', suite: 'agentledger_runtime_core', passed: true, checks: ['contract_validate', ...checks, ...semanticChecks] }, null, 2));
    return 0;
  }
  if (args.length === 2 && args[0] === 'contract' && args[1] === 'validate') {
    validateContract();
    return 0;
  }
  if (args.length === 2 && args[0] === 'contract' && args[1] === 'export') {
    process.stdout.write(readFileSync(contractPath(), 'utf8'));
    return 0;
  }
  console.error(`unknown command ${args.join(' ')}; run agentledger-ts --help`);
  return 1;
}

function isDirectCLIEntry() {
  if (!process.argv[1]) return false;
  try {
    return realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url));
  } catch {
    return import.meta.url === `file://${process.argv[1]}`;
  }
}

if (isDirectCLIEntry()) {
  try {
    process.exitCode = await main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}


async function runBoundaryLintSmoke() {
  const report = scanBoundarySource('agent.py', "import os\nimport requests\nos.system('echo unsafe')\nrequests.post('https://example.com')\n");
  if (report.passed || report.finding_count !== 2) throw new Error('boundary lint finding count mismatch');
  if (report.findings[0].rule_id !== 'direct-shell-os-system' || report.findings[1].rule_id !== 'direct-http-requests') throw new Error('boundary lint rule mismatch');
  const ignored = scanBoundarySource('agent.py', "import os\n# agentledger: ignore-next-line\nos.system('echo intentional')\n");
  if (!ignored.passed || ignored.finding_count !== 0) throw new Error('boundary lint ignore mismatch');
}


async function runSchedulerSmoke() {
  const store = JSONStore.memory();
  const rt = new Runtime(store);
  const { runId } = await rt.createRun({ input: 'scheduler' });
  const scheduler = new RuntimeScheduler(store);
  let status = scheduler.status(runId);
  if (status.run_id !== runId || status.run_status !== 'pending' || status.steps.length !== 1 || !status.cost_summary) throw new Error('scheduler status mismatch');
  const claim = await store.claimStep({ workerId: 'scheduler-stale', runId, leaseSeconds: 0 });
  if (!claim) throw new Error('scheduler claim failed');
  const recovery = await scheduler.recoverExpiredLeases();
  if (recovery.recovered_steps !== 1) throw new Error('scheduler recovered steps mismatch');
  const cancelled = await scheduler.cancelRun(runId, 'scheduler smoke');
  if (cancelled !== 1) throw new Error('scheduler cancelled steps mismatch');
  status = scheduler.status(runId);
  if (status.run_status !== 'cancelled' || status.steps[0].status !== 'cancelled') throw new Error('scheduler cancelled status mismatch');
}


async function runAdversarialReviewSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'review' });
  await rt.runOnce({ runId, workerId: 'review-worker', agentRole: 'ReviewAgent', agent: async (ctx) => ctx.writeState('answer', 'ok') });
  const bundle = exportEvidence(rt.store, runId);
  const report = adversarialReview(bundle);
  if (!report.passed) throw new Error('clean adversarial review should pass');
  const pending = structuredClone(bundle);
  pending.summary.has_pending_approvals = true;
  pending.approvals = [{ risk_level: 'high', status: 'PENDING' }];
  if (adversarialReview(pending).passed) throw new Error('pending high-risk approval should block');
  const costly = structuredClone(bundle);
  costly.cost_summary.total_usd = 1.0;
  if (adversarialReview(costly, { maxTotalUsd: 0.5 }).passed) throw new Error('cost limit should block');
}


async function runEvidenceRegressionSmoke() {
  const rt = new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun({ input: 'eval' });
  await rt.runOnce({ runId, workerId: 'eval-worker', agentRole: 'EvalAgent', agent: async (ctx) => ctx.writeState('answer', 'ok') });
  const bundle = exportEvidence(rt.store, runId);
  if (!evaluateEvidence(bundle).passed) throw new Error('clean evidence health check should pass');
  const changed = structuredClone(bundle);
  changed.final_state = { answer: 'changed' };
  changed.events.push({ seq: changed.events.length + 1, type: 'extra_event' });
  if (evaluateEvidenceRegression(bundle, changed).passed) throw new Error('regression changes should fail');
  const costly = structuredClone(bundle);
  costly.cost_summary.total_usd = 1.0;
  if (evaluateEvidenceRegression(bundle, costly, { maxTotalUsdDelta: 0.5 }).passed) throw new Error('cost delta should fail');
}


function runShadowSmoke() {
  const diff = diffStates({ answer: 'old', stable: true }, { answer: 'new', stable: true, extra: 1 });
  if (diff.changed_count !== 2) throw new Error('shadow diff changed_count mismatch');
  const report = shadowReport('run_source', 'run_shadow', true, { answer: 'old' }, { answer: 'new' });
  if (report.source_run_id !== 'run_source' || report.shadow_run_id !== 'run_shadow' || !report.ok) throw new Error('shadow report mismatch');
}


async function runReproGoldenSmoke() {
  if (builtinGoldenNames().join(',') !== 'media-stream-checkpoint,minimal-success,tool-ledger-success') throw new Error('builtin golden names mismatch');
  const bundle = await builtinGoldenEvidence('minimal-success');
  if (bundle.schema_version !== 'agentledger.evidence.v1' || bundle.final_state.answer !== 'ok') throw new Error('minimal golden evidence mismatch');
  const changed = structuredClone(bundle);
  changed.final_state = { answer: 'changed' };
  if (goldenRegression(bundle, changed).passed) throw new Error('golden regression should detect final state change');
}


async function runTimeTravelTimelineSmoke() {
  const bundle = await builtinGoldenEvidence('minimal-success');
  const report = timeTravel(bundle, { atSeq: 999, includeStates: true });
  if (report.state_at_seq.answer !== 'ok' || report.event_count !== bundle.events.length) throw new Error('time travel state mismatch');
  if (!report.timeline.some((frame) => frame.state_changed)) throw new Error('time travel missing changed frame');
  const html = timeTravelHTML(report);
  for (const token of ['AgentLedger Time Travel Report', 'State At Selected Point', 'Selected Event']) if (!html.includes(token)) throw new Error(`time travel html missing ${token}`);
}

function runOptionalAdaptersSmoke() {
  const caps = optionalAdapterCapabilities();
  const seen = new Set(caps.map((cap) => cap.name));
  for (const cap of caps) {
    if (cap.core_imports_heavy_sdks || !cap.adapter_is_optional || !cap.fail_closed_without_adapter || !cap.contract_surface?.length) throw new Error(`invalid optional adapter capability: ${cap.name}`);
  }
  for (const name of ['postgres', 'mysql', 's3', 'docker', 'langgraph', 'mcp-transport', 'langfuse', 'shadow-runner']) {
    if (!seen.has(name)) throw new Error(`missing optional adapter capability: ${name}`);
  }
}

async function runOfficialAdaptersSmoke() {
  const sql = { count: 0, async exec() { this.count += 1; } };
  const pg = new PostgresAdapter(sql);
  if (pg.migrationPlan()[0].dialect !== 'postgres') throw new Error('postgres adapter plan failed');
  await pg.applyMigrations();
  if (sql.count < 2) throw new Error('postgres adapter apply failed');
  const mysqlStart = sql.count;
  const mysql = new MySQLAdapter(sql);
  if (mysql.migrationPlan()[0].dialect !== 'mysql') throw new Error('mysql adapter plan failed');
  await mysql.applyMigrations();
  if (sql.count < mysqlStart + 2) throw new Error('mysql adapter apply failed');
  const objects = new Map();
  const s3 = new S3BlobStoreAdapter({ async putObject(input) { objects.set(`${input.Bucket}/${input.Key}`, input); }, async getObject(bucket, key) { return { Body: objects.get(`${bucket}/${key}`).Body }; } }, { bucket: 'agentledger-test' });
  const put = await s3.putJSON({ answer: 'ok' });
  if (!put.ref.startsWith('s3://agentledger-test/agentledger/blobs/sha256/')) throw new Error('s3 ref mismatch');
  if ((await s3.getJSON(put.ref)).answer !== 'ok') throw new Error('s3 roundtrip failed');
  const otlp = { contentType: null, async postJSON(_endpoint, _payload, contentType) { this.contentType = contentType; } };
  await new OTLPTransport(otlp, { endpoint: 'http://collector' }).export({});
  if (otlp.contentType !== 'application/json') throw new Error('otlp transport failed');
  const manifest = new DockerSandboxAdapter().manifest({ network: 'deny' }, ['echo', 'ok']);
  if (manifest.network !== 'none' || manifest.read_only_root !== true || manifest.requires_explicit_execution !== true) throw new Error('docker manifest failed');
  const closed = await new DockerSandboxExecutor().runTool({}, { _sandbox_command: ['echo', 'ok'] }, { executor: 'docker', network: 'deny', timeout_seconds: 1 });
  if (closed.ok || closed.metadata.error_type !== 'SandboxAdapterNotInstalled') throw new Error('docker executor should fail closed without explicit execution');
  const executed = await new DockerSandboxExecutor({ binary: '/bin/echo', image: 'fake-image', allowCommandExecution: true }).runTool({}, { _sandbox_command: ['echo', 'ok'] }, { executor: 'docker', network: 'deny', timeout_seconds: 1 });
  if (!executed.ok || !String(executed.output.stdout).includes('fake-image')) throw new Error('docker executor injected binary failed');
}
