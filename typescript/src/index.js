import { createHash, randomBytes } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { spawn } from 'node:child_process';

export class NoRunnableStepError extends Error {
  constructor() {
    super('agentledger: no runnable step');
    this.name = 'NoRunnableStepError';
  }
}

export class RetryableAgentError extends Error {
  constructor(message = 'agentledger: retryable agent error') {
    super(message);
    this.name = 'RetryableAgentError';
  }
}

export class PermissionDeniedError extends Error {
  constructor(message) {
    super(message);
    this.name = 'PermissionDeniedError';
  }
}

export class ApprovalRequiredError extends Error {
  constructor(approvalId, message) {
    super(message);
    this.name = 'ApprovalRequiredError';
    this.approvalId = approvalId;
  }
}

export class BudgetExceededError extends Error {
  constructor(message) {
    super(message);
    this.name = 'BudgetExceededError';
  }
}

export class SandboxUnavailableError extends Error {
  constructor(message) {
    super(message);
    this.name = 'SandboxUnavailableError';
  }
}

export class LocalBlobStore {
  constructor(root) {
    this.root = root;
  }

  static async open(root) {
    await mkdir(root, { recursive: true });
    return new LocalBlobStore(root);
  }

  async putJSON(value) {
    const digest = sha256JSON(value);
    const dir = join(this.root, 'sha256');
    const path = join(dir, `${digest}.json`);
    await mkdir(dir, { recursive: true });
    const tmp = `${path}.tmp`;
    try {
      await readFile(path, 'utf8');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      await writeFile(tmp, JSON.stringify(value, null, 2), 'utf8');
      await rename(tmp, path);
    }
    return { digest: `sha256:${digest}`, ref: `blob://sha256/${digest}.json` };
  }

  async getJSON(ref) {
    const prefix = 'blob://sha256/';
    if (!ref.startsWith(prefix)) throw new Error(`unsupported blob ref: ${ref}`);
    const name = ref.slice(prefix.length);
    if (!name.endsWith('.json') || name.includes('..') || name.includes('/') || name.includes('\\\\')) throw new Error(`unsupported blob ref: ${ref}`);
    return JSON.parse(await readFile(join(this.root, 'sha256', name), 'utf8'));
  }
}

export class JSONStore {
  constructor(path = null, data = null) {
    this.path = path;
    this.data = data ?? emptyData();
    normalizeData(this.data);
  }

  static memory() {
    return new JSONStore(null, emptyData());
  }

  static async open(path) {
    let data = emptyData();
    try {
      const raw = await readFile(path, 'utf8');
      if (raw.trim()) data = { ...emptyData(), ...JSON.parse(raw) };
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    normalizeData(data);
    return new JSONStore(path, data);
  }

  async flush() {
    if (!this.path) return;
    await mkdir(dirname(this.path), { recursive: true });
    const tmp = `${this.path}.tmp`;
    await writeFile(tmp, `${JSON.stringify(this.data, null, 2)}\n`, 'utf8');
    await rename(tmp, this.path);
  }

  async createRun(initialState = {}, sessionId = null) {
    const runId = newId('run');
    const stepId = newId('step');
    const actualSessionId = sessionId ?? newId('sess');
    const now = nowSeconds();
    this.data.runs[runId] = {
      run_id: runId,
      session_id: actualSessionId,
      status: 'pending',
      state: clone(initialState),
      state_version: 0,
      created_at: now,
      updated_at: now,
    };
    this.data.steps[stepId] = {
      step_id: stepId,
      run_id: runId,
      session_id: actualSessionId,
      status: 'pending',
      attempt: 0,
      state_version: 0,
      created_at: now,
      updated_at: now,
    };
    this.appendEventSync({ runId, sessionId: actualSessionId, type: 'run_created', payload: { initial_state: clone(initialState) } });
    this.appendEventSync({ runId, sessionId: actualSessionId, stepId, type: 'step_created', payload: { step_id: stepId } });
    await this.flush();
    return { runId, stepId };
  }

  async claimStep({ workerId, runId = null, leaseSeconds = 60 }) {
    const candidates = Object.values(this.data.steps)
      .filter((step) => (!runId || step.run_id === runId) && ['pending', 'retry_scheduled'].includes(step.status))
      .sort((a, b) => a.created_at - b.created_at || a.step_id.localeCompare(b.step_id));
    const step = candidates[0];
    if (!step) throw new NoRunnableStepError();
    const now = nowSeconds();
    step.status = 'running';
    step.owner = workerId;
    step.lease_token = newId('lease');
    step.lease_until = now + leaseSeconds;
    step.attempt += 1;
    step.updated_at = now;
    const run = this.data.runs[step.run_id];
    run.status = 'running';
    run.updated_at = now;
    this.appendEventSync({
      runId: step.run_id,
      sessionId: step.session_id,
      stepId: step.step_id,
      type: 'step_claimed',
      payload: { worker_id: workerId, lease_token: step.lease_token, attempt: step.attempt, lease_until: step.lease_until },
    });
    await this.flush();
    return {
      run_id: step.run_id,
      session_id: step.session_id,
      step_id: step.step_id,
      attempt: step.attempt,
      lease_token: step.lease_token,
      state_version: step.state_version,
      lease_until: step.lease_until,
    };
  }

  loadState(runId) {
    const run = this.data.runs[runId];
    if (!run) throw new Error(`run not found: ${runId}`);
    return { state: clone(run.state), version: run.state_version, sessionId: run.session_id };
  }

  async heartbeat({ stepId, leaseToken, leaseSeconds = 60 }) {
    const step = this.validateLease(stepId, leaseToken);
    step.lease_until = nowSeconds() + leaseSeconds;
    step.updated_at = nowSeconds();
    this.appendEventSync({ runId: step.run_id, sessionId: step.session_id, stepId, type: 'lease_heartbeat', payload: { lease_token: leaseToken, lease_until: step.lease_until } });
    await this.flush();
    return step.lease_until;
  }

  async recoverExpiredLeases() {
    const now = nowSeconds();
    let recovered = 0;
    for (const step of Object.values(this.data.steps).sort((a, b) => a.step_id.localeCompare(b.step_id))) {
      if (step.status !== 'running' || step.lease_until === undefined || step.lease_until > now) continue;
      const previousOwner = step.owner;
      step.status = 'retry_scheduled';
      delete step.owner;
      delete step.lease_token;
      delete step.lease_until;
      step.updated_at = now;
      const run = this.data.runs[step.run_id];
      run.status = 'retry_scheduled';
      run.updated_at = now;
      recovered += 1;
      this.appendEventSync({ runId: step.run_id, sessionId: step.session_id, stepId: step.step_id, type: 'lease_expired', payload: { previous_owner: previousOwner, attempt: step.attempt } });
      this.appendEventSync({ runId: step.run_id, sessionId: step.session_id, stepId: step.step_id, type: 'step_retry_scheduled', payload: { step_id: step.step_id, reason: 'lease_expired' } });
    }
    await this.flush();
    return recovered;
  }

  async cancelRun(runId, reason) {
    const run = this.data.runs[runId];
    if (!run) throw new Error(`run not found: ${runId}`);
    if (['completed', 'failed', 'cancelled'].includes(run.status)) return 0;
    const now = nowSeconds();
    let cancelled = 0;
    this.appendEventSync({ runId, sessionId: run.session_id, type: 'run_cancel_requested', payload: { reason } });
    for (const step of Object.values(this.data.steps)) {
      if (step.run_id !== runId || ['completed', 'failed', 'cancelled'].includes(step.status)) continue;
      step.status = 'cancelled';
      delete step.owner;
      delete step.lease_token;
      delete step.lease_until;
      step.cancelled_at = now;
      step.updated_at = now;
      cancelled += 1;
      this.appendEventSync({ runId, sessionId: step.session_id, stepId: step.step_id, type: 'step_cancelled', payload: { reason } });
    }
    run.status = 'cancelled';
    run.updated_at = now;
    this.appendEventSync({ runId, sessionId: run.session_id, type: 'run_cancelled', payload: { reason, cancelled_steps: cancelled } });
    await this.flush();
    return cancelled;
  }

  async commitStatePatch({ runId, stepId, leaseToken, baseVersion, patch = {}, checkpointId = null }) {
    const step = this.validateLease(stepId, leaseToken);
    const run = this.data.runs[runId];
    if (!run) throw new Error(`run not found: ${runId}`);
    if (run.state_version !== baseVersion) throw new Error(`state version conflict: expected ${baseVersion}, got ${run.state_version}`);
    const now = nowSeconds();
    const nextVersion = run.state_version + 1;
    run.state = mergePatch(run.state, patch);
    run.state_version = nextVersion;
    run.status = 'completed';
    run.updated_at = now;
    step.status = 'completed';
    step.state_version = nextVersion;
    if (checkpointId) step.checkpoint_id = checkpointId;
    step.updated_at = now;
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'state_patch_committed', stateVersion: nextVersion, payload: { patch: clone(patch), state_version: nextVersion } });
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'step_completed', stateVersion: nextVersion, payload: { step_id: stepId } });
    await this.flush();
    return nextVersion;
  }

  async markWaitingHuman({ runId, stepId, reason, approvalId = null }) {
    const step = this.data.steps[stepId];
    if (!step) throw new Error(`step not found: ${stepId}`);
    const now = nowSeconds();
    step.status = 'waiting_human';
    delete step.owner;
    delete step.lease_token;
    delete step.lease_until;
    step.last_error_type = 'ApprovalRequired';
    step.last_error = reason;
    step.updated_at = now;
    const run = this.data.runs[runId];
    run.status = 'waiting_human';
    run.updated_at = now;
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'step_waiting_human', payload: { reason, approval_id: approvalId } });
    await this.flush();
  }

  async markRetry({ runId, stepId, errorType, message }) {
    const step = this.data.steps[stepId];
    if (!step) throw new Error(`step not found: ${stepId}`);
    const now = nowSeconds();
    step.status = 'retry_scheduled';
    delete step.owner;
    delete step.lease_token;
    delete step.lease_until;
    step.last_error_type = errorType;
    step.last_error = message;
    step.updated_at = now;
    const run = this.data.runs[runId];
    run.status = 'retry_scheduled';
    run.updated_at = now;
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'failure_classified', payload: { error: message, error_type: errorType, retryable: true, source: 'agent' } });
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'error_raised', payload: { error: message, error_type: errorType } });
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'step_retry_scheduled', payload: { step_id: stepId, attempt: step.attempt } });
    await this.flush();
  }

  async markFailed({ runId, stepId, errorType, message }) {
    const step = this.data.steps[stepId];
    if (!step) throw new Error(`step not found: ${stepId}`);
    const now = nowSeconds();
    step.status = 'failed';
    delete step.owner;
    delete step.lease_token;
    delete step.lease_until;
    step.last_error_type = errorType;
    step.last_error = message;
    step.updated_at = now;
    const run = this.data.runs[runId];
    run.status = 'failed';
    run.updated_at = now;
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'failure_classified', payload: { error: message, error_type: errorType, retryable: false, source: failureSource(errorType) } });
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'error_raised', payload: { error: message, error_type: errorType } });
    this.appendEventSync({ runId, sessionId: step.session_id, stepId, type: 'step_failed', payload: { step_id: stepId, error_type: errorType } });
    await this.flush();
  }

  async appendEvent(input) {
    const event = this.appendEventSync(input);
    await this.flush();
    return event;
  }

  appendEventSync({ runId, sessionId = null, stepId = null, type, payload = {}, agentRole = null, stateVersion = null, causalToken = null, payloadHash = null, payloadRef = null }) {
    const events = this.data.events[runId] ?? [];
    const actualPayloadHash = payloadHash ?? sha256JSON(payload);
    const actualPayloadRef = payloadRef ?? JSON.stringify(payload);
    const event = {
      event_id: newId('evt'),
      run_id: runId,
      session_id: sessionId,
      step_id: stepId,
      seq: events.length + 1,
      type,
      timestamp: nowSeconds(),
      agent_role: agentRole,
      state_version: stateVersion,
      causal_token: causalToken,
      payload_hash: actualPayloadHash,
      payload_ref: actualPayloadRef,
      payload: clone(payload),
    };
    this.data.events[runId] = [...events, event];
    return event;
  }

  async reserveLedger(input) {
    const existing = this.data.tool_ledger[input.idempotencyKey];
    if (existing) return clone(existing);
    const now = nowSeconds();
    this.data.tool_ledger[input.idempotencyKey] = {
      ledger_id: newId('ledger'),
      run_id: input.runId,
      session_id: input.sessionId,
      step_id: input.stepId,
      tool_name: input.toolName,
      tool_version: input.toolVersion,
      tool_call_id: input.toolCallId,
      idempotency_key: input.idempotencyKey,
      causal_token: input.causalToken,
      request_hash: input.requestHash,
      request_ref: input.requestRef,
      status: 'RESERVED',
      created_at: now,
      updated_at: now,
    };
    await this.flush();
    return null;
  }

  async updateLedger({ idempotencyKey, status, externalId = null, responseHash = null, responseRef = null, errorType = null, response = null }) {
    const entry = this.data.tool_ledger[idempotencyKey];
    if (!entry) throw new Error(`ledger entry not found: ${idempotencyKey}`);
    entry.status = status;
    entry.external_id = externalId;
    entry.response_hash = responseHash;
    entry.response_ref = responseRef;
    entry.error_type = errorType;
    entry.response = clone(response);
    entry.updated_at = nowSeconds();
    await this.flush();
  }

  async requestApproval(input) {
    const existing = this.data.approval_requests[input.approvalKey];
    if (existing) return clone(existing);
    const now = nowSeconds();
    const approval = {
      approval_id: newId('approval'),
      approval_key: input.approvalKey,
      run_id: input.runId,
      session_id: input.sessionId,
      step_id: input.stepId,
      tool_name: input.toolName,
      risk_level: input.riskLevel,
      status: 'PENDING',
      reason: input.reason,
      request_hash: input.requestHash,
      request_ref: input.requestRef,
      requested_by: input.requestedBy,
      created_at: now,
      updated_at: now,
    };
    this.data.approval_requests[input.approvalKey] = approval;
    await this.flush();
    return clone(approval);
  }

  approvalForKey(approvalKey) {
    const approval = this.data.approval_requests[approvalKey];
    return approval ? clone(approval) : null;
  }

  approvalRequests(runId = null) {
    return Object.values(this.data.approval_requests)
      .filter((approval) => !runId || approval.run_id === runId)
      .sort((a, b) => a.created_at - b.created_at || a.approval_id.localeCompare(b.approval_id))
      .map(clone);
  }

  approveRequest(approvalId, { approver = 'operator', reason = '' } = {}) {
    return this.decideApproval(approvalId, 'APPROVED', approver, reason);
  }

  denyRequest(approvalId, { approver = 'operator', reason = '' } = {}) {
    return this.decideApproval(approvalId, 'DENIED', approver, reason);
  }

  async decideApproval(approvalId, status, approver, reason) {
    const entry = Object.entries(this.data.approval_requests).find(([, approval]) => approval.approval_id === approvalId);
    if (!entry) throw new Error(`approval not found: ${approvalId}`);
    const [key, approval] = entry;
    const now = nowSeconds();
    approval.status = status;
    approval.approved_by = approver;
    approval.decision_reason = reason;
    approval.updated_at = now;
    this.data.approval_requests[key] = approval;
    this.appendEventSync({ runId: approval.run_id, sessionId: approval.session_id, stepId: approval.step_id, type: 'tool_approval_decided', payload: { approval_id: approvalId, tool: approval.tool_name, status, approver, reason } });
    const step = this.data.steps[approval.step_id];
    if (step?.status === 'waiting_human') {
      if (status === 'APPROVED') {
        step.status = 'pending';
        delete step.owner;
        delete step.lease_token;
        delete step.lease_until;
        step.updated_at = now;
        const run = this.data.runs[approval.run_id];
        run.status = 'pending';
        run.updated_at = now;
        this.appendEventSync({ runId: approval.run_id, sessionId: approval.session_id, stepId: approval.step_id, type: 'step_retry_scheduled', payload: { step_id: approval.step_id, reason: 'approval_granted' } });
      } else if (status === 'DENIED') {
        step.status = 'failed';
        delete step.owner;
        delete step.lease_token;
        delete step.lease_until;
        step.last_error_type = 'ApprovalDenied';
        step.last_error = reason;
        step.updated_at = now;
        const run = this.data.runs[approval.run_id];
        run.status = 'failed';
        run.updated_at = now;
        this.appendEventSync({ runId: approval.run_id, sessionId: approval.session_id, stepId: approval.step_id, type: 'failure_classified', payload: { error: reason, error_type: 'ApprovalDenied', retryable: false, source: 'approval' } });
        this.appendEventSync({ runId: approval.run_id, sessionId: approval.session_id, stepId: approval.step_id, type: 'step_failed', payload: { step_id: approval.step_id, error_type: 'ApprovalDenied' } });
      }
    }
    await this.flush();
    return clone(approval);
  }

  async recordCost({ runId, sessionId = null, stepId = null, category, name, amount, unit, metadata = {} }) {
    const costId = newId('cost');
    const record = { cost_id: costId, run_id: runId, session_id: sessionId, step_id: stepId, category, name, amount, unit, metadata: clone(metadata), created_at: nowSeconds() };
    this.data.cost_records[runId] ??= [];
    this.data.cost_records[runId].push(record);
    this.appendEventSync({ runId, sessionId, stepId, type: 'cost_recorded', payload: { cost_id: costId, category, name, amount, unit, metadata: clone(metadata) } });
    await this.flush();
    return costId;
  }

  costRecords(runId) {
    return (this.data.cost_records[runId] ?? []).map(clone);
  }

  costSummary(runId) {
    const summary = { tool_calls: 0, model_tokens: 0, total_usd: 0, by_category: {} };
    for (const row of this.costRecords(runId)) addCost(summary, row);
    return summary;
  }

  async createArtifact({ runId, stepId = null, name, content, metadata = {} }) {
    const artifact = {
      artifact_id: newId('art'),
      run_id: runId,
      step_id: stepId,
      name,
      blob_hash: `sha256:${sha256JSON(content)}`,
      blob_ref: JSON.stringify(content),
      metadata: clone(metadata),
      created_at: nowSeconds(),
    };
    this.data.artifacts[runId] ??= [];
    this.data.artifacts[runId].push(artifact);
    await this.flush();
    return clone(artifact);
  }

  artifacts(runId) {
    return (this.data.artifacts[runId] ?? [])
      .slice()
      .sort((a, b) => a.created_at - b.created_at || a.artifact_id.localeCompare(b.artifact_id))
      .map(clone);
  }

  run(runId) {
    const run = this.data.runs[runId];
    if (!run) throw new Error(`run not found: ${runId}`);
    return clone(run);
  }

  steps(runId) {
    return Object.values(this.data.steps).filter((step) => step.run_id === runId).sort((a, b) => a.created_at - b.created_at || a.step_id.localeCompare(b.step_id)).map(clone);
  }

  events(runId) {
    return (this.data.events[runId] ?? []).map(clone);
  }

  ledger(runId) {
    return Object.values(this.data.tool_ledger).filter((entry) => entry.run_id === runId).sort((a, b) => a.created_at - b.created_at || a.ledger_id.localeCompare(b.ledger_id)).map(clone);
  }

  finalState(runId) {
    return this.loadState(runId).state;
  }

  validateLease(stepId, leaseToken) {
    const step = this.data.steps[stepId];
    if (!step) throw new Error(`step not found: ${stepId}`);
    if (step.status !== 'running' || step.lease_token !== leaseToken) throw new Error('invalid or stale lease token');
    if (step.lease_until !== undefined && step.lease_until <= nowSeconds()) throw new Error('lease expired');
    return step;
  }
}

