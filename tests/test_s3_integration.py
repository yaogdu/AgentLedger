from __future__ import annotations

import os
import unittest
import uuid
from dataclasses import replace

from agentledger.blobstore_s3 import S3BlobStore, S3BlobStoreConfig, S3DependencyMissing
from agentledger.conformance import BlobStoreConformanceRunner


class S3MinIOIntegrationTests(unittest.TestCase):
    def test_real_s3_or_minio_blob_store_conformance(self) -> None:
        if os.environ.get("AGENTLEDGER_RUN_S3_INTEGRATION") != "1":
            self.skipTest("set AGENTLEDGER_RUN_S3_INTEGRATION=1 to run real S3/MinIO BlobStore checks")
        try:
            base_config = S3BlobStoreConfig.from_env()
        except ValueError as exc:
            self.skipTest(str(exc))

        base_prefix = base_config.prefix.strip("/")
        run_prefix = f"{base_prefix}/integration/{uuid.uuid4().hex}" if base_prefix else f"integration/{uuid.uuid4().hex}"
        config = replace(base_config, prefix=run_prefix)

        try:
            S3BlobStore(config)
        except S3DependencyMissing as exc:
            self.skipTest(str(exc))

        def factory() -> S3BlobStore:
            return S3BlobStore(config)

        report = BlobStoreConformanceRunner(factory, name="s3-real").run()
        self.assertTrue(report.passed, report.to_dict())
