import unittest


class InspectorPackageImportTests(unittest.TestCase):
    def test_imports(self) -> None:
        from agentledger_inspector import INSPECTOR_SCHEMA_VERSION, EvidenceStateStoreProtocol, InspectorDataSource, InspectorRedactionPolicy, InspectorReportBuilder, ReadOnlyPostgresStore

        self.assertEqual(INSPECTOR_SCHEMA_VERSION, "agentledger.inspector.v1")
        self.assertEqual(EvidenceStateStoreProtocol.__name__, "EvidenceStateStoreProtocol")
        self.assertEqual(InspectorDataSource.__name__, "InspectorDataSource")
        self.assertEqual(InspectorRedactionPolicy(keys=("password",)).to_dict()["keys"], ["password"])
        self.assertEqual(InspectorReportBuilder.__name__, "InspectorReportBuilder")
        self.assertEqual(ReadOnlyPostgresStore.__name__, "ReadOnlyPostgresStore")


if __name__ == "__main__":
    unittest.main()
