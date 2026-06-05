# Case Study Template: Legal Agent Tool Audit

This is a public-safe template for documenting how AgentLedger can be used in a legal-agent workflow. Do not include private client data, confidential documents, secrets, or internal deployment details.

## Problem

Legal agents often call tools that read documents, create review notes, draft filings, or update case-management systems. A failed run can leave maintainers with hard questions:

- Which tools were called?
- Which inputs and state versions were used?
- Did a write action actually happen?
- Was a high-risk tool approved?
- Can the run be replayed without touching legal systems again?
- Can reviewers inspect evidence without re-running the agent?

## AgentLedger Boundary

AgentLedger should sit around the model/tool/state boundary:

```text
legal agent logic
  -> AgentLedger AgentContext
  -> ToolGateway / policy / approval / Tool Ledger
  -> document tools, case tools, storage tools
  -> evidence bundle / replay / audit report
```

AgentLedger does not own legal reasoning, legal advice, document interpretation, or business workflow. It owns runtime evidence and side-effect governance.

## Integration Notes

Document these details for a real case study:

| Item | Notes |
|---|---|
| Agent framework | LangGraph, OpenAI Agents SDK, custom Python, or other |
| Runtime store | SQLite, Postgres, MySQL |
| Artifact store | local blobs, S3/MinIO, internal object store |
| Tools governed | document read, note write, case update, email, PR/ticket creation |
| High-risk controls | approval required, sandbox required, redaction required, budget cap |
| Evidence exported | bundle JSON, static HTML, trace JSONL, replay summary |
| Private data handling | redaction, synthetic samples, omitted fields |

## Expected Evidence

A useful public case study can include sanitized examples of:

- Tool Ledger rows
- approval records
- replay summary
- final state shape
- failure attribution report
- static HTML evidence screenshot

Do not include privileged legal text, personal data, production secrets, or real customer identifiers.

## Summary Template

```text
We used AgentLedger to wrap the legal agent's tool boundary. The integration
records document/tool calls, approval decisions, state transitions, and evidence
bundles so failed or disputed runs can be inspected and replayed without
repeating external side effects.
```

