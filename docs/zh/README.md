# AgentLedger 中文文档

这是 AgentLedger 的中文文档入口。英文文档入口见 `../README.md`。

AgentLedger 是面向 Agent Harness stack 的 runtime reliability layer。它不是完整 Harness 产品，而是提供 durable execution、tool/model governance、evidence、replay、policy/sandbox、cost/failure attribution 和 adapter contracts，用来组合 LangGraph、Temporal、Langfuse、MCP、model provider、storage backend 和 sandbox infrastructure 等系统。

## 推荐阅读路径

| 目标 | 中文文档 | 英文文档 |
|---|---|---|
| 运行 3 分钟副作用安全 showcase | `../../examples/showcase/duplicate_side_effect_crash/README.md` | same path |
| 从零开始 | `GETTING_STARTED.md` | `../GETTING_STARTED.md` |
| 快速了解项目 | `../../README.zh-CN.md` | `../../README.md` |
| 判断 AgentLedger 是否适合你的场景 | `USE_CASES.md` | `../USE_CASES.md` |
| 学会使用 runtime | `USAGE.md`, `LANGUAGE_QUICKSTART.md` | `../USAGE.md`, `../LANGUAGE_QUICKSTART.md` |
| 查找示例 | `../../examples/README.md`, `../../go/examples/README.md`, `../../typescript/examples/README.md`, `../../rust/examples/README.md` | same paths |
| 查询 runtime 表 | `QUERY_EXAMPLES.md` | `../QUERY_EXAMPLES.md` |
| 可视化排查 run | `INSPECTOR.md` | `../INSPECTOR.md` |
| 运行 benchmark 和覆盖门禁 | `BENCHMARKS.md` | `../BENCHMARKS.md` |
| 理解开源生态价值 | `OPEN_SOURCE_IMPACT.md` | `../OPEN_SOURCE_IMPACT.md` |
| 理解维护者职责 | `MAINTAINER_NOTES.md` | `../MAINTAINER_NOTES.md` |
| 规划 adoption 工作 | `ADOPTION.md` | `../ADOPTION.md` |
| 理解整体架构 | `ARCHITECTURE.md` | `../ARCHITECTURE.md` |
| 理解 Policy Engine 控制闭环 | `POLICY_ENGINE.md` | `../POLICY_ENGINE.md` |
| 对比相邻工具 | `COMPARISONS.md` | `../COMPARISONS.md` |
| 理解 Harness stack 组合方式 | `HARNESS_STACK.md` | `../HARNESS_STACK.md` |
| 理解 Agent Harness 定位 | `ROADMAP.md#agent-harness-定位` | `../ROADMAP.md#agent-harness-positioning` |
| 规划 Oh My Pi / OMP runtime adapter | `OMP_RUNTIME_ADAPTER_DESIGN.md` | `../OMP_RUNTIME_ADAPTER_DESIGN.md` |
| 理解设计与实现 | `DESIGN_AND_IMPLEMENTATION.md` | `../DESIGN_AND_IMPLEMENTATION.md` |
| 查看正式 runtime 规范 | `../RUNTIME_SPEC.md` | `../RUNTIME_SPEC.md` |
| 查看扩展/adapter 模型 | `EXTENSIBILITY.md` | `../EXTENSIBILITY.md` |
| 查看存储和迁移 | `STORAGE.md`, `MYSQL.md` | `../STORAGE.md`, `../MYSQL.md` |
| 查看当前实现状态 | `IMPLEMENTATION_STATUS.md` | `../IMPLEMENTATION_STATUS.md` |
| 查看路线图 | `ROADMAP.md` | `../ROADMAP.md` |
| 查看发布检查 | `RELEASE_CHECKLIST.md` | `../RELEASE_CHECKLIST.md` |
| 理解多语言 parity | `LANGUAGE_IMPLEMENTATION_COMPARISON.md`, `LANGUAGE_PARITY_MATRIX.md` | `../LANGUAGE_IMPLEMENTATION_COMPARISON.md`, `../MULTI_LANGUAGE.md` |
| 理解 execution backends | `EXECUTION_BACKENDS.md` | `../EXECUTION_BACKENDS.md` |
| 规划 1.5.0 framework/Temporal adoption | `FRAMEWORK_TEMPORAL_ADOPTION_DESIGN.md` | `../FRAMEWORK_TEMPORAL_ADOPTION_DESIGN.md` |

## 推荐读者路径

