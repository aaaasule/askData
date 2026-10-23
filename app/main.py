"""AskData FastAPI entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import api_router
from app.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Independent 调研问数 research service (FastAPI rewrite of LangChat "
        "智能问数). Not related to Creo. Reference only: https://github.com/LangChat/langchat"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=f"{settings.api_prefix}/v1")

_web_root = Path(__file__).resolve().parents[1] / "web"
_demo_dir = _web_root / "demo"
_dist_dir = _web_root / "dist"

if _demo_dir.is_dir():
    app.mount("/demo", StaticFiles(directory=_demo_dir, html=True), name="demo")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


_SPA_FALLBACK = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>AskData</title>
  <style>
    body { font-family: "Segoe UI", "PingFang SC", sans-serif; margin: 48px auto; max-width: 640px; color: #1c2421; }
    a { color: #0f6e6b; }
    code { background: #f3f1ea; padding: 2px 6px; }
  </style>
</head>
<body>
  <h1>AskData</h1>
  <p>Vue 界面还没有构建。在仓库的 <code>web/</code> 目录执行 <code>npm install</code> 和 <code>npm run build</code> 后重启服务，即可在此打开数据源管理和问数页。</p>
  <p>静态演示页仍然可用：<a href="/demo/">/demo</a>。接口文档：<a href="/docs">/docs</a>。</p>
</body>
</html>
"""


def _dist_file(relative: str) -> Path | None:
    if not relative or not _dist_dir.is_dir():
        return None
    root = _dist_dir.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
async def spa(full_path: str) -> FileResponse | HTMLResponse:
    """Serve the built Vue app. API, docs, health, and /demo are registered first."""
    asset = _dist_file(full_path)
    if asset is not None:
        return FileResponse(asset)
    index = _dist_dir / "index.html"
    if index.is_file():
        return FileResponse(index)
    return HTMLResponse(_SPA_FALLBACK)
