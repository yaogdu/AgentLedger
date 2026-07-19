# agentledger-langgraph

LangGraph-compatible checkpointer and node adapter package for AgentLedger.

```bash
pip install agentledger-langgraph
pip install "agentledger-runtime[langgraph]"
```

```python
from agentledger_langgraph import LangGraphCheckpointerAdapter, LangGraphNodeAdapter
```

The current package exposes the dependency-free AgentLedger facade. Install the optional `sdk` extra when a project wants to combine it with a concrete LangGraph version:

```bash
pip install "agentledger-langgraph[sdk]"
```

Certification:

```bash
python3 -m agentledger adapter certify --kind langgraph --adapter-version 1.5.2
```
