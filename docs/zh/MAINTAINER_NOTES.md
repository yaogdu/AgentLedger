# Maintainer Notes

本文说明 AgentLedger 如何维护，以及哪些工作属于这个项目。它面向 contributor、reviewer，以及需要理解维护面的开源项目审核者。

## Maintainer 角色

项目 owner 和 primary maintainer 负责：

- runtime 架构和 scope 决策
- runtime-core contract 设计与兼容性
- roadmap planning 和 release management
- core reliability feature 实现
- issue、pull request 和 adapter proposal review
- 文档、示例和 migration notes
- conformance fixtures 和跨语言 parity gates
- adapter certification boundary 和 maturity label
- tool、approval、sandbox routing、evidence handling 相关安全边界

## 维护原则

AgentLedger 应该保持为 runtime reliability layer，而不是大而全的 Agent 平台。

- runtime-core 保持小、明确、dependency-light。
- framework、storage、observability、sandbox、provider 集成都放到 adapter 后面。
- 优先使用 contract 和 conformance fixture，而不是未记录的隐式行为。
- 把 tool side effect 当成 runtime-managed、可审计操作。
- 失败路径也要记录 evidence，而不只记录成功路径。
- replay 和 shadow execution 必须保证不产生真实外部副作用。
- 诚实标注 maturity：stable、preview、experimental、external-required 或 out-of-scope。
- adapter 没有真实服务验证前，不声明 production hardening 完成。

## 当前维护面

当前维护工作主要围绕这些方向：

| 方向 | Maintainer 工作 |
| --- | --- |
| Runtime contract | 维护 `contracts/agentledger.runtime.v1.json`、runtime event、wire object 和 invariant 稳定 |
| Reliability semantics | 维护 lease、fencing、cancellation、checkpoint/resume、replay、shadow 和 failure attribution 行为 |
| Tool governance | 维护 Tool Ledger、policy decision、approval gate、sandbox routing、idempotency 和 audit evidence |
| Storage and evidence | 维护 StateStore、BlobStore、migration、evidence bundle、static debug export 和查询文档 |
| Adapter boundaries | 保持 optional adapter 可安装，同时不把 heavy dependency 加进 core |
| Language parity | 保持 Python reference behavior 与 Go、TypeScript、Rust conformance gates 对齐 |
| Documentation | 保持 usage、architecture、maturity、comparison、release、roadmap 文档准确 |
| Release quality | 运行 release check、package check、language parity check 和 package publishing verification |

## Review Checklist

Maintainer review 时应关注：

- 这个变更是否保持 runtime boundary？
- 是否引入 hidden state 或绕过 runtime-managed tool call？
- 是否改变 event ordering、state versioning 或 replay 行为？
- 是否引入本该属于 adapter 的 core dependency？
- 是否处理 cancellation、retry、timeout 和 unknown side-effect status？
- 是否记录足够 evidence 用于 debug 和 audit？
- 语义变化是否更新 conformance fixtures？
- public behavior 变化是否更新文档？

## 使用 Coding Agents

Coding agents 可以辅助维护 AgentLedger，但生成的变更仍需要正常工程 review。适合使用 coding agents 的任务包括：

- issue triage 和复现说明
- adapter skeleton 和 conformance fixture 更新
- 文档一致性检查
- changelog 和 release checklist 准备
- failure path regression test 生成
- 跨语言 parity audit
- approval、replay、evidence export、sandbox 示例

Coding agents 不应该用于绕过安全敏感变更 review、release signing、secret、package publishing credential 或破坏性数据操作。

## 当前开源状态

AgentLedger 是早期但活跃维护的项目。它应该被描述为具备 stable runtime-core contract、optional adapter 持续演进的基础设施项目，而不是应用管理产品或已经被广泛部署的成熟系统。

当前较强的公开维护信号包括：

- versioned releases 和 changelog entries
- 正式 runtime 与 adapter 文档
- 多语言实现
- Python、Go、TypeScript、Rust 的 conformance checks
- examples 和查询/debugging 文档
- 明确的 maturity 与 roadmap 文档

后续维护应继续补强真实世界证据：用户示例、issue、discussion、integration guide、adapter hardening report 和 external service validation。
