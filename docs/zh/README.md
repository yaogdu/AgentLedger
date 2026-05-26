# AgentLedger 中文文档

这是 AgentLedger 的中文文档入口。英文文档入口见 `../README.md`。

## 推荐阅读路径

| 目标 | 中文文档 | 英文文档 |
|---|---|---|
| 从零开始 | `GETTING_STARTED.md` | `../GETTING_STARTED.md` |
| 快速了解项目 | `../../README.zh-CN.md` | `../../README.md` |
| 学会使用 runtime | `USAGE.md`, `LANGUAGE_QUICKSTART.md` | `../USAGE.md`, `../LANGUAGE_QUICKSTART.md` |
| 查找示例 | `../../examples/README.md`, `../../go/examples/README.md`, `../../typescript/examples/README.md`, `../../rust/examples/README.md` | same paths |
| 理解整体架构 | `ARCHITECTURE.md` | `../ARCHITECTURE.md` |
| 理解 Policy Engine 控制闭环 | `POLICY_ENGINE.md` | `../POLICY_ENGINE.md` |
| 对比相邻工具 | `COMPARISONS.md` | `../COMPARISONS.md` |
| 理解设计与实现 | `DESIGN_AND_IMPLEMENTATION.md` | `../DESIGN_AND_IMPLEMENTATION.md` |
| 查看正式 runtime 规范 | `../RUNTIME_SPEC.md` | `../RUNTIME_SPEC.md` |
| 查看扩展/adapter 模型 | `EXTENSIBILITY.md` | `../EXTENSIBILITY.md` |
| 查看存储和迁移 | `STORAGE.md` | `../STORAGE.md` |
| 查看当前实现状态 | `IMPLEMENTATION_STATUS.md` | `../IMPLEMENTATION_STATUS.md` |
| 查看路线图 | `ROADMAP.md` | `../ROADMAP.md` |
| 查看发布检查 | `RELEASE_CHECKLIST.md` | `../RELEASE_CHECKLIST.md` |
| 理解多语言 parity | `LANGUAGE_PARITY_MATRIX.md`, `LANGUAGE_IMPLEMENTATION_COMPARISON.md` | `../MULTI_LANGUAGE.md`, `../LANGUAGE_IMPLEMENTATION_COMPARISON.md` |
| 理解 execution backends | `EXECUTION_BACKENDS.md` | `../EXECUTION_BACKENDS.md` |

## 推荐读者路径

| 读者 | 路径 |
|---|---|
| 新用户 | `GETTING_STARTED.md` -> `LANGUAGE_QUICKSTART.md` -> `../../examples/README.md` -> 对应语言 example README |
| Runtime 实现者 | `ARCHITECTURE.md` -> `COMPARISONS.md` -> `DESIGN_AND_IMPLEMENTATION.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` |
| Adapter 作者 | `EXTENSIBILITY.md` -> `ADAPTER_PACKAGING.md` -> `ADAPTER_CERTIFICATION.md` -> `../../examples/` 下的相关示例 -> conformance commands |
| Production pilot reviewer | `IMPLEMENTATION_STATUS.md` -> `../MATURITY_MODEL.md` -> `SECURITY_ENTERPRISE.md` -> `STORAGE.md` -> `RELEASE_CHECKLIST.md` |
| 后续语言实现者 | `../MULTI_LANGUAGE.md` -> `LANGUAGE_PARITY_MATRIX.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` -> `../../contracts/conformance/runtime_semantics.v1.json` -> `../../contracts/conformance/runtime_baseline.v1.json` -> language README -> conformance fixtures |

## 项目定位

AgentLedger 不是新的 Agent 框架，而是一个 framework-neutral runtime reliability layer。

```text
Agent 框架负责 planning / workflow / reasoning。
AgentLedger 负责 execution guarantees / evidence / replay / tool governance / policy / sandbox / adapter contracts。
```

## 当前状态

当前 Python 实现是 v1.0 stable runtime-core release，适合：

- 本地使用
- runtime 设计评审
- framework adapter integration
- adapter 实验
- reliability semantics 验证
- 在明确 adapter 边界下做 production pilot 准备

runtime-core contract 已稳定；optional production adapter、外部基础设施加固、非 Python stable runtime-readiness 和完整 eval 系统仍按独立阶段推进。Go、TypeScript、Rust 已有 native runtime-core baselines；多语言长期目标是 Python、Go、TypeScript、Rust 的 native runtime-core parity，而不是只提供薄 SDK。

## 仓库规范

- 许可证：`../../LICENSE`
- 安全报告：`../../SECURITY.md`
- 贡献方式：`../../CONTRIBUTING.md`
- 社区行为：`../../CODE_OF_CONDUCT.md`
- 发布检查：`RELEASE_CHECKLIST.md`
- 版本与兼容策略：`../VERSIONING.md`

## 文档范围

中文文档覆盖主要读者路径：

- 项目定位
- 使用方式
- 架构图和分层说明
- 设计与实现细节
- 与英文规范文档的对应关系

更细的 API、schema、Postgres、S3/MinIO 和 adapter certification 细节仍以英文规范为准；中文主路径会覆盖定位、使用、架构、实现状态、路线图和发布检查。

## 多语言对齐

在仓库根目录执行 `python3.11 scripts/check_language_parity.py`，可以一次跑 Python reference tests、Go、TypeScript、Rust、contract diff、Markdown link 和 whitespace checks。该 runner 会读取 `contracts/conformance/runtime_semantics.v1.json` 作为 required semantic-check manifest。

- [`LANGUAGE_PARITY_AUDIT.md`](LANGUAGE_PARITY_AUDIT.md) - Python 与 Go/TypeScript/Rust parity claim 的 completion audit。
