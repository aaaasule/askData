# AskData — 调研问数（独立研究项目）

与 Creo **无关**。用 **FastAPI** 重写 LangChat「智能问数」能力，供调研与二次开发。

协议与事件形状参考开源项目 [LangChat/langchat](https://github.com/LangChat/langchat)（Apache-2.0），本仓库不捆绑其完整平台。

## 已锁定选型

| 项 | 选择 |
| --- | --- |
| 后端 | FastAPI 重写问数层 |
| 模型 | 自建轻量 `aigc_model` 表 |
| 流式 | 沿用 LangChat analysis SSE（OpenAI chunk + `delta.event`） |
| 前端 | 后续精简迁 Vue 问数/数据源页 → `web/` |
| 鉴权 | API Key（`Authorization: Bearer` 或 `X-API-Key`） |
| JSON | `{ "code": "SUCCESS", "message", "data" }`；**SSE 不包这层** |

## 快速启动

在克隆下来的仓库根目录执行（下面的路径都相对于该目录）：

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # 修改 API_KEY；不要把 .env 提交进 git
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

默认 `DATABASE_URL` 是仓库根目录下的 SQLite 文件 `askdata.db`（已在 `.gitignore`）。这是**应用库**（数据源登记、轻量模型表），不是被问数的业务库。

Postgres / MySQL 走同一个 `DATABASE_URL`，驱动在可选依赖里，当前默认路径不安装它们：

```bash
pip install -e ".[db]"
# .env 示例（占位口令，按环境替换）：
# DATABASE_URL=postgresql+asyncpg://askdata:askdata@localhost:5432/askdata
# DATABASE_URL=mysql+aiomysql://askdata:askdata@localhost:3306/askdata
alembic upgrade head
```

- 健康检查：`GET /health`
- OpenAPI：`http://127.0.0.1:8000/docs`
- API 前缀：`/api/v1`

示例：

```bash
curl -s -H "X-API-Key: change-me" http://127.0.0.1:8000/api/v1/datasources
curl -s -H "Authorization: Bearer change-me" \
  "http://127.0.0.1:8000/api/v1/core/data-analysis/catalog?datasourceId=demo"
```

SSE 桩（需 API Key）：

```bash
curl -N -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"datasourceId":"demo","question":"ping","tableNames":[]}' \
  http://127.0.0.1:8000/api/v1/core/data-analysis/chat/stream
```

## 路由一览（骨架）

- ` /api/v1/datasources` — CRUD / test / introspect / structure（写入应用库）
- ` POST /api/v1/datasources/{id}/query` — 只读 SQL（`sql_guard`：仅 SELECT/WITH、表白名单、最多约 200 行、超时约 30 秒）
- ` /api/v1/core/data-analysis/catalog` — 读已 introspect 的 structure
- ` /api/v1/core/data-analysis/chat/stream` — SSE（NL→SQL 仍是 stub）
- ` /api/v1/aigc/models` — 轻量模型 CRUD（表已迁移，接口仍是 stub）

数据源口令目前明文落在应用库，生产前需要加密（见模型上的 TODO）。响应里不返回 `password`。

只读查询示例（先登记一个 SQLite 业务库，再把允许的表放进 `tables`）：

```bash
curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"name":"biz","db_type":"sqlite","database":"/absolute/path/biz.db"}' \
  http://127.0.0.1:8000/api/v1/datasources

curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"sql":"SELECT id, name FROM orders","tables":["orders"]}' \
  http://127.0.0.1:8000/api/v1/datasources/<id>/query
```

## SSE 事件（必须对齐）

线格式：仅 `data:` 行；结束 `data: [DONE]`。

| name | 说明 |
| --- | --- |
| `message.delta` | 文本增量 `delta.content` |
| `tool.before` / `tool.executed` | 工具前后 |
| `analysis.table` | `columns`, `rows`, `row_count`, `sql`, `title`（蛇形） |
| `analysis.echart` | `chart_type`, `option`（`series` 非空）, `title` |
| `error` / `timeout` | `code`, `message` |

常量与组装函数见 `app/services/sse_assembler.py`。

## 目录

```text
askdata/
├── app/           # FastAPI 应用
├── alembic/       # 迁移（aigc_datasource / aigc_model）
├── web/           # 待迁 Vue
├── pyproject.toml
├── .env.example
└── README.md
```

## 测试

```bash
pytest
```

## 下一步

1. 实现 `AnalysisRuntime` 工具循环，调用 `DatasourceService.execute_read_only_query`
2. 落地 `aigc_model` CRUD，并在生产前加密数据源口令
3. 迁入 `web/` Vue 页并对齐路径  

可回看选型页（Cursor Page）：调研问数独立服务选型与骨架。
