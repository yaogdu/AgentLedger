# Benchmarks

AgentLedger benchmarks are release-quality gates, not marketing numbers. They verify that the runtime still covers the full semantic surface while also recording same-machine timing for representative local paths.

The default benchmark is dependency-free for runtime scenarios:

- SQLite `StateStore`
- `LocalBlobStore`
- no model provider calls
- no real database, object store, Docker daemon, or cloud service
- optional local CLI timing for Python, Go, TypeScript, and Rust conformance commands

## Run

From the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/benchmark_runtime.py --iterations 20 --output-dir /tmp/agentledger-benchmark
```

For a fast Python-only smoke while editing:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/benchmark_runtime.py --iterations 1 --skip-language-commands --output-dir /tmp/agentledger-benchmark-smoke
```

The command writes:

- `benchmark.json`: machine-readable result, samples, coverage matrix, validation failures, and command output tails.
- `benchmark.md`: human-readable report for release review.
- `run-*/`: isolated runtime/evidence/static HTML artifacts for that invocation.
- `execution_claim`: `release_gate` for the default full command, or `local_runtime_smoke` when language commands are skipped.
- `warnings`: explicit caveats for dry-run, synthetic, or skipped validation paths.

## Coverage

The benchmark reads `contracts/conformance/runtime_semantics.v1.json` and reports every required semantic check in `coverage_matrix`.

Current required coverage includes:

- durable run, persistence, replay, and evidence export
- local blob store
- tool schema validation
- worker/service and scheduler behavior
- Tool Ledger idempotent retry
- policy, approval, and sandbox fail-closed behavior
- cost and failure attribution
- media artifact and stream checkpoint evidence
- evidence consumers, trace, OTLP JSON, Inspector HTML, and time-travel HTML
- ops readiness, storage schema helpers, and non-destructive retention/backup checks
- MCP and framework adapter contracts
- boundary lint
- adversarial review and evidence regression checks
- failure injection
- shadow/repro harness primitives
- optional and official adapter certification/dry-run boundaries

When language commands are enabled, Go, TypeScript, and Rust conformance CLIs must report the shared manifest ids. A full successful run should show:

```text
required_check_count = 27
covered_check_count = 27
not_run_count = 0
by_status.measured_and_language_conformance = 27
```

The coverage matrix also includes `verification_depths`:

- `executable_local` / `executable_local_fault`: real local runtime execution.
- `negative_runtime_path`: an intentionally failing runtime boundary such as invalid tool input, approval pause, sandbox fail-closed, or budget denial.
- `read_model_local`: evidence, replay, failure, cost, Inspector, scheduler, retention, or backup read models over persisted local data.
- `synthetic_probe`: deliberately generated failure/lint fixtures.
- `contract_dry_run` / `static_helper`: adapter contracts, DDL helpers, or static surfaces that do not prove a live external service.
- `language_conformance`: Python, Go, TypeScript, or Rust CLI conformance reported the shared semantic check id.

## Interpreting Results

Use the timing numbers for same-machine regression tracking only. They are not a portable performance claim across laptops, CI runners, operating systems, or Python versions.

The benchmark intentionally measures several non-happy-path behaviors:

- crash after a side effect, followed by safe retry
- exactly-once external side-effect count through Tool Ledger idempotency
- invalid tool input rejected before execution
- approval pause and resume
- required sandbox fail-closed path
- model call evidence, model failure evidence, tool-call proposal evidence, and model cost attribution
- budget exhaustion that blocks tool execution before a side effect can run
- failure injection for retry exhaustion, stale lease fencing, cancellation fencing, and side-effect idempotency
- boundary lint detecting a deliberately unsafe direct shell call

Some adapter-related checks are contract/dry-run checks by design. Postgres, MySQL, S3, Docker, Langfuse, OTLP collectors, and Temporal require separate service-backed validation before production claims.

By default, the full release gate fails if a language conformance command fails, times out, or is skipped because a toolchain is missing. Use `--allow-language-skips` only for local investigation, not for release evidence.

## Release Use

For runtime-core or cross-language releases, run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 scripts/benchmark_runtime.py --iterations 20 --output-dir /tmp/agentledger-benchmark
python3.11 scripts/check_language_parity.py
```

Attach or summarize `benchmark.md` in release notes when the release changes runtime semantics, failure handling, Inspector/debug output, evidence consumers, adapters, or language parity.

The GitHub Actions workflow also runs the full benchmark in the `Runtime benchmark gate` job on `main` pushes and pull requests. That job uploads an artifact named `agentledger-benchmark` containing `benchmark.json`, `benchmark.md`, and the isolated `run-*/` evidence/debug artifacts. Use the latest successful CI artifact as release evidence, and keep separate service-backed validation for Postgres, MySQL, S3, Docker, Langfuse, OTLP collectors, Temporal, or other production adapter claims.

---

generated by codex cli
