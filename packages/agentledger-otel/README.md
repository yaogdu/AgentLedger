# agentledger-otel

OTLP trace export adapter package for AgentLedger evidence.

```bash
pip install agentledger-otel
pip install "agentledger-runtime[otel]"
```

```python
from agentledger_otel import OTLPTraceExporter, OTLPResource
```

The `1.2.x` package exports dependency-free OTLP JSON and POST helpers. Full OpenTelemetry SDK wiring can be added as an optional adapter layer without changing runtime-core.

Certification:

```bash
python3 -m agentledger adapter certify --kind otel --adapter-version 1.2.0
```

