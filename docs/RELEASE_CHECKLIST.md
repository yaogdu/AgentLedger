# Release Checklist

This checklist is for v1.0 stable runtime-core releases of the AgentLedger Python reference runtime. It is intentionally read-only except for temporary runtime data, generated contract output, and optional static debug artifacts.

## Scope Gate

Before cutting a release, confirm the package still keeps these boundaries:

```text
Agent frameworks own planning and workflow logic.
AgentLedger owns execution guarantees, evidence, replay, tool governance, policy, sandbox boundaries, and adapter contracts.
Core remains dependency-light; concrete integrations stay optional.
No destructive database cleanup command is part of the release path.
Static HTML exports are debug artifacts, not a long-running app.
```

## Required Local Gates

Run these from the repository root:

Use Python 3.11 or newer. If `python3` points to an older interpreter, replace it with `python3.11`.

```bash
PYTHONPYCACHEPREFIX=/tmp/agentledger-pycache PYTHONPATH=src python3 -m compileall -q src tests examples
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PYTHONTRACEMALLOC=10 python3 -W default::ResourceWarning -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger --root /tmp/agentledger-release-check conformance
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger lint boundary examples src --exclude src/agentledger --no-fail
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
```

Expected result:

```text
compileall exits 0
unit tests pass
ResourceWarning-sensitive test run emits no unclosed database warnings
conformance reports passed=true
boundary lint reports passed=true
contract export is valid JSON and contains a contract_version
checked-in contract fixture matches the current export
```

## Cross-language Runtime Gate

If the release or PR touches the runtime contract, event/evidence schema, Tool Ledger, policy/approval/sandbox, cost/failure attribution, or any Go/TypeScript/Rust implementation, also run:

```bash
python3.11 scripts/check_language_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
```

For a 1.0.1-style runtime-core parity release, `audit_python_parity.py` should report `gap_count: 0`.

This aggregate runner executes the Python reference tests, Go tests, TypeScript tests/check, Rust tests, each preview language conformance CLI, contract diff, Markdown local link check, and `git diff --check`. It loads the shared semantic manifest at `contracts/conformance/runtime_semantics.v1.json`; the JSON report includes `required_semantic_checks`, `semantic_manifest`, and `language_conformance` entries, so it is useful for release notes, CI artifacts, and adapter certification evidence.

## Example Smoke

Run representative dependency-free examples:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/langgraph/basic_graph.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/media_stream/basic_media_stream.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/media_stream/managed_tool.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger worker-run examples/transient_retry
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/media_stream
```

## Optional Service-backed Gates

Only run these when the external services are explicitly configured for test data:

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
PYTHONPATH=src python3 -m agentledger blob conformance --backend s3
```

Do not point these gates at real application data.

## Evidence Gates

For changes to prompts, policies, tool schemas, adapters, replay, or state handling, add at least one evidence-based check:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger evidence-regression ./golden-bundle.json ./current-bundle-dir
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-bundle-dir
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger divergence ./golden-bundle.json ./current-bundle-dir --evidence-paths --fail-on-divergence
```

Use allow flags only when the change is intentional and documented in the release notes.

## Release Notes

The release note should include:

```text
runtime contract version
storage schema version
new or changed CLI commands
new or changed adapter contracts
new or changed evidence bundle fields
known preview or experimental areas
commands run for release verification
```
