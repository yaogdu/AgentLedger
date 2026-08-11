# Adapter Validation

本文档说明官方 production-pilot adapter 的本地真实服务验证路径。它比 injected-client conformance 更强，但仍然不等于 production hardening 声明。

## 覆盖范围

本地验证栈会启动一次性 Docker 服务，并用现有 AgentLedger conformance 命令检查：

- Postgres StateStore conformance
- Postgres worker concurrency conformance
- 基于 MinIO 的 S3-compatible BlobStore conformance

它不验证 cloud IAM、KMS、lifecycle rules、数据库 backup/restore、Docker daemon hardening、OTLP collector、Langfuse server ingestion 或生产网络策略。

## 运行

先在 Python 环境里安装可选客户端依赖：

```bash
python3 -m pip install "psycopg[binary]" boto3
```

然后运行：

```bash
bash scripts/validate_adapters_local.sh --output-dir /tmp/agentledger-adapter-validation
```

也可以用临时依赖运行，不创建项目虚拟环境：

```bash
UV_CACHE_DIR=/tmp/agentledger-uv-cache uv run --no-project --with "psycopg[binary]" --with boto3 --python python3 python scripts/validate_adapters_local.py --output-dir /tmp/agentledger-adapter-validation
```

脚本默认使用：

- `examples/adapter_validation/docker-compose.yml`
- Postgres：`127.0.0.1:15432`
- MinIO S3 API：`127.0.0.1:19000`
- bucket：`agentledger-runs`
- 每次运行一个唯一 S3 prefix

默认会在结束时执行 `docker compose down -v` 清理服务。调试时可以加 `--keep-services`。

## 输出

脚本会写：

```text
/tmp/agentledger-adapter-validation/adapter-validation.json
/tmp/agentledger-adapter-validation/adapter-validation.md
```

`adapter-validation.json` 使用 schema `agentledger.adapter_validation.v1`，包含：

- 脱敏后的服务配置
- 每个 check 的名称、命令、状态、返回码和耗时
- 可解析时的 conformance JSON
- stdout/stderr 文件路径
- 仍然属于 `external-required` 的验证项

## 如何理解结果

`ok=true` 表示本地一次性真实服务通过了 adapter conformance 路径。它可以作为 release evidence，说明 Postgres/S3 已经从“只有 contract”推进到“本地真实服务验证”。

它仍然不足以声明 production hardening。生产级声明还需要：

- Postgres backup/restore 或 rollback drill
- 目标数据库上的预期并发 worker 测试
- 数据库 role 和 schema isolation 审查
- S3/MinIO lifecycle、encryption 和 restore 检查
- 使用云 S3 时的 IAM/KMS 策略审查
- 执行不可信代码时的 Docker daemon 或 sandbox infrastructure hardening

不要把这个脚本指向真实业务数据。
