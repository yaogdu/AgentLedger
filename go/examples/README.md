# AgentLedger Go Examples

Run from the repository root unless noted.

## Quickstart

```bash
go run ./go/examples/quickstart
```

Source: `quickstart/main.go`

## Adoption Demos

```bash
cd go
go run ./examples/three_minute_demo
go run ./examples/mcp_governance
```

The 3-minute demo shows crash/retry without duplicate external writes. The MCP governance demo shows descriptor annotations flowing into approval, sandbox metadata, idempotency, and audit evidence.

## Library Install Smoke

Use AgentLedger inside a Go module:

```bash
go mod init your-module-name  # only if your project does not have go.mod yet
go get github.com/yaogdu/AgentLedger/go@v1.4.1
```

Import:

```go
import agentledger "github.com/yaogdu/AgentLedger/go"
```

## CLI Install

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.4.1
agentledger-go quickstart
```

Do not run `go install github.com/yaogdu/AgentLedger/go@v1.4.1`; that path is the library package and is not `package main`.

## Travel Assistant

`travel_assistant/main.go` is a larger local demo. Treat it as an example app, not part of the release gate.

Run from the repository root:

```bash
cd go && go run examples/travel_assistant/main.go
```
