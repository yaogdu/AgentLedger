from __future__ import annotations

import os
import unittest
import uuid
from dataclasses import replace

from agentledger.conformance import StateStoreConformanceRunner, WorkerConformanceRunner
from agentledger.storage_postgres import PostgresDependencyMissing, PostgresStore, PostgresStoreConfig


class PostgresIntegrationTests(unittest.TestCase):
    def test_real_postgres_state_store_conformance(self) -> None:
        if os.environ.get("AGENTLEDGER_RUN_POSTGRES_INTEGRATION") != "1":
            self.skipTest("set AGENTLEDGER_RUN_POSTGRES_INTEGRATION=1 to run real Postgres StateStore checks")
        try:
            base_config = PostgresStoreConfig.from_env()
        except ValueError as exc:
            self.skipTest(str(exc))

        schema_prefix = (base_config.schema or "agentledger").strip() or "agentledger"
        config = replace(base_config, schema=f"{schema_prefix}_it_{uuid.uuid4().hex[:12]}")
        stores: list[PostgresStore] = []

        try:
            probe = PostgresStore(config)
            probe.init()
            probe.close()
        except PostgresDependencyMissing as exc:
            self.skipTest(str(exc))

        def factory() -> PostgresStore:
            store = PostgresStore(config)
            store.init()
            stores.append(store)
            return store

        try:
            report = StateStoreConformanceRunner(factory, name="postgres-real").run()
            worker_report = WorkerConformanceRunner(factory, name="postgres-real-worker", workers=4, concurrent=True).run()
        finally:
            for store in stores:
                store.close()
        self.assertTrue(report.passed, report.to_dict())
        self.assertTrue(worker_report.passed, worker_report.to_dict())
