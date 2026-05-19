# Complete Core Parity Checklist

[English](../COMPLETE_CORE_PARITY_CHECKLIST.md) | [中文](COMPLETE_CORE_PARITY_CHECKLIST.md)

本文定义 AgentLedger Python、Go、TypeScript、Rust 的“完全对齐”。Conformance 通过是必要条件，但不充分。完整 core parity 还要求四种语言在 portable runtime-core 能力、使用体验、文档、测试、package metadata 和 release evidence 上都有对应证据。

## 范围

包含：

- Python、Go、TypeScript、Rust 都能合理存在的 runtime-core 能力
- 跨语言通用 official adapter API：Postgres、S3/MinIO、OTLP transport、Docker sandbox manifest
- 每种语言的 CLI/DX baseline
- 每种语言的 docs、quickstart、examples、conformance、package metadata

排除或不适用：

- 上游生态不存在或不成熟的生态特定 adapter，例如 Python 之外的 LangGraph
- 需要真实外部基础设施的 cloud/service hardening，除非某个 release 明确声明
- SaaS、hosted multi-tenant platform、full eval platform、workflow engine、RAG system、sandbox provider

## 当前边界

严格 core parity gate 已覆盖之前的弱项：

1. 四语言 CLI baseline 已有自动化检查，不再只依赖 conformance。
2. Go、TypeScript、Rust 已有 runnable quickstart example files。
3. TypeScript/Rust package surface 已有 `npm pack --dry-run` / `cargo package --allow-dirty --no-verify` 发布 dry-run，并已完成发布后 clean install smoke。
4. Python、TypeScript、Rust 的 package version 已自动检查；当前 release train 对齐到 `1.0.5`。
5. Go module 外部消费依赖 Git tag/release；每次 release 推送 `go/vX.Y.Z` tag 后都需要重复 clean external `go get` smoke。
6. 真实服务 hardening 仍不属于 core parity，继续作为 optional follow-up 记录。

## 必要完成 Gate

声明完全对齐前必须运行：

```bash
python3.11 scripts/audit_python_parity.py > /tmp/agentledger-python-parity-audit.json
python3.11 scripts/check_language_parity.py --json-report /tmp/agentledger-language-parity.json
python3.11 scripts/check_complete_core_parity.py
```

`check_complete_core_parity.py` 必须在 semantic conformance 之外，检查 CLI baseline、runnable examples、package metadata 和文档链接。
