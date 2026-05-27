# Adapter Packaging

AgentLedger `1.2.1` 引入 adapter packaging model。runtime-core 保持小而稳定，具体生态集成进入 optional adapter packages，用户可以通过 extras 或直接安装 adapter 包启用。

## 为什么拆包

拆包不是为了形式，而是为了工程边界：

- optional integration 会带来重依赖或快节奏依赖，例如 `psycopg`、`boto3`、LangGraph、MCP SDK、OpenTelemetry、Docker tooling
- 某个生态的依赖冲突不应该破坏 core runtime 安装
- cloud storage、database credentials、sandbox executor 这类安全敏感能力应该显式启用
- adapter 修复应该可以独立发布，不必强迫 runtime-core 发版
- production hardening 应落在拥有外部服务行为的 adapter 包里

规则是：

```text
runtime-core 负责稳定执行语义
adapter package 负责生态集成
extras 保持安装体验简单
```

## 安装模型

adapter packaging 是按语言生态落地的。同一个目标，在不同语言里使用不同机制：

| 语言 | `1.2.1` 机制 | 原因 |
| --- | --- | --- |
| Python | `packages/` 下独立 PyPI 包，加 `agentledger-runtime[...]` extras | Python extras 最适合把 optional SDK dependency 留在 core 之外 |
| TypeScript/Node | `agentledger-runtime` subpath exports，加 `typescript/packages/` 下 npm adapter packages | subpath exports 方便本地使用；独立 package 保留后续独立发布能力 |
| Go | `go/adapters/...` 下可 import 的 adapter subpackages | Go 没有 extras，用户一般消费同一个 module 下的 subpackage |
| Rust | crate features，加 `rust/crates/` 下 adapter crate packages | Rust 可以通过 feature-gated boundary 或独立 crate 接入 |

跨语言规则是：不使用某个 adapter 时，core runtime 仍然不需要 import 该 adapter boundary。

只安装 core：

```bash
pip install agentledger-runtime
```

通过 extras 按能力安装：

```bash
pip install "agentledger-runtime[postgres]"
pip install "agentledger-runtime[s3]"
pip install "agentledger-runtime[langgraph]"
pip install "agentledger-runtime[mcp]"
pip install "agentledger-runtime[otel]"
pip install "agentledger-runtime[docker]"
pip install "agentledger-runtime[all]"
```

直接安装 adapter 包：

```bash
pip install agentledger-postgres
pip install agentledger-s3
pip install agentledger-langgraph
pip install agentledger-mcp
pip install agentledger-otel
pip install agentledger-sandbox-docker
```

普通项目优先使用 extras。需要显式锁依赖、内部镜像或独立治理 adapter 发版时，再直接安装 adapter package。

## 包结构

monorepo 结构：

```text
agentledger-runtime/
  src/agentledger/                       # dependency-light runtime-core
  packages/
    agentledger-postgres/
      pyproject.toml
      README.md
      src/agentledger_postgres/
      tests/
      examples/
    agentledger-s3/
    agentledger-langgraph/
    agentledger-mcp/
    agentledger-otel/
    agentledger-sandbox-docker/
  typescript/
    src/adapters/                        # runtime subpath exports
    packages/                            # npm adapter packages
      agentledger-postgres/
      agentledger-s3/
      agentledger-langgraph/
      agentledger-mcp/                   # npm package name: agentledger-mcp-adapter
      agentledger-otel/
      agentledger-sandbox-docker/
  go/adapters/
    postgres/
    s3/
    mcp/
    otel/
    sandbox/docker/
    framework/
  rust/
    crates/
      agentledger-postgres/
      agentledger-s3/
      agentledger-mcp/
      agentledger-otel/
      agentledger-sandbox-docker/
      agentledger-framework/
```

每个 adapter package 应提供：

- 独立 import path，例如 `agentledger_postgres`
- 当前 core adapter class name 的 compatibility exports
- 至少一个本地 smoke test
- README，说明 install、usage、limitations、certification commands
- real external service 非必需时，使用 optional dependency 或 injected-client tests
- adapter certification bundle profile 或 command

## 第一批 Adapter Packages

| Package | `1.2.1` 负责 | 依赖状态 |
| --- | --- | --- |
| `agentledger-postgres` | `PostgresStore`、`PostgresStoreConfig`、migration/conformance helpers | 依赖 `psycopg[binary]`；production rollout 仍需要真实服务演练。 |
| `agentledger-s3` | `S3BlobStore`、`S3BlobStoreConfig` | 依赖 `boto3`；production rollout 仍需要 IAM/KMS/lifecycle 和 restore drill。 |
| `agentledger-langgraph` | 基于 dependency-free facade 的 LangGraph checkpointer/node wrapper | core facade 不引入重依赖；optional native SDK 使用放在 package extras 或后续 smoke matrix 中。 |
| `agentledger-mcp` / npm 上使用 `agentledger-mcp-adapter` | MCP-style tool/context mapping package boundary | 当前 package 保持 dependency-light；exact MCP SDK client/server transport 是后续 adapter hardening。 |
| `agentledger-otel` | 围绕 AgentLedger spans 的 OTLP JSON/export package boundary | 当前 package 保持 dependency-light；hardened OpenTelemetry SDK wiring 是后续工作。 |
| `agentledger-sandbox-docker` | Docker sandbox executor package 和本地/团队 recipe | 当前边界支持 Docker CLI/manifest 语义；daemon hardening、network policy、resource validation 属于外部。 |

