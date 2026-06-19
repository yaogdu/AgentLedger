import { randomBytes } from 'node:crypto';

export class LangGraphCheckpointerAdapter {
  constructor(runtime) {
    this.runtime = runtime;
    this.name = 'langgraph-checkpointer';
  }

  configForRun(runId, { threadId = null, checkpointNs = '' } = {}) {
    return { configurable: { agentledger_run_id: runId, thread_id: threadId ?? runId, checkpoint_ns: checkpointNs } };
  }

  checkpointFromRun(runId) {
    const loaded = this.runtime.store.loadState(runId);
    return { run_id: runId, session_id: loaded.sessionId, state_version: loaded.version, state: loaded.state };
  }

  put(config, checkpoint, metadata = {}, newVersions = {}) {
    const checkpointId = String(checkpoint.id ?? checkpoint.checkpoint_id ?? newCheckpointId());
    const nextConfig = this.withCheckpointId(config, checkpointId);
    return { config: nextConfig, checkpoint: { ...checkpoint, id: checkpointId }, metadata, new_versions: newVersions };
  }

  get(config) {
    const runId = this.runIdFromConfig(config);
    return this.checkpointFromRun(runId);
  }

  getTuple(config) {
    return { config, checkpoint: this.get(config), metadata: {}, parent_config: null, pending_writes: [] };
  }

  list(config = null) {
    return config ? [this.getTuple(config)] : [];
  }

  runIdFromConfig(config) {
    const configurable = config?.configurable ?? {};
    const runId = configurable.agentledger_run_id ?? configurable.run_id;
    if (!runId) throw new Error('LangGraph config must include configurable.agentledger_run_id or configurable.run_id');
    return String(runId);
  }

  withCheckpointId(config, checkpointId) {
    return { ...config, configurable: { ...(config?.configurable ?? {}), checkpoint_id: checkpointId } };
  }
}

function newCheckpointId() {
  return `lgckpt_${randomBytes(12).toString('hex')}`;
}

export class LangGraphNodeAdapter {
  constructor(node, { role = 'LangGraphAgent' } = {}) {
    this.node = node;
    this.role = role;
    this.name = 'langgraph-node';
  }

  mapRunSpec() {
    return { adapter: this.name, role: this.role, node: this.node?.name ?? '<anonymous>' };
  }

  asAgent({ outputKey = 'output' } = {}) {
    return async (ctx, state) => {
      const result = await this.node(ctx, state);
      if (outputKey && result !== undefined) await ctx.writeState(outputKey, result);
    };
  }
}

export const adapterPackage = {
  name: 'agentledger-langgraph',
  runtimePackage: 'agentledger-runtime',
  version: '1.4.1',
  category: 'framework',
};
