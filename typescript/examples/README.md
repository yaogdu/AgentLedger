# AgentLedger TypeScript Examples

Run from `typescript/` unless noted.

## Quickstart

```bash
cd typescript
node examples/quickstart/quickstart.js
```

Source: `quickstart/quickstart.js`

## Adoption Demos

```bash
cd typescript
node examples/three_minute_demo/three_minute_demo.js
node examples/mcp_governance/mcp_governance.js
node examples/omp_bridge/omp_bridge.js
```

The 3-minute demo shows crash/retry without duplicate external writes. The MCP governance demo shows descriptor annotations flowing into approval, sandbox metadata, idempotency, and audit evidence. The OMP bridge demo maps normalized runtime records into AgentLedger evidence without depending on OMP internals.

## CLI Quickstart

```bash
cd typescript
node src/cli.js quickstart
node src/cli.js conformance
```

Package surface: `agentledger-runtime`. See `../README.md` for package metadata and API examples.


## Travel Assistant

`travel_assistant/travel_assistant.js` is a larger interactive demo. Treat it as an example app, not part of the npm package release gate.

Run from the repository root:

```bash
node typescript/examples/travel_assistant/travel_assistant.js
```

Or pass a custom local state root:

```bash
node typescript/examples/travel_assistant/travel_assistant.js .agentledger-ts
```
