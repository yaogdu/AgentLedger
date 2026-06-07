import unittest


class InspectorPackageImportTests(unittest.TestCase):
    def test_imports(self) -> None:
        from agentledger_inspector import INSPECTOR_RUN_INDEX_SCHEMA_VERSION, INSPECTOR_SCHEMA_VERSION, EvidenceStateStoreProtocol, InspectorDataSource, InspectorRedactionPolicy, InspectorReportBuilder, InspectorRunIndex, ReadOnlyPostgresStore

        self.assertEqual(INSPECTOR_SCHEMA_VERSION, "agentledger.inspector.v1")
        self.assertEqual(INSPECTOR_RUN_INDEX_SCHEMA_VERSION, "agentledger.inspector.runs.v1")
        self.assertEqual(EvidenceStateStoreProtocol.__name__, "EvidenceStateStoreProtocol")
        self.assertEqual(InspectorDataSource.__name__, "InspectorDataSource")
        self.assertEqual(InspectorRedactionPolicy(keys=("password",)).to_dict()["keys"], ["password"])
        self.assertEqual(InspectorReportBuilder.__name__, "InspectorReportBuilder")
        self.assertEqual(InspectorRunIndex({"schema_version": INSPECTOR_RUN_INDEX_SCHEMA_VERSION}).to_dict()["schema_version"], INSPECTOR_RUN_INDEX_SCHEMA_VERSION)
        self.assertEqual(ReadOnlyPostgresStore.__name__, "ReadOnlyPostgresStore")


if __name__ == "__main__":
    unittest.main()
