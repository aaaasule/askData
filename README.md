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

```bash
cd /workspace/askdata   # 或你的克隆路径
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env    # 修改 API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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

- ` /api/v1/datasources` — CRUD / test / introspect / structure
- ` /api/v1/core/data-analysis/catalog`
- ` /api/v1/core/data-analysis/chat/stream` — SSE
- ` /api/v1/aigc/models` — 轻量模型 CRUD

业务逻辑多为 stub / `NotImplemented`，见各 `services/*`。

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
├── alembic/       # 迁移占位
├── web/           # 待迁 Vue
├── pyproject.toml
├── .env.example
└── README.md
```

## 下一步

1. 接上 AsyncSession + Alembic，落地 datasource / model CRUD  
2. 实现 `sql_guard` + 只读查询  
3. 实现 `AnalysisRuntime` 工具循环与真实 SSE  
4. 迁入 `web/` Vue 页并对齐路径  

可回看选型页（Cursor Page）：调研问数独立服务选型与骨架。
