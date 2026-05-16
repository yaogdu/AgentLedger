# Docs Tool Catalog Demo

This example name is used by the tool catalog CLI to register a dependency-free
`docs.read` tool specification. It is a catalog fixture, not a Python module.

Export the AgentLedger tool manifest:

```bash
PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
```

Export an OpenAI-compatible function-tool descriptor:

```bash
PYTHONPATH=src python3 -m agentledger tools manifest --format openai --example examples/docs
```

The fixture demonstrates the runtime-owned tool schema boundary:

```text
ToolSpec
  -> input_schema
  -> output_schema
  -> manifest export
  -> framework adapter consumption
```

It does not read files or call external services.
