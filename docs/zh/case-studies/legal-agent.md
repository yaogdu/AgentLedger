# Case Study 模板：Legal Agent Tool Audit

这是一个公开安全的模板，用来记录 AgentLedger 如何用于 legal-agent workflow。不要包含私有客户数据、机密文档、secret 或内部部署细节。

## 问题

Legal agent 经常调用工具读取文档、创建 review note、起草材料或更新 case-management 系统。一次失败的 run 可能留下很多难以回答的问题：

- 调用了哪些工具？
- 使用了哪些输入和 state version？
- 写操作是否真的发生？
- 高风险工具是否被审批？
- 能不能在不再次触碰法律系统的情况下 replay？
- reviewer 能不能检查 evidence，而不是重新运行 agent？

## AgentLedger 边界

AgentLedger 应该包住 model/tool/state boundary：

```text
legal agent logic
  -> AgentLedger AgentContext
  -> ToolGateway / policy / approval / Tool Ledger
  -> document tools, case tools, storage tools
  -> evidence bundle / replay / audit report
```

AgentLedger 不负责法律推理、法律建议、文档解读或业务流程。它负责 runtime evidence 和 side-effect governance。

## 集成说明

真实 case study 应该记录这些内容：

| 项目 | 说明 |
|---|---|
| Agent framework | LangGraph、OpenAI Agents SDK、自定义 Python 或其它 |
| Runtime store | SQLite、Postgres、MySQL |
| Artifact store | local blobs、S3/MinIO、内部对象存储 |
| 被治理的工具 | document read、note write、case update、email、PR/ticket creation |
| 高风险控制 | approval required、sandbox required、redaction required、budget cap |
| 导出的 evidence | bundle JSON、static HTML、trace JSONL、replay summary |
| 私有数据处理 | redaction、synthetic samples、omitted fields |

## 预期 Evidence

有用且可公开的 case study 可以包含脱敏后的：

- Tool Ledger rows
- approval records
- replay summary
- final state shape
- failure attribution report
- static HTML evidence screenshot

不要包含 privileged legal text、个人数据、生产 secret 或真实客户标识。

## 摘要模板

```text
We used AgentLedger to wrap the legal agent's tool boundary. The integration
records document/tool calls, approval decisions, state transitions, and evidence
bundles so failed or disputed runs can be inspected and replayed without
repeating external side effects.
```

