export type JSONObject = Record<string, unknown>;

export interface ToolSpec {
  name: string;
  version?: string;
  description?: string;
  sideEffect?: 'none' | 'external' | string;
  riskLevel?: 'low' | 'medium' | 'high' | string;
  idempotencyRequired?: boolean;
  approvalRequired?: boolean;
  sandboxRequired?: boolean;
  sandboxExecutor?: string | null;
  sandboxPolicy?: JSONObject;
  inputSchema?: JSONObject;
  outputSchema?: JSONObject;
  func: (args: JSONObject) => unknown | Promise<unknown>;
}

export interface RunRef {
  runId: string;
  stepId: string;
}

export interface BudgetLimits {
  maxToolCalls?: number | null;
  maxModelTokens?: number | null;
  maxTotalUsd?: number | null;
}

export class NoRunnableStepError extends Error {}
export class RetryableAgentError extends Error {}
export class PermissionDeniedError extends Error {}
export class ApprovalRequiredError extends Error { readonly approvalId: string; }
export class BudgetExceededError extends Error {}
export class SandboxUnavailableError extends Error {}

export class LocalBlobStore {
  constructor(root: string);
  static open(root: string): Promise<LocalBlobStore>;
  putJSON(value: unknown): Promise<{ digest: string; ref: string }>;
  getJSON(ref: string): Promise<unknown>;
}

export class JSONStore {
  constructor(path?: string | null, data?: unknown);
  static memory(): JSONStore;
  static open(path: string): Promise<JSONStore>;
  flush(): Promise<void>;
  createRun(initialState?: JSONObject, sessionId?: string | null): Promise<RunRef>;
  claimStep(input: { workerId: string; runId?: string | null; leaseSeconds?: number }): Promise<JSONObject>;
  loadState(runId: string): { state: JSONObject; version: number; sessionId: string };
  heartbeat(input: { stepId: string; leaseToken: string; leaseSeconds?: number }): Promise<number>;
  recoverExpiredLeases(): Promise<number>;
  cancelRun(runId: string, reason: string): Promise<number>;
  commitStatePatch(input: { runId: string; stepId: string; leaseToken: string; baseVersion: number; patch?: JSONObject; checkpointId?: string | null }): Promise<number>;
  markWaitingHuman(input: { runId: string; stepId: string; reason: string; approvalId?: string | null }): Promise<void>;
  approvalRequests(runId?: string | null): JSONObject[];
  approveRequest(approvalId: string, input?: { approver?: string; reason?: string }): Promise<JSONObject>;
  denyRequest(approvalId: string, input?: { approver?: string; reason?: string }): Promise<JSONObject>;
  recordCost(input: { runId: string; sessionId?: string | null; stepId?: string | null; category: string; name: string; amount: number; unit: string; metadata?: JSONObject }): Promise<string>;
  costRecords(runId: string): JSONObject[];
  costSummary(runId: string): JSONObject;
  createArtifact(input: { runId: string; stepId?: string | null; name: string; content: unknown; metadata?: JSONObject }): Promise<JSONObject>;
  artifacts(runId: string): JSONObject[];
  finalState(runId: string): JSONObject;
  steps(runId: string): JSONObject[];
  events(runId: string): JSONObject[];
  ledger(runId: string): JSONObject[];
}

export class ToolRegistry {
  constructor();
  register(spec: ToolSpec): void;
}

export class PolicyEngine {
  constructor();
  allowTool(role: string, tool: string): void;
  denyTool(role: string, tool: string): void;
  allowRisk(role: string, risk: string): void;
  checkTool(role: string, toolName: string, riskLevel: string): { allowed: boolean; reason: string };
}

export class BudgetController {
  constructor(limits?: BudgetLimits);
}

export class DisabledSandboxExecutor {
  runTool(spec: ToolSpec, args: JSONObject, policy: JSONObject): Promise<JSONObject>;
}

export class LocalSandboxExecutor {
  runTool(spec: ToolSpec, args: JSONObject, policy: JSONObject): Promise<JSONObject>;
}

export class DockerSandboxExecutor {
  constructor(options?: { image?: string; binary?: string; allowCommandExecution?: boolean; allowShell?: boolean; shell?: string; memory?: string | null; cpus?: string | null });
  runTool(spec: ToolSpec, args: JSONObject, policy: JSONObject): Promise<JSONObject>;
  manifest(policy: JSONObject, command: string[]): JSONObject;
}

export function validateToolSchema(schema: JSONObject | undefined | null, value: unknown, path?: string): void;

export class Runtime {
  constructor(store?: JSONStore);
  static local(path: string): Promise<Runtime>;
  setBudget(limits?: BudgetLimits): void;
  setSandbox(executor: unknown): void;
  registerTool(spec: ToolSpec): void;
  createRun(initialState?: JSONObject): Promise<RunRef>;
  runOnce(input: {
    runId: string;
    workerId?: string;
    agentRole?: string;
    leaseSeconds?: number;
    agent: (ctx: AgentContext, state: JSONObject) => void | Promise<void>;
  }): Promise<boolean>;
}

