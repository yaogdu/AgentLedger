# 多语言 Quickstart

[English](../LANGUAGE_QUICKSTART.md) | [中文](LANGUAGE_QUICKSTART.md)

AgentLedger 1.2.0 包含 Python reference runtime，以及 Go、TypeScript、Rust 的 native preview runtime-core baseline。共享承诺是 runtime-core 语义对齐：durable run、lease、Tool Ledger、evidence、replay、policy/approval/sandbox boundary、cost/failure attribution、conformance 和 official optional adapter contract。

非 Python package 是 native runtime package，不是 thin client：它们都能运行本地 native runtime loop，并报告共享 conformance checks。

## Python

安装：

```bash
python3 -m pip install agentledger-runtime
agentledger doctor
```

最小 API：

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

验证：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger conformance
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export
```

## Go

在 Go 项目中使用已发布 module：

```bash
go mod init your-module-name  # 如果项目还没有 go.mod 才需要
go get github.com/yaogdu/AgentLedger/go@v1.2.0
```

安装可选 CLI 命令：

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.2.0
agentledger-go --help
agentledger-go doctor
agentledger-go quickstart
```

本地 repo 验证：

```bash
cd go
go test . ./cmd/agentledger-go
go run ./cmd/agentledger-go conformance
```

注意：`go get` 必须在 Go module 内运行。`go install github.com/yaogdu/AgentLedger/go@v1.2.0` 会失败，因为 library package 不是 `package main`；安装 CLI 要使用 `/cmd/agentledger-go` 路径。

最小 runtime：

```go
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
```

Official optional adapter 形态：

```go
pg := agentledger.NewPostgresAdapter("agentledger", injectedSQLClient)
_ = pg.ApplyMigrations(context.Background())

s3 := agentledger.NewS3BlobStore("agentledger-test", "agentledger/blobs", injectedObjectClient)
_, ref, _ := s3.PutJSON(context.Background(), agentledger.JSONObject{"answer": "ok"})
```

## TypeScript / Node.js

当前使用 repo 内本地 package：

```bash
cd typescript
npm test
npm run check
npm run conformance
```

最小 runtime：

```js
import { Runtime, exportEvidence } from './src/index.js';

const rt = await Runtime.local('.agentledger-ts/state.json');
rt.registerTool({ name: 'docs.echo', func: async (args) => ({ echo: args.text }) });

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

Official optional adapter 形态：

```js
await new PostgresAdapter(injectedSqlClient).applyMigrations();
const s3 = new S3BlobStoreAdapter(injectedObjectClient, { bucket: 'agentledger-test' });
const { ref } = await s3.putJSON({ answer: 'ok' });
```

## Rust

在 Rust 项目中使用已发布 crates.io package：

```bash
cargo add agentledger-runtime
```

代码里以 `agentledger` 作为 library crate 导入：

```rust
use agentledger::{simple_run, AgentContext, Result, State, Value};
```

本地 repo 验证：

```bash
cd rust
cargo test --lib --bins
cargo run --quiet -- conformance
cargo run --quiet --example quickstart
```

最小 runtime：

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

Official optional adapter 形态：

```rust
use agentledger::{PostgresAdapter, S3BlobStoreAdapter};

let mut pg = PostgresAdapter::new(injected_sql_client, "agentledger");
pg.apply_migrations()?;

let mut s3 = S3BlobStoreAdapter::new(injected_object_client, "agentledger-test", "agentledger/blobs");
let (_digest, reference) = s3.put_json(&value)?;
println!("{}", reference);
```

## 聚合验证

在 repo 根目录运行：

```bash
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

1.2.0 期望：

```text
gap_count: 0
AgentLedger language parity checks passed
```

## 不要误解

- Go/TypeScript/Rust 仍是 package surface，但 runtime-core 语义已 conformance-aligned。
- 1.2.0 的 official adapter 使用 injected client 和 dry-run manifest；真实云 SDK 和 live service hardening 是后续 optional gate。
- AgentLedger 不替代 LangGraph、LangChain、LangSmith、Langfuse、Temporal、Ray、Kubernetes、vector DB 或 eval platform；它提供的是这些系统可以接入的 runtime safety/evidence layer。
