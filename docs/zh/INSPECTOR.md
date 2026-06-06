# AgentLedger Inspector

AgentLedger Inspector 是语言无关、只读的 run 调试和审计视图。它消费 AgentLedger runtime metadata 和 evidence bundle；Python、Go、TypeScript、Rust 只要产出同一份 evidence contract，都可以被 Inspector 读取。

它不是长运行服务，也不是 runtime 控制平面。它不会 approve request、cancel run、修改 Tool Ledger、调用工具或访问 model provider。

## 安装

Inspector 可以通过 core CLI 使用，也提供 optional companion package：

```bash
pip install "agentledger-runtime[inspector]"
pip install agentledger-inspector
```

`agentledger-inspector` 只重导出 read model 和 data source API；CLI 入口仍然是 `agentledger`。

## 语言边界

Inspector 只实现一套，作为 companion evidence consumer 存在。Go、TypeScript、Rust 实现不需要各自再做一套 Inspector UI package；只要它们产出符合共享 contract 的 AgentLedger runtime metadata 或 evidence bundle，就可以被同一个 Inspector 读取。

边界是：

- 各语言 runtime 写入 AgentLedger metadata、Tool Ledger、event、artifact 和 evidence
- Inspector 通过稳定 read model `agentledger.inspector.v1` 读取这些数据
- 用户可以基于 read model 二开自己的 viewer、API endpoint 或内部 debug 工具

这样 Inspector 不进入 runtime-core 执行语义，但四种语言实现都能通过同一个工具排查问题。

## 数据来源

Inspector 支持两条只读路径。

| 来源 | 命令形态 | 适用场景 |
|---|---|---|
| 导出的 evidence | `agentledger inspector evidence <path>` | 任意语言实现或 CI job 导出的可移植证据包。 |
| 本地 SQLite runtime | `agentledger inspector run <run_id> --root .agentledger` | 本地开发和小规模部署。 |
| 直接 SQLite 路径 | `agentledger inspector run <run_id> --backend sqlite --db state.db --blob-root blobs` | 自定义 runtime 目录结构。 |
| Postgres metadata | `agentledger inspector run <run_id> --backend postgres --dsn ... --schema ... --blob-root ...` | 使用 server-side StateStore 的部署。 |
| MySQL metadata | `agentledger inspector run <run_id> --backend mysql --dsn ... --database ... --blob-root ...` | 使用 MySQL StateStore 的部署。 |
| 自定义 store | `InspectorDataSource.from_runtime_store(...)` | 内部 viewer、自定义数据库 adapter 或 API service。 |

### Evidence bundle

这是最可移植的方式，适合读取任意语言实现导出的 evidence：

```bash
agentledger inspector evidence ./evidence/<run_id> --html ./inspector.html
agentledger inspector evidence ./bundle.json --out ./inspector.json
```

### Runtime database

这条路径直接读取 AgentLedger runtime metadata。SQLite 会用 read-only mode 打开，Inspector 不会初始化或迁移数据库。

```bash
agentledger inspector run <run_id> --root .agentledger --html ./inspector.html
agentledger inspector run <run_id> --backend sqlite --db .agentledger/state.db --blob-root .agentledger/blobs --out ./inspector.json
```

Postgres 和 MySQL 通过已有 StateStore adapter boundary 读取。Inspector 在这些路径上使用 read-only store wrapper，不会运行 migration，也不会创建表：

```bash
agentledger inspector run <run_id> --backend postgres --dsn "$AGENTLEDGER_POSTGRES_DSN" --schema agentledger --blob-root .agentledger/blobs --html ./inspector.html
agentledger inspector run <run_id> --backend mysql --dsn "$AGENTLEDGER_MYSQL_DSN" --database agentledger --blob-root .agentledger/blobs --html ./inspector.html
```

Postgres/MySQL 建议使用只读数据库账号。AgentLedger 不为 Inspector 单独做一套权限系统；数据库 grant、文件系统 ACL 和部署策略才是权限执行层。Inspector 代码路径不暴露 runtime 写入/控制动作，但 Postgres/MySQL 客户端无法替代数据库侧的只读授权。

