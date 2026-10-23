# AskData — 调研问数（独立研究项目）

与 Creo **无关**。用 **FastAPI** 重写 LangChat「智能问数」能力，供调研与二次开发。

协议与事件形状参考开源项目 [LangChat/langchat](https://github.com/LangChat/langchat)（Apache-2.0），本仓库不捆绑其完整平台。

## 已锁定选型

| 项 | 选择 |
| --- | --- |
| 后端 | FastAPI 重写问数层 |
| 模型 | 自建轻量 `aigc_model` 表 |
| 流式 | 沿用 LangChat analysis SSE（OpenAI chunk + `delta.event`） |
| 前端 | Vue 3 + Vite + Naive UI，源码在 `web/`，构建后由 FastAPI 挂在 `/` |
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

前端（数据源、问数、模型）在 `web/`。构建一次后，上面的服务会在 `/` 提供页面；没构建时 `/` 会提示构建步骤，`/demo` 仍是静态演示页。

```bash
cd web
npm install
npm run build          # 产物在 web/dist，由 FastAPI 挂到 /
npm run dev            # 开发：Vite 5173，把 /api 代理到 127.0.0.1:8000
```

`npm run dev` 时 API Base URL 留空。页面设置里的 API Key 存在浏览器 localStorage，请求使用 `Authorization: Bearer`。

Mac 上如果用 launchd 把工作目录指到 `~/askData`，那个目录消费的是同一套仓库：同样安装 Python 依赖、执行迁移，并在 `web/` 里 `npm install && npm run build`。不要在 `~/askData` 里维护另一份前端。

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

## 路由一览

- ` /api/v1/datasources` — CRUD / test / introspect / structure（写入应用库）
- ` PUT /api/v1/datasources/{id}/structure` — 只保存表授权。请求体用 LangChat 的 `structureJson`（JSON 字符串或对象），也接受 `structure_json` 对象。不改主机、库名和密码。`GET` 仍直接返回结构对象（不是字符串）
- ` POST /api/v1/datasources/{id}/query` — 只读 SQL（`sql_guard`：仅 SELECT/WITH、表白名单、最多约 200 行、超时约 30 秒）
- ` GET /api/v1/core/data-analysis/catalog?datasourceId=` — 已授权表（`structureJson` 里 imported 且 enabled）
- ` POST /api/v1/core/data-analysis/chat/stream` — NL→SQL，OpenAI 兼容工具循环，SSE
- ` /api/v1/aigc/models` — 轻量模型 CRUD。列表和详情里的 `api_key` 为掩码

`conversationId` 会回显在 `message.start` 里，本服务不保存会话。

## 安全

问数工具 `query_data` 仍然走 `sql_guard`：只允许单条 SELECT/WITH，表必须在本次 `tableNames`（为空则用目录里已授权的表）与 `structureJson` 的交集里，行数和超时沿用 `SQL_MAX_ROWS` / `SQL_TIMEOUT_SECONDS`。

**明文 TODO：** 数据源 `password` 和模型 `api_key` 仍以明文写入应用库（`aigc_datasource.password`、`aigc_model.api_key`）。响应不返回 password，模型密钥只返回掩码（例如 `sk-****1234`）。本版本没有加密落库，生产前需要补上。

服务鉴权使用环境变量 `API_KEY`（`Authorization: Bearer` 或 `X-API-Key`）。未传 `modelId` 时，优先用最近更新的已启用模型；都没有时用 `DEFAULT_MODEL_BASE_URL`、`DEFAULT_MODEL_API_KEY`、`DEFAULT_MODEL_NAME`。`base_url` / `endpoint` 填 OpenAI 兼容前缀，一般以 `/v1` 结尾。

## 本地问数演示

下面用一份 SQLite 样例库跑通「迁移 → 建模型 → 建数据源 → 在 structureJson 里授权表 → catalog → 流式提问」。把 `change-me` 换成 `.env` 里的 `API_KEY`。模型地址和密钥换成你自己的 OpenAI 兼容服务；单元测试不需要真实密钥。

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个终端：

```bash
python scripts/seed_sample_sqlite.py /tmp/askdata-orders.db

# 1. 登记被问数的 SQLite 库
curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{"name":"orders","db_type":"sqlite","database":"/tmp/askdata-orders.db"}' \
  http://127.0.0.1:8000/api/v1/datasources

# 2. 拉结构（introspect 会把表写成 imported=true, enabled=true）
curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/api/v1/datasources/<datasourceId>/introspect

# 3. 只保存表授权。未导入或 enabled=false 的表不会进目录，也不能被 query_data 访问。
#    整份数据源 PUT 仍然接受 structure_json，但改授权不必带上连接字段。
curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -X PUT http://127.0.0.1:8000/api/v1/datasources/<datasourceId>/structure \
  -d '{
    "structureJson": {
      "tables": [{
        "name": "orders",
        "tableName": "orders",
        "comment": "订单",
        "imported": true,
        "enabled": true,
        "columns": [
          {"name": "id", "type": "INTEGER"},
          {"name": "name", "type": "TEXT"},
          {"name": "amount", "type": "REAL"},
          {"name": "created_at", "type": "TEXT"}
        ]
      }]
    }
  }'

# 4. 登记对话模型。响应里的 api_key 是掩码
curl -s -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{
    "name": "默认对话",
    "provider": "openai-compatible",
    "model": "gpt-4o-mini",
    "type": "chat",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-your-key",
    "temperature": 0.2,
    "enabled": true
  }' \
  http://127.0.0.1:8000/api/v1/aigc/models

# 5. 目录只含已授权表
curl -s -H "X-API-Key: change-me" \
  "http://127.0.0.1:8000/api/v1/core/data-analysis/catalog?datasourceId=<datasourceId>"

# 6. 流式问数。结束标记是 data: [DONE]
curl -N -H "X-API-Key: change-me" -H "Content-Type: application/json" \
  -d '{
    "datasourceId": "<datasourceId>",
    "modelId": "<modelId>",
    "question": "每个客户的订单金额合计是多少？",
    "tableNames": ["orders"]
  }' \
  http://127.0.0.1:8000/api/v1/core/data-analysis/chat/stream
```

浏览器打开 <http://127.0.0.1:8000/>（需已执行 `web` 下的 `npm run build`）。在设置里填写 API Key，于数据源页建库、读取表并保存授权，再在问数页提问。静态页 <http://127.0.0.1:8000/demo> 仍可直接调 SSE。

只读查询示例（不经过模型）：

```bash
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
| `message.start` / `log.delta` / `message.completed` / `message.stop` | 可选，便于对齐协议 |

常量与组装函数见 `app/services/sse_assembler.py`。

## 目录

```text
askdata/
├── app/           # FastAPI 应用（构建后的 Vue 挂在 /）
├── alembic/       # 迁移（aigc_datasource / aigc_model）
├── scripts/       # 样例 SQLite
├── web/           # Vue 问数与数据源；demo/ 为静态演示
├── pyproject.toml
├── .env.example
└── README.md
```

## 测试

```bash
pytest
```

测试使用脚本化的模型客户端，不访问真实供应商，也不需要 `DEFAULT_MODEL_API_KEY`。

## 表授权

`structure_json.tables` 里同时看 `imported` 和 `enabled`（也认 LangChat 的 `tableName`）。两者都不是 false 的表才会出现在问数目目录，并成为 `query_data` 的表白名单。缺省标志按 true 处理，所以内省结果默认全部可问。

`POST /datasources/{id}/introspect` 仍会把内省快照写回 `structure_json`（表标记为 imported 且 enabled）。界面在已有授权时会把原标记合并回去，再调用 `PUT /structure` 写回，避免一次内省把勾选冲掉。

## 下一步

1. 生产前加密数据源口令和模型 api_key
2. Oracle / SQL Server 驱动与内省（当前只保证 sqlite、mysql/mariadb、postgres）
3. 服务端多轮会话历史（现在 `conversationId` 只在 `message.start` 回显）

可回看选型页（Cursor Page）：调研问数独立服务选型与骨架。
