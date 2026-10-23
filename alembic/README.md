# Alembic

占位目录。接入 `DATABASE_URL` 与 `app.db.models` 后，在此初始化迁移：

```bash
pip install 'askdata[db]'   # 或 pip install alembic
alembic init alembic        # 若尚未生成 env.py（本仓库仅预留目录）
alembic revision --autogenerate -m "init datasources and models"
alembic upgrade head
```

当前骨架用 SQLAlchemy 模型定义了 `aigc_datasource` / `aigc_model`，尚未绑定 engine 与迁移脚本。
