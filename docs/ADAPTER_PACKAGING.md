# Adapter Packaging

AgentLedger `1.2.0` introduces the adapter packaging model. Runtime-core stays small and dependency-light; concrete integrations move into optional adapter packages that can be installed through extras or directly.

## Why Split Adapters

Adapter packages are split from runtime-core for practical engineering reasons:

- optional integrations carry heavy or fast-moving dependencies such as `psycopg`, `boto3`, LangGraph, MCP SDKs, OpenTelemetry, and Docker tooling
- dependency conflicts in one ecosystem should not break a core runtime install
- security-sensitive integrations such as cloud storage, database credentials, and sandbox executors should be explicit opt-ins
- adapter fixes should be releasable without forcing a core runtime release
- production hardening should live next to the adapter that owns the external service behavior

The product rule is:

```text
runtime-core owns stable execution semantics
adapter packages own ecosystem integration
extras preserve easy installation
```

## Installation Model

Adapter packaging is language-specific. The goal is the same across languages, but the package mechanism follows each ecosystem:

| Language | Mechanism in `1.2.0` | Reason |
| --- | --- | --- |
| Python | separate PyPI packages under `packages/` plus `agentledger-runtime[...]` extras | Python extras are the cleanest way to keep optional SDK dependencies out of core |
| TypeScript/Node | `agentledger-runtime` subpath exports plus separate npm package skeletons under `typescript/packages/` | subpath exports are ergonomic for local use; adapter packages preserve future independent npm releases |
| Go | importable adapter subpackages under `go/adapters/...` | Go users consume subpackages from the same module instead of extras |
| Rust | crate features plus adapter crate skeletons under `rust/crates/` | Rust users can choose feature-gated boundaries or independent crates |

The portable rule is: if an adapter is unused, the core runtime API still works without importing that adapter boundary.

Core-only install:

```bash
pip install agentledger-runtime
```

Install by feature through extras:

```bash
pip install "agentledger-runtime[postgres]"
pip install "agentledger-runtime[s3]"
pip install "agentledger-runtime[langgraph]"
pip install "agentledger-runtime[mcp]"
pip install "agentledger-runtime[otel]"
pip install "agentledger-runtime[docker]"
pip install "agentledger-runtime[all]"
```

Install an adapter package directly:

```bash
pip install agentledger-postgres
pip install agentledger-s3
pip install agentledger-langgraph
pip install agentledger-mcp
pip install agentledger-otel
pip install agentledger-sandbox-docker
```

Use extras for normal projects. Use direct adapter packages when an organization wants explicit dependency locks, separate package mirrors, or independent adapter release governance.

## Package Layout

The monorepo layout is:

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
    packages/                            # npm adapter package skeletons
      agentledger-postgres/
      agentledger-s3/
      agentledger-langgraph/
      agentledger-mcp/
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

Each adapter package should provide:

- a narrow public import path, such as `agentledger_postgres`
- compatibility exports for the current core adapter class names
- at least one local smoke test
- a README with install, usage, limitations, and certification commands
- optional dependencies or injected-client tests when a real external service is not required
- an adapter certification bundle profile or command

## First Adapter Packages

| Package | Owns | Expected dependency |
| --- | --- | --- |
| `agentledger-postgres` | `PostgresStore`, `PostgresStoreConfig`, migration/conformance helpers | `psycopg[binary]` |
| `agentledger-s3` | `S3BlobStore`, `S3BlobStoreConfig` | `boto3` |
| `agentledger-langgraph` | LangGraph checkpointer/node wrappers around the dependency-free facade | `langgraph` |
| `agentledger-mcp` | real MCP client/server transport adapters around `ToolSpec` and context reads | MCP SDK |
| `agentledger-otel` | OpenTelemetry SDK/exporter integration around AgentLedger spans | OpenTelemetry packages |
| `agentledger-sandbox-docker` | Docker sandbox executor package and local/team recipes | Docker SDK or Docker CLI |

Language fit matters. `agentledger-langgraph` is first-class for Python and TypeScript/Node because those ecosystems have LangGraph packages. Go and Rust expose a generic `framework` adapter boundary instead of pretending a native LangGraph ecosystem exists there.

## Compatibility Shims

`1.2.0` should avoid breaking existing imports.

Existing imports such as:

```python
from agentledger.storage_postgres import PostgresStore
from agentledger.blobstore_s3 import S3BlobStore
from agentledger.adapters_langgraph import LangGraphCheckpointerAdapter
```

should either continue to work when the adapter package is installed, or fail with a precise message:

```text
Postgres support moved to agentledger-postgres.
Install with: pip install "agentledger-runtime[postgres]"
```

Do not remove these shim paths in `1.2.0`. A future `2.0` may remove compatibility shims after a deprecation window.

## Core Extras

`agentledger-runtime` should expose extras that point to the adapter packages:

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

During local monorepo development, tests may install packages from `packages/*` paths. Published wheels should resolve extras from package indexes.

## Release Gates

The `1.2.0` packaging release should pass:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger adapter certify --kind postgres --adapter-version 1.2.0
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/check_adapter_packages.py
go test ./...
cd typescript && npm test
cd rust && cargo test --features adapters-all
```

Each adapter package should also pass:

```bash
python3 -m build packages/<adapter>
python3 -m pip install dist/<adapter>.whl
python3 -c "import <adapter_import_name>"
```

## Non-Goals For 1.2.0

`1.2.0` should not claim production hardening just because packages exist. The following stay as later work:

- real Postgres/S3 restore drills and load/concurrency reports
- full framework-native version matrix
- complete MCP SDK server/client coverage
- Temporal/Ray/Kubernetes backend adapters
- media processing adapters
- sub-agent or multi-agent runtime semantics
- hosted platform, SaaS, long-running UI, or full eval platform
