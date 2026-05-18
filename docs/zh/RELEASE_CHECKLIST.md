# 发布检查清单

本文是 `../RELEASE_CHECKLIST.md` 的中文主路径版本，用于 v1.0 stable runtime-core release 检查。

## Scope Gate

发布前确认边界仍然清晰：

```text
Agent frameworks own planning and workflow logic.
AgentLedger owns execution guarantees, evidence, replay, tool governance, policy, sandbox boundaries, and adapter contracts.
Core remains dependency-light; concrete integrations stay optional.
No destructive database cleanup command is part of the release path.
Static HTML exports are debug artifacts, not a long-running app.
```

## 必跑本地 Gate

请使用 Python 3.11 或更高版本。如果 `python3` 指向旧版本解释器，请替换为 `python3.11`。

```bash
PYTHONPYCACHEPREFIX=/tmp/agentledger-pycache PYTHONPATH=src python3 -m compileall -q src tests examples
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src PYTHONTRACEMALLOC=10 python3 -W default::ResourceWarning -m unittest discover -s tests -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger --root /tmp/agentledger-release-check conformance
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger lint boundary examples src --exclude src/agentledger --no-fail
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger contract export > /tmp/agentledger-contract.json
python3 -m json.tool /tmp/agentledger-contract.json >/dev/null
diff -u contracts/agentledger.runtime.v1.json /tmp/agentledger-contract.json
```

预期：

```text
compileall exits 0
unit tests pass
ResourceWarning-sensitive tests emit no unclosed database warnings
conformance reports passed=true
boundary lint reports passed=true
contract export is valid JSON
checked-in contract fixture matches current export
```

## 多语言 Runtime Gate

如果本次 release 或 PR 涉及 runtime contract、event/evidence schema、Tool Ledger、policy/approval/sandbox、cost/failure attribution，或 Go/TypeScript/Rust 任一实现，必须额外运行：

```bash
python3.11 scripts/check_language_parity.py
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
```

对于 1.0.1 这类 runtime-core parity release，`audit_python_parity.py` 应报告 `gap_count: 0`。

该 runner 会一次执行 Python reference tests、Go tests、TypeScript tests/check、Rust tests、各 preview 语言 conformance CLI、contract diff、Markdown local link check 和 `git diff --check`。它会读取 `contracts/conformance/runtime_semantics.v1.json` 共享语义清单；JSON report 会包含 `required_semantic_checks`、`semantic_manifest` 与 `language_conformance`，可作为 release notes、CI artifact 和 adapter certification evidence。

## Example Smoke

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/hello_world/hello.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/langgraph/basic_graph.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/media_stream/basic_media_stream.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/media_stream/managed_tool.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger worker-run examples/transient_retry
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/docs
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger tools manifest --format agentledger --example examples/media_stream
```

## 可选外部服务 Gate

只在明确配置测试服务时运行：

```bash
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database PYTHONPATH=src python3 -m agentledger state conformance --backend postgres
AGENTLEDGER_POSTGRES_DSN=postgresql://user:password@localhost:15432/database PYTHONPATH=src python3 -m agentledger worker conformance --backend postgres --concurrent
PYTHONPATH=src python3 -m agentledger blob conformance --backend s3
```

不要指向真实业务数据。

## Evidence Gate

涉及 prompt、policy、tool schema、adapter、replay、state handling 的变更，至少添加一个 evidence-based 检查：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger evidence-regression ./golden-bundle.json ./current-bundle-dir
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger corpus check side-effect ./current-bundle-dir
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m agentledger divergence ./golden-bundle.json ./current-bundle-dir --evidence-paths --fail-on-divergence
```

allow flags 只应在变更有意且 release notes 说明清楚时使用。