这里要尊重语言生态。`agentledger-langgraph` 对 Python 和 TypeScript/Node 是一等 adapter，因为这两个生态有 LangGraph 包；Go 和 Rust 不强行假装有原生 LangGraph 生态，而是提供通用 `framework` adapter boundary。

## Sandbox Adapter 范围

Docker 是第一批官方 sandbox package，因为它是最低摩擦的 reference implementation：本地开发、CI、示例和很多受控团队环境都能跑。这个选择不表示 AgentLedger core 依赖 Docker，也不表示 Docker 是最终安全答案。

runtime-core 负责 sandbox contract：

- sandbox policy input
- sandbox-required tool 的 fail-closed routing
- command/input/artifact handoff 形状
- timeout、cancellation 和 cleanup semantics
- audit、evidence 和 replay-safe result records

sandbox infrastructure 仍然属于 adapter 层。Docker、E2B、Kubernetes Jobs、通过 `runtimeClass` 使用的 gVisor/Kata、Firecracker、bubblewrap、nsjail 或 custom remote executor，都应该在运行模型足够稳定时，通过同一套 sandbox adapter boundary 接入。

实际顺序是：

1. Docker adapter：reference package 和本地/团队 baseline。
2. Kubernetes Job recipe/adapter：面向集群用户，支持 namespace/service account policy、dry-run manifest 和 optional execution。
3. E2B 或 custom remote executor：托管 remote sandbox，用于 code/tool execution。
4. gVisor/Kata/Firecracker/bubblewrap/nsjail：更强或更专门的隔离后端，通常由部署约束驱动。

对于高风险不可信代码，不应把 Docker adapter 单独视为完整安全边界。应使用更强隔离基础设施，并用真实的 network、secret、filesystem、resource-limit 和 cleanup 测试认证该 adapter。

## Compatibility Shims

`1.2.1` 不应该破坏已有 import。

已有 import 例如：

```python
from agentledger.storage_postgres import PostgresStore
from agentledger.blobstore_s3 import S3BlobStore
from agentledger.adapters_langgraph import LangGraphCheckpointerAdapter
```

应该在 adapter package 已安装时继续可用；如果没安装，应给出明确错误：

```text
Postgres support moved to agentledger-postgres.
Install with: pip install "agentledger-runtime[postgres]"
```

`1.2.1` 不删除这些 shim path。未来 `2.0` 可在 deprecation window 后移除 compatibility shims。

## Core Extras

`agentledger-runtime` 应暴露指向 adapter package 的 extras：

```toml
[project.optional-dependencies]
postgres = ["agentledger-postgres>=1.2,<2"]
s3 = ["agentledger-s3>=1.2,<2"]
langgraph = ["agentledger-langgraph>=1.2,<2"]
mcp = ["agentledger-mcp>=1.2,<2"]
otel = ["agentledger-otel>=1.2,<2"]
docker = ["agentledger-sandbox-docker>=1.2,<2"]
all = [
  "agentledger-postgres>=1.2,<2",
  "agentledger-s3>=1.2,<2",
  "agentledger-langgraph>=1.2,<2",
  "agentledger-mcp>=1.2,<2",
  "agentledger-otel>=1.2,<2",
  "agentledger-sandbox-docker>=1.2,<2",
]
```

monorepo 本地开发时，测试可以从 `packages/*` 路径安装；发布后的 wheel 应通过 package index 解析 extras。

## Release Gates

`1.2.1` packaging release 期望通过：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.2.1
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/check_adapter_packages.py
go test ./...
cd typescript && npm test
cd rust && cargo test --features adapters-all
```

每个 adapter package 也应通过：

```bash
python3 -m build packages/<adapter>
python3 -m pip install dist/<adapter>.whl
python3 -c "import <adapter_import_name>"
```

## 1.2.1 非目标

`1.2.1` 不因为 package 存在就声明 production hardening 完成。以下内容继续作为后续工作：

- 真实 Postgres/S3 restore drill 和 load/concurrency report
- 完整 framework-native version matrix
- 完整 MCP SDK server/client coverage
- Temporal/Ray/Kubernetes backend adapters
- media processing adapters
- sub-agent 或 multi-agent runtime semantics
- hosted platform、SaaS、长运行 UI 或完整 eval platform
