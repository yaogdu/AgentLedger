# agentledger-langfuse

Langfuse evidence and trace export adapter package for AgentLedger.

```bash
pip install agentledger-langfuse
pip install "agentledger-runtime[langfuse]"
```

```python
from agentledger_langfuse import LangfuseTraceExporter

payload = LangfuseTraceExporter().to_ingestion_payload(evidence_bundle)
```

This adapter is intentionally thin. It converts AgentLedger evidence spans into Langfuse-style ingestion records and can POST JSON to a user-provided endpoint. It does not replace Langfuse, own project/key management, or import the Langfuse SDK in runtime-core.

Certification:

```bash
python3 -m agentledger adapter certify --kind langfuse --adapter-version 1.4.1
```
