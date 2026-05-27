# agentledger-sandbox-docker

TypeScript Docker sandbox adapter package for AgentLedger Runtime.

```bash
npm install agentledger-runtime agentledger-sandbox-docker
```

```js
import { DockerSandboxAdapter, DockerSandboxExecutor } from 'agentledger-sandbox-docker';

const manifest = new DockerSandboxAdapter().manifest({ network: 'deny' }, ['echo', 'ok']);
runtime.setSandbox(new DockerSandboxExecutor({
  image: 'python:3.11-slim',
  allowCommandExecution: true,
}));
```

Command execution is disabled by default and must be explicitly enabled. The executor only accepts command-style tools through `_sandbox_command` / `command`; it does not serialize arbitrary JavaScript functions into the container.
