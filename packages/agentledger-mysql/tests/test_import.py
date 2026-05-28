def test_mysql_adapter_imports():
    from agentledger_mysql import MySQLStore, MySQLStoreConfig

    assert MySQLStore.__name__ == "MySQLStore"
    assert MySQLStoreConfig.__name__ == "MySQLStoreConfig"
