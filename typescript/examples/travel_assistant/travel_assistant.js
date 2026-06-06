#!/usr/bin/env node
/**
 * Travel Assistant Demo — AgentLedger TypeScript Interactive Demo
 * ================================================================
 * 旅游助手交互式演示 — 每一步展示数据库里的实际变化
 *
 * Usage:
 *   node typescript/examples/travel_assistant/travel_assistant.js
 *   node typescript/examples/travel_assistant/travel_assistant.js .agentledger-ts
 */

import { createInterface } from 'node:readline';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  Runtime, JSONStore, LocalBlobStore, RetryableAgentError,
  exportEvidence, replay, costAttribution,
} from '../../src/index.js';

// ════════════════════════════════════════════════════════════
// ANSI Colors
// ════════════════════════════════════════════════════════════
const C = {
  R: '\x1b[91m', G: '\x1b[92m', Y: '\x1b[93m', B: '\x1b[94m',
  M: '\x1b[95m', C: '\x1b[96m', BOLD: '\x1b[1m', DIM: '\x1b[2m', RST: '\x1b[0m',
};

// ════════════════════════════════════════════════════════════
// Mock data
// ════════════════════════════════════════════════════════════
const MOCK_FLIGHTS = [
  { id: 'FL-002', from_city: 'Beijing', from_code: 'PEK', to_city: 'Tokyo', to_code: 'NRT', date: '2025-06-15', airline: 'JAL', price_usd: 580 },
];
const MOCK_HOTELS = [
  { id: 'HT-002', city: 'Tokyo', name: 'APA Hotel Shinjuku', nightly_usd: 85, stars: 3 },
];
const MOCK_WEATHER = { Tokyo: { temp_c: 24, condition: 'Partly Cloudy', humidity: 65 } };
const bookingDB = {};

// ════════════════════════════════════════════════════════════
// Tool implementations
// ════════════════════════════════════════════════════════════

function searchFlights(args) {
  const origin = (args.from || '').trim().toLowerCase();
  const dest = (args.to || '').trim().toLowerCase();
  const results = MOCK_FLIGHTS.filter(f =>
    (f.from_city.toLowerCase().includes(origin) || f.from_code.toLowerCase().includes(origin)) &&
    (f.to_city.toLowerCase().includes(dest) || f.to_code.toLowerCase().includes(dest))
  );
  return { results, count: results.length };
}

function searchHotels(args) {
  const city = (args.city || '').trim().toLowerCase();
  const results = MOCK_HOTELS.filter(h => h.city.toLowerCase() === city);
  return { results, count: results.length };
}

function checkWeather(args) {
  const city = (args.city || '').trim();
  return { city, ...(MOCK_WEATHER[city] || { temp_c: 20, condition: 'Unknown' }) };
}

function bookFlight(args) {
  const ref = `BK-F-${args.flight_id}-${(args.passenger || '').slice(0, 3).toUpperCase()}`;
  if (bookingDB[ref]) return bookingDB[ref];
  const f = MOCK_FLIGHTS.find(f => f.id === args.flight_id);
  if (!f) throw new Error(`Flight not found: ${args.flight_id}`);
  const booking = { booking_ref: ref, type: 'flight', airline: f.airline, price_usd: f.price_usd, status: 'confirmed', external_id: ref };
  bookingDB[ref] = booking;
  return booking;
}

function bookHotel(args) {
  const ref = `BK-H-${args.hotel_id}-${(args.guest || '').slice(0, 3).toUpperCase()}`;
  if (bookingDB[ref]) return bookingDB[ref];
  const h = MOCK_HOTELS.find(h => h.id === args.hotel_id);
  if (!h) throw new Error(`Hotel not found: ${args.hotel_id}`);
  const booking = { booking_ref: ref, type: 'hotel', name: h.name, price_total_usd: h.nightly_usd * 5, status: 'confirmed', external_id: ref };
  bookingDB[ref] = booking;
  return booking;
}

