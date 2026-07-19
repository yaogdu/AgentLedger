# OMP Runtime Bridge Demo

This example shows the generic Oh My Pi / OMP runtime adapter boundary. It does not depend on OMP internals and does not encode any Her-specific paths or product semantics.

The bridge accepts normalized runtime records:

- session and turn lifecycle
- externally executed model call evidence
- model-proposed tool calls
- externally executed tool results and Tool Ledger status
- versioned state changes with before/after/diff artifact refs
- retryable model/runtime failure evidence

Run:

```bash
PYTHONPATH=src python3 examples/omp_bridge/demo.py
```

Cross-language equivalents:

```bash
cd go && go run ./examples/omp_bridge
cd typescript && node examples/omp_bridge/omp_bridge.js
cd rust && cargo run --example omp_bridge
```
