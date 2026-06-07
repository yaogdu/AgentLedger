# Language Quickstarts

[English](LANGUAGE_QUICKSTART.md) | [中文](zh/LANGUAGE_QUICKSTART.md)

AgentLedger 1.3.x has one Python reference runtime and native preview runtime-core baselines for Go, TypeScript, and Rust. The shared promise is semantic parity for runtime-core: durable runs, leases, Tool Ledger, evidence, replay, policy/approval/sandbox boundaries, cost/failure attribution, conformance, and official optional adapter contracts. Python may carry Inspector-only patch releases such as 1.3.5 while the non-Python runtime-core package baselines remain on the latest shared runtime-core tag.

The non-Python packages are native runtime packages, not thin clients: each runs a native local runtime loop and reports the shared conformance checks.

## Python

Install from PyPI:

```bash
python3 -m pip install agentledger-runtime
agentledger doctor
```

Minimal API:

```python
from agentledger import agent, run

@agent
def hello(ctx):
    ctx.write_state("message", "hello")
    return "hello world"

result = run(hello)
print(result.output)
print(result.run_id)
```

Runtime-managed tool call:

```python
from agentledger import Runtime, ToolSpec

rt = Runtime.local(".agentledger/state.sqlite")

rt.register_tool(ToolSpec(
    name="docs.echo",
    func=lambda args: {"echo": args["text"]},
    input_schema={"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}},
))

run_id, _ = rt.create_run({"input": "hello"})

async def agent(ctx, state):
    result = await ctx.call_tool("docs.echo", {"text": state["input"]})
    ctx.write_state("result", result)

# See docs/USAGE.md for CLI and async examples.
```

Verify:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger conformance
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export
```

## Go

Use the released Go module from a Go project:

```bash
go mod init your-module-name  # only if your project does not have go.mod yet
go get github.com/yaogdu/AgentLedger/go@v1.3.1
```

Install the optional CLI command:

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.3.1
agentledger-go --help
agentledger-go doctor
agentledger-go quickstart
```

Local repo verification:

```bash
cd go
go test . ./cmd/agentledger-go
go run ./cmd/agentledger-go conformance
```

Note: `go get` must run inside a Go module. `go install github.com/yaogdu/AgentLedger/go@v1.3.1` fails because the library package is not a `package main`; use `/cmd/agentledger-go` for the CLI.

Minimal runtime:

```go
package main

import (
    "context"
    "fmt"

    agentledger "github.com/yaogdu/AgentLedger/go"
)

func main() {
    rt, err := agentledger.NewLocalRuntime(".agentledger-go/state.json")
    if err != nil { panic(err) }

    _ = rt.RegisterTool(agentledger.ToolSpec{
        Name: "docs.echo",
        Func: func(ctx context.Context, args agentledger.JSONObject) (any, error) {
            return agentledger.JSONObject{"echo": args["text"]}, nil
        },
    })

    runID, _, _ := rt.CreateRun(agentledger.JSONObject{"input": "hello"})
    _, err = rt.RunOnce(context.Background(), runID, "worker-go", "Agent", 60,
        func(ctx context.Context, agentCtx *agentledger.AgentContext, state agentledger.JSONObject) error {
            result, err := agentCtx.CallTool(ctx, "docs.echo", agentledger.JSONObject{"text": state["input"]})
            if err != nil { return err }
            return agentCtx.WriteState("result", result)
        },
    )
    if err != nil { panic(err) }
    evidence, _ := agentledger.ExportEvidence(rt.Store, runID)
    fmt.Println(evidence.Run.RunID)
}
```

Official optional adapter smoke shape:

```go
pg := agentledger.NewPostgresAdapter("agentledger", injectedSQLClient)
_ = pg.ApplyMigrations(context.Background())

mysql := agentledger.NewMySQLAdapter("agentledger", injectedSQLClient)
_ = mysql.ApplyMigrations(context.Background())

s3 := agentledger.NewS3BlobStore("agentledger-test", "agentledger/blobs", injectedObjectClient)
_, ref, _ := s3.PutJSON(context.Background(), agentledger.JSONObject{"answer": "ok"})
fmt.Println(ref)
```

