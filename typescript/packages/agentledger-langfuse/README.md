# agentledger-langfuse

Langfuse evidence and trace export adapter package for AgentLedger Runtime.

```bash
npm install agentledger-runtime agentledger-langfuse
```

```js
import { langfuseTracePayload } from 'agentledger-langfuse';
```

This package re-exports a dependency-free payload builder for Langfuse-style ingestion. Use your application HTTP client or Langfuse SDK to deliver the payload.