// ════════════════════════════════════════════════════════════
// Agent function
// ════════════════════════════════════════════════════════════

async function travelPlanner(ctx, state) {
  // Phase 1: Research
  const flights = await ctx.callTool('travel.search_flights', { from: 'Beijing', to: 'Tokyo' });
  const hotels = await ctx.callTool('travel.search_hotels', { city: 'Tokyo' });
  const weather = await ctx.callTool('travel.check_weather', { city: 'Tokyo' });
  await ctx.writeState('research', { flights: flights.count, hotels: hotels.count, weather: weather.temp_c });

  // Phase 2: Book flight (approval required)
  const flight = await ctx.callTool('travel.book_flight', {
    flight_id: 'FL-002', passenger: 'Demo User',
    _logical_operation: 'book-demo-flight',
  });

  // Phase 3: Simulated crash on attempt 2
  if (ctx.attempt === 2) {
    throw new RetryableAgentError('after flight booking');
  }

  // Phase 4: Book hotel (approval required)
  const hotel = await ctx.callTool('travel.book_hotel', {
    hotel_id: 'HT-002', check_in: '2025-06-15', check_out: '2025-06-20',
    guest: 'Demo User', _logical_operation: 'book-demo-hotel',
  });

  await ctx.writeState('bookings', { flight: flight.booking_ref, hotel: hotel.booking_ref });
  await ctx.writeState('trip_status', 'confirmed');
}

// ════════════════════════════════════════════════════════════
// Display helpers
// ════════════════════════════════════════════════════════════

function wait(msg = 'Press Enter to continue') {
  return new Promise((resolve) => {
    process.stdout.write(`\n${C.DIM}  ⏎ ${msg}...${C.RST}`);
    const rl = createInterface({ input: process.stdin, output: process.stdout });
    rl.once('line', () => { rl.close(); resolve(); });
  });
}

function showRows(label, headers, rows, color = C.C) {
  if (!rows || rows.length === 0) {
    console.log(`\n  ${color}${label}:${C.RST} ${C.DIM}(empty)${C.RST}`);
    return;
  }
  console.log(`\n  ${color}${label} (${rows.length} rows):${C.RST}`);
  for (const row of rows) {
    const items = headers.map((h, i) => `${h}=${C.BOLD}${row[i]}${C.RST}`);
    console.log(`    ${C.DIM}${items.join(' | ')}${C.RST}`);
  }
}

function showDB(store, runID) {
  // Runs
  const runData = store.run(runID);
  const runRows = [];
  if (runData) {
    const shortID = runData.run_id.length > 24 ? runData.run_id.slice(0, 24) + '...' : runData.run_id;
    runRows.push([shortID, runData.status, String(runData.state_version)]);
  }
  showRows('Runs', ['run_id', 'status', 'state_version'], runRows, C.B);

  // Steps
  const steps = store.steps(runID);
  const stepRows = steps.map(s => {
    const shortID = s.step_id.length > 24 ? s.step_id.slice(0, 24) + '...' : s.step_id;
    return [shortID, s.status, String(s.attempt)];
  });
  showRows('Steps', ['step_id', 'status', 'attempt'], stepRows, C.B);

  // Tool Ledger
  const ledger = store.ledger(runID);
  const ledgerRows = ledger.map(tl => {
    const key = tl.idempotency_key;
    const parts = key.split(':');
    const shortKey = parts.length >= 2 ? parts[parts.length - 2] + ':' + parts[parts.length - 1].slice(0, 10) : key.slice(0, 25);
    return [tl.tool_name, tl.status, shortKey];
  });
  showRows('Tool Ledger', ['tool', 'status', 'idemp_key'], ledgerRows, C.Y);

  // Approval requests
  const approvals = store.approvalRequests(runID);
  const approvalRows = approvals.map(a => [a.tool_name, a.status, a.approved_by || '-']);
  showRows('Approval Requests', ['tool', 'status', 'approved_by'], approvalRows, C.R);

  console.log();
}

