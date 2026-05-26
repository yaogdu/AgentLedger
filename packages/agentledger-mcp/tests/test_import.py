def test_imports() -> None:
    from agentledger_mcp import MCPContextAdapter, MCPToolAdapter

    assert MCPContextAdapter.__name__ == "MCPContextAdapter"
    assert MCPToolAdapter.__name__ == "MCPToolAdapter"

