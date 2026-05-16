# AgentLedger Documentation

This directory is the canonical documentation set for AgentLedger. English docs are maintained in `docs/`; Chinese counterparts for the primary reader path are maintained in `docs/zh/`.

## Language

| Language | Entry |
|---|---|
| English | `README.md`, this file, and the documents below |
| 中文 | `README.zh-CN.md`, `docs/zh/README.md` |

## Start Here

| Goal | English | 中文 |
|---|---|---|
| Understand the project | `../README.md` | `../README.zh-CN.md` |
| Use the runtime | `USAGE.md` | `zh/USAGE.md` |
| Understand architecture | `ARCHITECTURE.md` | `zh/ARCHITECTURE.md` |
| Read design and implementation notes | `DESIGN_AND_IMPLEMENTATION.md` | `zh/DESIGN_AND_IMPLEMENTATION.md` |
| Check current status | `IMPLEMENTATION_STATUS.md` | `zh/IMPLEMENTATION_STATUS.md` |
| Prepare a release | `RELEASE_CHECKLIST.md` | `zh/RELEASE_CHECKLIST.md` |

## Recommended Reader Paths

| Reader | Path |
|---|---|
| New user | `../README.md` -> `USAGE.md` -> `../examples/hello_world/hello.py` -> `../examples/side_effect_idempotency/README.md` |
| Runtime implementer | `ARCHITECTURE.md` -> `DESIGN_AND_IMPLEMENTATION.md` -> `RUNTIME_SPEC.md` -> `../contracts/agentledger.runtime.v1.json` |
| Adapter author | `EXTENSIBILITY.md` -> `ADAPTER_CERTIFICATION.md` -> relevant example under `../examples/` -> conformance commands |
| Production pilot reviewer | `IMPLEMENTATION_STATUS.md` -> `MATURITY_MODEL.md` -> `SECURITY_ENTERPRISE.md` -> `STORAGE.md` -> `RELEASE_CHECKLIST.md` |
| Future language implementer | `MULTI_LANGUAGE.md` -> `RUNTIME_SPEC.md` -> `../contracts/agentledger.runtime.v1.json` -> conformance fixtures |

## Core Design Docs

- `ARCHITECTURE.md`: runtime layers, SVG architecture diagram, module map, invariants, adapter boundaries.
- `DESIGN_AND_IMPLEMENTATION.md`: state machine, tool governance, replay, evidence, worker, sandbox, storage, media/stream implementation notes.
- `RUNTIME_SPEC.md`: runtime concepts, state model, event schema, Tool Ledger semantics, evidence regression/replay/debug interfaces.
- `EXTENSIBILITY.md`: adapter model for storage, tools, frameworks, protocols, observability, media, and sandbox.
- `STORAGE.md`: runtime metadata schema, migrations, StateStore and BlobStore extension contract.
- `ADAPTER_CERTIFICATION.md`: compatibility checklist for storage, blob, framework, tool, sandbox, media/stream, and observability adapters.

## Operations and Reliability

- `DISTRIBUTED_WORKERS.md`: worker pool recipe, leases, cancellation, and failure drills.
- `BACKUP_RESTORE.md`: backup and restore expectations for StateStore and BlobStore recovery.
- `POSTGRES.md`: optional Postgres StateStore setup and conformance guidance.
- `S3_MINIO.md`: optional S3/MinIO BlobStore setup and conformance guidance.
- `SECURITY_ENTERPRISE.md`: security model, permission boundaries, sandbox, secrets, and high-risk tools.
- `RELEASE_CHECKLIST.md`: local gates for tests, conformance, lint, contract export, examples, and evidence checks.

## Planning and Compatibility

- `ROADMAP.md`: phased plan from stable runtime-core to optional production adapters and external consumers.
- `MATURITY_MODEL.md`: feature maturity matrix.
- `IMPLEMENTATION_STATUS.md`: implemented, partial, missing, and non-goal capability audit.
- `IMPLEMENTATION_PLAN.md`: historical implementation plan and phase breakdown.
- `VERSIONING.md`: v1 compatibility, schema migration, and evidence-versioning policy.
- `MULTI_LANGUAGE.md`: Python reference implementation and Rust/TypeScript/Go compatibility plan.

## Project Policy

- License: `../LICENSE`
- Security reporting: `../SECURITY.md`
- Contributing guide: `../CONTRIBUTING.md`
- Community conduct: `../CODE_OF_CONDUCT.md`
- Release gates: `RELEASE_CHECKLIST.md`
- Versioning and compatibility: `VERSIONING.md`

## Diagram

The primary architecture diagram is maintained as SVG:

```text
docs/assets/agentledger-runtime-architecture.svg
```

It is embedded by `ARCHITECTURE.md` and `zh/ARCHITECTURE.md`.
