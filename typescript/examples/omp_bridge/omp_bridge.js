import { JSONStore, OmpLedgerBridge, Runtime } from '../../src/index.js';

const runtime = new Runtime(JSONStore.memory());
const bridge = new OmpLedgerBridge(runtime, { appName: 'omp-demo' });

const runId = await bridge.recordSessionStarted({
  sessionId: 'omp-session-1',
  initialState: { task: 'review contract' },
  metadata: { runtime: 'synthetic-omp' },
});
await bridge.recordTurnStarted({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  agentRole: 'OMPPlanner',
  metadata: { phase: 'planning' },
});
await bridge.recordModelCall({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  provider: 'openai-compatible-gateway',
  model: 'legal-router',
  request: { messages: [{ role: 'user', content: 'find payment clause' }] },
  response: { tool_calls: [{ name: 'contract.search', arguments: { clause: 'payment' } }] },
  usage: { input_tokens: 12, output_tokens: 7, total_tokens: 19 },
  totalUsd: 0.003,
});
await bridge.recordToolProposal({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  toolName: 'contract.search',
  arguments: { clause: 'payment' },
  provider: 'openai-compatible-gateway',
  model: 'legal-router',
  reason: 'model proposed a contract search',
});
await bridge.recordToolExecution({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  toolName: 'contract.search',
  arguments: { clause: 'payment' },
  result: { matches: ['Section 9.2'], external_id: 'search-001' },
  ledgerStatus: 'SUCCEEDED',
});
await bridge.recordStateChange({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  reason: 'persist normalized runtime-adjacent state',
  patch: { memory_version: 1 },
  beforeSnapshot: { memory_version: 0 },
  afterSnapshot: { memory_version: 1 },
  diff: { memory_version: [0, 1] },
});
await bridge.recordTurnCompleted({
  sessionId: 'omp-session-1',
  turnId: 'turn-1',
  statePatch: { last_tool: 'contract.search' },
});

console.log(JSON.stringify({
  run_id: runId,
  events: runtime.store.events(runId).map((event) => event.type),
  tool_ledger: runtime.store.ledger(runId),
  final_state: runtime.store.finalState(runId),
}, null, 2));