| 读者 | 路径 |
|---|---|
| 新用户 | `GETTING_STARTED.md` -> `LANGUAGE_QUICKSTART.md` -> `../../examples/README.md` -> 对应语言 example README |
| Runtime 实现者 | `ARCHITECTURE.md` -> `COMPARISONS.md` -> `DESIGN_AND_IMPLEMENTATION.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` |
| Adapter 作者 | `EXTENSIBILITY.md` -> `ADAPTER_PACKAGING.md` -> `ADAPTER_CERTIFICATION.md` -> `../../examples/` 下的相关示例 -> conformance commands |
| Production pilot reviewer | `IMPLEMENTATION_STATUS.md` -> `../MATURITY_MODEL.md` -> `SECURITY_ENTERPRISE.md` -> `STORAGE.md` -> `RELEASE_CHECKLIST.md` |
| 后续语言实现者 | `../MULTI_LANGUAGE.md` -> `LANGUAGE_PARITY_MATRIX.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` -> `../../contracts/conformance/runtime_semantics.v1.json` -> `../../contracts/conformance/runtime_baseline.v1.json` -> language README -> conformance fixtures |

## 项目定位

AgentLedger 不是新的 Agent 框架，也不是完整 Agent Harness 平台，而是面向 Agent Harness stacks 的 framework-neutral runtime reliability layer。

```text
Agent 框架负责 planning / workflow / reasoning。
AgentLedger 负责 execution guarantees / evidence / replay / tool governance / policy / sandbox / adapter contracts。
```

## 当前状态

当前 1.5.x 是 stable runtime-core release，Python 是 reference implementation，Go、TypeScript、Rust 已由共享 runtime-core parity gate 覆盖，并包含 read-only Inspector evidence/runtime metadata consumer，适合：

- 本地使用
- runtime 设计评审
- framework adapter integration
- adapter 实验
- reliability semantics 验证
- 在明确 adapter 边界下做 production pilot 准备

runtime-core contract 已稳定；optional production adapter、外部基础设施加固、framework-native package hardening 和完整 eval 系统仍按独立阶段推进。多语言目标是 Python、Go、TypeScript、Rust 共享 runtime-core contract 和 conformance，而不是只提供薄 SDK。

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

更细的 API、schema、Postgres、MySQL、S3/MinIO 和 adapter certification 细节仍以英文规范为准；中文主路径会覆盖定位、使用、架构、实现状态、路线图和发布检查。

## 多语言对齐

在仓库根目录执行 `python3.11 scripts/check_language_parity.py`，可以一次跑 Python reference tests、Go、TypeScript、Rust、contract diff、Markdown link 和 whitespace checks。该 runner 会读取 `contracts/conformance/runtime_semantics.v1.json` 作为 required semantic-check manifest。

- [`LANGUAGE_PARITY_AUDIT.md`](LANGUAGE_PARITY_AUDIT.md) - Python 与 Go/TypeScript/Rust parity claim 的 completion audit。

## 文档结构原则

当前文档按读者任务拆分，不建议合并成一个巨大手册：

- `README.md` / `README.zh-CN.md` 是项目入口。
- `USE_CASES.md` 是采用入口，回答适合什么场景、什么时候不该优先接、3 分钟 demo 怎么验证。
- `../articles/what-happened-after-agent-tool-failure.zh-CN.md` 和 `../articles/social-posts.md` 是传播型内容入口，用来解释 tool success 后 crash/retry 的真实风险和录制 GIF。
- `GETTING_STARTED.md` 和 `LANGUAGE_QUICKSTART.md` 是使用路径。
- `ARCHITECTURE.md`、`DESIGN_AND_IMPLEMENTATION.md`、`RUNTIME_SPEC.md` 是设计路径。
- `BENCHMARKS.md` 是 benchmark 和覆盖矩阵入口，说明如何验证全部 required semantic checks。
- `FRAMEWORK_TEMPORAL_ADOPTION_DESIGN.md` 是 1.5.0 adoption 设计入口，说明 OpenAI Agents SDK-style example、framework-native smoke 和 Temporal bridge 边界。
- `OMP_RUNTIME_ADAPTER_DESIGN.md` 是 OMP runtime adapter 设计入口，说明 OMP runtime event 映射、state versioning、redaction、replay 和不做应用定制的边界。
- `IMPLEMENTATION_STATUS.md`、`MATURITY_MODEL.md`、`LANGUAGE_IMPLEMENTATION_COMPARISON.md` 是 stable、parity、preview、optional、out-of-scope 的事实来源。
- `ADAPTER_PACKAGING.md`、`ADAPTER_CERTIFICATION.md`、`ADAPTER_ROADMAP.md` 是 adapter 作者路径。

后续新增文档时，不要重复粘贴完整能力矩阵；优先链接到 status/comparison 文档，并保持 README 级内容简洁。
