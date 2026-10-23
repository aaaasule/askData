"""AskData FastAPI entrypoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

_demo_dir = Path(__file__).resolve().parents[1] / "web" / "demo"
if _demo_dir.is_dir():
    app.mount("/demo", StaticFiles(directory=_demo_dir, html=True), name="demo")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
