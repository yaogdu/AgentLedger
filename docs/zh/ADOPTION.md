# Adoption Plan

本文跟踪让 AgentLedger 更容易被理解、试用、讨论和验证的近期工作。它不改变 runtime-core scope。

## 为什么需要这条线

AgentLedger 已经有较深的 runtime-core 能力。当前 adoption 的瓶颈不是继续增加大功能，而是让新用户快速回答三个问题：

```text
它解决什么问题？
我能不能三分钟看到效果？
我能不能自己验证这个可靠性声明？
```

## 当前 Adoption 优先级

| 优先级 | 事项 | 验收标准 |
|---|---|---|
| P0 | 3-minute demo | 用户可以运行 Python、Go、TypeScript 或 Rust 的 3-minute demo，看到一次外部副作用、一条 Tool Ledger、安全重试和 replay-safe evidence。 |
| P0 | README 第一屏痛点 | 第一屏先解释 tool side-effect 问题，再介绍架构。 |
| P1 | MCP governance example | dependency-free MCP-style tool 在 Python、Go、TypeScript、Rust 中展示 schema、approval、sandbox metadata、idempotency 和 audit evidence。 |
| P1 | 公开 issue/discussion 清单 | 后续 adoption tasks 可以直接转成 GitHub issue 或 discussion。 |
| P1 | Case study 模板 | 真实集成可以在不暴露私有数据的情况下写清楚。 |

## 建议公开 Issues

项目准备好公开跟踪时，可以把这些条目开成 GitHub issues。

| 标题 | 类型 | 为什么重要 |
|---|---|---|
| Build a cross-language 3-minute Tool Ledger demo | example | 几分钟内跨 Python、Go、TypeScript、Rust 展示核心价值。 |
| Add OpenAI Agents SDK approval/replay example | example | 对接主流 agent SDK 边界，但不声明官方 endorsement。 |
| Add MCP tool governance example | example | 展示 MCP-style tools 如何经过 policy、approval、sandbox、idempotency 和 evidence。 |
| Prototype AgentLedger Inspector | product | 让 run timeline、Tool Ledger、approval、replay 和 failure 可见。 |
| Add Temporal bridge example | integration | 说明 Temporal 管 workflow lifecycle，AgentLedger 管 node 内部 reliability。 |
| Add tool-injection risk scanner | security | 检测危险 tool schema、缺失 approval/sandbox 和 runtime-boundary bypass。 |
| Publish legal-agent case study | case study | 展示真实 audit/evidence 使用场景，但不暴露私有数据。 |

## Case Study 规则

Case study 应该有用，但要克制：

- 移除私有数据、客户数据、secret 和内部实现细节
- 先描述 runtime 问题，再描述 AgentLedger
- 说明 AgentLedger 的集成边界
- 只有在安全时才包含具体 evidence artifact
- 没有真实运维证据时，不声明 production hardening

## 有价值的 Adoption Evidence

- 可运行示例
- 简短 terminal recording 或 GIF
- 公开 issues 和 discussions
- package downloads
- 真实 integration notes
- 外部 demo 或博客文章
- adapter conformance reports
- real-service hardening reports
