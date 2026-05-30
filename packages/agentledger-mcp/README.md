# agentledger-mcp

MCP-style tool and context adapter package for AgentLedger.

```bash
pip install agentledger-mcp
pip install "agentledger-runtime[mcp]"
```

```python
from agentledger_mcp import MCPToolAdapter, MCPContextAdapter
```

This package exposes the runtime-owned conversion between MCP-style descriptors and AgentLedger `ToolSpec` objects. Concrete MCP transports can be added behind this package without changing runtime-core.

Certification:

```bash
python3 -m agentledger adapter certify --kind mcp --adapter-version 1.2.3
```