export class LocalWorker {
  constructor(runtime: Runtime, options?: { workerId?: string; agentRole?: string; leaseSeconds?: number; recoverExpired?: boolean });
  runUntilIdle(input: { runId?: string | null; maxIterations?: number; agent: (ctx: AgentContext, state: JSONObject) => void | Promise<void> }): Promise<JSONObject>;
}

export class WorkerService {
  constructor(worker: LocalWorker);
  requestStop(reason?: string): void;
  serve(input: { runId?: string | null; maxLoops?: number; maxIdlePolls?: number | null; agent: (ctx: AgentContext, state: JSONObject) => void | Promise<void> }): Promise<JSONObject>;
}

export class AgentContext {
  readonly runId: string;
  readonly sessionId: string;
  readonly stepId: string;
  readonly agentRole: string;
  readonly leaseToken: string;
  readonly attempt: number;
  readonly stateVersion: number;
  readonly pendingPatch: JSONObject;
  callTool(name: string, args?: JSONObject): Promise<unknown>;
  writeState(key: string, value: unknown): Promise<void>;
  createArtifact(name: string, content: unknown, metadata?: JSONObject): Promise<string>;
  createMediaArtifact(name: string, kind: string, options?: {
    uri?: string;
    contentRef?: string;
    mediaMetadata?: JSONObject;
    lineage?: JSONObject;
    derivedOutputs?: JSONObject;
    metadata?: JSONObject;
  }): Promise<string>;
  createStreamCheckpoint(name: string, options: {
    streamId: string;
    consumerId: string;
    offset: number | string;
    watermark?: number | string;
    chunk?: JSONObject;
    partialResultRef?: string;
    backpressure?: JSONObject;
    metadata?: JSONObject;
  }): Promise<string>;
  recordModelCall(input: { model: string; inputTokens?: number; outputTokens?: number; totalUsd?: number }): Promise<void>;
  recordModelCallEvidence(input: { provider?: string; model: string; request?: JSONObject; response?: JSONObject; usage?: JSONObject; totalUsd?: number; metadata?: JSONObject }): Promise<void>;
  recordModelFailure(input: { provider?: string; model: string; errorType?: string; message: string; retryable?: boolean; request?: JSONObject; usage?: JSONObject; totalUsd?: number; metadata?: JSONObject }): Promise<void>;
  recordToolCallProposal(input: { toolName: string; arguments?: JSONObject; provider?: string; model?: string; modelCallRef?: string; confidence?: number; reason?: string; metadata?: JSONObject }): Promise<void>;
  heartbeat(leaseSeconds?: number): Promise<number>;
}

export function exportEvidence(store: JSONStore, runId: string): JSONObject;
export function replay(store: JSONStore, runId: string): JSONObject;
export function costAttribution(store: JSONStore, runId: string): JSONObject;
export type FailureAttributionReport = JSONObject;
export function failureAttribution(store: JSONStore, runId: string): JSONObject;

export function traceSpans(bundle: any): any[];
export function traceJSONL(bundle: any): string;
export function diffEvidence(left: any, right: any): any;
export function divergenceReport(left: any, right: any): any;
export function debugSummary(bundle: any): any;

export function simpleRun(agent: (ctx: any, state: any) => any | Promise<any>, options?: any): Promise<any>;

export function otlpTraceJSON(bundle: any, options?: any): any;

export function debugHTML(bundle: any): string;

export function planRetention(bundle: any): any;
export function checkBackupReadiness(bundle: any): any;
export function migrationsFor(dialect: string): any[];
export function latestSchemaVersion(dialect: string): string | null;
export function ddlFor(dialect: string): string;
export class InMemoryMCPToolServer { addTool(descriptor: any, handler: any): void; listTools(): any[]; callTool(name: string, args?: any): any; }
export class InMemoryMCPContextServer { addResource(options: any): void; listResources(): any[]; readResource(uri: string): any; }
export class MCPToolAdapter { constructor(clientCall: any); toolSpecFromDescriptor(descriptor: any): any; }
export class MCPContextAdapter { constructor(resourceRead: any); readToolSpec(options?: any): any; }
export class FunctionAdapter { constructor(func: any, options?: any); mapRunSpec(): any; asAgent(options?: any): any; }
export class MethodFrameworkAdapter { constructor(target: any, options?: any); mapRunSpec(): any; asAgent(): any; invoke(payload: any): any; }

