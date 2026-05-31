# 开源影响力

AgentLedger 是一个早期开源基础设施项目，面向生产级 AI Agent 的可靠性与治理问题。它不是 Agent 框架，不是托管平台，也不替代 LangGraph、Temporal、Langfuse、MCP 或模型供应商。它的价值在于提供这些系统可以共享的 runtime boundary：durable state、governed tool use、evidence、replay、policy check、sandbox routing 和 cost/failure attribution。

## 生态问题

很多 Agent 项目能先跑通 happy path，但离生产环境可靠运行还有一段距离。真正困难的问题通常出现在 demo 之后：

- worker 在模型调用之后、状态提交之前崩溃
- tool timeout，但外部系统可能已经被修改
- retry 重复发送邮件、创建 ticket、写数据库或执行基础设施操作
- prompt、模型、tool schema 变更后缺少可复现执行记录
- reviewer 无法判断是哪次 state、tool result、policy decision 或 approval 导致最终结果
- 团队用零散日志和 retry patch 代替统一 reliability contract

这些是基础设施问题，不是 prompt engineering 问题。AgentLedger 关注 execution layer，在这一层强制管理状态转换、工具副作用、审批、证据和 replay。

## AgentLedger 提供什么

AgentLedger 提供一个 runtime reliability layer，可以放在 Agent 框架和 orchestration 系统的下方或旁边。

| 能力 | 生态价值 |
| --- | --- |
| Durable execution records | Agent run 可以基于已提交 runtime event 恢复、检查和 replay，而不是依赖内存状态。 |
| Tool Ledger | 工具副作用具备 idempotency key、causal request record、状态跟踪和 audit evidence。 |
| Policy and approval gates | 高风险工具可以在执行前强制要求权限、人类审批或 sandbox routing。 |
| Evidence bundles | debug、review、合规和 regression check 可以消费一份可携带的 state、tool result、artifact、cost、failure 记录。 |
| Replay and shadow semantics | 历史 run 可以在不重复外部副作用的情况下 replay，新逻辑可以和历史 evidence 做对比。 |
| Adapter contracts | 框架、存储、observability、MCP-style tool system 和 sandbox executor 可以集成进来，而不会把 runtime-core 变成臃肿平台。 |
| Multi-language runtime contract | Python、Go、TypeScript、Rust 对齐同一份 language-neutral runtime contract 和共享 conformance fixtures。 |

## 和 Agent 框架的区别

Agent 框架通常负责 planning、reasoning、graph routing、prompt strategy 和 model/tool selection。AgentLedger 负责 execution 周围的 reliability boundary：

```text
Agent framework:
  决定下一步应该做什么

AgentLedger:
  让这一步执行具备持久化、治理、审计、replay 和恢复能力
```

因此 AgentLedger 的设计目标是和已有框架组合使用，而不是替代它们。LangGraph、OpenAI Agents SDK、CrewAI、AutoGen、LlamaIndex、Semantic Kernel 或自定义 Agent 可以继续保留自己的 reasoning model；AgentLedger 负责记录 durable runtime evidence 并治理副作用。

## 当前阶段

AgentLedger 仍是年轻项目。当前阶段更应该看基础设施深度和 contract 清晰度，而不是只看广泛采用指标。

已经具备的内容：

- stable v1.x runtime-core contract
- Python reference implementation
- Go、TypeScript、Rust runtime-core parity gates
- Tool Ledger、evidence/replay、policy/approval/sandbox boundary、cost/failure attribution、worker/conformance 和 adapter seam
- storage、observability、sandbox、framework、protocol adapter 的 optional package boundary
- architecture、runtime spec、storage、adapter、maturity、release check、language parity 等正式文档

仍然明确不属于当前 core 或属于后续阶段：

- 托管 dashboard 产品
- 完整 eval 平台
- RAG/vector memory 系统
- 对每个外部 backend 的生产级声明
- 替代成熟 workflow、tracing 或 sandbox infrastructure

## 开源维护价值

AgentLedger 值得以开源方式维护，因为这个问题横跨整个 Agent 生态。不同团队可能使用不同 Agent 框架和部署栈，但都会遇到类似 runtime reliability 问题：

- 哪些副作用已经发生？
- 哪些 tool call 被审批过？
- 当时使用的是哪个 state version？
- 这个 run 能不能恢复？
- 这个结果能不能复现？
- 这个失败能不能归因？
- 新版本 Agent 能不能和历史 evidence 对比？

开源开发可以让 runtime contract、adapter boundary、conformance fixture 和 example 更容易被不同生态复用和审查。

