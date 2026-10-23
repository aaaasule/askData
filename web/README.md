# web/ — 前端（待迁）

计划从 LangChat 精简迁入：

- `views/data-analysis/*` — 智能问数页
- `views/datasource/*` — 数据源管理
- 对应 API 客户端（路径对齐本服务 `/api/v1/...`）

鉴权：`Authorization: Bearer <API_KEY>` 或 `X-API-Key`。

SSE 须对齐 `app/services/sse_assembler.py` 中的 analysis 事件（`analysis.table` / `analysis.echart` 等）。

本目录目前不包含 Vue 工程。`demo/index.html` 是一个无构建的静态问数页，由服务挂在 `/demo`。
