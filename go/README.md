# AgentLedger Go Runtime

This directory contains the native Go runtime-core baseline for AgentLedger 1.2.0.

The package is dependency-free and runs a real local runtime loop. It participates in the shared Python/Go/TypeScript/Rust conformance gate and should be treated as runtime-core aligned; concrete production adapters are shipped separately as they mature.

## Current Status

Implemented:

- local `JSONStore` with atomic file writes and in-memory store for tests
- run/session/step state model
- leased step claim, heartbeat, lease recovery, and cancellation fencing
- `AgentContext` with state patch writes and runtime-managed tool calls
- `ToolGateway` with Tool Ledger idempotency for side-effect tools
- evidence export, replay, trace/diff/debug consumers, time-travel timeline, repro helpers
- policy denial, approval pause/resume, sandbox fail-closed behavior
- cost records, budget enforcement, and failure attribution
- media artifact refs and stream checkpoint refs in evidence/replay
- scheduler facade, worker service, failure injection, adversarial review, evidence regression
- MCP-style and dependency-free framework adapters
- official optional adapter APIs for Postgres, S3/MinIO, OTLP transport, and Docker sandbox manifests
- CLI for `conformance`, `contract validate`, and `contract export`

Not claimed yet:

- live Postgres/S3/Docker/OTLP service-backed hardening
- framework-native packages for ecosystems that do not exist in Go
- full media processing and stream transport adapters


## Install

Use AgentLedger as a Go library inside an existing Go module:

```bash
go mod init your-module-name  # only if your project does not have go.mod yet
go get github.com/yaogdu/AgentLedger/go@v1.2.0
```

Import it with:

```go
import agentledger "github.com/yaogdu/AgentLedger/go"
```

Install the optional CLI command with the `cmd` package path:

```bash
go install github.com/yaogdu/AgentLedger/go/cmd/agentledger-go@v1.2.0
agentledger-go --help
agentledger-go doctor
agentledger-go quickstart
```

`go get github.com/yaogdu/AgentLedger/go@v1.2.0` must run inside a Go module. `go install github.com/yaogdu/AgentLedger/go@v1.2.0` is not valid because the library package is not a `package main`; use `/cmd/agentledger-go` for the CLI.

## Quickstart

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

    bundle, _ := agentledger.ExportEvidence(rt.Store, runID)
    fmt.Println(bundle.Run.RunID)
}
```

## Adapter Quickstart

```go
pg := agentledger.NewPostgresAdapter("agentledger", injectedSQLClient)
_ = pg.ApplyMigrations(context.Background())

s3 := agentledger.NewS3BlobStore("agentledger-test", "agentledger/blobs", injectedObjectClient)
_, ref, _ := s3.PutJSON(context.Background(), agentledger.JSONObject{"answer": "ok"})
fmt.Println(ref)

manifest := (agentledger.DockerSandboxAdapter{}).Manifest(
    agentledger.SandboxPolicy{Network: "deny"},
    []string{"echo", "ok"},
)
fmt.Println(manifest)
```

## Verify

```bash
cd go
go test . ./cmd/agentledger-go
go run ./cmd/agentledger-go conformance
go run ./cmd/agentledger-go contract validate
```

From the repository root:

```bash
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
```

## Compatibility Target

```text
../contracts/agentledger.runtime.v1.json
../contracts/conformance/runtime_semantics.v1.json
../docs/LANGUAGE_QUICKSTART.md
../docs/LANGUAGE_PARITY_MATRIX.md
```