// ════════════════════════════════════════════════════════════
// Main
// ════════════════════════════════════════════════════════════

async function main() {
  const root = process.argv[2] || await mkdtemp(join(tmpdir(), 'agentledger-ts-'));

  // Intro
  console.log(`\n${C.BOLD}${C.C}  ╔════════════════════════════════════════════════════╗${C.RST}`);
  console.log(`${C.BOLD}${C.C}  ║   AgentLedger Travel Assistant (TS) — Interactive Demo  ║${C.RST}`);
  console.log(`${C.BOLD}${C.C}  ║   See real database state at every step                 ║${C.RST}`);
  console.log(`${C.BOLD}${C.C}  ╚════════════════════════════════════════════════════╝${C.RST}`);

  console.log(`\n  ${C.DIM}AgentLedger — Durable Execution Runtime for AI Agents${C.RST}`);
  console.log(`  ┌────────────────────────────────────────────────────┐`);
  console.log(`  │  ${C.G}✓${C.RST} Durable execution — crash recovery              │`);
  console.log(`  │  ${C.G}✓${C.RST} Tool Ledger — idempotent replay                │`);
  console.log(`  │  ${C.G}✓${C.RST} Approval gates — human-in-the-loop              │`);
  console.log(`  │  ${C.G}✓${C.RST} Policy engine — role-based access               │`);
  console.log(`  │  ${C.G}✓${C.RST} Budget control — tool call limits               │`);
  console.log(`  │  ${C.G}✓${C.RST} Evidence export — full audit trail              │`);
  console.log(`  └────────────────────────────────────────────────────┘`);

  await wait('Press Enter to start / 按 Enter 开始');

  // ════════════════════════════════════════════════════════
  // Step 1: Setup
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.B}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.B}  Step 1: Initialize — Register tools, configure policy${C.RST}`);
  console.log(`${C.BOLD}${C.B}${'═'.repeat(60)}${C.RST}`);

  const store = await JSONStore.open(`${root}/state.json`);
  const rt = new Runtime(store);
  rt.setBudget({ maxToolCalls: 25 });

  for (const t of ['travel.search_flights', 'travel.search_hotels', 'travel.check_weather',
    'travel.book_flight', 'travel.book_hotel']) {
    rt.policy.allowTool('TravelPlanner', t);
  }

  rt.registerTool({
    name: 'travel.search_flights', version: 'v1', sideEffect: 'none', riskLevel: 'low',
    inputSchema: { type: 'object', required: ['from', 'to'] },
    outputSchema: { type: 'object' },
    func: searchFlights,
  });
  rt.registerTool({
    name: 'travel.search_hotels', version: 'v1', sideEffect: 'none', riskLevel: 'low',
    inputSchema: { type: 'object', required: ['city'] },
    outputSchema: { type: 'object' },
    func: searchHotels,
  });
  rt.registerTool({
    name: 'travel.check_weather', version: 'v1', sideEffect: 'none', riskLevel: 'low',
    inputSchema: { type: 'object', required: ['city'] },
    outputSchema: { type: 'object' },
    func: checkWeather,
  });
  rt.registerTool({
    name: 'travel.book_flight', version: 'v1', sideEffect: 'external_write', riskLevel: 'high',
    idempotencyRequired: true, approvalRequired: true,
    inputSchema: { type: 'object', required: ['flight_id', 'passenger'] },
    outputSchema: { type: 'object' },
    func: bookFlight,
  });
  rt.registerTool({
    name: 'travel.book_hotel', version: 'v1', sideEffect: 'external_write', riskLevel: 'high',
    idempotencyRequired: true, approvalRequired: true,
    inputSchema: { type: 'object', required: ['hotel_id', 'guest'] },
    outputSchema: { type: 'object' },
    func: bookHotel,
  });

  const { runId } = await rt.createRun({ trip: 'Tokyo', budget_usd: 3000 });
  console.log(`\n  ${C.B}Run created: ${C.BOLD}${runId}${C.RST}`);
  showDB(store, runId);
  await wait('Press Enter to continue');

  // ════════════════════════════════════════════════════════
  // Step 2: Attempt 1 — Approval interception
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.R}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.R}  Step 2: Attempt 1 — Agent runs → Approval triggered${C.RST}`);
  console.log(`${C.BOLD}${C.R}${'═'.repeat(60)}${C.RST}`);
  console.log(`\n  ${C.DIM}Agent executing: search flights → search hotels → check weather → book flight...${C.RST}`);

  await rt.runOnce({ runId, workerId: 'worker-node', agentRole: 'TravelPlanner', agent: travelPlanner });

  console.log(`\n  ${C.R}book_flight triggered approval! Runtime paused, waiting for human.${C.RST}`);
  showDB(store, runId);
  console.log(`  ${C.R}Note: Tool Ledger has RESERVED entry, approval status is PENDING${C.RST}`);
  await wait('Press Enter to approve / 按 Enter 审批');

  for (const req of store.approvalRequests(runId)) {
    if (req.status === 'PENDING') {
      await store.approveRequest(req.approval_id, { approver: 'traveler', reason: 'Within budget, approved' });
      console.log(`\n  ${C.G}✅ Approved: ${req.tool_name} — by traveler${C.RST}`);
    }
  }
  showDB(store, runId);
  await wait('Press Enter to continue');

  // ════════════════════════════════════════════════════════
  // Step 3: Attempt 2 — Execute + Crash
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.Y}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.Y}  Step 3: Attempt 2 — Approved → Execute booking → Simulated crash${C.RST}`);
  console.log(`${C.BOLD}${C.Y}${'═'.repeat(60)}${C.RST}`);
  console.log(`\n  ${C.DIM}Re-running agent (approval passed, book_flight will execute)...${C.RST}`);

  await rt.runOnce({ runId, workerId: 'worker-node', agentRole: 'TravelPlanner', agent: travelPlanner });

  console.log(`\n  ${C.Y}Agent booked flight, then crashed before committing state!${C.RST}`);
  console.log(`  ${C.Y}Flight is booked in external system, but agent state was NOT persisted.${C.RST}`);
  showDB(store, runId);
  console.log(`  ${C.Y}Key: Tool Ledger book_flight status = ${C.G}SUCCEEDED${C.Y} (external side effect executed)${C.RST}`);
  console.log(`  ${C.Y}      Step status = retry_scheduled (state not committed, waiting for retry)${C.RST}`);
  await wait('Press Enter to continue');

  // ════════════════════════════════════════════════════════
  // Step 4: Attempt 3 — Recovery + Hotel approval
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.G}  Step 4: Attempt 3 — Crash recovery → Tool Ledger idempotent replay${C.RST}`);
  console.log(`${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);
  console.log(`\n  ${C.DIM}Agent re-executes. book_flight: Tool Ledger sees SUCCEEDED record...${C.RST}`);
  console.log(`  ${C.DIM}${C.G}→ Returns cached result, no duplicate API call, no double charge!${C.RST}`);

  await rt.runOnce({ runId, workerId: 'worker-node', agentRole: 'TravelPlanner', agent: travelPlanner });

  console.log(`\n  ${C.G}✅ Flight idempotent replay successful! (no duplicate _book_flight call)${C.RST}`);
  console.log(`  ${C.R}Hotel booking → triggers approval again${C.RST}`);

  for (const req of store.approvalRequests(runId)) {
    if (req.status === 'PENDING') {
      await store.approveRequest(req.approval_id, { approver: 'traveler', reason: 'Hotel within budget, approved' });
      console.log(`\n  ${C.G}✅ Approved: ${req.tool_name} — by traveler${C.RST}`);
    }
  }
  showDB(store, runId);
  await wait('Press Enter to continue');

  // ════════════════════════════════════════════════════════
  // Step 5: Attempt 4 — Complete
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.G}  Step 5: Attempt 4 — Hotel approved → Full execution → State committed${C.RST}`);
  console.log(`${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);

  const ok = await rt.runOnce({ runId, workerId: 'worker-node', agentRole: 'TravelPlanner', agent: travelPlanner });
  if (!ok) {
    console.error('Recovery failed');
    process.exit(1);
  }
  if (Object.keys(bookingDB).length !== 2) {
    console.error(`Expected 2 bookings, got ${Object.keys(bookingDB).length}`);
    process.exit(1);
  }

  console.log(`\n  ${C.G}✅ Travel planning complete! State persisted to database.${C.RST}`);
  showDB(store, runId);
  console.log(`  ${C.G}Step status = completed, State has bookings + trip_status${C.RST}`);
  console.log(`  ${C.G}External bookings: [${Object.keys(bookingDB).join(', ')}] (2 total, no duplicates)${C.RST}`);
  await wait('Press Enter to continue');

  // ════════════════════════════════════════════════════════
  // Step 6: Evidence + Cost + Replay
  // ════════════════════════════════════════════════════════
  console.log(`\n${C.BOLD}${C.M}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.M}  Step 6: Evidence export + Cost attribution + Replay verification${C.RST}`);
  console.log(`${C.BOLD}${C.M}${'═'.repeat(60)}${C.RST}`);

  const bundle = exportEvidence(store, runId);
  const replayResult = replay(store, runId);
  const cost = costAttribution(store, runId);

  console.log(`\n  ${C.M}Cost attribution: ${cost.total?.tool_calls ?? 0} tool calls${C.RST}`);
  console.log(`  ${C.M}Replay: ${replayResult.event_count} events, safe=${C.G}${replayResult.replay_safe}${C.RST}`);
  console.log(`  ${C.M}Evidence bundle: ${bundle.events.length} events total${C.RST}`);

  // Final summary
  console.log(`\n${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);
  console.log(`${C.BOLD}${C.G}  Summary: What AgentLedger (TypeScript) did in this demo${C.RST}`);
  console.log(`${C.BOLD}${C.G}${'═'.repeat(60)}${C.RST}`);
  console.log(`
  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │  ${C.G}✓ Durable execution${C.RST}  Crash → auto retry, state preserved         │
  │                   Step: retry_scheduled → completed           │
  │                                                          │
  │  ${C.G}✓ Tool Ledger${C.RST}      Idempotent replay, flight booked ${C.BOLD}1x${C.RST} only       │
  │                   SUCCEEDED → cached result on retry        │
  │                                                          │
  │  ${C.G}✓ Approval gates${C.RST}    Flight + hotel each trigger approval          │
  │                   approval_requests records in store        │
  │                                                          │
  │  ${C.G}✓ Policy engine${C.RST}     Each tool call checked by policy             │
  │                   TravelPlanner role allowed              │
  │                                                          │
  │  ${C.G}✓ Budget control${C.RST}    Tracked ${cost.total?.tool_calls ?? 0} tool calls                       │
  │                   BudgetController.beforeToolCall()       │
  │                                                          │
  │  ${C.G}✓ Evidence export${C.RST}   ${bundle.events.length} events recorded                         │
  │                   events stored in JSON store              │
  │                                                          │
  │  ${C.G}✓ Cost attribution${C.RST}  Auto-recorded per run                        │
  │                   CostAttribution by agent                │
  │                                                          │
  │  ${C.G}✓ Replay engine${C.RST}     Event hash verification passed                │
  │                   Verify history without re-running       │
  │                                                          │
  └──────────────────────────────────────────────────────────┘
`);

  console.log(`  ${C.DIM}Storage file: ${root}/state.json${C.RST}`);
  console.log(`  ${C.DIM}Run: node typescript/examples/travel_assistant/travel_assistant.js${C.RST}`);
  console.log();
}

main().catch(err => { console.error(err); process.exit(1); });
