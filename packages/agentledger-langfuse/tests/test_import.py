def test_imports() -> None:
    from agentledger_langfuse import LangfuseProject, LangfuseTraceExporter

    assert LangfuseProject.__name__ == "LangfuseProject"
    assert LangfuseTraceExporter.__name__ == "LangfuseTraceExporter"