## TypeScript / Node.js

Use the local package in this repository today:

```bash
cd typescript
npm test
npm run check
npm run conformance
```

Minimal runtime:

```js
import { Runtime, exportEvidence } from './src/index.js';

const rt = await Runtime.local('.agentledger-ts/state.json');
rt.registerTool({
  name: 'docs.echo',
  func: async (args) => ({ echo: args.text }),
});

const { runId } = await rt.createRun({ input: 'hello' });
await rt.runOnce({
  runId,
  workerId: 'worker-ts',
  agentRole: 'Agent',
  agent: async (ctx, state) => {
    const result = await ctx.callTool('docs.echo', { text: state.input });
    await ctx.writeState('result', result);
  },
});

console.log(exportEvidence(rt.store, runId).run.run_id);
```

Simple API:

```js
import { simpleRun } from './src/index.js';

const result = await simpleRun(async (_ctx, state) => ({ message: `hello ${state.name}` }), {
  initialState: { name: 'world' },
});
console.log(result.output);
```

Official optional adapter smoke shape:

```js
import { MySQLAdapter, PostgresAdapter, S3BlobStoreAdapter } from './src/index.js';

await new PostgresAdapter(injectedSqlClient).applyMigrations();
await new MySQLAdapter(injectedSqlClient).applyMigrations();
const s3 = new S3BlobStoreAdapter(injectedObjectClient, { bucket: 'agentledger-test' });
const { ref } = await s3.putJSON({ answer: 'ok' });
console.log(ref);
```

## Rust

Use the published crates.io package in a Rust project:

```bash
cargo add agentledger-runtime
```

Import the library crate as `agentledger`:

```rust
use agentledger::{simple_run, AgentContext, Result, State, Value};
```

Local repo verification:

```bash
cd rust
cargo test --lib --bins
cargo run --quiet -- conformance
cargo run --quiet --example quickstart
```

Minimal runtime:

```rust
use agentledger::{simple_run, AgentContext, Result, State, Value};

fn agent(ctx: &mut AgentContext, input: State) -> Result<Option<Value>> {
    if let Some(name) = input.get("name") {
        ctx.write_state("message", Value::String(format!("hello {:?}", name)));
    }
    Ok(Some(Value::String("done".to_string())))
}

fn main() -> Result<()> {
    let mut input = State::new();
    input.insert("name".to_string(), "world".into());
    let result = simple_run(agent, input)?;
    println!("{}", result.run_id);
    Ok(())
}
```

Official optional adapter smoke shape:

```rust
use agentledger::{MySQLAdapter, PostgresAdapter, S3BlobStoreAdapter};

let mut pg = PostgresAdapter::new(injected_sql_client, "agentledger");
pg.apply_migrations()?;

let mut mysql = MySQLAdapter::new(injected_sql_client, "agentledger");
mysql.apply_migrations()?;

let mut s3 = S3BlobStoreAdapter::new(injected_object_client, "agentledger-test", "agentledger/blobs");
let (_digest, reference) = s3.put_json(&value)?;
println!("{}", reference);
```

## Aggregate Verification

From the repository root:

```bash
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

Expected for 1.3.x:

```text
gap_count: 0
AgentLedger language parity checks passed
```

## What Not To Assume

- Go/TypeScript/Rust are package surfaces, even though runtime-core semantics are conformance-aligned.
- Official adapters in 1.3.x use injected clients and dry-run manifests; real cloud SDKs and live service hardening are optional follow-up gates.
- AgentLedger does not replace LangGraph, LangChain, LangSmith, Langfuse, Temporal, Ray, Kubernetes, vector DBs, or eval platforms. It provides the runtime safety/evidence layer those systems can integrate with.
