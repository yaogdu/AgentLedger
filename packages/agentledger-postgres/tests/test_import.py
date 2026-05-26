def test_imports() -> None:
    from agentledger_postgres import PostgresStore, PostgresStoreConfig

    assert PostgresStore.__name__ == "PostgresStore"
    assert PostgresStoreConfig.__name__ == "PostgresStoreConfig"

