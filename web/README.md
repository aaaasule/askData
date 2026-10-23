# web/ — AskData 界面

Vue 3 + Vite + Naive UI。覆盖数据源管理、表授权、问数（SSE 表格 / 图表 / 文本）和轻量模型登记。没有 LangChat 的登录、RBAC、Agent、RAG 或知识库。

API Key 存在浏览器 `localStorage`（`askdata.web.settings`），请求头为 `Authorization: Bearer <API_KEY>`。

## 安装与运行

在仓库根目录先把 FastAPI 跑在 8000 端口，然后：

```bash
cd web
npm install
npm run dev
```

开发服务器是 <http://127.0.0.1:5173>。`vite.config.ts` 把 `/api`、`/docs`、`/health`、`/demo` 代理到 `http://127.0.0.1:8000`（可用环境变量 `ASKDATA_API` 改目标）。设置页的 API Base URL 留空。

给本机单一入口（包括 `~/askData` 这种 launchd 工作目录）时，构建后由 FastAPI 托管：

```bash
cd web
npm install
npm run build
```

产物在 `web/dist`（不提交）。重启 `uvicorn app.main:app` 后打开 <http://127.0.0.1:8000/>。`/api/v1`、`/docs`、`/health` 保持原样。`/demo` 仍是无构建静态页。还没构建时，`/` 会显示这段构建说明。

## 表授权

数据源详情：

1. **读取库表**调用 `POST /api/v1/datasources/{id}/introspect`。服务端会把内省快照写入 `structure_json`，表默认 `imported=true` 且 `enabled=true`。
2. 若之前已经保存过结构，页面会把原有的导入/启用标记合并回新列信息，并立刻 `PUT /api/v1/datasources/{id}/structure`，避免内省冲掉授权。新出现的表默认不导入。
3. 勾选「导入」并打开「启用」后点 **保存授权**。请求体是 `{ "structureJson": { "tables": [...] } }`，同时写 `name` 和 `tableName`。这个 PUT 只改结构，不改密码和连接字段。
4. 问数目目录和只读查询只接受 **已导入且已启用** 的表。

`GET /api/v1/datasources/{id}/structure` 的 `data` 是结构对象本身；没有保存过时为 `null`。

## 问数 SSE

`POST /api/v1/core/data-analysis/chat/stream` 的解析在 `src/sse.ts`，对齐 `app/services/sse_assembler.py`：

- `message.delta` → 文本（`delta.content`）
- `analysis.table` → `columns` / `rows` / `row_count` / `sql` / `title`
- `analysis.echart` → `chart_type` / `option`（`series` 非空才渲染）
- `tool.before` / `tool.executed`、`error` / `timeout`
- 结束标记 `data: [DONE]`

服务端按 `conversationId` 保存多轮问答。问数页把这个 id 放在 `localStorage` 的 `askdata.conversation.<datasourceId>`，同一数据源的后续提问会带上它。`message.start` 里的 id 会写回本地。「新对话」清空本地 id，并调用 `DELETE /api/v1/core/data-analysis/conversations/{id}`。

数据源类型包含 Oracle 和 SQL Server。Oracle 的「数据库」填服务名。可选 JDBC URL 例如 `jdbc:oracle:thin:@//host:1521/FREEPDB1`。驱动不在默认安装里，见仓库根目录 README。

## 还没做

模型页只做列表和编辑；更细的参数仍可用 `/docs`。会话历史只保留问题和助手正文，不回放工具参数。
