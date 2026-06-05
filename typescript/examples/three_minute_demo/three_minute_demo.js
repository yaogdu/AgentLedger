import { JSONStore, RetryableAgentError, Runtime, replay } from '../../src/index.js';

const rt = new Runtime(JSONStore.memory());
const externalTickets = [];
let actualToolExecutions = 0;

rt.registerTool({
  name: 'ticket.create',
  version: 'v1',
  sideEffect: 'external_write',
  idempotencyRequired: true,
  inputSchema: { type: 'object', required: ['title'] },
  func: async (args) => {
    actualToolExecutions += 1;
    const ticket = { external_id: `TICKET-${externalTickets.length + 1}`, title: args.title };
    externalTickets.push(ticket);
    return ticket;
  },
});

const agent = async (ctx) => {
  const ticket = await ctx.callTool('ticket.create', {
    title: 'Investigate failed payment',
    _logical_operation: 'open-payment-ticket',
  });
  if (ctx.attempt === 1) throw new RetryableAgentError('after external ticket create, before state commit');
  await ctx.writeState('ticket', ticket);
  await ctx.writeState('recovered', true);
};

const { runId } = await rt.createRun({});
const firstOK = await rt.runOnce({ runId, workerId: 'worker-before-crash', agentRole: 'SupportAgent', agent });
const secondOK = await rt.runOnce({ runId, workerId: 'worker-after-restart', agentRole: 'SupportAgent', agent });
const summary = replay(rt.store, runId);

console.log(JSON.stringify({
  run_id: runId,
  first_attempt_ok: firstOK,
  second_attempt_ok: secondOK,
  external_ticket_count: externalTickets.length,
  actual_tool_executions: actualToolExecutions,
  tool_ledger: rt.store.ledger(runId).map((row) => ({
    tool_name: row.tool_name,
    status: row.status,
    external_id: row.external_id,
    idempotency_key: row.idempotency_key,
  })),
  final_state: rt.store.finalState(runId),
  replay: {
    safe: summary.replay_safe,
    event_count: summary.event_count,
    tool_call_count: summary.tool_call_count,
  },
}, null, 2));
