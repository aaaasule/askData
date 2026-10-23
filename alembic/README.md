# Alembic

应用库迁移。模型在 `app/db/models.py`（`aigc_datasource`、`aigc_model`）。连接串来自环境变量 `DATABASE_URL`（见 `.env.example`），本地默认 SQLite。

在仓库根目录：

```bash
pip install -e .
cp .env.example .env
alembic upgrade head
```

Postgres / MySQL 使用同一个命令，先 `pip install -e ".[db]"` 并改 `DATABASE_URL`。`alembic/` 这个目录名会挡住已安装的 Alembic 包，所以用控制台脚本 `alembic`，不要在仓库根目录执行 `python -m alembic`。

新迁移：

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
