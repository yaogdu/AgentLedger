# Getting Started

[English](GETTING_STARTED.md) | [中文](zh/GETTING_STARTED.md)

This is the shortest path from install to a working AgentLedger run. If you are unsure where to start, start here.

## 1. Pick Your Language

| Language | Install / use | Quickstart | Examples | Package / command |
|---|---|---|---|---|
| Python | `pipx install agentledger-runtime` or `pip install agentledger-runtime` | `agentledger quickstart` | `../examples/README.md` | PyPI package `agentledger-runtime`, CLI `agentledger` |
| Go | `go get github.com/yaogdu/AgentLedger/go@v1.4.2` inside a Go module | `cd go && go run ./examples/quickstart` from this repo | `../go/examples/README.md` | Go module `github.com/yaogdu/AgentLedger/go`, CLI package `.../go/cmd/agentledger-go` |
| TypeScript | `npm install agentledger-runtime` | `node typescript/examples/quickstart/quickstart.js` | `../typescript/examples/README.md` | npm package `agentledger-runtime`, CLI `agentledger-ts` |
| Rust | crates.io package: `agentledger-runtime` | `cargo add agentledger-runtime` 或 `cd rust && cargo run --example quickstart` | `../rust/examples/README.md` | crate `agentledger-runtime`, binary `agentledger-rust` |

## 2. Install Or Run Locally

### Python

```bash
pipx install agentledger-runtime
agentledger --help
agentledger quickstart
```

Inside a project virtual environment:

```bash
pip install agentledger-runtime
python -m agentledger doctor
```

### Go

Use the library inside a Go module:

```bash
go mod init your-module-name  # only if your project does not already have go.mod
go get github.com/yaogdu/AgentLedger/go@v1.4.2
```

Install the optional CLI:

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.4.2
agentledger-go --help
```

Important: `go get` must run inside a Go module. `go install github.com/yaogdu/AgentLedger/go@v1.4.2` is not valid because that path is a library, not `package main`. Use `/cmd/agentledger-go` for the CLI.

### TypeScript

From this repository:

```bash
cd typescript
node src/cli.js quickstart
node examples/quickstart/quickstart.js
```

Use the published npm package:

```bash
npm install agentledger-runtime
```

For optional adapter packages, see `ADAPTER_PACKAGING.md` and `typescript/README.md`.

### Rust

Use the published crate in a Rust project:

```bash
cargo add agentledger-runtime
```

Import it as `agentledger` in code. From this repository:

```bash
cd rust
cargo run --quiet -- quickstart
cargo run --quiet --example quickstart
```

The crate is published as `agentledger-runtime`; the library crate is imported as `agentledger`.

## 3. Find The Right Example

| Goal | Example |
|---|---|
| Understand the core value in 3 minutes | `../examples/three_minute_demo/README.md`; Go `../go/examples/three_minute_demo`; TypeScript `../typescript/examples/three_minute_demo`; Rust `../rust/examples/three_minute_demo.rs` |
| Smallest Python run | `../examples/hello_world/hello.py` |
| Idempotent side effects | `../examples/side_effect_idempotency/README.md` |
| Retry transient errors | `../examples/transient_retry/README.md` |
| LangGraph integration | `../examples/langgraph/basic_graph.py` |
| LangChain integration | `../examples/langchain/basic_runnable.py` |
| MCP tool/context | `../examples/mcp_tool/basic_tool.py`, `../examples/mcp_context/basic_context_server.py` |
| MCP governance | `../examples/mcp_governance/README.md`; Go `../go/examples/mcp_governance`; TypeScript `../typescript/examples/mcp_governance`; Rust `../rust/examples/mcp_governance.rs` |
| Sandbox command tool | `../examples/sandbox/command_tool.py` |
| Media/stream refs | `../examples/media_stream/basic_media_stream.py` |
| Read-only Inspector/custom viewer | `../examples/inspector/README.md` |
| Go quickstart | `../go/examples/quickstart/main.go` |
| TypeScript quickstart | `../typescript/examples/quickstart/quickstart.js` |
| Rust quickstart | `../rust/examples/quickstart.rs` |

See the example indexes:

- `../examples/README.md`
- `../go/examples/README.md`
- `../typescript/examples/README.md`
- `../rust/examples/README.md`

## 3.1 Multi-language Travel Assistant Demo

The travel assistant demo exists in all four language areas as a richer interactive example:

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

These demos are useful for understanding behavior, but they are not the release-gate conformance suite.

## 4. Understand The Mental Model

Read these in order:

1. `../README.md` - project positioning and scope.
2. `USAGE.md` - Python CLI and runtime usage.
3. `LANGUAGE_QUICKSTART.md` - Python / Go / TypeScript / Rust usage.
4. `LANGUAGE_IMPLEMENTATION_COMPARISON.md` - what is aligned across languages and what is intentionally language-specific.
5. `ARCHITECTURE.md` - runtime layers and architecture diagram.
6. `COMPARISONS.md` - differences from LangGraph, LangChain, LangSmith, Langfuse, Temporal, Ray, Kubernetes, and eval platforms.

## 5. Validate The Repo

```bash
python3.11 scripts/check_complete_core_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

These checks verify runtime-core parity, CLI/DX baseline, examples, package metadata, docs links, and shared conformance semantics.

---

generated by codex cli
