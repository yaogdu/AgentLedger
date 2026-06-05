import { InMemoryMCPToolServer, JSONStore, LocalSandboxExecutor, MCPToolAdapter, Runtime } from '../../src/index.js';

const rt = new Runtime(JSONStore.memory());
rt.setSandbox(new LocalSandboxExecutor());
const externalActions = [];
const server = new InMemoryMCPToolServer();

server.addTool({
  name: 'mcp.github.create_pr',
  inputSchema: {
    type: 'object',
    required: ['title'],
    properties: { title: { type: 'string', minLength: 1 } },
    additionalProperties: true,
  },
  annotations: {
    side_effect: 'external_write',
    risk_level: 'high',
    idempotency_required: true,
    approval_required: true,
    sandbox_required: true,
    sandbox_policy: { network: 'deny', filesystem: 'read-only' },
  },
}, (_name, args) => {
  const action = { external_id: `PR-${externalActions.length + 1}`, title: args.title };
  externalActions.push(action);
  return action;
});

const adapter = new MCPToolAdapter((name, args) => server.callTool(name, args));
for (const descriptor of server.listTools()) rt.registerTool(adapter.toolSpecFromDescriptor(descriptor));

const agent = async (ctx) => {
  const result = await ctx.callTool('mcp.github.create_pr', {
    title: 'Update runtime docs',
    _logical_operation: 'docs-pr',
  });
  await ctx.writeState('pull_request', result);
};

const { runId } = await rt.createRun({});
const firstOK = await rt.runOnce({ runId, workerId: 'worker-before-approval', agentRole: 'MCPAgent', agent });
const approval = rt.store.approvalRequests(runId)[0];
await rt.store.approveRequest(approval.approval_id, { approver: 'maintainer', reason: 'demo approval' });
const secondOK = await rt.runOnce({ runId, workerId: 'worker-after-approval', agentRole: 'MCPAgent', agent });

console.log(JSON.stringify({
  run_id: runId,
  first_attempt_waited_for_approval: !firstOK,
  second_attempt_ok: secondOK,
  approvals: rt.store.approvalRequests(runId).map((row) => ({
    approval_id: row.approval_id,
    tool_name: row.tool_name,
    risk_level: row.risk_level,
    status: row.status,
    reason: row.reason,
  })),
  external_action_count: externalActions.length,
  final_state: rt.store.finalState(runId),
}, null, 2));