export interface BoundaryLintRule { rule_id: string; pattern: string; category: string; message: string; suggestion: string; prefix?: boolean; }
export interface BoundaryLintFinding { path: string; line: number; column: number; rule_id: string; severity: string; callee: string; category: string; message: string; suggestion: string; }
export interface BoundaryLintReport { passed: boolean; scanned_files: string[]; finding_count: number; findings: BoundaryLintFinding[]; }
export function defaultBoundaryRules(): BoundaryLintRule[];
export function scanBoundarySource(path: string, source: string, rules?: BoundaryLintRule[]): BoundaryLintReport;

export interface RecoverySummary { recovered_steps: number; }
export interface SchedulerStepStatus { step_id: string; status: string; owner?: string | null; attempt: number; lease_until?: number | null; last_error_type?: string | null; }
export interface SchedulerStatus { run_id: string; run_status: string; state_version: number; steps: SchedulerStepStatus[]; cost_summary: CostSummary; }
export class RuntimeScheduler {
  constructor(store: JSONStore);
  recoverExpiredLeases(): Promise<RecoverySummary>;
  cancelRun(runId: string, reason?: string): Promise<number>;
  status(runId: string): SchedulerStatus;
}

export interface ReviewCheck { name: string; passed: boolean; severity: string; detail: string; }
export interface AdversarialReviewReport { passed: boolean; run_id?: string | null; checks: ReviewCheck[]; metadata: Record<string, unknown>; }
export function adversarialReview(bundle: EvidenceBundle | Record<string, unknown>, options?: { maxTotalUsd?: number | null }): AdversarialReviewReport;

export interface EvidenceCheck { name: string; passed: boolean; detail: string; }
export interface EvidenceCheckReport { passed: boolean; checks: EvidenceCheck[]; metadata?: Record<string, unknown>; }
export function evaluateEvidence(bundle: EvidenceBundle | Record<string, unknown>, options?: { maxTotalUsd?: number | null }): EvidenceCheckReport;
export function evaluateEvidenceRegression(golden: EvidenceBundle | Record<string, unknown>, current: EvidenceBundle | Record<string, unknown>, options?: { maxTotalUsdDelta?: number | null }): EvidenceCheckReport;

export interface FailureInjectionCheck { name: string; passed: boolean; detail: string; run_id?: string; }
export interface FailureInjectionReport { passed: boolean; checks: FailureInjectionCheck[]; }
export function runFailureInjectionSuite(): Promise<FailureInjectionReport>;

export interface ShadowReport { source_run_id: string; shadow_run_id: string; ok: boolean; state_diff: Record<string, unknown>; }
export function diffStates(source: Record<string, unknown>, shadow: Record<string, unknown>): Record<string, unknown>;
export function shadowReport(sourceRunId: string, shadowRunId: string, ok: boolean, sourceState: Record<string, unknown>, shadowState: Record<string, unknown>): ShadowReport;

export function builtinGoldenNames(): string[];
export function builtinGoldenEvidence(name: string): Promise<EvidenceBundle>;
export function goldenRegression(golden: EvidenceBundle, current: EvidenceBundle): EvidenceCheckReport;

export interface TimeTravelFrame { seq: number; event_id?: string; type: string; step_id?: string | null; agent_role?: string | null; state_version?: number | null; timestamp: number; state_changed: boolean; changed_keys: string[]; patch?: Record<string, unknown> | null; state_after?: Record<string, unknown> | null; }
export interface TimeTravelReport { run_id: string | null; at_seq: number | null; event_count: number; timeline: TimeTravelFrame[]; state_at_seq: Record<string, unknown>; selected_event: TimeTravelFrame | null; }
export function timeTravel(bundle: EvidenceBundle | Record<string, unknown>, options?: { atSeq?: number; includeStates?: boolean }): TimeTravelReport;
export function timeTravelHTML(report: TimeTravelReport): string;

export function optionalAdapterCapabilities(): Array<{ name: string; category: string; core_imports_heavy_sdks: boolean; adapter_is_optional: boolean; fail_closed_without_adapter: boolean; contract_surface: string[] }>;

export class PostgresAdapter { constructor(client: any, options?: any); migrationPlan(): any[]; exec(sql: string, params?: any[]): Promise<any>; applyMigrations(): Promise<void>; }
export class MySQLAdapter { constructor(client: any, options?: any); migrationPlan(): any[]; exec(sql: string, params?: any[]): Promise<any>; applyMigrations(): Promise<void>; }
export class S3BlobStoreAdapter { constructor(client: any, options?: any); putObject(input: any): Promise<any>; getObject(bucket: string, key: string): Promise<any>; putJSON(value: any): Promise<{ digest: string; ref: string }>; getJSON(ref: string): Promise<any>; }
export class OTLPTransport { constructor(client: any, options?: any); export(payload: any): Promise<any>; }
export class DockerSandboxAdapter { constructor(options?: any); manifest(policy: any, command: string[]): any; }
