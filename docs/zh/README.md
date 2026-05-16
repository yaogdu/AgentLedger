# AgentLedger 中文文档

这是 AgentLedger 的中文文档入口。英文文档入口见 `../README.md`。

## 推荐阅读路径

| 目标 | 中文文档 | 英文文档 |
|---|---|---|
| 快速了解项目 | `../../README.zh-CN.md` | `../../README.md` |
| 学会使用 runtime | `USAGE.md` | `../USAGE.md` |
| 理解整体架构 | `ARCHITECTURE.md` | `../ARCHITECTURE.md` |
| 理解设计与实现 | `DESIGN_AND_IMPLEMENTATION.md` | `../DESIGN_AND_IMPLEMENTATION.md` |
| 查看正式 runtime 规范 | `../RUNTIME_SPEC.md` | `../RUNTIME_SPEC.md` |
| 查看扩展/adapter 模型 | `EXTENSIBILITY.md` | `../EXTENSIBILITY.md` |
| 查看存储和迁移 | `STORAGE.md` | `../STORAGE.md` |
| 查看当前实现状态 | `IMPLEMENTATION_STATUS.md` | `../IMPLEMENTATION_STATUS.md` |
| 查看路线图 | `ROADMAP.md` | `../ROADMAP.md` |
| 查看发布检查 | `RELEASE_CHECKLIST.md` | `../RELEASE_CHECKLIST.md` |

## 推荐读者路径

| 读者 | 路径 |
|---|---|
| 新用户 | `../../README.zh-CN.md` -> `USAGE.md` -> `../../examples/hello_world/hello.py` -> `../../examples/side_effect_idempotency/README.md` |
| Runtime 实现者 | `ARCHITECTURE.md` -> `DESIGN_AND_IMPLEMENTATION.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` |
| Adapter 作者 | `EXTENSIBILITY.md` -> `ADAPTER_CERTIFICATION.md` -> `../../examples/` 下的相关示例 -> conformance commands |
| Production pilot reviewer | `IMPLEMENTATION_STATUS.md` -> `../MATURITY_MODEL.md` -> `SECURITY_ENTERPRISE.md` -> `STORAGE.md` -> `RELEASE_CHECKLIST.md` |
| 后续语言实现者 | `../MULTI_LANGUAGE.md` -> `../RUNTIME_SPEC.md` -> `../../contracts/agentledger.runtime.v1.json` -> conformance fixtures |

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

runtime-core contract 已稳定；optional production adapter、外部基础设施加固、非 Python 实现和完整 eval 系统仍按独立阶段推进。

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