`--blob-root` 当前指向本地 blob 目录，用于读取 runtime metadata 中引用的 payload blob。如果 payload blob 在 S3/MinIO 或其它托管对象存储中，优先先导出 evidence bundle，或者通过 extension API 提供自定义 `EvidenceBlobStoreProtocol` 实现。

## 输出

`--out` 写出稳定 JSON read model：

```json
{
  "schema_version": "agentledger.inspector.v1",
  "run": {},
  "summary": {},
  "timeline": [],
  "tool_ledger": [],
  "approvals": [],
  "policy_decisions": [],
  "cost_records": [],
  "failure_events": [],
  "artifacts": []
}
```

`--html` 写出静态 HTML 报告，适合本地或内网排查问题；打开 HTML 不需要启动服务。

## 二开接口

Inspector 分成三层，方便用户二开：

| 层 | API | 用途 |
|---|---|---|
| Data source | `InspectorDataSource` | 读取 evidence path 或 runtime store。 |
| Read model | `InspectorReportBuilder` | 将 evidence 转为 `agentledger.inspector.v1`。 |
| Renderer | `InspectorReport.to_html()` | 默认静态 HTML renderer。 |

示例：

```python
from agentledger import InspectorDataSource, InspectorReportBuilder

report = InspectorDataSource().from_evidence_path("./evidence/run-1")
data = report.to_dict()

custom_report = InspectorReportBuilder().from_evidence_path("./evidence/run-1")
html = custom_report.to_html()
```

可运行示例见 `../../examples/inspector/custom_viewer.py`：它会创建临时 runtime，读取 SQLite metadata，导出 evidence bundle，并基于 `InspectorReport.to_dict()` 生成一个简化自定义视图。

自定义 UI 应优先消费 `InspectorReport.to_dict()`，不要直接读取未文档化的数据库内部表，这样才能跨 storage adapter 和多语言实现保持稳定。

自定义存储集成也可以提供自己的只读 StateStore/BlobStore，然后复用 builder：

```python
from agentledger import EvidenceBlobStoreProtocol, EvidenceStateStoreProtocol, InspectorDataSource

report = InspectorDataSource().from_runtime_store(
    store=my_read_only_state_store,
    blobs=my_read_only_blob_store,
    run_id="run_123",
)
data = report.to_dict()
```

`EvidenceStateStoreProtocol` 和 `EvidenceBlobStoreProtocol` 描述了自定义 backend 需要实现的最小只读 API。这是给用户二开内部 viewer、API endpoint 或自定义 renderer 的推荐扩展点，避免 UI 直接耦合未文档化 SQL 表。

二开时建议稳定依赖这些 contract：

- 将 `InspectorReport.to_dict()` 作为 UI/API 输入
- 保留 `schema_version == "agentledger.inspector.v1"`
- 为自定义 store 实现 `EvidenceStateStoreProtocol` / `EvidenceBlobStoreProtocol`
- Inspector surface 保持只读，不加入写入/控制动作
- 需要 approve、deny、cancel、recover run 时走 runtime API，不要走 Inspector data source

## 安全说明

- Inspector JSON 和 HTML 可能包含敏感运行证据，应按敏感运维数据处理。
- 报告可能包含 tool name、tool status、external id、approval reason、model metadata、artifact ref、payload summary 和 failure detail。
- Postgres/MySQL 使用只读数据库账号。
- 不要基于 Inspector report 自行增加写入动作。runtime 控制应走 runtime API，debug viewer 保持只读。
- 如果 blob store 是远程服务或由其它系统管理，优先使用 evidence bundle 输入。
- 不要用可写账号把 Inspector 指向生产数据库。

## 当前边界

`1.3.0` 已实现：

- 语言无关 read model `agentledger.inspector.v1`
- 静态 HTML report export
- evidence bundle input
- SQLite read-only DB input
- Postgres/MySQL DB input，通过已有 adapter boundary
- 用于自定义 data source 和 renderer 的 extension API
- optional `agentledger-inspector` companion package

本版本不包含：

- 长运行 Web server
- 写入/控制平面动作
- 用户/组织管理
- permission、identity、billing 或 administration backend
- 完整 LangSmith/Langfuse 替代品
- Inspector package 内置 live remote blob adapter