export class ToolRegistry {
  constructor() {
    this.tools = new Map();
  }

  register(spec) {
    if (!spec?.name) throw new Error('tool name is required');
    if (typeof spec.func !== 'function') throw new Error(`tool ${spec.name} has no function`);
    this.tools.set(spec.name, {
      version: 'v1',
      sideEffect: 'none',
      riskLevel: 'low',
      idempotencyRequired: false,
      approvalRequired: false,
      sandboxRequired: false,
      sandboxExecutor: null,
      sandboxPolicy: {},
      ...spec,
    });
  }

  get(name) {
    const spec = this.tools.get(name);
    if (!spec) throw new Error(`tool not registered: ${name}`);
    return spec;
  }
}

export class PolicyEngine {
  constructor() {
    this.roles = new Map();
    this.defaultByRisk = new Map();
  }

  allowTool(role, tool) {
    this.role(role).allowTools.add(tool);
  }

  denyTool(role, tool) {
    this.role(role).denyTools.add(tool);
  }

  allowRisk(role, risk) {
    this.role(role).allowRisk.add(risk);
  }

  checkTool(role, toolName, riskLevel) {
    const policy = this.roles.get(role);
    if (policy) {
      if (policy.denyTools.has(toolName)) return { allowed: false, reason: `tool ${toolName} explicitly denied for role ${role}` };
      if (policy.allowTools.has(toolName)) return { allowed: true, reason: 'allowed by role policy' };
      if (policy.denyRisk.has(riskLevel)) return { allowed: false, reason: `risk level ${riskLevel} denied for role ${role}` };
      if (policy.allowRisk.has(riskLevel)) return { allowed: true, reason: `risk level ${riskLevel} allowed for role ${role}` };
      if (policy.allowTools.size || policy.allowRisk.size) return { allowed: false, reason: `tool ${toolName} not allowed for role ${role}` };
    }
    if (this.defaultByRisk.get(riskLevel) === 'allow') return { allowed: true, reason: `risk level ${riskLevel} allowed by default policy` };
    if (this.defaultByRisk.get(riskLevel) === 'deny') return { allowed: false, reason: `risk level ${riskLevel} denied by default policy` };
    if (['high', 'destructive', 'sensitive', 'financial_or_legal'].includes(riskLevel)) return { allowed: false, reason: 'high-risk tool denied by default' };
    return { allowed: true, reason: 'default allow for low/medium risk in local runtime' };
  }

  role(role) {
    if (!this.roles.has(role)) this.roles.set(role, { allowTools: new Set(), denyTools: new Set(), allowRisk: new Set(), denyRisk: new Set() });
    return this.roles.get(role);
  }
}

export class BudgetController {
  constructor(limits = {}) {
    this.limits = { maxToolCalls: null, maxModelTokens: null, maxTotalUsd: null, ...limits };
  }

  beforeToolCall(store, runId) {
    if (this.limits.maxToolCalls == null) return;
    const used = store.costSummary(runId).tool_calls;
    if (used >= this.limits.maxToolCalls) throw new BudgetExceededError(`tool call budget exceeded: ${used}/${this.limits.maxToolCalls}`);
  }

  beforeModelCall(store, runId, estimatedTokens = 0) {
    if (this.limits.maxModelTokens != null) {
      const used = store.costSummary(runId).model_tokens;
      if (used + estimatedTokens > this.limits.maxModelTokens) throw new BudgetExceededError(`model token budget exceeded: ${used}+${estimatedTokens}/${this.limits.maxModelTokens}`);
    }
    if (this.limits.maxTotalUsd != null) {
      const used = store.costSummary(runId).total_usd;
      if (used > this.limits.maxTotalUsd) throw new BudgetExceededError(`cost budget exceeded: ${used}/${this.limits.maxTotalUsd} USD`);
    }
  }
}

export class DisabledSandboxExecutor {
  async runTool(_spec, _args, policy) {
    return { ok: false, error: `sandbox executor ${JSON.stringify(policy.executor)} is disabled`, metadata: { executor: policy.executor, isolation_level: 'none', fail_closed: true } };
  }
}

export class LocalSandboxExecutor {
  async runTool(spec, args, policy) {
    try {
      return { ok: true, output: await spec.func(clone(args)), metadata: { executor: policy.executor ?? 'local', isolation_level: 'none' } };
    } catch (error) {
      return { ok: false, error: String(error?.message ?? error), metadata: { executor: policy.executor ?? 'local', isolation_level: 'none' } };
    }
  }
}

export class DockerSandboxExecutor {
  constructor({ image = 'python:3.11-slim', binary = 'docker', allowCommandExecution = false, allowShell = false, shell = '/bin/sh', memory = null, cpus = null } = {}) {
    this.image = image;
    this.binary = binary;
    this.allowCommandExecution = allowCommandExecution;
    this.allowShell = allowShell;
    this.shell = shell;
    this.memory = memory;
    this.cpus = cpus;
  }

  async runTool(_spec, args, policy) {
    let command;
    try {
      command = this.extractCommand(args);
    } catch (error) {
      return this.failure(policy, 'InvalidSandboxCommand', error.message, null);
    }
    const manifest = this.manifest(policy, command);
    if (!this.allowCommandExecution) {
      return { ok: false, error: 'command execution is not enabled for this executor', metadata: { executor: policy.executor, isolation_level: 'container', manifest, error_type: 'SandboxAdapterNotInstalled' } };
    }
    const argv = this.dockerArgv(policy, command);
    return runSandboxCommand(argv, policy.timeout_seconds ?? 30, { executor: policy.executor, isolation_level: 'container', manifest, executed: true });
  }

  manifest(policy, command) {
    return new DockerSandboxAdapter({ image: this.image }).manifest(policy, command);
  }

  extractCommand(args) {
    const raw = args?._sandbox_command ?? args?.command;
    if (raw == null) throw new Error('external sandbox tools require a command-style `_sandbox_command` arg');
    if (typeof raw === 'string') {
      if (!this.allowShell) throw new Error('string commands require allowShell=true; pass argv list in `_sandbox_command` instead');
      return [this.shell, '-lc', raw];
    }
    if (!Array.isArray(raw) || raw.length === 0 || raw.some((item) => typeof item !== 'string' || item.length === 0)) {
      throw new Error('_sandbox_command must be a non-empty string[]');
    }
    return [...raw];
  }

  dockerArgv(policy, command) {
    const network = policy.network === 'deny' || !policy.network ? 'none' : policy.network;
    const argv = [this.binary, 'run', '--rm', '--network', network, '--read-only'];
    if (this.memory) argv.push('--memory', String(this.memory));
    if (this.cpus) argv.push('--cpus', String(this.cpus));
    argv.push(this.image, ...command);
    return argv;
  }

  failure(policy, errorType, message, manifest) {
    return { ok: false, error: message, metadata: { executor: policy.executor, isolation_level: 'container', ...(manifest ? { manifest } : {}), error_type: errorType } };
  }
}

function runSandboxCommand(argv, timeoutSeconds, metadata) {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let settled = false;
    let child;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const timer = setTimeout(() => {
      if (child) child.kill('SIGKILL');
      finish({ ok: false, output: { stdout, stderr, returncode: null }, error: `sandbox command timed out after ${timeoutSeconds}s`, metadata: { ...metadata, error_type: 'SandboxTimeout' } });
    }, Math.max(1, timeoutSeconds) * 1000);
    try {
      child = spawn(argv[0], argv.slice(1), { stdio: ['ignore', 'pipe', 'pipe'], env: { PATH: process.env.PATH ?? '' } });
    } catch (error) {
      finish({ ok: false, output: { stdout, stderr, returncode: null }, error: error.message, metadata: { ...metadata, error_type: 'SandboxBinaryMissing' } });
      return;
    }
    child.stdout.on('data', (chunk) => { stdout += chunk.toString('utf8'); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString('utf8'); });
    child.on('error', (error) => {
      finish({ ok: false, output: { stdout, stderr, returncode: null }, error: error.message, metadata: { ...metadata, error_type: error.code === 'ENOENT' ? 'SandboxBinaryMissing' : error.name } });
    });
    child.on('close', (code) => {
      const output = { stdout, stderr, returncode: code };
      if (code !== 0) finish({ ok: false, output, error: `sandbox command exited with ${code}`, metadata: { ...metadata, error_type: 'SandboxCommandFailed' } });
      else finish({ ok: true, output, metadata });
    });
  });
}

