# 使用指南

本文档说明如何在本地使用 AgentLedger。英文版本见 `../USAGE.md`。

## 从源码运行

当前 runtime-core 没有强制第三方依赖。

请使用 Python 3.11 或更高版本。如果系统默认 `python3` 较旧，请替换为 `python3.11`。

从 PyPI 安装：

```bash
python3 -m pip install agentledger-runtime
agentledger --help
agentledger doctor
```

PyPI distribution 名是 `agentledger-runtime`；代码中仍然这样 import：

```python
from agentledger import agent, run
```

`agentledger --help` 和 `agentledger doctor` 都会输出 GitHub 文档地址，方便用户安装后继续阅读和使用。

```bash
PYTHONPATH=src python3 -m agentledger --help
PYTHONPATH=src python3 -m agentledger doctor
```

开发模式安装：

```bash
python3 -m pip install -e .
agentledger --help
```

可选 adapter 依赖：

```bash
python3 -m pip install "agentledger-runtime[postgres]"
python3 -m pip install "agentledger-runtime[s3]"
```

如果是从仓库本地开发，再使用 `python3 -m pip install -e ".[postgres]"` 或 `python3 -m pip install -e ".[s3]"`。

## 前 10 分钟

先用这条路径验证本地 runtime，再继续读架构和实现文档：

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo run examples/side_effect_idempotency
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo debug <run_id> --json --include-diffs
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo ledger <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo replay <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo evidence <run_id> --html ./evidence.html
```

重点不是输出文本，而是确认这个 run 具备 durable state、带 lease 的 step、Tool Ledger entry、无副作用 replay，以及可导出的 evidence。

## Hello World

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello world"

result = run(hello)
print(result.output)
print(result.run_id)
```

运行示例：

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
```

这个例子虽然很小，但底层仍然会创建 durable run、claim step、记录 event、提交状态，并支持 evidence export。

## Side-effect 幂等 Demo

这个 demo 模拟“外部副作用成功后 worker crash”。重试时 runtime 会通过 Tool Ledger 避免重复执行外部写入。

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo run examples/side_effect_idempotency
```

使用输出里的 `run_id`：

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo debug <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo ledger <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo replay <run_id>
PYTHONPATH=src python3 -m agentledger --root .agentledger-demo evidence <run_id> --dir ./evidence/<run_id>
```

## 注册 Runtime-managed Tool

外部能力应该通过 `ctx.call_tool(...)` 进入 runtime，而不是在 Agent 里直接调用高风险 SDK。

dependency-free schema subset 支持 portable object、array、string、numeric、enum/const、composition 和 uniqueness 约束；framework-specific validator 仍可放在 optional adapter。

```python
from agentledger import Runtime

rt = Runtime.local(".agentledger-tools")

@rt.tool(
    name="docs.read",
    description="Read a document by path.",
    side_effect="none",
    input_schema={
        "type": "object",
        "required": ["path"],
        "properties": {"path": {"type": "string", "minLength": 1}},
        "additionalProperties": False,
    },
)
def read_doc(args):
    return {"path": args["path"], "content": ""}
