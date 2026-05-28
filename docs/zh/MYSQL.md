# MySQL Adapter

AgentLedger `1.2.2` 增加了官方可选 MySQL StateStore adapter boundary。

这不是 runtime-core 依赖。只有应用需要把 durable state 放到 MySQL 时再安装：

```bash
pip install "agentledger-runtime[mysql]"
# 或
pip install agentledger-mysql
```

## 配置

```bash
export AGENTLEDGER_MYSQL_DSN="mysql://agentledger:password@127.0.0.1:3306/agentledger"
python3 -m agentledger migrate status --dialect mysql
python3 -m agentledger migrate up --dialect mysql
```

如果 DSN 没有包含 database name，可以设置：

```bash
export AGENTLEDGER_MYSQL_DATABASE="agentledger"
```

Python 代码：

```python
from agentledger_mysql import MySQLStore, MySQLStoreConfig

store = MySQLStore(MySQLStoreConfig.from_env())
store.init()
```

## 范围

这个 adapter 提供 DDL、migration metadata、CLI migration/status wiring、Python `pymysql` 连接，以及 Go、TypeScript、Rust 的 injected-client adapter contract。

生产可用仍需要外部验证：真实 MySQL 服务测试、最小权限账号、并发/负载检查、备份/恢复演练、schema rollout 流程和运维监控。
