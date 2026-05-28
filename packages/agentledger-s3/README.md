# agentledger-s3

S3-compatible BlobStore adapter package for AgentLedger.

```bash
pip install agentledger-s3
pip install "agentledger-runtime[s3]"
```

```python
from agentledger_s3 import S3BlobStore, S3BlobStoreConfig

blobs = S3BlobStore(S3BlobStoreConfig.from_env())
```

This package supports AWS S3 and S3-compatible services such as MinIO through `endpoint_url`. It re-exports the stable adapter classes from `agentledger.blobstore_s3` in the `1.2.x` line.

Certification:

```bash
python3 -m agentledger adapter certify --kind s3 --adapter-version 1.2.2
```

