# AgentLedger Examples

[English](README.md) | [中文](../docs/zh/GETTING_STARTED.md#3-找示例)

Run Python examples from the repository root with `PYTHONPATH=src` unless the example says otherwise.

| Goal | Path | Command / note |
|---|---|---|
| Smallest hello-world run | `hello_world/hello.py` | `PYTHONPATH=src python3 examples/hello_world/hello.py` |
| Idempotent side effects | `side_effect_idempotency/README.md` | Demonstrates Tool Ledger retry behavior. |
| Transient retry | `transient_retry/README.md` | Demonstrates retryable errors and recovery. |
| Travel assistant demo | `travel_assistant/demo.py` | Rich local demo with policy/storage options. |
| LangGraph adapter | `langgraph/basic_graph.py` | Python-only ecosystem adapter. |
| LangChain adapter | `langchain/basic_runnable.py` | Python-only ecosystem adapter. |
| CrewAI adapter | `crewai/basic_crew.py` | Python-only ecosystem adapter. |
| AutoGen adapter | `autogen/basic_agent.py` | Python-only ecosystem adapter. |
| OpenAI Agents SDK adapter | `openai_agents/basic_agent.py` | Python-only ecosystem adapter. |
| LlamaIndex adapter | `llamaindex/basic_query.py` | Python-only ecosystem adapter. |
| Semantic Kernel adapter | `semantic_kernel/basic_kernel.py` | Python-only ecosystem adapter. |
| MCP tool/context | `mcp_tool/basic_tool.py`, `mcp_context/basic_context_server.py` | Dependency-free MCP-style examples. |
| Tool catalog | `tool_catalog/basic_catalog.py` | Tool registry/catalog shape. |
| Sandbox tool | `sandbox/command_tool.py` | Uses `sandbox/sandbox.yaml`. |
| Boundary lint | `lint/boundary_rules.json` | Example lint rules. |
| Media/stream refs | `media_stream/basic_media_stream.py` | Artifact refs and stream checkpoints, not media processing. |

Other language examples:

- Go: `../go/examples/README.md`
- TypeScript: `../typescript/examples/README.md`
- Rust: `../rust/examples/README.md`

Start from `../docs/GETTING_STARTED.md` if you want a guided path.