```

导出工具清单：

```bash
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONPATH=src python3 -m agentledger tools manifest --format openai --example examples/docs
```

## Policy 和 Approval

检查 policy：

```bash
PYTHONPATH=src python3 -m agentledger policy check examples/policy/local.policy.yaml ExecutorAgent github.create_issue medium
```

带 policy 运行：

```bash
PYTHONPATH=src python3 -m agentledger --policy examples/policy/local.policy.yaml run examples/side_effect_idempotency
```

审批命令：

```bash
PYTHONPATH=src python3 -m agentledger approvals <run_id>
PYTHONPATH=src python3 -m agentledger approve <approval_id> --approver alice --reason "reviewed"
PYTHONPATH=src python3 -m agentledger deny <approval_id> --approver alice --reason "not allowed"
```

## Evidence、Replay、Debug、Regression Checks

AgentLedger 以 evidence 为中心。大部分可靠性工具只读取现有 runtime metadata，不调用真实外部工具或模型。

```bash
PYTHONPATH=src python3 -m agentledger evidence <run_id> --out ./bundle.json
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./bundle-dir
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs --include-states --html ./time-travel.html
PYTHONPATH=src python3 -m agentledger evidence-check <run_id>  # side-effect-free evidence invariant check
PYTHONPATH=src python3 -m agentledger review checklist <run_id> --fail-on-risk
```

Regression / corpus：

```bash
PYTHONPATH=src python3 -m agentledger evidence-regression ./golden-bundle.json ./current-bundle-dir
PYTHONPATH=src python3 -m agentledger corpus seed --list-builtins
PYTHONPATH=src python3 -m agentledger corpus seed minimal-success
PYTHONPATH=src python3 -m agentledger corpus seed tool-ledger-success
PYTHONPATH=src python3 -m agentledger corpus seed media-stream-checkpoint
PYTHONPATH=src python3 -m agentledger corpus add side-effect ./golden-bundle.json
PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-bundle-dir
PYTHONPATH=src python3 -m agentledger divergence ./golden-bundle.json ./current-bundle-dir --evidence-paths
```

## Worker、取消和恢复

```bash
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker-run examples/transient_retry
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker serve examples/transient_retry --max-loops 5
PYTHONPATH=src python3 -m agentledger --root .agentledger-worker worker plan examples/transient_retry --replicas 2
PYTHONPATH=src python3 -m agentledger status <run_id>
PYTHONPATH=src python3 -m agentledger cancel <run_id> --reason "operator requested"
PYTHONPATH=src python3 -m agentledger recover-expired
```

## 存储

默认本地存储：

```text
SQLite WAL StateStore + local file BlobStore
```

SQLite：

```bash
PYTHONPATH=src python3 -m agentledger migrate status
PYTHONPATH=src python3 -m agentledger migrate ddl --dialect sqlite
```

Postgres 是可选 experimental adapter：

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database \
PYTHONPATH=src python3 -m agentledger migrate up --dialect postgres
```

不要把 conformance 或实验命令指向真实业务数据。

## Media 和 Stream

runtime-core 只保存 refs、metadata、lineage、offset 和 checkpoint，不做音视频解码或 stream transport。

```bash
PYTHONPATH=src python3 examples/media_stream/basic_media_stream.py
PYTHONPATH=src python3 examples/media_stream/managed_tool.py
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/media_stream
```

## 边界检查和 Conformance

```bash
PYTHONPATH=src python3 -m agentledger lint boundary examples src --exclude src/agentledger --no-fail
PYTHONPATH=src python3 -m agentledger lint boundary ./my_agents --rules examples/lint/boundary_rules.json
PYTHONPATH=src python3 -m agentledger conformance
PYTHONPATH=src python3 -m agentledger state conformance --backend sqlite
PYTHONPATH=src python3 -m agentledger blob conformance --backend local
PYTHONPATH=src python3 -m agentledger worker conformance --backend sqlite --concurrent
PYTHONPATH=src python3 -m agentledger adapter conformance --kind langchain
PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.1.0 --out ./postgres-certification.json
```

`adapter certify` 会生成机器可读的 adapter certification bundle，包含 package metadata、conformance command、smoke command、required external services、security assumptions、known limitations，以及 production validation 是否仍然依赖真实基础设施。例如 Postgres/S3/Docker/Temporal 会标记为 `external-required`，直到在真实服务凭证、并发/负载、restore 或 rollback drill 下完成验证。

## 下一步读什么

| 需求 | 文档 |
| --- | --- |
| 理解 runtime boundary | `ARCHITECTURE.md` |
| 理解 state、Tool Ledger、replay 和 worker 内部机制 | `DESIGN_AND_IMPLEMENTATION.md` |
| 扩展 tool、storage、framework、sandbox 或 observability | `EXTENSIBILITY.md` |
| 查看 stable、preview、roadmap 边界 | `IMPLEMENTATION_STATUS.md` 和 `../MATURITY_MODEL.md` |
| 准备 release 或 contribution | `RELEASE_CHECKLIST.md` 和 `../../CONTRIBUTING.md` |
