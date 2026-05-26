def test_imports() -> None:
    from agentledger_otel import OTLPResource, OTLPTraceExporter

    assert OTLPResource.__name__ == "OTLPResource"
    assert OTLPTraceExporter.__name__ == "OTLPTraceExporter"

