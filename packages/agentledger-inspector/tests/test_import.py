def test_imports() -> None:
    from agentledger_inspector import INSPECTOR_SCHEMA_VERSION, EvidenceStateStoreProtocol, InspectorDataSource, InspectorReportBuilder, ReadOnlyPostgresStore

    assert INSPECTOR_SCHEMA_VERSION == "agentledger.inspector.v1"
    assert EvidenceStateStoreProtocol.__name__ == "EvidenceStateStoreProtocol"
    assert InspectorDataSource.__name__ == "InspectorDataSource"
    assert InspectorReportBuilder.__name__ == "InspectorReportBuilder"
    assert ReadOnlyPostgresStore.__name__ == "ReadOnlyPostgresStore"