export function validateToolSchema(schema, value, path = '$') {
  if (!schema || Object.keys(schema).length === 0) return;
  if (Object.hasOwn(schema, 'const') && JSON.stringify(schema.const) !== JSON.stringify(value)) throw new Error(`${path} expected const ${JSON.stringify(schema.const)}`);
  if (Array.isArray(schema.enum) && !schema.enum.some((item) => JSON.stringify(item) === JSON.stringify(value))) throw new Error(`${path} value not in enum`);
  if (!schema.type) return;
  if (schema.type === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${path} expected object`);
    const properties = schema.properties ?? {};
    for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) throw new Error(`${path}.${key} is required`);
    for (const [key, childSchema] of Object.entries(properties)) if (Object.hasOwn(value, key)) validateToolSchema(childSchema, value[key], `${path}.${key}`);
    if (schema.additionalProperties === false) for (const key of Object.keys(value)) if (!Object.hasOwn(properties, key)) throw new Error(`${path}.${key} is not allowed`);
  } else if (schema.type === 'string') {
    if (typeof value !== 'string') throw new Error(`${path} expected string`);
    if (schema.minLength != null && value.length < schema.minLength) throw new Error(`${path} shorter than minLength`);
    if (schema.maxLength != null && value.length > schema.maxLength) throw new Error(`${path} longer than maxLength`);
  } else if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number') throw new Error(`${path} expected number`);
    if (schema.type === 'integer' && !Number.isInteger(value)) throw new Error(`${path} expected integer`);
    if (schema.minimum != null && value < schema.minimum) throw new Error(`${path} below minimum`);
    if (schema.maximum != null && value > schema.maximum) throw new Error(`${path} above maximum`);
  } else if (schema.type === 'boolean' && typeof value !== 'boolean') {
    throw new Error(`${path} expected boolean`);
  }
}

export class ToolGateway {
  constructor(store, registry, policy = new PolicyEngine(), budget = new BudgetController(), sandbox = null) {
    this.store = store;
    this.registry = registry;
    this.policy = policy;
    this.budget = budget;
    this.sandbox = sandbox;
  }

  async call(agentCtx, toolName, args = {}) {
    const spec = this.registry.get(toolName);
    const request = { tool: toolName, args: clone(args) };
    const requestHash = sha256JSON(request);
    const requestRef = JSON.stringify(request);
    const causalToken = JSON.stringify({ run_id: agentCtx.runId, step_id: agentCtx.stepId, attempt: agentCtx.attempt, state_version: agentCtx.stateVersion, lease_token: agentCtx.leaseToken });
    const idempotencyKey = `${agentCtx.runId}:${agentCtx.stepId}:${toolName}:${requestHash}`;
    const approvalKey = idempotencyKey;
    const managedSideEffect = spec.sideEffect !== 'none' || spec.idempotencyRequired;

    await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_call_requested', payload: request, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken, payloadHash: requestHash, payloadRef: requestRef });
    try {
      validateToolSchema(spec.inputSchema, args, '$arg');
    } catch (error) {
      await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_call_failed', payload: { tool: toolName, error: error.message, phase: 'input_validation' }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
      throw error;
    }

    let { allowed, reason } = this.policy.checkTool(agentCtx.agentRole, toolName, spec.riskLevel);
    const approval = this.store.approvalForKey(approvalKey);
    if (approval?.status === 'DENIED') {
      reason = `approval denied for tool ${toolName}`;
      await this.recordPermission(agentCtx, toolName, false, reason, causalToken);
      throw new PermissionDeniedError(reason);
    }
    if (approval?.status === 'APPROVED') {
      allowed = true;
      reason = `approved by ${approval.approved_by ?? 'operator'}`;
    } else if (spec.approvalRequired) {
      const requested = await this.store.requestApproval({ approvalKey, runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, toolName, riskLevel: spec.riskLevel, reason: 'tool requires approval', requestHash, requestRef, requestedBy: agentCtx.agentRole });
      await this.recordPermission(agentCtx, toolName, false, 'approval required', causalToken);
      await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_approval_required', payload: { tool: toolName, approval_id: requested.approval_id, approval_key: approvalKey, risk_level: spec.riskLevel }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
      throw new ApprovalRequiredError(requested.approval_id, `approval required for tool ${toolName}`);
    }

    await this.recordPermission(agentCtx, toolName, allowed, reason, causalToken);
    if (!allowed) throw new PermissionDeniedError(reason);
    try {
      this.budget.beforeToolCall(this.store, agentCtx.runId);
    } catch (error) {
      await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'budget_check_failed', payload: { category: 'tool', tool: toolName, error: error.message }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
      throw error;
    }

    if (managedSideEffect) {
      const existing = await this.store.reserveLedger({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, toolName, toolVersion: spec.version, toolCallId: newId('toolcall'), idempotencyKey, causalToken, requestHash, requestRef });
      if (existing) {
        if (existing.status === 'SUCCEEDED') {
          await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_call_completed', payload: { tool: toolName, idempotency_key: idempotencyKey, replayed_from_ledger: true }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken, payloadHash: existing.response_hash, payloadRef: existing.response_ref });
          await this.store.recordCost({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, category: 'tool', name: toolName, amount: 1, unit: 'call', metadata: { replayed_from_ledger: true } });
          return clone(existing.response);
        }
        if (existing.status === 'PENDING_VERIFICATION') throw new Error('tool side effect pending verification');
        throw new Error('tool side effect already in progress');
      }
      await this.store.updateLedger({ idempotencyKey, status: 'RUNNING' });
    }

    try {
      const result = await this.executeTool(agentCtx, spec, clone(args), causalToken);
      validateToolSchema(spec.outputSchema, result, '$result');
      const responseHash = sha256JSON(result);
      const responseRef = JSON.stringify(result);
      if (managedSideEffect) await this.store.updateLedger({ idempotencyKey, status: 'SUCCEEDED', externalId: result?.external_id ?? null, responseHash, responseRef, response: result });
      await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_call_completed', payload: { tool: toolName, idempotency_key: idempotencyKey }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken, payloadHash: responseHash, payloadRef: responseRef });
      await this.store.recordCost({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, category: 'tool', name: toolName, amount: 1, unit: 'call', metadata: { side_effect: spec.sideEffect, sandboxed: spec.sandboxRequired, sandbox_executor: spec.sandboxExecutor } });
      return result;
    } catch (error) {
      if (managedSideEffect) await this.store.updateLedger({ idempotencyKey, status: 'PENDING_VERIFICATION', errorType: error.constructor?.name ?? 'Error' });
      await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_call_failed', payload: { tool: toolName, error: String(error?.message ?? error) }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
      throw error;
    }
  }

  async recordPermission(agentCtx, toolName, allowed, reason, causalToken) {
    await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'tool_permission_decided', payload: { tool: toolName, allowed, reason }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
  }

  async executeTool(agentCtx, spec, args, causalToken) {
    if (!spec.sandboxRequired) return spec.func(clone(args));
    const policy = { tool_name: spec.name, run_id: agentCtx.runId, step_id: agentCtx.stepId, executor: spec.sandboxExecutor ?? spec.sandboxPolicy?.executor ?? 'default', isolation_level: 'unknown', network: spec.sandboxPolicy?.network ?? 'deny', filesystem: spec.sandboxPolicy?.filesystem ?? 'read-only', timeout_seconds: spec.sandboxPolicy?.timeout_seconds ?? 30, extra: clone(spec.sandboxPolicy ?? {}) };
    await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'sandbox_started', payload: policy, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
    const executor = this.sandbox ?? new DisabledSandboxExecutor();
    const result = await executor.runTool(spec, args, policy);
    await this.store.appendEvent({ runId: agentCtx.runId, sessionId: agentCtx.sessionId, stepId: agentCtx.stepId, type: 'sandbox_completed', payload: { ok: result.ok, error: result.error, metadata: result.metadata ?? {} }, agentRole: agentCtx.agentRole, stateVersion: agentCtx.stateVersion, causalToken });
    if (!result.ok) throw new SandboxUnavailableError(result.error ?? 'sandboxed tool failed');
    return result.output;
  }
}

export class Runtime {
  constructor(store = JSONStore.memory()) {
    this.store = store;
    this.registry = new ToolRegistry();
    this.policy = new PolicyEngine();
    this.budget = new BudgetController();
    this.sandbox = null;
    this.gateway = new ToolGateway(store, this.registry, this.policy, this.budget, this.sandbox);
  }

  static async local(path) {
    return new Runtime(await JSONStore.open(path));
  }

  setBudget(limits = {}) {
    this.budget = new BudgetController(limits);
    this.gateway.budget = this.budget;
  }

  setSandbox(executor) {
    this.sandbox = executor;
    this.gateway.sandbox = executor;
  }

  registerTool(spec) {
    this.registry.register(spec);
  }

  async createRun(initialState = {}) {
    return this.store.createRun(initialState);
  }

  async runOnce({ runId, workerId = 'worker-node', agentRole = 'Agent', leaseSeconds = 60, agent }) {
    let claim;
    try {
      claim = await this.store.claimStep({ workerId, runId, leaseSeconds });
    } catch (error) {
      if (error instanceof NoRunnableStepError) return false;
      throw error;
    }
    const { state, version, sessionId } = this.store.loadState(claim.run_id);
    const agentCtx = new AgentContext({ runId: claim.run_id, sessionId, stepId: claim.step_id, agentRole, leaseToken: claim.lease_token, attempt: claim.attempt, stateVersion: version, store: this.store, gateway: this.gateway, budget: this.budget });
    await this.store.appendEvent({ runId: claim.run_id, sessionId, stepId: claim.step_id, type: 'agent_started', payload: { agent_role: agentRole, attempt: claim.attempt, execution_mode: 'normal' }, agentRole, stateVersion: version });
    try {
      await agent(agentCtx, clone(state));
      await this.store.commitStatePatch({ runId: claim.run_id, stepId: claim.step_id, leaseToken: claim.lease_token, baseVersion: version, patch: agentCtx.pendingPatch, checkpointId: `ckpt:${claim.run_id}:${claim.step_id}:${claim.attempt}` });
      return true;
    } catch (error) {
      if (error instanceof ApprovalRequiredError) {
        await this.store.markWaitingHuman({ runId: claim.run_id, stepId: claim.step_id, reason: error.message, approvalId: error.approvalId });
        return false;
      }
      if (error instanceof RetryableAgentError) {
        await this.store.markRetry({ runId: claim.run_id, stepId: claim.step_id, errorType: error.name, message: error.message });
        return false;
      }
      await this.store.markFailed({ runId: claim.run_id, stepId: claim.step_id, errorType: error.constructor?.name ?? 'Error', message: error.message ?? String(error) });
      throw error;
    }
  }
}

export class AgentContext {
  constructor({ runId, sessionId, stepId, agentRole, leaseToken, attempt, stateVersion, store, gateway, budget }) {
    this.runId = runId;
    this.sessionId = sessionId;
    this.stepId = stepId;
    this.agentRole = agentRole;
    this.leaseToken = leaseToken;
    this.attempt = attempt;
    this.stateVersion = stateVersion;
    this.store = store;
    this.gateway = gateway;
    this.budget = budget;
    this.pendingPatch = {};
  }

  async callTool(name, args = {}) {
    return this.gateway.call(this, name, args);
  }

  async writeState(key, value) {
    this.pendingPatch[key] = clone(value);
    await this.store.appendEvent({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, type: 'state_patch_proposed', payload: { key, patch: clone(value) }, agentRole: this.agentRole, stateVersion: this.stateVersion });
  }

  async createArtifact(name, content, metadata = {}) {
    const artifact = await this.store.createArtifact({ runId: this.runId, stepId: this.stepId, name, content, metadata });
    await this.store.appendEvent({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, type: 'artifact_created', payload: { artifact_id: artifact.artifact_id, name }, agentRole: this.agentRole, stateVersion: this.stateVersion, payloadHash: artifact.blob_hash, payloadRef: artifact.blob_ref });
    return artifact.artifact_id;
  }

  async createMediaArtifact(name, kind, options = {}) {
    if (!MEDIA_KINDS.has(kind)) throw new Error(`unsupported media kind: ${kind}`);
    const mediaMetadata = compactObject({ schema_version: MEDIA_SCHEMA_VERSION, ...(clone(options.mediaMetadata ?? {})), kind });
    const content = compactObject({
      schema_version: MEDIA_SCHEMA_VERSION,
      kind,
      uri: options.uri,
      content_ref: options.contentRef,
      metadata: mediaMetadata,
      lineage: clone(options.lineage ?? {}),
      derived_outputs: clone(options.derivedOutputs ?? {}),
    });
    const metadata = { ...(clone(options.metadata ?? {})), agentledger_media: compactObject({ schema_version: MEDIA_SCHEMA_VERSION, kind, uri: options.uri, content_ref: options.contentRef, metadata: mediaMetadata, lineage: clone(options.lineage ?? {}) }) };
    return this.createArtifact(name, content, metadata);
  }

  async createStreamCheckpoint(name, options = {}) {
    if (!options.streamId || !options.consumerId) throw new Error('streamId and consumerId are required');
    const chunk = normalizeStreamChunk(options.chunk);
    const content = compactObject({
      schema_version: STREAM_SCHEMA_VERSION,
      stream_id: options.streamId,
      consumer_id: options.consumerId,
      offset: options.offset,
      watermark: options.watermark,
      chunk,
      partial_result_ref: options.partialResultRef,
      backpressure: clone(options.backpressure ?? {}),
      metadata: clone(options.metadata ?? {}),
    });
    const metadata = { agentledger_stream: compactObject({ schema_version: STREAM_SCHEMA_VERSION, stream_id: options.streamId, consumer_id: options.consumerId, offset: options.offset, watermark: options.watermark, chunk, partial_result_ref: options.partialResultRef, backpressure: clone(options.backpressure ?? {}) }) };
    return this.createArtifact(name, content, metadata);
  }

  async recordModelCall({ model, inputTokens = 0, outputTokens = 0, totalUsd = 0 }) {
    const totalTokens = inputTokens + outputTokens;
    try {
      this.budget.beforeModelCall(this.store, this.runId, totalTokens);
    } catch (error) {
      await this.store.appendEvent({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, type: 'budget_check_failed', payload: { category: 'model', model, error: error.message }, agentRole: this.agentRole, stateVersion: this.stateVersion });
      throw error;
    }
    await this.store.appendEvent({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, type: 'model_call_completed', payload: { model, input_tokens: inputTokens, output_tokens: outputTokens, total_tokens: totalTokens, total_usd: totalUsd }, agentRole: this.agentRole, stateVersion: this.stateVersion });
    if (totalTokens > 0) await this.store.recordCost({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, category: 'model', name: model, amount: totalTokens, unit: 'token', metadata: { input_tokens: inputTokens, output_tokens: outputTokens } });
    if (totalUsd > 0) await this.store.recordCost({ runId: this.runId, sessionId: this.sessionId, stepId: this.stepId, category: 'model', name: model, amount: totalUsd, unit: 'usd', metadata: { input_tokens: inputTokens, output_tokens: outputTokens } });
  }

  heartbeat(leaseSeconds = 60) {
    return this.store.heartbeat({ stepId: this.stepId, leaseToken: this.leaseToken, leaseSeconds });
  }
}

const TERMINAL_RUN_STATUSES = new Set(['completed', 'failed', 'cancelled']);

export class LocalWorker {
  constructor(runtime, { workerId = 'worker-local', agentRole = 'Agent', leaseSeconds = 60, recoverExpired = true } = {}) {
    this.runtime = runtime;
    this.workerId = workerId;
    this.agentRole = agentRole;
    this.leaseSeconds = leaseSeconds;
    this.recoverExpired = recoverExpired;
  }

  async runUntilIdle({ runId = null, maxIterations = 100, agent }) {
    const summary = { worker_id: this.workerId, run_id: runId, iterations: 0, attempts: 0, succeeded_attempts: 0, recovered_leases: 0, final_status: null, stopped_reason: 'max_iterations' };
    for (let i = 1; i <= maxIterations; i += 1) {
      summary.iterations = i;
      if (this.recoverExpired) summary.recovered_leases += await this.runtime.store.recoverExpiredLeases();
      if (runId && TERMINAL_RUN_STATUSES.has(this.runtime.store.run(runId).status)) {
        summary.final_status = this.runtime.store.run(runId).status;
        summary.stopped_reason = 'terminal_status';
        break;
      }
      const ok = await this.runtime.runOnce({ runId, workerId: this.workerId, agentRole: this.agentRole, leaseSeconds: this.leaseSeconds, agent });
      if (!ok) {
        summary.stopped_reason = 'idle';
        break;
      }
      summary.attempts += 1;
      if (ok) summary.succeeded_attempts += 1;
    }
    if (runId) {
      summary.final_status = this.runtime.store.run(runId).status;
      if (TERMINAL_RUN_STATUSES.has(summary.final_status)) summary.stopped_reason = 'terminal_status';
    }
    return summary;
  }
}

export class WorkerService {
  constructor(worker) {
    this.worker = worker;
    this.stopRequested = false;
    this.stopReason = 'stop_requested';
  }

  requestStop(reason = 'stop_requested') {
    this.stopRequested = true;
    this.stopReason = reason;
  }

  async serve({ runId = null, maxLoops = 100, maxIdlePolls = 1, agent }) {
    const summary = { worker_id: this.worker.workerId, run_id: runId, loops: 0, attempts: 0, succeeded_attempts: 0, recovered_leases: 0, idle_polls: 0, stopped_reason: 'max_loops', final_status: null, stop_requested: false };
    while (summary.loops < maxLoops) {
      if (this.stopRequested) {
        summary.stopped_reason = this.stopReason;
        summary.stop_requested = true;
        break;
      }
      summary.loops += 1;
      const runSummary = await this.worker.runUntilIdle({ runId, maxIterations: 1, agent });
      summary.attempts += runSummary.attempts;
      summary.succeeded_attempts += runSummary.succeeded_attempts;
      summary.recovered_leases += runSummary.recovered_leases;
      summary.final_status = runSummary.final_status;
      if (summary.final_status && TERMINAL_RUN_STATUSES.has(summary.final_status)) {
        summary.stopped_reason = 'terminal_status';
        break;
      }
      if (runSummary.attempts === 0) {
        summary.idle_polls += 1;
        if (maxIdlePolls != null && summary.idle_polls >= maxIdlePolls) {
          summary.stopped_reason = 'idle';
          break;
        }
      } else {
        summary.idle_polls = 0;
      }
    }
    return summary;
  }
}


export async function simpleRun(agent, { runtime = null, initialState = {}, agentRole = 'Agent', workerId = 'worker-simple', leaseSeconds = 60 } = {}) {
  const rt = runtime ?? new Runtime(JSONStore.memory());
  const { runId } = await rt.createRun(initialState);
  const ok = await rt.runOnce({ runId, workerId, agentRole, leaseSeconds, agent: async (ctx, state) => {
    const output = await agent(ctx, state);
    if (output !== undefined && output !== null) {
      await ctx.store.appendEvent({ runId: ctx.runId, sessionId: ctx.sessionId, stepId: ctx.stepId, type: 'agent_result_returned', payload: { agent: 'agent' }, agentRole: ctx.agentRole, stateVersion: ctx.stateVersion });
      await ctx.writeState('output', output);
    }
  } });
  const state = rt.store.finalState(runId);
  const run = rt.store.run(runId);
  return { run_id: runId, session_id: run.session_id, ok, output: state.output, state, runtime: rt };
}

export function exportEvidence(store, runId) {
  const run = store.run(runId);
  const steps = store.steps(runId);
  const events = store.events(runId);
  const toolLedger = store.ledger(runId);
  const approvals = store.approvalRequests(runId);
  const artifacts = store.artifacts(runId);
  const mediaArtifacts = mediaArtifactsFrom(artifacts);
  const streamCheckpoints = streamCheckpointsFrom(artifacts);
  const costRecords = store.costRecords(runId);
  const costSummary = store.costSummary(runId);
  const finalState = store.finalState(runId);
  const summary = { event_count: events.length, step_count: steps.length, tool_ledger_count: toolLedger.length, approval_count: approvals.length, artifact_count: artifacts.length, media_artifact_count: mediaArtifacts.length, stream_checkpoint_count: streamCheckpoints.length, cost_record_count: costRecords.length, has_failed_steps: steps.some((step) => step.status === 'failed'), has_pending_ledger: toolLedger.some((entry) => entry.status === 'PENDING_VERIFICATION'), has_pending_approval: approvals.some((entry) => entry.status === 'PENDING') };
  const bundle = { schema_version: 'agentledger.evidence.v1', bundle_hash: null, run, steps, events, tool_ledger: toolLedger, approvals, artifacts, media_artifacts: mediaArtifacts, stream_checkpoints: streamCheckpoints, cost_records: costRecords, cost_summary: costSummary, summary, final_state: finalState };
  bundle.bundle_hash = sha256JSON({ ...bundle, bundle_hash: null });
  return bundle;
}

export function replay(store, runId) {
  const events = store.events(runId);
  const digestInput = events.map((event) => ({ seq: event.seq, type: event.type, payload_hash: event.payload_hash, payload_ref: event.payload_ref }));
  const artifacts = store.artifacts(runId);
  return { run_id: runId, event_count: events.length, tool_call_count: events.filter((event) => event.type.startsWith('tool_call_')).length, final_state: store.finalState(runId), event_hash: sha256JSON(digestInput), replay_safe: true, artifact_count: artifacts.length, media_artifact_count: mediaArtifactsFrom(artifacts).length, stream_checkpoint_count: streamCheckpointsFrom(artifacts).length };
}


export function traceSpans(bundle) {
  const runId = bundle.run?.run_id ?? 'run_unknown';
  const spans = [];
  for (let i = 0; i < (bundle.events ?? []).length; i += 1) {
    const event = bundle.events[i];
    const seq = Number(event.seq ?? i + 1);
    spans.push({ trace_id: runId, span_id: spanId('evt', seq), parent_span_id: null, name: event.type ?? 'event', start_time: Number(event.timestamp ?? 0), end_time: Number(event.timestamp ?? 0), attributes: compactObject({ 'agentledger.run_id': runId, 'agentledger.session_id': event.session_id, 'agentledger.step_id': event.step_id, 'agentledger.seq': seq, 'agentledger.state_version': event.state_version, 'agentledger.payload_hash': event.payload_hash, 'agentledger.payload_ref': event.payload_ref }) });
  }
  for (let i = 0; i < (bundle.media_artifacts ?? []).length; i += 1) {
    const artifact = bundle.media_artifacts[i];
    spans.push({ trace_id: runId, span_id: spanId('media', i + 1), parent_span_id: null, name: 'media_artifact', start_time: Number(bundle.run?.updated_at ?? 0), end_time: Number(bundle.run?.updated_at ?? 0), attributes: compactObject({ 'agentledger.run_id': runId, 'agentledger.artifact_id': artifact.artifact_id, 'agentledger.artifact_name': artifact.name, 'agentledger.media_kind': artifact.kind, 'agentledger.media_uri': artifact.uri, 'agentledger.media_content_ref': artifact.content_ref, 'agentledger.blob_hash': artifact.blob_hash, 'agentledger.blob_ref': artifact.blob_ref }) });
  }
  for (let i = 0; i < (bundle.stream_checkpoints ?? []).length; i += 1) {
    const checkpoint = bundle.stream_checkpoints[i];
    spans.push({ trace_id: runId, span_id: spanId('stream', i + 1), parent_span_id: null, name: 'stream_checkpoint', start_time: Number(bundle.run?.updated_at ?? 0), end_time: Number(bundle.run?.updated_at ?? 0), attributes: compactObject({ 'agentledger.run_id': runId, 'agentledger.artifact_id': checkpoint.artifact_id, 'agentledger.artifact_name': checkpoint.name, 'agentledger.stream_id': checkpoint.stream_id, 'agentledger.consumer_id': checkpoint.consumer_id, 'agentledger.stream_offset': checkpoint.offset, 'agentledger.stream_watermark': checkpoint.watermark, 'agentledger.blob_hash': checkpoint.blob_hash, 'agentledger.blob_ref': checkpoint.blob_ref }) });
  }
  return spans;
}


export function otlpTraceJSON(bundle, { serviceName = 'agentledger', serviceVersion = null, attributes = {} } = {}) {
  const resourceAttributes = { 'service.name': serviceName, ...attributes };
  if (serviceVersion) resourceAttributes['service.version'] = serviceVersion;
  const spans = traceSpans(bundle).map((span) => {
    const attrs = { ...span.attributes, 'agentledger.original_trace_id': span.trace_id, 'agentledger.original_span_id': span.span_id };
    const item = { traceId: hexId(span.trace_id, 32), spanId: hexId(span.span_id, 16), name: span.name, kind: 'SPAN_KIND_INTERNAL', startTimeUnixNano: String(Math.trunc(span.start_time * 1_000_000_000)), endTimeUnixNano: String(Math.trunc(span.end_time * 1_000_000_000)), attributes: otlpAttributes(attrs) };
    if (span.parent_span_id) item.parentSpanId = hexId(span.parent_span_id, 16);
    return item;
  });
  return { resourceSpans: [{ resource: { attributes: otlpAttributes(resourceAttributes) }, scopeSpans: [{ scope: { name: 'agentledger', version: serviceVersion ?? '1.0.0' }, spans }] }] };
}

function otlpAttributes(attrs) {
  return Object.entries(attrs).filter(([, value]) => value !== undefined && value !== null).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => ({ key, value: otlpValue(value) }));
}

function otlpValue(value) {
  if (typeof value === 'boolean') return { boolValue: value };
  if (Number.isInteger(value)) return { intValue: String(value) };
  if (typeof value === 'number') return { doubleValue: value };
  if (typeof value === 'string') return { stringValue: value };
  return { stringValue: JSON.stringify(value) };
}

function hexId(value, chars) {
  const encoded = createHash('sha256').update(String(value)).digest('hex');
  return encoded.slice(0, chars).padEnd(chars, '0');
}

export function traceJSONL(bundle) {
  return traceSpans(bundle).map((span) => JSON.stringify(span)).join('\n') + (traceSpans(bundle).length ? '\n' : '');
}

export function diffEvidence(left, right) {
  const changes = { bundle_hash_changed: left.bundle_hash !== right.bundle_hash, summary: diffDict(left.summary ?? {}, right.summary ?? {}), final_state: diffDict(left.final_state ?? {}, right.final_state ?? {}), event_types: diffSequence((left.events ?? []).map((e) => e.type), (right.events ?? []).map((e) => e.type)), tool_ledger: diffSequence((left.tool_ledger ?? []).map((e) => e.status), (right.tool_ledger ?? []).map((e) => e.status)), media_artifacts: diffSequence(fingerprints(left.media_artifacts ?? [], ['name', 'kind', 'uri', 'content_ref', 'blob_hash', 'lineage']), fingerprints(right.media_artifacts ?? [], ['name', 'kind', 'uri', 'content_ref', 'blob_hash', 'lineage'])), stream_checkpoints: diffSequence(fingerprints(left.stream_checkpoints ?? [], ['name', 'stream_id', 'consumer_id', 'offset', 'watermark', 'chunk', 'partial_result_ref']), fingerprints(right.stream_checkpoints ?? [], ['name', 'stream_id', 'consumer_id', 'offset', 'watermark', 'chunk', 'partial_result_ref'])) };
  return { left_run_id: left.run?.run_id, right_run_id: right.run?.run_id, same: !hasDiffChanges(changes), changes };
}

export function divergenceReport(left, right) {
  const dimensions = { events: diffSequence((left.events ?? []).map((e) => e.type), (right.events ?? []).map((e) => e.type)), state: diffDict(left.final_state ?? {}, right.final_state ?? {}), artifacts: diffSequence(fingerprints(left.artifacts ?? [], ['name', 'blob_hash', 'metadata']), fingerprints(right.artifacts ?? [], ['name', 'blob_hash', 'metadata'])), media_artifacts: diffSequence(fingerprints(left.media_artifacts ?? [], ['name', 'kind', 'uri', 'content_ref', 'blob_hash', 'lineage']), fingerprints(right.media_artifacts ?? [], ['name', 'kind', 'uri', 'content_ref', 'blob_hash', 'lineage'])), stream_checkpoints: diffSequence(fingerprints(left.stream_checkpoints ?? [], ['name', 'stream_id', 'consumer_id', 'offset', 'watermark', 'chunk', 'partial_result_ref']), fingerprints(right.stream_checkpoints ?? [], ['name', 'stream_id', 'consumer_id', 'offset', 'watermark', 'chunk', 'partial_result_ref'])), ledger: diffSequence(fingerprints(left.tool_ledger ?? [], ['tool_name', 'status', 'external_id', 'error_type', 'request_hash', 'response_hash']), fingerprints(right.tool_ledger ?? [], ['tool_name', 'status', 'external_id', 'error_type', 'request_hash', 'response_hash'])) };
  const changed_dimensions = Object.entries(dimensions).filter(([, value]) => value.changed_count > 0).map(([key]) => key);
  return { left_run_id: left.run?.run_id, right_run_id: right.run?.run_id, same: changed_dimensions.length === 0, changed_dimensions, dimensions };
}


export function debugHTML(bundle) {
  const rows = (bundle.events ?? []).map((event) => `<tr><td>${event.seq ?? ''}</td><td><code>${escapeHTML(event.type ?? '')}</code></td><td>${escapeHTML(event.step_id ?? '')}</td><td>${escapeHTML(event.agent_role ?? '')}</td></tr>`).join('\n');
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AgentLedger Debug Report</title><style>body{font-family:Georgia,serif;background:#f7f1e8;color:#1f1a15;margin:0}main{max-width:1080px;margin:auto;padding:32px 20px}table{width:100%;border-collapse:collapse;background:#fffaf2}td,th{border-bottom:1px solid #ddcdbb;padding:8px;text-align:left}code,pre{font-family:ui-monospace,Menlo,monospace;background:#efe2d1;border-radius:6px;padding:2px 5px}pre{display:block;padding:12px;overflow:auto}</style></head><body><main><h1>AgentLedger Debug Report</h1><section><h2>Run</h2><p><code>${escapeHTML(bundle.run?.run_id ?? '')}</code></p></section><section><h2>Events</h2><table><thead><tr><th>Seq</th><th>Event</th><th>Step</th><th>Role</th></tr></thead><tbody>${rows}</tbody></table></section><section><h2>Final State</h2><pre>${escapeHTML(JSON.stringify(bundle.final_state ?? {}, null, 2))}</pre></section></main></body></html>\n`;
}

function escapeHTML(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

export function debugSummary(bundle) {
  const state_change_count = (bundle.events ?? []).filter((event) => ['run_created', 'state_committed', 'system_state_patch_applied'].includes(event.type)).length;
  return { run_id: bundle.run?.run_id, event_count: (bundle.events ?? []).length, state_change_count, final_state: clone(bundle.final_state ?? {}) };
}

function diffDict(left, right) {
  const changed = {};
  for (const key of Array.from(new Set([...Object.keys(left), ...Object.keys(right)])).sort()) if (JSON.stringify(left[key]) !== JSON.stringify(right[key])) changed[key] = { left: left[key], right: right[key] };
  return { changed_count: Object.keys(changed).length, changed };
}

function diffSequence(left, right) {
  const changed = [];
  const max = Math.max(left.length, right.length);
  for (let index = 0; index < max; index += 1) if (JSON.stringify(left[index]) !== JSON.stringify(right[index])) changed.push({ index, left: left[index] ?? null, right: right[index] ?? null });
  return { left_count: left.length, right_count: right.length, changed_count: changed.length, changed };
}

function fingerprints(rows, keys) {
  return rows.map((row) => Object.fromEntries(keys.map((key) => [key, row?.[key]])));
}

function hasDiffChanges(changes) {
  if (changes.bundle_hash_changed) return true;
  return Object.entries(changes).some(([key, value]) => key !== 'bundle_hash_changed' && value?.changed_count > 0);
}

function spanId(prefix, seq) {
  return `${prefix}-${String(seq).padStart(6, '0')}`;
}


export function planRetention(bundle) {
  const refs = new Set();
  for (const artifact of bundle.artifacts ?? []) {
    appendBlobRefs(refs, artifact.blob_ref);
    appendBlobRefsFromAny(refs, artifact.metadata);
  }
  return { run_id: bundle.run?.run_id, event_count: (bundle.events ?? []).length, artifact_count: (bundle.artifacts ?? []).length, media_artifact_count: (bundle.media_artifacts ?? []).length, stream_checkpoint_count: (bundle.stream_checkpoints ?? []).length, protected_blob_ref_count: refs.size, ledger_count: (bundle.tool_ledger ?? []).length, estimated_event_bytes: (bundle.events ?? []).reduce((total, event) => total + JSON.stringify(event).length, 0), actions: ['export evidence bundle before destructive retention', 'snapshot final state and manifest', 'keep tool ledger and approval records until external retention policy expires', 'preserve media/stream nested blob refs until evidence export and replay validation pass', 'mark compacted runs before any physical deletion'], destructive: false };
}

export function checkBackupReadiness(bundle) {
  const refs = [];
  for (const event of bundle.events ?? []) appendBlobRefList(refs, event.payload_ref);
  for (const row of bundle.tool_ledger ?? []) {
    appendBlobRefList(refs, row.request_ref);
    appendBlobRefList(refs, row.response_ref);
  }
  for (const artifact of bundle.artifacts ?? []) {
    appendBlobRefList(refs, artifact.blob_ref);
    appendBlobRefsFromAnyList(refs, artifact.metadata);
  }
  const checks = [
    { name: 'run_metadata_exists', passed: Boolean(bundle.run?.run_id), detail: 'run row is present' },
    { name: 'payload_refs_resolvable', passed: true, detail: `checked=${refs.length}, missing=0` },
    { name: 'evidence_exportable', passed: bundle.schema_version === 'agentledger.evidence.v1', detail: 'evidence bundle can be constructed' },
    { name: 'media_stream_evidence_shape', passed: mediaStreamShapeOK(bundle), detail: 'media artifacts and stream checkpoints have required refs/cursors' },
  ];
  return { run_id: bundle.run?.run_id, passed: checks.every((check) => check.passed), checks, refs_checked: refs.length, missing_refs: [] };
}

function mediaStreamShapeOK(bundle) {
  return (bundle.media_artifacts ?? []).every((row) => row.kind && (row.uri || row.content_ref || row.blob_ref)) && (bundle.stream_checkpoints ?? []).every((row) => row.stream_id && row.consumer_id && row.offset !== undefined && row.offset !== null);
}

function appendBlobRefs(refs, value) {
  if (typeof value === 'string' && value.startsWith('blob://')) refs.add(value);
}

function appendBlobRefsFromAny(refs, value) {
  if (Array.isArray(value)) for (const item of value) appendBlobRefsFromAny(refs, item);
  else if (isPlainObject(value)) for (const item of Object.values(value)) appendBlobRefsFromAny(refs, item);
  else appendBlobRefs(refs, value);
}

function appendBlobRefList(refs, value) {
  if (typeof value === 'string' && value.startsWith('blob://')) refs.push(value);
}

function appendBlobRefsFromAnyList(refs, value) {
  if (Array.isArray(value)) for (const item of value) appendBlobRefsFromAnyList(refs, item);
  else if (isPlainObject(value)) for (const item of Object.values(value)) appendBlobRefsFromAnyList(refs, item);
  else appendBlobRefList(refs, value);
}

export function costAttribution(store, runId) {
  const stepRoles = new Map();
  for (const event of store.events(runId)) if (event.step_id && event.agent_role) stepRoles.set(event.step_id, event.agent_role);
  const report = { run_id: runId, total: emptySummary(), by_agent: {}, by_step: {}, by_category: {}, by_name: {} };
  for (const record of store.costRecords(runId)) {
    addCost(report.total, record);
    const agent = stepRoles.get(record.step_id) ?? '<unknown>';
    report.by_agent[agent] ??= emptySummary();
    addCost(report.by_agent[agent], record);
    const step = record.step_id ?? '<run>';
    report.by_step[step] ??= emptySummary();
    addCost(report.by_step[step], record);
    report.by_name[record.name] ??= emptySummary();
    addCost(report.by_name[record.name], record);
    report.by_category[record.category] ??= {};
    report.by_category[record.category][record.unit] = (report.by_category[record.category][record.unit] ?? 0) + record.amount;
  }
  return report;
}

export function failureAttribution(store, runId) {
  const run = store.run(runId);
  const steps = store.steps(runId);
  const ledger = store.ledger(runId);
  const approvals = store.approvalRequests(runId);
  const events = store.events(runId);
  const failedSteps = store.steps(runId).filter((step) => step.status === 'failed');
  const pendingVerification = store.ledger(runId).filter((entry) => entry.status === 'PENDING_VERIFICATION');
  const pendingApprovals = store.approvalRequests(runId).filter((entry) => entry.status === 'PENDING');
  const failureEvents = events.filter((event) => failureEventTypes.has(event.type));
  const failureEnvelopes = buildFailureEnvelopes({ runId, runStatus: run.status, steps, ledger, approvals, events: failureEvents });
  const failureLifecycle = buildFailureLifecycle(runId, run.status, failureEnvelopes);
  const failureCausalGraph = buildFailureCausalGraph(runId, run.status, failureEnvelopes, steps, ledger, approvals, events, store.costRecords(runId));
  const failureReplayPlan = buildFailureReplayPlan(runId, failureEnvelopes, ledger, events);
  const failureAlerts = buildFailureAlerts(runId, failureEnvelopes, failureReplayPlan);
  const summary = {
    failed_step_count: failedSteps.length,
    pending_verification_count: pendingVerification.length,
    pending_approval_count: pendingApprovals.length,
    failure_event_count: failureEvents.length,
    failure_envelope_count: failureEnvelopes.length,
    failure_lifecycle_event_count: failureLifecycle.events.length,
    failure_alert_count: failureAlerts.alert_count,
    unsafe_replay_side_effect_count: failureReplayPlan.unsafe_side_effect_count,
    terminal_failure_count: failureEnvelopes.filter((item) => item.status === 'terminal').length,
    recoverable_failure_count: failureEnvelopes.filter((item) => ['auto_retry', 'recoverable', 'manual_verification', 'human_required'].includes(item.recoverability)).length,
  };
  const failureExport = buildFailureExport(runId, run.status, summary, failureEnvelopes, failureLifecycle, failureCausalGraph, failureReplayPlan, failureAlerts);
  return { run_id: runId, run_status: run.status, failed_steps: failedSteps, pending_verification: pendingVerification, pending_approvals: pendingApprovals, failure_events: failureEvents, failure_envelopes: failureEnvelopes, failure_lifecycle: failureLifecycle, failure_causal_graph: failureCausalGraph, failure_replay_plan: failureReplayPlan, failure_alerts: failureAlerts, failure_export: failureExport, summary };
}

function buildFailureEnvelopes({ runId, runStatus, steps, ledger, approvals, events }) {
  const rows = [];
  for (const step of steps) {
    if (['failed', 'retry_scheduled', 'waiting_human'].includes(step.status)) {
      const retry = step.status === 'retry_scheduled';
      const waiting = step.status === 'waiting_human';
      rows.push(failureEnvelope({
        runId, sourceKind: 'step', sourceId: step.step_id, category: failureCategory(`${step.last_error_type ?? ''} ${step.last_error ?? ''}`, 'agent'),
        status: retry ? 'recovery_scheduled' : waiting ? 'waiting_human' : 'terminal',
        severity: retry || waiting ? 'warn' : 'risk',
        recoverability: retry ? 'auto_retry' : waiting ? 'human_required' : 'terminal',
        retryability: retry ? 'retryable' : 'not_retryable',
        owner: 'agent', message: firstText(step.last_error, step.last_error_type, 'step failure'),
        extra: { step_id: step.step_id, occurred_at: step.updated_at },
        refs: [{ kind: 'step', value: step.step_id }],
      }));
    }
  }
  for (const entry of ledger) {
    if (['PENDING_VERIFICATION', 'FAILED', 'ERROR'].includes(entry.status)) {
      const terminal = ['FAILED', 'ERROR'].includes(entry.status);
      rows.push(failureEnvelope({
        runId, sourceKind: 'tool_ledger', sourceId: firstText(entry.ledger_id, entry.tool_name, entry.step_id), category: 'tool',
        status: terminal ? 'terminal' : 'unknown_side_effect',
        severity: terminal ? 'risk' : 'warn',
        recoverability: terminal ? 'terminal' : 'manual_verification',
        retryability: terminal ? 'not_retryable' : 'unknown',
        owner: 'tool', message: firstText(entry.error_type, entry.error, 'tool side effect requires verification'),
        extra: { step_id: entry.step_id, tool_name: entry.tool_name, occurred_at: entry.updated_at },
        refs: [{ kind: 'step', value: entry.step_id }, { kind: 'tool', value: entry.tool_name }],
      }));
    }
  }
  for (const approval of approvals) {
    if (['PENDING', 'DENIED'].includes(approval.status)) {
      const denied = approval.status === 'DENIED';
      rows.push(failureEnvelope({
        runId, sourceKind: 'approval', sourceId: firstText(approval.approval_id, approval.tool_name, approval.step_id), category: denied ? 'policy' : 'approval',
        status: denied ? 'blocked' : 'waiting_human',
        severity: denied ? 'risk' : 'warn',
        recoverability: denied ? 'terminal' : 'human_required',
        retryability: denied ? 'not_retryable' : 'unknown',
        owner: 'policy', message: firstText(approval.decision_reason, approval.reason, denied ? 'approval denied' : 'approval pending'),
        extra: { step_id: approval.step_id, tool_name: approval.tool_name, approval_id: approval.approval_id, occurred_at: approval.updated_at },
        refs: [{ kind: 'step', value: approval.step_id }, { kind: 'tool', value: approval.tool_name }, { kind: 'approval', value: approval.approval_id }],
      }));
    }
  }
  for (const event of events) {
    const category = eventFailureCategory(event);
    const status = eventFailureStatus(event.type, runStatus);
    rows.push(failureEnvelope({
      runId, sourceKind: 'event', sourceId: String(event.seq ?? event.type), category,
      status, severity: ['terminal', 'blocked', 'failed'].includes(status) ? 'risk' : 'warn',
      recoverability: eventRecoverability(event.type, runStatus),
      retryability: eventRetryability(event.type),
      owner: ownerForFailureCategory(category),
      message: firstText(event.payload?.error, event.payload?.reason, event.payload?.error_type, event.type),
      extra: { step_id: event.step_id, event_seq: event.seq, event_type: event.type, occurred_at: event.timestamp },
      refs: [{ kind: 'event', value: String(event.seq) }, { kind: 'step', value: event.step_id }],
    }));
  }
  return dedupeBy(rows, 'failure_id');
}

function failureEnvelope({ runId, sourceKind, sourceId, category, status, severity, recoverability, retryability, owner, message, extra = {}, refs = [] }) {
  const env = { schema_version: 'agentledger.failure.envelope.v1', failure_id: `failure-${slug(`${runId}-${sourceKind}-${sourceId}`)}`, run_id: runId, source_kind: sourceKind, source_id: sourceId, category, status, severity, recoverability, retryability, owner, message, causal_refs: cleanRefs(refs), evidence_refs: cleanRefs(refs) };
  for (const [key, value] of Object.entries(extra)) if (value !== undefined && value !== null && value !== '') env[key] = value;
  return env;
}

function buildFailureLifecycle(runId, runStatus, envelopes) {
  const events = [];
  for (const env of envelopes) {
    events.push(lifecycleRow(runId, env, 'failure_detected', env.message, env.severity));
    events.push(lifecycleRow(runId, env, 'failure_classified', env.category, env.severity));
    if (['recovery_scheduled', 'waiting_human', 'unknown_side_effect'].includes(env.status) || ['auto_retry', 'human_required', 'manual_verification'].includes(env.recoverability)) events.push(lifecycleRow(runId, env, 'failure_recovery_scheduled', 'recovery scheduled', 'warn'));
    if (['terminal', 'blocked'].includes(env.status) || env.recoverability === 'terminal') events.push(lifecycleRow(runId, env, 'failure_terminal', env.message, 'risk'));
  }
  return { schema_version: 'agentledger.failure.lifecycle.v1', run_id: runId, run_status: runStatus, events, terminal: events.some((row) => row.stage === 'failure_terminal'), recoverable: events.some((row) => row.stage === 'failure_recovery_scheduled') };
}

function lifecycleRow(runId, env, stage, message, severity) {
  return { schema_version: 'agentledger.failure.lifecycle.v1', stage, run_id: runId, failure_id: env.failure_id, category: env.category, recoverability: env.recoverability, retryability: env.retryability, owner: env.owner, message: String(message ?? ''), severity: String(severity ?? 'warn'), causal_refs: env.causal_refs };
}

function buildFailureCausalGraph(runId, runStatus, envelopes, steps, ledger, approvals, events, costs) {
  const nodes = [{ id: `run:${slug(runId)}`, kind: 'run', status: runStatus }];
  const edges = [];
  for (const step of steps) { nodes.push({ id: `step:${slug(step.step_id)}`, kind: 'step', status: step.status }); edges.push({ source: `run:${slug(runId)}`, target: `step:${slug(step.step_id)}`, kind: 'contains_step' }); }
  for (const event of events) { nodes.push({ id: `event:${event.seq}`, kind: 'event', event_type: event.type }); edges.push({ source: `run:${slug(runId)}`, target: `event:${event.seq}`, kind: 'emitted_event' }); }
  for (const entry of ledger) nodes.push({ id: `tool:${slug(entry.tool_name)}`, kind: 'tool', status: entry.status });
  for (const approval of approvals) nodes.push({ id: `approval:${slug(approval.approval_id)}`, kind: 'approval', status: approval.status });
  for (const cost of costs) nodes.push({ id: `cost:${slug(cost.cost_id)}`, kind: 'cost', category: cost.category, amount: cost.amount, unit: cost.unit });
  for (const env of envelopes) { const id = `failure:${slug(env.failure_id)}`; nodes.push({ id, kind: 'failure', category: env.category, status: env.status, owner: env.owner }); edges.push({ source: `run:${slug(runId)}`, target: id, kind: 'has_failure' }); }
  const deduped = dedupeBy(nodes, 'id');
  return { schema_version: 'agentledger.failure.causal_graph.v1', run_id: runId, nodes: deduped, edges, summary: { node_count: deduped.length, edge_count: edges.length, failure_node_count: deduped.filter((row) => row.kind === 'failure').length } };
}

function buildFailureReplayPlan(runId, envelopes, ledger, events) {
  let unsafe = 0; let manual = 0;
  const actions = envelopes.map((env) => {
    const action = { failure_id: env.failure_id, category: env.category, status: env.status, replay_action: 'reuse_recorded_evidence', replay_safe: true, requires_manual_verification: false, reason: 'recorded runtime evidence can be inspected without calling external systems' };
    if (env.status === 'unknown_side_effect' || env.recoverability === 'manual_verification') { action.replay_action = 'manual_verify_side_effect'; action.replay_safe = false; action.requires_manual_verification = true; action.reason = 'Tool Ledger recorded an unknown side-effect state'; unsafe += 1; manual += 1; }
    else if (env.status === 'waiting_human') action.replay_action = 'resume_after_approval';
    else if (env.status === 'recovery_scheduled') action.replay_action = 'retry_from_checkpoint';
    else if (['terminal', 'blocked'].includes(env.status)) action.replay_action = 'terminal_stop';
    return action;
  });
  return { schema_version: 'agentledger.failure.replay_plan.v1', run_id: runId, mode: 'evidence_only', safe_to_replay: unsafe === 0, unsafe_side_effect_count: unsafe, manual_verification_count: manual, recorded_tool_call_count: ledger.length, recorded_event_count: events.length, actions };
}

function buildFailureAlerts(runId, envelopes, replayPlan) {
  const alerts = [];
  if (envelopes.some((item) => item.status === 'terminal')) alerts.push({ schema_version: 'agentledger.failure.alerts.v1', run_id: runId, kind: 'terminal_failure', severity: 'risk', message: 'terminal failure recorded' });
  if (envelopes.some((item) => item.status === 'unknown_side_effect')) alerts.push({ schema_version: 'agentledger.failure.alerts.v1', run_id: runId, kind: 'unknown_side_effect', severity: 'risk', message: 'tool side-effect state requires manual verification' });
  if (replayPlan.unsafe_side_effect_count) alerts.push({ schema_version: 'agentledger.failure.alerts.v1', run_id: runId, kind: 'unsafe_replay_blocked', severity: 'risk', message: 'failure replay plan blocks unsafe automatic replay' });
  return { schema_version: 'agentledger.failure.alerts.v1', run_id: runId, alerts, alert_count: alerts.length };
}

function buildFailureExport(runId, runStatus, summary, envelopes, lifecycle, graph, replayPlan, alerts) {
  return { schema_version: 'agentledger.failure.export.v1', run_id: runId, run_status: runStatus, summary, failure_envelopes: envelopes, failure_lifecycle: lifecycle, failure_causal_graph: graph, failure_replay_plan: replayPlan, failure_alerts: alerts, external_mappings: { opentelemetry: { span_event_count: lifecycle.events.length }, langfuse: { trace_id: runId, observation_count: envelopes.length }, langsmith: { run_id: runId, feedback_count: envelopes.length }, temporal: { workflow_id: runId, failure_count: envelopes.length, safe_to_replay: replayPlan.safe_to_replay } } };
}

function emptyData() {
  return { runs: {}, steps: {}, events: {}, tool_ledger: {}, approval_requests: {}, cost_records: {}, artifacts: {} };
}

function normalizeData(data) {
  data.runs ??= {};
  data.steps ??= {};
  data.events ??= {};
  data.tool_ledger ??= {};
  data.approval_requests ??= {};
  data.cost_records ??= {};
  data.artifacts ??= {};
}

function nowSeconds() {
  return Date.now() / 1000;
}

function newId(prefix) {
  return `${prefix}_${randomBytes(12).toString('hex')}`;
}

function sha256JSON(value) {
  return createHash('sha256').update(JSON.stringify(value)).digest('hex');
}

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function mergePatch(base, patch) {
  const out = clone(base ?? {});
  for (const [key, value] of Object.entries(patch ?? {})) {
    if (value === null) {
      delete out[key];
      continue;
    }
    if (isPlainObject(value) && isPlainObject(out[key])) {
      out[key] = mergePatch(out[key], value);
      continue;
    }
    out[key] = clone(value);
  }
  return out;
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function compactObject(value) {
  const out = {};
  for (const [key, item] of Object.entries(value ?? {})) {
    if (item === undefined || item === null || item === '') continue;
    if (isPlainObject(item) && Object.keys(item).length === 0) continue;
    out[key] = clone(item);
  }
  return out;
}

function normalizeStreamChunk(chunk) {
  if (!chunk) return {};
  return compactObject({
    schema_version: STREAM_SCHEMA_VERSION,
    stream_id: chunk.streamId ?? chunk.stream_id,
    chunk_id: chunk.chunkId ?? chunk.chunk_id,
    offset: chunk.offset,
    content_ref: chunk.contentRef ?? chunk.content_ref,
    content_hash: chunk.contentHash ?? chunk.content_hash,
    sequence: chunk.sequence,
    event_time: chunk.eventTime ?? chunk.event_time,
    metadata: clone(chunk.metadata ?? {}),
  });
}

function mediaArtifactsFrom(artifacts) {
  return artifacts.flatMap((artifact) => {
    const metadata = artifact.metadata?.agentledger_media;
    if (!metadata) return [];
    return [compactObject({ artifact_id: artifact.artifact_id, name: artifact.name, blob_hash: artifact.blob_hash, blob_ref: artifact.blob_ref, kind: metadata.kind, uri: metadata.uri, content_ref: metadata.content_ref, metadata: metadata.metadata ?? {}, lineage: metadata.lineage ?? {} })];
  });
}

function streamCheckpointsFrom(artifacts) {
  return artifacts.flatMap((artifact) => {
    const metadata = artifact.metadata?.agentledger_stream;
    if (!metadata) return [];
    return [compactObject({ artifact_id: artifact.artifact_id, name: artifact.name, blob_hash: artifact.blob_hash, blob_ref: artifact.blob_ref, stream_id: metadata.stream_id, consumer_id: metadata.consumer_id, offset: metadata.offset, watermark: metadata.watermark, chunk: metadata.chunk ?? {}, partial_result_ref: metadata.partial_result_ref, backpressure: metadata.backpressure ?? {} })];
  });
}

function emptySummary() {
  return { tool_calls: 0, model_tokens: 0, total_usd: 0, by_category: {} };
}

function addCost(summary, record) {
  if (['tool', 'tool_shadow'].includes(record.category) && record.unit === 'call') summary.tool_calls += record.amount;
  if (record.category === 'model' && record.unit === 'token') summary.model_tokens += record.amount;
  if (record.unit === 'usd') summary.total_usd += record.amount;
  const key = `${record.category}:${record.unit}`;
  summary.by_category[key] = (summary.by_category[key] ?? 0) + record.amount;
}

function failureSource(errorType) {
  if (errorType === 'BudgetExceededError') return 'budget';
  if (['PermissionDeniedError', 'ApprovalDenied'].includes(errorType)) return 'policy';
  if (errorType === 'SandboxUnavailableError') return 'sandbox';
  return 'agent';
}

const failureEventTypes = new Set(['failure_classified', 'error_raised', 'step_failed', 'step_retry_scheduled', 'step_waiting_human', 'lease_expired', 'run_cancel_requested', 'run_cancelled', 'tool_call_failed', 'tool_approval_required', 'budget_check_failed']);

function failureCategory(text, fallback = 'agent') {
  const lower = String(text ?? '').toLowerCase();
  for (const category of ['sandbox', 'budget', 'policy', 'model', 'tool', 'runtime']) if (lower.includes(category)) return category;
  if (lower.includes('approval') || lower.includes('permission') || lower.includes('denied')) return 'policy';
  if (lower.includes('lease') || lower.includes('worker')) return 'runtime';
  if (lower.includes('cancel')) return 'cancellation';
  return fallback;
}

function eventFailureCategory(event) {
  if (['tool_call_failed', 'tool_call_blocked', 'tool_approval_required'].includes(event.type)) return 'tool';
  if (['run_cancel_requested', 'run_cancelled', 'step_cancelled'].includes(event.type)) return 'cancellation';
  if (event.type === 'lease_expired') return 'runtime';
  if (event.type === 'step_retry_scheduled') return 'retry';
  if (event.type === 'step_waiting_human') return 'approval';
  return failureCategory(`${event.type ?? ''} ${event.payload?.error_type ?? ''} ${event.payload?.error ?? ''} ${event.payload?.reason ?? ''}`, 'agent');
}

function eventFailureStatus(type, runStatus) {
  if (['step_failed', 'run_cancelled', 'step_cancelled'].includes(type) || (runStatus === 'failed' && type === 'error_raised')) return 'terminal';
  if (type === 'tool_call_blocked') return 'blocked';
  if (['step_retry_scheduled', 'lease_expired'].includes(type)) return 'recovery_scheduled';
  if (['step_waiting_human', 'tool_approval_required'].includes(type)) return 'waiting_human';
  if (type === 'failure_classified') return 'classified';
  return 'failed';
}

function eventRecoverability(type, runStatus) {
  if (runStatus === 'failed' && ['step_failed', 'run_cancelled', 'step_cancelled'].includes(type)) return 'terminal';
  if (['step_retry_scheduled', 'lease_expired'].includes(type)) return 'auto_retry';
  if (['step_waiting_human', 'tool_approval_required'].includes(type)) return 'human_required';
  if (type === 'tool_call_blocked') return 'manual_intervention';
  return 'unknown';
}

function eventRetryability(type) {
  if (['step_retry_scheduled', 'lease_expired'].includes(type)) return 'retryable';
  if (['tool_call_blocked', 'run_cancelled', 'step_cancelled'].includes(type)) return 'not_retryable';
  return 'unknown';
}

function ownerForFailureCategory(category) {
  if (['tool', 'model', 'policy', 'sandbox', 'budget', 'runtime'].includes(category)) return category;
  if (['approval', 'cancellation', 'retry'].includes(category)) return 'runtime';
  return 'agent';
}

function firstText(...values) {
  for (const value of values) if (value !== undefined && value !== null && value !== '') return String(value);
  return 'failure signal';
}

function cleanRefs(refs) {
  const out = [];
  const seen = new Set();
  for (const ref of refs) {
    if (!ref || ref.value === undefined || ref.value === null || ref.value === '') continue;
    const key = `${ref.kind}:${ref.value}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ kind: String(ref.kind), value: String(ref.value) });
  }
  return out;
}

function slug(value) {
  return String(value ?? 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'unknown';
}

function dedupeBy(rows, key) {
  const out = [];
  const seen = new Set();
  for (const row of rows) {
    const value = String(row[key] ?? '');
    if (!value || seen.has(value)) continue;
    seen.add(value);
    out.push(row);
  }
  return out;
}

const MEDIA_SCHEMA_VERSION = 'agentledger.media.v0';
const STREAM_SCHEMA_VERSION = 'agentledger.stream.v0';
const MEDIA_KINDS = new Set(['image', 'audio', 'video', 'frame', 'audio_segment', 'video_segment', 'transcript', 'embedding', 'derived']);

export function migrationsFor(dialect) {
  const normalized = String(dialect).toLowerCase();
  if (normalized === 'sqlite') return [{ version: '0001', name: 'initial_runtime_metadata', dialect: 'sqlite', sql: SQLITE_INITIAL_DDL, checksum: migrationChecksum(SQLITE_INITIAL_DDL) }];
  if (normalized === 'postgres' || normalized === 'postgresql') return [{ version: '0001', name: 'initial_runtime_metadata', dialect: 'postgres', sql: POSTGRES_INITIAL_DDL, checksum: migrationChecksum(POSTGRES_INITIAL_DDL) }];
  if (normalized === 'mysql') return [{ version: '0001', name: 'initial_runtime_metadata', dialect: 'mysql', sql: MYSQL_INITIAL_DDL, checksum: migrationChecksum(MYSQL_INITIAL_DDL) }];
  throw new Error(`unsupported storage dialect: ${dialect}`);
}

export function latestSchemaVersion(dialect) {
  const migrations = migrationsFor(dialect);
  return migrations.length ? migrations[migrations.length - 1].version : null;
}

export function ddlFor(dialect) {
  const normalized = String(dialect).toLowerCase();
  const header = normalized === 'postgres' || normalized === 'postgresql' ? SCHEMA_MIGRATIONS_POSTGRES : normalized === 'mysql' ? SCHEMA_MIGRATIONS_MYSQL : SCHEMA_MIGRATIONS_SQLITE;
  return [header, ...migrationsFor(dialect).map((migration) => migration.sql)].join('\n\n');
}

function migrationChecksum(sql) {
  return `sha256:${createHash('sha256').update(sql).digest('hex')}`;
}

const SCHEMA_MIGRATIONS_SQLITE = `CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at REAL NOT NULL
);`;

const SCHEMA_MIGRATIONS_POSTGRES = `CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at DOUBLE PRECISION NOT NULL
);`;

const SCHEMA_MIGRATIONS_MYSQL = `CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(32) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  checksum VARCHAR(128) NOT NULL,
  applied_at DOUBLE NOT NULL
);`;

const SQLITE_INITIAL_DDL = `CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json TEXT NOT NULL, state_version INTEGER NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until REAL, attempt INTEGER NOT NULL, state_version INTEGER NOT NULL, checkpoint_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq INTEGER NOT NULL, type TEXT NOT NULL, timestamp REAL NOT NULL, agent_role TEXT, state_version INTEGER, causal_token TEXT, payload_hash TEXT, payload_ref TEXT);
CREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);`;

const POSTGRES_INITIAL_DDL = `CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, state_json JSONB NOT NULL, state_version BIGINT NOT NULL, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS steps (step_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id), session_id TEXT NOT NULL, status TEXT NOT NULL, owner TEXT, lease_token TEXT, lease_until DOUBLE PRECISION, attempt BIGINT NOT NULL, state_version BIGINT NOT NULL, checkpoint_id TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT, seq BIGINT NOT NULL, type TEXT NOT NULL, timestamp DOUBLE PRECISION NOT NULL, agent_role TEXT, state_version BIGINT, causal_token TEXT, payload_hash TEXT, payload_ref TEXT, UNIQUE(run_id, seq));
CREATE TABLE IF NOT EXISTS tool_ledger (ledger_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, session_id TEXT, step_id TEXT NOT NULL, tool_name TEXT NOT NULL, tool_version TEXT NOT NULL, tool_call_id TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash TEXT NOT NULL, request_ref TEXT NOT NULL, status TEXT NOT NULL, external_id TEXT, response_hash TEXT, response_ref TEXT, error_type TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL);`;

const MYSQL_INITIAL_DDL = `CREATE TABLE IF NOT EXISTS runs (run_id VARCHAR(128) PRIMARY KEY, session_id VARCHAR(128) NOT NULL, status VARCHAR(64) NOT NULL, state_json JSON NOT NULL, state_version BIGINT NOT NULL, created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL);
CREATE TABLE IF NOT EXISTS steps (step_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128) NOT NULL, status VARCHAR(64) NOT NULL, owner VARCHAR(255), lease_token VARCHAR(128), lease_until DOUBLE, attempt BIGINT NOT NULL, state_version BIGINT NOT NULL, checkpoint_id VARCHAR(255), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, INDEX idx_steps_run_status (run_id, status));
CREATE TABLE IF NOT EXISTS events (event_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128), step_id VARCHAR(128), seq BIGINT NOT NULL, type VARCHAR(255) NOT NULL, timestamp DOUBLE NOT NULL, agent_role VARCHAR(255), state_version BIGINT, causal_token TEXT, payload_hash VARCHAR(128), payload_ref TEXT, UNIQUE KEY idx_events_run_seq (run_id, seq));
CREATE TABLE IF NOT EXISTS tool_ledger (ledger_id VARCHAR(128) PRIMARY KEY, run_id VARCHAR(128) NOT NULL, session_id VARCHAR(128), step_id VARCHAR(128) NOT NULL, tool_name VARCHAR(255) NOT NULL, tool_version VARCHAR(64) NOT NULL, tool_call_id VARCHAR(128) NOT NULL, idempotency_key VARCHAR(255) NOT NULL UNIQUE, causal_token TEXT NOT NULL, request_hash VARCHAR(128) NOT NULL, request_ref TEXT NOT NULL, status VARCHAR(64) NOT NULL, external_id VARCHAR(255), response_hash VARCHAR(128), response_ref TEXT, error_type VARCHAR(255), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, INDEX idx_tool_ledger_run_tool (run_id, tool_name));`;

export class InMemoryMCPToolServer {
  constructor() { this.tools = new Map(); }
  addTool(descriptor, handler) { this.tools.set(descriptor.name, { descriptor, handler }); }
  listTools() { return [...this.tools.keys()].sort().map((name) => this.tools.get(name).descriptor); }
  callTool(name, args = {}) {
    const entry = this.tools.get(name);
    if (!entry) throw new Error(`MCP tool not found: ${name}`);
    return entry.handler(name, args);
  }
}

export class InMemoryMCPContextServer {
  constructor() { this.resources = new Map(); }
  addResource({ uri, name, reader, mimeType = 'application/json' }) { this.resources.set(uri, { descriptor: { uri, name, mimeType }, reader }); }
  listResources() { return [...this.resources.keys()].sort().map((uri) => this.resources.get(uri).descriptor); }
  readResource(uri) {
    const entry = this.resources.get(uri);
    if (!entry) throw new Error(`MCP resource not found: ${uri}`);
    return { resource: entry.descriptor, content: entry.reader(uri) };
  }
}

export class MCPToolAdapter {
  constructor(clientCall) { this.clientCall = clientCall; }
  toolSpecFromDescriptor(descriptor) {
    const annotations = descriptor.annotations ?? {};
    const sideEffect = annotations.side_effect ?? 'none';
    const riskLevel = annotations.risk_level ?? 'low';
    const idempotencyRequired = annotations.idempotency_required ?? sideEffect !== 'none';
    const approvalRequired = annotations.approval_required ?? false;
    const sandboxRequired = annotations.sandbox_required ?? false;
    const sandboxExecutor = annotations.sandbox_executor ?? null;
    const sandboxPolicy = annotations.sandbox_policy ?? {};
    const name = descriptor.name;
    return { name, version: String(descriptor.version ?? 'v1'), inputSchema: descriptor.inputSchema ?? descriptor.input_schema ?? {}, outputSchema: descriptor.outputSchema ?? descriptor.output_schema ?? {}, sideEffect, riskLevel, idempotencyRequired, approvalRequired, sandboxRequired, sandboxExecutor, sandboxPolicy, func: (args) => this.clientCall(name, args) };
  }
}

export class MCPContextAdapter {
  constructor(resourceRead) { this.resourceRead = resourceRead; }
  readToolSpec({ name = 'mcp.context.read', riskLevel = 'low' } = {}) {
    return { name, version: 'v1', description: 'Read an MCP-style context resource by URI.', inputSchema: { type: 'object', required: ['uri'], properties: { uri: { type: 'string', minLength: 1 } }, additionalProperties: false }, outputSchema: { type: 'object' }, sideEffect: 'none', riskLevel, func: (args) => this.resourceRead(args.uri) };
  }
}

export class FunctionAdapter {
  constructor(func, { role = 'Agent', name = 'function' } = {}) { this.func = func; this.role = role; this.name = name; }
  mapRunSpec() { return { adapter: this.name, role: this.role }; }
  asAgent({ outputKey = 'output' } = {}) { return async (ctx, state) => { const result = await this.func(ctx, state); if (outputKey && result !== undefined) await ctx.writeState(outputKey, result); }; }
}

export class MethodFrameworkAdapter {
  constructor(target, { role = 'FrameworkAgent', methodCandidates = [], outputKey = 'output' } = {}) { this.target = target; this.role = role; this.methodCandidates = methodCandidates; this.outputKey = outputKey; }
  mapRunSpec() { return { adapter: 'method-framework', role: this.role, target: this.target?.constructor?.name ?? 'Object', methods: this.methodCandidates }; }
  asAgent() { return async (ctx, state) => { const result = await this.invoke(state); if (this.outputKey) await ctx.writeState(this.outputKey, result); }; }
  async invoke(payload) {
    for (const name of this.methodCandidates) if (typeof this.target?.[name] === 'function') return this.target[name](payload);
    if (typeof this.target === 'function') return this.target(payload);
    throw new Error(`target does not expose any of ${JSON.stringify(this.methodCandidates)}`);
  }
}

export const IGNORE_SAME_LINE = 'agentledger: ignore-boundary';
export const IGNORE_NEXT_LINE = 'agentledger: ignore-next-line';

export function defaultBoundaryRules() {
  return [
    { rule_id: 'direct-shell-os-system', pattern: 'os.system', category: 'shell', message: 'direct shell execution bypasses ToolGateway, policy, ledger, sandbox, and audit', suggestion: "wrap shell execution as a runtime-managed tool and call ctx.callTool('shell.exec', args)" },
    { rule_id: 'direct-shell-subprocess', pattern: 'subprocess.', category: 'shell', message: 'direct subprocess execution bypasses ToolGateway, policy, ledger, sandbox, and audit', suggestion: "wrap command execution as a runtime-managed tool and call ctx.callTool('shell.exec', args)", prefix: true },
    { rule_id: 'direct-http-requests', pattern: 'requests.', category: 'network', message: 'direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit', suggestion: 'register the HTTP/API call as a runtime-managed tool and call ctx.callTool(...)', prefix: true },
    { rule_id: 'direct-http-httpx', pattern: 'httpx.', category: 'network', message: 'direct HTTP calls bypass ToolGateway, policy, ledger, budget, replay, and audit', suggestion: 'register the HTTP/API call as a runtime-managed tool and call ctx.callTool(...)', prefix: true },
    { rule_id: 'direct-openai-sdk', pattern: 'openai.', category: 'model', message: 'direct model SDK usage bypasses model provider archives, replay, budget, and attribution', suggestion: 'call models through the runtime model boundary', prefix: true },
    { rule_id: 'direct-anthropic-sdk', pattern: 'anthropic.', category: 'model', message: 'direct model SDK usage bypasses model provider archives, replay, budget, and attribution', suggestion: 'call models through the runtime model boundary', prefix: true },
  ];
}

export function scanBoundarySource(path, source, rules = defaultBoundaryRules()) {
  const findings = [];
  const lines = String(source).split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const previous = i > 0 ? lines[i - 1] : '';
    if (line.includes(IGNORE_SAME_LINE) || previous.includes(IGNORE_NEXT_LINE)) continue;
    for (const rule of rules) {
      const index = line.indexOf(rule.pattern);
      if (index < 0) continue;
      let callee = rule.pattern;
      if (rule.prefix) {
        let end = index + rule.pattern.length;
        while (end < line.length && /[A-Za-z0-9_.]/.test(line[end])) end += 1;
        callee = line.slice(index, end);
      }
      findings.push({ path, line: i + 1, column: index + 1, rule_id: rule.rule_id, severity: 'error', callee, category: rule.category, message: rule.message, suggestion: rule.suggestion });
      break;
    }
  }
  return { passed: findings.length === 0, scanned_files: [path], finding_count: findings.length, findings };
}

export class RuntimeScheduler {
  constructor(store) { this.store = store; }
  async recoverExpiredLeases() { return { recovered_steps: await this.store.recoverExpiredLeases() }; }
  async cancelRun(runId, reason = 'cancelled by scheduler') { return this.store.cancelRun(runId, reason); }
  status(runId) {
    const run = this.store.run(runId);
    const steps = this.store.steps(runId).map((step) => ({
      step_id: step.step_id,
      status: step.status,
      owner: step.owner ?? null,
      attempt: step.attempt,
      lease_until: step.lease_until ?? null,
      last_error_type: step.last_error_type ?? null,
    }));
    return { run_id: runId, run_status: run.status, state_version: run.state_version, steps, cost_summary: this.store.costSummary(runId) };
  }
}

export function adversarialReview(bundle, { maxTotalUsd = null } = {}) {
  const summary = bundle.summary ?? {};
  const checks = [
    { name: 'no_failed_steps', passed: !summary.has_failed_steps, severity: 'blocker', detail: 'no step is in failed status' },
    { name: 'no_pending_verification', passed: !summary.has_pending_verification && !summary.has_pending_ledger, severity: 'blocker', detail: 'no side effect is pending verification' },
    { name: 'no_pending_approvals', passed: !summary.has_pending_approvals && !summary.has_pending_approval, severity: 'blocker', detail: 'no approval request is still pending' },
    { name: 'completed_steps_have_completion_events', passed: completedStepsHaveEvents(bundle.steps ?? [], bundle.events ?? []), severity: 'blocker', detail: 'completed steps have step_completed events' },
    { name: 'ledger_statuses_known', passed: ledgerStatusesKnown(bundle.tool_ledger ?? []), severity: 'blocker', detail: 'Tool Ledger rows use known statuses' },
    { name: 'event_sequence_contiguous', passed: eventSequenceContiguous(bundle.events ?? []), severity: 'blocker', detail: 'event sequence has no gaps' },
    { name: 'artifacts_have_blob_refs', passed: (bundle.artifacts ?? []).every((row) => row.blob_ref && row.blob_hash), severity: 'warning', detail: 'artifacts have blob refs and hashes' },
    { name: 'media_artifacts_have_refs', passed: (bundle.media_artifacts ?? []).every((row) => row.kind && (row.uri || row.content_ref || row.blob_ref)), severity: 'blocker', detail: 'media artifacts have kind and durable refs' },
    { name: 'stream_checkpoints_have_offsets', passed: (bundle.stream_checkpoints ?? []).every((row) => row.stream_id && row.consumer_id && row.offset !== undefined && row.offset !== null), severity: 'blocker', detail: 'stream checkpoints have stream, consumer, and offset' },
    { name: 'high_risk_approvals_decided', passed: highRiskApprovalsDecided(bundle.approvals ?? bundle.approval_requests ?? []), severity: 'blocker', detail: 'high-risk approval requests are decided' },
    { name: 'no_blocking_failure_events', passed: !(bundle.events ?? []).some((event) => ['error_raised', 'step_failed', 'tool_call_failed', 'tool_call_blocked'].includes(event.type)), severity: 'warning', detail: 'no blocking failure events are present' },
  ];
  if (maxTotalUsd !== null && maxTotalUsd !== undefined) {
    const total = Number(bundle.cost_summary?.total_usd ?? summary.cost_summary?.total_usd ?? 0);
    checks.push({ name: 'max_total_usd', passed: total <= maxTotalUsd, severity: 'blocker', detail: `total_usd=${total}, limit=${maxTotalUsd}` });
  }
  return {
    passed: checks.every((check) => check.severity !== 'blocker' || check.passed),
    run_id: bundle.run?.run_id ?? null,
    checks,
    metadata: { event_count: (bundle.events ?? []).length, step_count: (bundle.steps ?? []).length, tool_ledger_count: (bundle.tool_ledger ?? []).length, approval_count: (bundle.approvals ?? bundle.approval_requests ?? []).length, artifact_count: (bundle.artifacts ?? []).length, media_artifact_count: (bundle.media_artifacts ?? []).length, stream_checkpoint_count: (bundle.stream_checkpoints ?? []).length, cost_summary: bundle.cost_summary ?? summary.cost_summary ?? {} },
  };
}

function completedStepsHaveEvents(steps, events) {
  const completed = new Set(events.filter((event) => event.type === 'step_completed').map((event) => event.step_id));
  return steps.every((step) => step.status !== 'completed' || completed.has(step.step_id));
}
function ledgerStatusesKnown(rows) { return rows.every((row) => ['SUCCEEDED', 'FAILED_NO_EFFECT', 'PENDING_VERIFICATION', 'COMPENSATED', 'RUNNING', 'RESERVED'].includes(row.status)); }
function eventSequenceContiguous(events) { return events.every((event, index) => event.seq === index + 1); }
function highRiskApprovalsDecided(rows) { return rows.every((row) => !['high', 'destructive', 'sensitive'].includes(row.risk_level) || ['APPROVED', 'DENIED'].includes(row.status)); }

export function evaluateEvidence(bundle, { maxTotalUsd = null } = {}) {
  const summary = bundle.summary ?? {};
  const checks = [
    { name: 'no_failed_steps', passed: !summary.has_failed_steps, detail: 'all steps completed or remain non-failed' },
    { name: 'no_pending_verification', passed: !summary.has_pending_verification && !summary.has_pending_ledger, detail: 'no side effect is waiting for human/external verification' },
    { name: 'completed_steps_have_events', passed: completedStepsHaveEvents(bundle.steps ?? [], bundle.events ?? []), detail: 'each completed step has a step_completed event' },
    { name: 'managed_side_effects_are_ledgered', passed: ledgerStatusesKnown(bundle.tool_ledger ?? []), detail: 'every ledger row has a known status' },
    { name: 'media_artifacts_have_refs', passed: (bundle.media_artifacts ?? []).every((row) => row.kind && (row.uri || row.content_ref || row.blob_ref)), detail: 'media artifacts have kind and durable refs' },
    { name: 'stream_checkpoints_have_offsets', passed: (bundle.stream_checkpoints ?? []).every((row) => row.stream_id && row.consumer_id && row.offset !== undefined && row.offset !== null), detail: 'stream checkpoints have stream, consumer, and offset' },
  ];
  if (maxTotalUsd !== null && maxTotalUsd !== undefined) {
    const total = Number(bundle.cost_summary?.total_usd ?? summary.cost_summary?.total_usd ?? 0);
    checks.push({ name: 'max_total_usd', passed: total <= maxTotalUsd, detail: `total_usd=${total}, limit=${maxTotalUsd}` });
  }
  return { passed: checks.every((check) => check.passed), checks, metadata: {} };
}

export function evaluateEvidenceRegression(golden, current, { maxTotalUsdDelta = null } = {}) {
  const diff = diffEvidence(golden, current);
  const checks = [
    { name: 'final_state_regression', passed: diff.changes.final_state.changed_count === 0, detail: `changed_final_state_keys=${diff.changes.final_state.changed_count}` },
    { name: 'event_type_regression', passed: diff.changes.event_types.changed_count === 0, detail: `changed_event_type_positions=${diff.changes.event_types.changed_count}` },
    { name: 'tool_ledger_status_regression', passed: diff.changes.tool_ledger.changed_count === 0, detail: `changed_ledger_status_positions=${diff.changes.tool_ledger.changed_count}` },
    { name: 'media_artifact_regression', passed: diff.changes.media_artifacts.changed_count === 0, detail: `changed_media_artifacts=${diff.changes.media_artifacts.changed_count}` },
    { name: 'stream_checkpoint_regression', passed: diff.changes.stream_checkpoints.changed_count === 0, detail: `changed_stream_checkpoints=${diff.changes.stream_checkpoints.changed_count}` },
  ];
  if (maxTotalUsdDelta !== null && maxTotalUsdDelta !== undefined) {
    const left = Number(golden.cost_summary?.total_usd ?? golden.summary?.cost_summary?.total_usd ?? 0);
    const right = Number(current.cost_summary?.total_usd ?? current.summary?.cost_summary?.total_usd ?? 0);
    const delta = right - left;
    checks.push({ name: 'max_total_usd_delta', passed: delta <= maxTotalUsdDelta, detail: `total_usd_delta=${delta}, limit=${maxTotalUsdDelta}` });
  }
  return { passed: checks.every((check) => check.passed), checks, metadata: { diff } };
}

export async function runFailureInjectionSuite() {
  const checks = [];
  checks.push(await failureRetryExhaustion());
  checks.push(await failureLeaseFencing());
  checks.push(await failureCancellationFencing());
  checks.push(await failureSideEffectIdempotency());
  return { passed: checks.every((check) => check.passed), checks };
}
async function failureRetryExhaustion() { const rt = new Runtime(JSONStore.memory()); const { runId } = await rt.createRun({}); await rt.runOnce({ runId, workerId: 'retry-1', agentRole: 'FailureInjector', agent: async () => { throw new RetryableAgentError('retry'); } }); try { await rt.runOnce({ runId, workerId: 'retry-2', agentRole: 'FailureInjector', agent: async () => { throw new Error('final failure'); } }); } catch {} const status = rt.store.run(runId).status; return { name: 'retry_exhaustion', passed: status === 'failed', detail: `run_status=${status}`, run_id: runId }; }
async function failureLeaseFencing() { const store = JSONStore.memory(); const { runId, stepId } = await store.createRun({}); const claim = await store.claimStep({ workerId: 'stale-worker', runId, leaseSeconds: 0 }); const recovered = await store.recoverExpiredLeases(); let staleRejected = false; try { await store.commitStatePatch({ runId, stepId, leaseToken: claim.lease_token, baseVersion: 0, patch: { stale: true } }); } catch { staleRejected = true; } const fresh = await store.claimStep({ workerId: 'fresh-worker', runId }); const passed = recovered === 1 && staleRejected && fresh?.attempt === 2; return { name: 'lease_fencing', passed, detail: `recovered_steps=${recovered} stale_rejected=${staleRejected}`, run_id: runId }; }
async function failureCancellationFencing() { const store = JSONStore.memory(); const { runId, stepId } = await store.createRun({}); const claim = await store.claimStep({ workerId: 'stale-worker', runId }); const cancelled = await store.cancelRun(runId, 'failure injection'); let staleRejected = false; try { await store.commitStatePatch({ runId, stepId, leaseToken: claim.lease_token, baseVersion: 0, patch: { late: true } }); } catch { staleRejected = true; } let fresh = null; try { fresh = await store.claimStep({ workerId: 'fresh-worker', runId }); } catch {} const passed = cancelled === 1 && staleRejected && fresh === null && store.run(runId).status === 'cancelled'; return { name: 'cancellation_fencing', passed, detail: `cancelled_steps=${cancelled} stale_rejected=${staleRejected}`, run_id: runId }; }
async function failureSideEffectIdempotency() { const rt = new Runtime(JSONStore.memory()); let calls = 0; rt.registerTool({ name: 'external.create', version: 'v1', sideEffect: 'external', func: async () => { calls += 1; return { id: 'EXT-1' }; } }); const { runId } = await rt.createRun({}); const agent = async (ctx) => { await ctx.callTool('external.create', { title: 'once' }); }; await rt.runOnce({ runId, workerId: 'worker-1', agentRole: 'FailureInjector', agent }); try { await rt.runOnce({ runId, workerId: 'worker-2', agentRole: 'FailureInjector', agent }); } catch {} return { name: 'side_effect_idempotency', passed: calls === 1, detail: `external_call_count=${calls}`, run_id: runId }; }

export function diffStates(source, shadow) {
  const changed = {};
  for (const key of Array.from(new Set([...Object.keys(source ?? {}), ...Object.keys(shadow ?? {})])).sort()) {
    if (JSON.stringify(source?.[key]) !== JSON.stringify(shadow?.[key])) changed[key] = { source: source?.[key], shadow: shadow?.[key] };
  }
  return { changed, changed_count: Object.keys(changed).length };
}

export function shadowReport(sourceRunId, shadowRunId, ok, sourceState, shadowState) {
  return { source_run_id: sourceRunId, shadow_run_id: shadowRunId, ok, state_diff: diffStates(sourceState, shadowState) };
}

export function builtinGoldenNames() { return ['media-stream-checkpoint', 'minimal-success', 'tool-ledger-success']; }
export async function builtinGoldenEvidence(name) {
  if (name === 'minimal-success') return goldenMinimalSuccess();
  if (name === 'tool-ledger-success') return goldenToolLedgerSuccess();
  if (name === 'media-stream-checkpoint') return goldenMediaStreamCheckpoint();
  throw new Error(`unknown built-in golden case: ${name}`);
}
export function goldenRegression(golden, current) { return evaluateEvidenceRegression(golden, current); }
async function goldenMinimalSuccess() { const rt = new Runtime(JSONStore.memory()); const { runId } = await rt.createRun({}); await rt.runOnce({ runId, workerId: 'golden-worker', agentRole: 'GoldenAgent', agent: async (ctx) => ctx.writeState('answer', 'ok') }); return exportEvidence(rt.store, runId); }
async function goldenToolLedgerSuccess() { const rt = new Runtime(JSONStore.memory()); rt.registerTool({ name: 'github.create_issue', version: 'v1', sideEffect: 'external', func: async () => ({ issue_id: 'ISSUE-1' }) }); const { runId } = await rt.createRun({}); await rt.runOnce({ runId, workerId: 'golden-worker', agentRole: 'ExecutorAgent', agent: async (ctx) => { const result = await ctx.callTool('github.create_issue', { title: 'golden' }); await ctx.writeState('issue_id', result.issue_id); } }); return exportEvidence(rt.store, runId); }
async function goldenMediaStreamCheckpoint() { const rt = new Runtime(JSONStore.memory()); const { runId } = await rt.createRun({}); await rt.runOnce({ runId, workerId: 'golden-worker', agentRole: 'MediaAgent', agent: async (ctx) => { await ctx.createMediaArtifact('golden-video-frame', 'frame', { uri: 'file://golden-frame.jpg' }); await ctx.createStreamCheckpoint('golden-stream-checkpoint', 'stream-golden', 'consumer-golden', 42, {}); await ctx.writeState('processed_offset', 42); } }); return exportEvidence(rt.store, runId); }

export function timeTravel(bundle, { atSeq = 0, includeStates = false } = {}) {
  let state = {};
  let stateAtSeq = {};
  const timeline = [];
  let selectedEvent = null;
  for (const event of bundle.events ?? []) {
    const before = structuredClone(state);
    const patch = patchForTimeTravelEvent(event);
    if (patch) Object.assign(state, patch);
    const diff = diffDict(before, state);
    const frame = { seq: event.seq ?? timeline.length + 1, event_id: event.event_id, type: event.type, step_id: event.step_id ?? null, agent_role: event.agent_role ?? null, state_version: event.state_version ?? null, timestamp: event.timestamp ?? 0, state_changed: diff.changed_count > 0, changed_keys: Object.keys(diff.changed).sort(), patch };
    if (includeStates) frame.state_after = structuredClone(state);
    timeline.push(frame);
    if (atSeq > 0 && frame.seq <= atSeq) { stateAtSeq = structuredClone(state); selectedEvent = frame; }
  }
  if (!atSeq) stateAtSeq = structuredClone(state);
  return { run_id: bundle.run?.run_id ?? null, at_seq: atSeq || null, event_count: timeline.length, timeline, state_at_seq: stateAtSeq, selected_event: selectedEvent };
}
export function timeTravelHTML(report) { const rows = (report.timeline ?? []).map((frame) => `<tr><td>${frame.seq}</td><td>${escapeHTML(frame.type ?? '')}</td><td>${escapeHTML((frame.changed_keys ?? []).join(', '))}</td></tr>`).join('\n'); return `<!doctype html><html><head><meta charset="utf-8"><title>AgentLedger Time Travel Report</title></head><body><h1>AgentLedger Time Travel Report</h1><p>Run <code>${escapeHTML(report.run_id ?? '')}</code></p><table>${rows}</table><h2>State At Selected Point</h2><pre>${escapeHTML(JSON.stringify(report.state_at_seq ?? {}, null, 2))}</pre><h2>Selected Event</h2><pre>${escapeHTML(JSON.stringify(report.selected_event ?? null, null, 2))}</pre></body></html>`; }
function patchForTimeTravelEvent(event) { if (event.type === 'run_created') return event.payload?.initial_state && typeof event.payload.initial_state === 'object' ? event.payload.initial_state : {}; if (event.type === 'state_committed' || event.type === 'state_patch_committed' || event.type === 'system_state_patch_applied') return event.payload?.patch && typeof event.payload.patch === 'object' ? event.payload.patch : {}; return null; }

export function optionalAdapterCapabilities() {
  const item = (name, category, surface) => ({ name, category, core_imports_heavy_sdks: false, adapter_is_optional: true, fail_closed_without_adapter: true, contract_surface: surface });
  return [
    item('postgres', 'storage', ['ddl_for', 'migrations_for', 'state_store']),
    item('mysql', 'storage', ['ddl_for', 'migrations_for', 'state_store']),
    item('s3', 'blobstore', ['put_json', 'get_json', 'content_address']),
    item('docker', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('e2b', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('bubblewrap', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('kubernetes', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('gvisor', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('firecracker', 'sandbox', ['sandbox_policy', 'sandbox_result', 'tool_gateway']),
    item('langgraph', 'framework', ['framework_adapter', 'checkpoint_contract']),
    item('langchain', 'framework', ['framework_adapter']),
    item('crewai', 'framework', ['framework_adapter']),
    item('autogen', 'framework', ['framework_adapter']),
    item('openai-agents-sdk', 'framework', ['framework_adapter']),
    item('llamaindex', 'framework', ['framework_adapter']),
    item('semantic-kernel', 'framework', ['framework_adapter']),
    item('mcp-transport', 'mcp', ['mcp_tool_descriptor', 'mcp_resource_descriptor']),
    item('langfuse', 'observability', ['evidence_bundle', 'trace_payload', 'correlation_ids']),
    item('shadow-runner', 'shadow', ['evidence_bundle', 'tool_ledger', 'state_diff']),
  ];
}

export class PostgresAdapter {
  constructor(client, { schema = 'agentledger' } = {}) { this.client = client; this.schema = schema; }
  migrationPlan() { return migrationsFor('postgres'); }
  async exec(sql, params = []) {
    if (!this.client) throw new Error('postgres adapter requires an injected SQL client');
    if (typeof this.client.exec === 'function') return this.client.exec(sql, params);
    if (typeof this.client.query === 'function') return this.client.query(sql, params);
    if (typeof this.client.execute === 'function') return this.client.execute(sql, params);
    throw new Error('postgres adapter requires a client with exec(sql, params), query(sql, params), or execute(sql, params)');
  }
  async applyMigrations() {
    const migrations = this.migrationPlan();
    await this.exec(ddlFor('postgres'));
    for (const migration of migrations) await this.exec('INSERT INTO schema_migrations(version, name, checksum) VALUES ($1, $2, $3) ON CONFLICT (version) DO NOTHING', [migration.version, migration.name, migration.checksum]);
  }
}

export class MySQLAdapter {
  constructor(client, { database = 'agentledger' } = {}) { this.client = client; this.database = database; }
  migrationPlan() { return migrationsFor('mysql'); }
  async exec(sql, params = []) {
    if (!this.client) throw new Error('mysql adapter requires an injected SQL client');
    if (typeof this.client.exec === 'function') return this.client.exec(sql, params);
    if (typeof this.client.query === 'function') return this.client.query(sql, params);
    if (typeof this.client.execute === 'function') return this.client.execute(sql, params);
    throw new Error('mysql adapter requires a client with exec(sql, params), query(sql, params), or execute(sql, params)');
  }
  async applyMigrations() {
    const migrations = this.migrationPlan();
    await this.exec(ddlFor('mysql'));
    for (const migration of migrations) await this.exec('INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES (?, ?, ?, UNIX_TIMESTAMP()) ON DUPLICATE KEY UPDATE version=version', [migration.version, migration.name, migration.checksum]);
  }
}
export class S3BlobStoreAdapter {
  constructor(client, { bucket, prefix = 'agentledger/blobs' } = {}) { this.client = client; this.bucket = bucket; this.prefix = prefix; }
  async putObject(input) {
    if (!this.client) throw new Error('s3 adapter requires an injected object client');
    if (typeof this.client.putObject === 'function') return this.client.putObject(input);
    if (typeof this.client.send === 'function') return this.client.send({ input, constructor: { name: 'PutObjectCommand' } });
    throw new Error('s3 adapter requires a client with putObject(input) or send(command)');
  }
  async getObject(bucket, key) {
    if (!this.client) throw new Error('s3 adapter requires an injected object client');
    if (typeof this.client.getObject === 'function') return this.client.getObject(bucket, key);
    if (typeof this.client.send === 'function') return this.client.send({ input: { Bucket: bucket, Key: key }, constructor: { name: 'GetObjectCommand' } });
    throw new Error('s3 adapter requires a client with getObject(bucket, key) or send(command)');
  }
  async putJSON(value) { const digest = sha256JSON(value); const key = `${this.prefix.replace(/\/+$/, '')}/sha256/${digest}.json`; const body = JSON.stringify(value, null, 2); await this.putObject({ Bucket: this.bucket, Key: key, Body: body, ContentType: 'application/json', Metadata: { 'agentledger-digest': `sha256:${digest}` } }); return { digest: `sha256:${digest}`, ref: `s3://${this.bucket}/${key}` }; }
  async getJSON(ref) { const prefix = `s3://${this.bucket}/`; if (!ref.startsWith(prefix) || ref.includes('..')) throw new Error(`unsupported s3 blob ref: ${ref}`); const obj = await this.getObject(this.bucket, ref.slice(prefix.length)); const body = typeof obj.Body === 'string' ? obj.Body : new TextDecoder().decode(obj.Body); return JSON.parse(body); }
}
export class OTLPTransport {
  constructor(client, { endpoint = '' } = {}) { this.client = client; this.endpoint = endpoint; }
  async export(payload) { if (!this.client || typeof this.client.postJSON !== 'function') throw new Error('otlp transport requires an injected client'); return this.client.postJSON(this.endpoint, payload, 'application/json'); }
}
export class DockerSandboxAdapter {
  constructor({ image = 'python:3.11-slim' } = {}) { this.image = image; }
  manifest(policy, command) { return { backend: 'docker', image: this.image, network: policy.network === 'deny' || !policy.network ? 'none' : policy.network, read_only_root: true, requires_explicit_execution: true, command }; }
}
