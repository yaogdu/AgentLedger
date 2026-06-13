# 快速开始

[English](../GETTING_STARTED.md) | [中文](GETTING_STARTED.md)

这是从安装到跑通 AgentLedger 的最短路径。如果你不知道从哪儿开始，就从这里开始。

## 1. 选择语言

| 语言 | 安装 / 使用 | Quickstart | 示例 | 包 / 命令 |
|---|---|---|---|---|
| Python | `pipx install agentledger-runtime` 或 `pip install agentledger-runtime` | `agentledger quickstart` | `../../examples/README.md` | PyPI package `agentledger-runtime`，CLI `agentledger` |
| Go | 在 Go module 内执行 `go get github.com/yaogdu/AgentLedger/go@v1.4.0` | 在 repo 内执行 `cd go && go run ./examples/quickstart` | `../../go/examples/README.md` | Go module `github.com/yaogdu/AgentLedger/go`，CLI package `.../go/cmd/agentledger-go` |
| TypeScript | `npm install agentledger-runtime` | `node typescript/examples/quickstart/quickstart.js` | `../../typescript/examples/README.md` | npm package `agentledger-runtime`，CLI `agentledger-ts` |
| Rust | crates.io package: `agentledger-runtime` | `cargo add agentledger-runtime` 或 `cd rust && cargo run --example quickstart` | `../../rust/examples/README.md` | crate `agentledger-runtime`，binary `agentledger-rust` |

## 2. 安装或本地运行

### Python

```bash
pipx install agentledger-runtime
agentledger --help
agentledger quickstart
```

在项目虚拟环境中：

```bash
pip install agentledger-runtime
python -m agentledger doctor
```

### Go

在 Go module 内使用 library：

```bash
go mod init your-module-name  # 如果项目还没有 go.mod 才需要
go get github.com/yaogdu/AgentLedger/go@v1.4.0
```

安装可选 CLI：

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.4.0
agentledger-go --help
```

注意：`go get` 必须在 Go module 里执行。`go install github.com/yaogdu/AgentLedger/go@v1.4.0` 是错误用法，因为该路径是 library，不是 `package main`。安装 CLI 要使用 `/cmd/agentledger-go`。

### TypeScript

在本仓库中：

```bash
cd typescript
node src/cli.js quickstart
node examples/quickstart/quickstart.js
```

使用已发布 npm package：

```bash
npm install agentledger-runtime
```

optional adapter packages 见 `../ADAPTER_PACKAGING.md` 和 `../../typescript/README.md`。

### Rust

在 Rust 项目中使用已发布 crate：

```bash
cargo add agentledger-runtime
```

代码中以 `agentledger` 导入。 在本仓库中：

```bash
cd rust
cargo run --quiet -- quickstart
cargo run --quiet --example quickstart
```

crate 发布名是 `agentledger-runtime`；代码中导入的 library crate 名是 `agentledger`。

## 3. 找示例

| 目标 | 示例 |
|---|---|
| 3 分钟理解核心价值 | `../../examples/three_minute_demo/README.md`；Go `../../go/examples/three_minute_demo`；TypeScript `../../typescript/examples/three_minute_demo`；Rust `../../rust/examples/three_minute_demo.rs` |
| 最小 Python run | `../../examples/hello_world/hello.py` |
| 幂等副作用 | `../../examples/side_effect_idempotency/README.md` |
| transient error retry | `../../examples/transient_retry/README.md` |
| LangGraph 集成 | `../../examples/langgraph/basic_graph.py` |
| LangChain 集成 | `../../examples/langchain/basic_runnable.py` |
| MCP tool/context | `../../examples/mcp_tool/basic_tool.py`, `../../examples/mcp_context/basic_context_server.py` |
| MCP governance | `../../examples/mcp_governance/README.md`；Go `../../go/examples/mcp_governance`；TypeScript `../../typescript/examples/mcp_governance`；Rust `../../rust/examples/mcp_governance.rs` |
| Sandbox command tool | `../../examples/sandbox/command_tool.py` |
| Media/stream refs | `../../examples/media_stream/basic_media_stream.py` |
| 只读 Inspector / 二开 viewer | `../../examples/inspector/README.md` |
| Go quickstart | `../../go/examples/quickstart/main.go` |
| TypeScript quickstart | `../../typescript/examples/quickstart/quickstart.js` |
| Rust quickstart | `../../rust/examples/quickstart.rs` |

示例索引：

- `../../examples/README.md`
- `../../go/examples/README.md`
- `../../typescript/examples/README.md`
- `../../rust/examples/README.md`

## 3.1 多语言 Travel Assistant Demo

Travel assistant demo 在四种语言目录里都有一个更完整的交互式示例：

```bash
# Python
python3 examples/travel_assistant/demo.py

# Go
cd go && go run examples/travel_assistant/main.go

# Rust
cd rust && cargo run --example travel_assistant

# TypeScript
node typescript/examples/travel_assistant/travel_assistant.js
```

这些 demo 适合理解行为和展示能力，但不属于 release-gate conformance suite。

## 4. 理解整体模型

建议按这个顺序读：

1. `../../README.zh-CN.md` - 项目定位和 scope。
2. `USAGE.md` - Python CLI 和 runtime 使用。
3. `LANGUAGE_QUICKSTART.md` - Python / Go / TypeScript / Rust 使用方式。
4. `LANGUAGE_IMPLEMENTATION_COMPARISON.md` - 四语言哪些对齐，哪些是语言/生态特定。
5. `ARCHITECTURE.md` - runtime 分层和架构图。
6. `COMPARISONS.md` - 与 LangGraph、LangChain、LangSmith、Langfuse、Temporal、Ray、Kubernetes、eval 平台的区别。

## 5. 验证仓库

```bash
python3.11 scripts/check_complete_core_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

这些检查覆盖 runtime-core parity、CLI/DX baseline、examples、package metadata、文档链接和共享 conformance semantics。
