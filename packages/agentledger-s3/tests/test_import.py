def test_imports() -> None:
    from agentledger_s3 import S3BlobStore, S3BlobStoreConfig

    assert S3BlobStore.__name__ == "S3BlobStore"
    assert S3BlobStoreConfig.__name__ == "S3BlobStoreConfig"

