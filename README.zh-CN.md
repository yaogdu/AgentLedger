# AgentLedger

[English](README.md) | [中文](README.zh-CN.md)

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Version 1.0.0 stable](https://img.shields.io/badge/Version-1.0.0--stable-111827)
![License Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-0f766e)
![Runtime Durable](https://img.shields.io/badge/Runtime-durable%20execution-1f6feb)
![Storage SQLite/Postgres](https://img.shields.io/badge/Storage-SQLite%20%7C%20Postgres-b45309)
![Replay Evidence](https://img.shields.io/badge/Replay-evidence%20driven-7c3aed)
![Tool Ledger](https://img.shields.io/badge/Tools-ledger%20guarded-d97706)

AgentLedger `1.0.0` 是一个面向 AI Agent 的 durable execution 与 reliability runtime。它不负责让 Agent 更会“思考”，而是让 Agent run 在 worker 崩溃、工具失败、prompt 变更和长任务恢复时，仍然具备持久化、可审计、可重放、可治理和可恢复能力。

大多数 Agent 框架关注 planning、reasoning 和 workflow logic。AgentLedger 放在 LangChain、LangGraph、CrewAI、AutoGen、OpenAI Agents SDK、LlamaIndex、Semantic Kernel 或自定义 Agent 的下方或旁边，提供 state、tool、evidence、replay、recovery 相关的 runtime guarantees。

Python 是当前 reference implementation。后续 Rust、TypeScript、Go 实现应对齐同一份 language-neutral runtime contract。

## 快速判断

| 问题 | 回答 |
| --- | --- |
| 哪些是稳定的？ | Python v1.0 runtime-core：本地 durable execution、Tool Ledger、evidence/replay、policy/approval/sandbox boundary、cost/failure report、worker/conformance 和 runtime contract。 |
| 哪些是可选的？ | Postgres、S3/MinIO、framework-native package、OTLP collector transport、sandbox infrastructure、distributed deployment recipe 和真实服务 hardening。 |
| 哪些是 preview？ | Media/stream artifact contracts，以及部分 dependency-free adapter facade。 |
| 哪些不属于 core？ | Planning engine、完整 eval 系统、RAG/vector memory、trace store、托管应用产品和托管 sandbox infrastructure。 |
| 其它语言怎么做？ | 这个 repo 是 contract-first。Python 是 reference runtime；TypeScript、Rust、Go 后续应对齐 `contracts/agentledger.runtime.v1.json` 和共享 conformance fixtures。 |

## 范围原则

AgentLedger 的 runtime 要保持“薄但不可替代”：core 只内建那些不在 runtime boundary 内就无法可靠保证的能力。其它能力通过 adapter、contract、conformance test 和 example 接入成熟生态。

```text
Runtime core:
  durable execution、governed tool use、evidence、replay、policy hook、
  lease、fencing、cancellation、budget、attribution、conformance

Adapters:
  agent framework、storage backend、blob store、sandbox、model provider、
  observability sink、policy engine、MCP、media processor、deployment

External tools:
  planning/workflow engine、完整 eval 系统、trace store、RAG 系统、
  distributed scheduler、sandbox infrastructure
```

大部分扩展能力都按三层处理：

```text
Core contract:
  稳定接口、事件、不变量、失败语义和 conformance

Built-in minimal implementation:
  dependency-free 的本地默认实现，用于 quickstart、demo、测试和轻量使用

Optional production adapter:
  面向真实基础设施、框架和运维环境的成熟集成
```

例如 sandbox semantics 属于 core，但 sandbox infrastructure 不属于 core。core 负责 `SandboxPolicy`、fail-closed routing、audit/evidence record 和 replay safety；Docker、E2B、bubblewrap、Kubernetes/gVisor、Firecracker 或自定义 executor 都是 adapter。

## 适合什么场景

- 长期运行的 Agent task 需要在 crash 或 restart 后从最后一次 checkpoint 恢复
- 外部副作用工具需要 Tool Ledger、idempotency key 和 causal request record，避免重复写入
- 需要导出完整 evidence bundle，用于 debug、review、regression check 和 audit trail
- 需要基于历史 run 做 replay，且不重复调用模型或真实工具
- 需要在 runtime 层控制 tool permission、approval、sandbox boundary、cost budget 和 failure semantics
- 需要为 Agent 框架、存储、blob store、tool system、trace、sandbox executor 提供 adapter seam
- 希望 core 保持 dependency-free，同时可以选择 Postgres、S3/MinIO、OTLP 和各类框架 adapter

## 主要能力

- Durable state machine：run、step、session、lease、fencing token、retry、cancellation、checkpoint resume
- Tool governance：schema validation、capability policy、approval gate、sandbox routing、audit event、side-effect status tracking
- Evidence and replay：event-level WAL、payload archive、evidence bundle、静态 HTML debug export、replay、diff、divergence、shadow run
- Reliability engineering：failure taxonomy、failure injection suite、evidence regression gate、adversarial review checklist、backup readiness check、retention plan
- Cost and budget control：token/cost record、in-flight budget enforcement、按 run/agent/step/tool/model 做归因
- Framework adoption：plain Python API，以及 LangGraph、LangChain、CrewAI、AutoGen、OpenAI Agents SDK、LlamaIndex、Semantic Kernel、MCP-style tools/context adapter facade
- Storage choices：默认 SQLite WAL + local blobs；可选 Postgres StateStore 和 S3/MinIO BlobStore adapter
- Media and stream contracts：durable refs、metadata、lineage、chunk refs、offsets、watermarks、replay validation；core 不内置 codec 或 stream transport

## 架构说明

![AgentLedger runtime architecture](docs/assets/agentledger-runtime-architecture.svg)

- 文档总览：[docs/zh/README.md](docs/zh/README.md)
- 架构说明：[docs/zh/ARCHITECTURE.md](docs/zh/ARCHITECTURE.md)
- 设计与实现：[docs/zh/DESIGN_AND_IMPLEMENTATION.md](docs/zh/DESIGN_AND_IMPLEMENTATION.md)
- Runtime contract：[docs/zh/RUNTIME_SPEC.md](docs/zh/RUNTIME_SPEC.md)

## 仓库规范

- 许可证：[Apache-2.0](LICENSE)
- 安全报告：[SECURITY.md](SECURITY.md)
- 贡献方式：[CONTRIBUTING.md](CONTRIBUTING.md)
- 社区行为：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 发布检查：[docs/zh/RELEASE_CHECKLIST.md](docs/zh/RELEASE_CHECKLIST.md)
- 兼容策略：[docs/VERSIONING.md](docs/VERSIONING.md)

## 快速开始

### 1. 安装

从 PyPI 安装：

```bash
python3 -m pip install agentledger-runtime
agentledger doctor
```

PyPI distribution 名是 `agentledger-runtime`；Python import package 和 CLI 仍然是 `agentledger`。

项目主页和完整文档：

```text
https://github.com/yaogdu/AgentLedger
```

### 2. 本地开发安装

请使用 Python 3.11 或更高版本。如果系统默认 `python3` 版本较低，可以把下面命令里的 `python3` 替换为 `python3.11`。

```bash
python3 -m pip install -e .
agentledger doctor
```

也可以直接从源码运行：

```bash
PYTHONPATH=src python3 -m agentledger doctor
```

### 3. 最小 API

```python
from agentledger import agent, run

@agent
def hello(ctx):
    return "hello world"

result = run(hello)
print(result.output)
print(result.run_id)
```

这个例子看起来只是一次普通函数调用，但 runtime 仍然会创建 durable run、领取带 lease 的 step、记录事件、原子提交 state，并支持后续 evidence export。

### 4. 常用 CLI flow

```bash
PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONPATH=src python3 -m agentledger init
PYTHONPATH=src python3 -m agentledger run examples/side_effect_idempotency
PYTHONPATH=src python3 -m agentledger debug <run_id> --json --include-diffs
PYTHONPATH=src python3 -m agentledger replay <run_id>
PYTHONPATH=src python3 -m agentledger evidence <run_id> --dir ./evidence/<run_id>
PYTHONPATH=src python3 -m agentledger evidence <run_id> --html ./evidence.html
PYTHONPATH=src python3 -m agentledger timetravel <run_id> --include-diffs --include-states --html ./time-travel.html
PYTHONPATH=src python3 -m agentledger cost report <run_id>
PYTHONPATH=src python3 -m agentledger failure report <run_id>
PYTHONPATH=src python3 -m agentledger review checklist <run_id> --fail-on-risk
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONPATH=src python3 -m agentledger contract export
```

## Runtime model

| Layer | 职责 | 扩展点 |
| --- | --- | --- |
| Agent logic | user function、framework node、prompt、model choice | LangGraph、LangChain、CrewAI、AutoGen、OpenAI Agents SDK、LlamaIndex、Semantic Kernel、custom worker |
| Runtime boundary | `AgentContext`、tool gateway、policy、approval、budget、sandbox routing | tool registry、policy loader、approval store、sandbox executor |
| Scheduling | step claim、lease、fencing、retry、heartbeat、cancellation、recovery | local worker loop、distributed worker recipe、custom claimer |
| Durable state | run、session、step、event、tool ledger、checkpoint、migration | SQLite、Postgres、custom StateStore |
| Evidence | payload ref、blob ref、artifact、media ref、trace、cost、failure | local blob store、S3/MinIO、OTLP JSON、静态 HTML export |
| Reliability consumers | replay、diff、shadow mode、evidence regression、conformance、backup check | golden corpus、adapter certification、custom review gate |

## 兼容边界与非目标

AgentLedger 不替代现有 Agent 或 workflow library。

| Agent 框架负责 | AgentLedger 负责 |
| --- | --- |
| planning、reasoning、routing、graph structure、prompt strategy | durable state、event log、Tool Ledger、policy、approval、sandbox boundary、evidence、replay、recovery |

AgentLedger 也不是新的 LLM SDK，不是 workflow engine，不是通用 observability 产品，不是完整 eval 系统，不是 RAG 系统，不是 sandbox infrastructure provider，不替代 Temporal/Ray/Kubernetes，也不承诺让所有外部系统天然 exactly-once。更准确的保证是：每一个 runtime-managed side effect 都应该关联 ledger entry、idempotency key、audit trail，以及明确的 unknown-state handling。

## 当前成熟度

AgentLedger 现在是 v1.0 stable runtime-core release，适合本地使用、framework adapter integration、reliability semantics 验证，以及在明确 adapter 边界下做 production pilot 准备。

runtime-core contract 已稳定；optional production adapter 和外部基础设施加固仍按独立阶段推进。详见 [docs/MATURITY_MODEL.md](docs/MATURITY_MODEL.md)、[docs/zh/IMPLEMENTATION_STATUS.md](docs/zh/IMPLEMENTATION_STATUS.md) 和 [docs/zh/ROADMAP.md](docs/zh/ROADMAP.md)。

## 文档导航

| 目标 | 文档 |
| --- | --- |
| 学会使用 runtime | [docs/zh/USAGE.md](docs/zh/USAGE.md) |
| 理解整体架构 | [docs/zh/ARCHITECTURE.md](docs/zh/ARCHITECTURE.md) |
| 阅读实现细节 | [docs/zh/DESIGN_AND_IMPLEMENTATION.md](docs/zh/DESIGN_AND_IMPLEMENTATION.md) |
| 查看 runtime spec | [docs/zh/RUNTIME_SPEC.md](docs/zh/RUNTIME_SPEC.md) |
| 扩展存储、工具和 adapter | [docs/zh/EXTENSIBILITY.md](docs/zh/EXTENSIBILITY.md)、[docs/zh/STORAGE.md](docs/zh/STORAGE.md)、[docs/zh/ADAPTER_CERTIFICATION.md](docs/zh/ADAPTER_CERTIFICATION.md) |
| 配置 Postgres 或 S3/MinIO | [docs/POSTGRES.md](docs/POSTGRES.md)、[docs/S3_MINIO.md](docs/S3_MINIO.md) |
| 准备发布 | [docs/zh/RELEASE_CHECKLIST.md](docs/zh/RELEASE_CHECKLIST.md)、[docs/VERSIONING.md](docs/VERSIONING.md) |
| 阅读英文文档 | [README.md](README.md)、[docs/README.md](docs/README.md) |

## 仓库结构

```text
src/agentledger/     Python reference runtime-core
tests/               unit、conformance 和 integration-style tests
examples/            dependency-free examples 和 adapter facades
docs/                英文文档和 runtime design docs
docs/zh/             中文主阅读路径
contracts/           language-neutral runtime contract snapshot
migrations/          SQLite/Postgres DDL 和 migration baselines
```

## 自动化验证

```bash
PYTHONPYCACHEPREFIX=/tmp/agentledger-pycache PYTHONPATH=src python3 -m compileall -q src tests examples
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PYTHONTRACEMALLOC=10 python3 -W default::ResourceWarning -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
python3 -m json.tool /tmp/agentledger-contract.json >/dev/null
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
```

完整 release gate 见 [docs/zh/RELEASE_CHECKLIST.md](docs/zh/RELEASE_CHECKLIST.md)。

## License

Apache-2.0. See [LICENSE](LICENSE)。
