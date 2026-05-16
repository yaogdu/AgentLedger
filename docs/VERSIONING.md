# Versioning and Compatibility

AgentLedger `1.0.0` stabilizes the Python runtime-core contract. Core APIs and schemas should evolve through explicit compatibility rules, migrations, conformance tests, and documented maturity levels. Optional adapters may still be preview or experimental.

## Versioned Surfaces

```text
Python package version:
  pyproject.toml

runtime contract:
  contracts/agentledger.runtime.v1.json

evidence schema:
  agentledger.evidence.v1

StateStore schema:
  schema_migrations table and DDL catalog

CLI:
  command names and JSON output shapes

adapter contracts:
  protocol interfaces and conformance runners
```

## Compatibility Rules For v1.x

Allowed in minor releases with documentation:

```text
add new optional fields to evidence or trace output
add new event types
add new CLI commands
add new conformance checks
add new adapter protocols behind optional packages
add new schema migrations
```

Requires migration notes and compatibility coverage:

```text
rename or remove event fields
change Tool Ledger status semantics
change lease/fencing behavior
change StateStore schema shape
change evidence bundle layout
change CLI JSON fields consumed by CI
```

Avoid unless a new major version is declared:

```text
silently changing idempotency key rules
making replay/shadow perform real side effects
weakening fail-closed security defaults
removing conformance coverage
dropping support for existing evidence bundles without a converter
```

## Migration Policy

State migrations should be:

```text
monotonic
named
checksumed
auditable through schema_migrations
safe to inspect with DDL export
non-destructive by default
```

Runtime core must not add convenience commands that drop real production schemas or delete real DB data. Destructive maintenance belongs in DBA/SRE runbooks with environment-specific approvals.

## Evidence Compatibility

Evidence bundles are the debugging and replay contract. New fields should be additive where possible:

```text
old readers ignore unknown fields
new readers tolerate missing optional fields
bundle_hash excludes only bundle_hash itself
payload refs remain stable and content-addressed
```

If evidence layout changes, include:

```text
schema_version bump
converter or documented manual migration path
golden fixture update
evidence regression coverage
```

## Adapter Compatibility

Adapter packages should declare:

```text
supported AgentLedger contract version
supported evidence schema
required conformance runner version
required external service versions
known unsupported runtime invariants
```

See `docs/ADAPTER_CERTIFICATION.md` for the certification bundle expected before serious pilots.
