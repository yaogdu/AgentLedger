# AgentLedger Rust Examples

Run from `rust/` unless noted.

## Quickstart

```bash
cd rust
cargo run --quiet --example quickstart
```

Source: `quickstart.rs`

## Adoption Demos

```bash
cd rust
cargo run --example three_minute_demo
cargo run --example mcp_governance
```

The 3-minute demo shows crash/retry without duplicate external writes. The MCP governance demo shows descriptor annotations flowing into approval, sandbox metadata, idempotency, and audit evidence.

## CLI Quickstart

```bash
cd rust
cargo run --quiet -- quickstart
cargo run --quiet -- conformance
```

Crate surface: `agentledger-runtime`. The library crate is imported as `agentledger`. See `../README.md` for package metadata and API examples.


## Travel Assistant

`travel_assistant.rs` is a larger interactive demo. Treat it as an example app, not part of the release gate. It is intentionally excluded from the crates.io package include list; use it from the repository.

```bash
cd rust
cargo run --example travel_assistant
```
