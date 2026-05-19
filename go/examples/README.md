# AgentLedger Go Examples

Run from the repository root unless noted.

## Quickstart

```bash
go run ./go/examples/quickstart
```

Source: `quickstart/main.go`

## Library Install Smoke

Use AgentLedger inside a Go module:

```bash
go mod init your-module-name  # only if your project does not have go.mod yet
go get github.com/yaogdu/AgentLedger/go@v1.0.5
```

Import:

```go
import agentledger "github.com/yaogdu/AgentLedger/go"
```

## CLI Install

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.0.5
agentledger-go quickstart
```

Do not run `go install github.com/yaogdu/AgentLedger/go@v1.0.5`; that path is the library package and is not `package main`.

## Travel Assistant

`travel_assistant/main.go` is a larger local demo. Treat it as an example app, not part of the release gate.

Run from the repository root:

```bash
cd go && go run examples/travel_assistant/main.go
```
