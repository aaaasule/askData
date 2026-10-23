"""API v1 — mount datasources, data-analysis, models."""

from fastapi import APIRouter

from app.api.v1 import data_analysis, datasources, models

api_router = APIRouter()
api_router.include_router(datasources.router, prefix="/datasources", tags=["datasources"])
api_router.include_router(
    data_analysis.router,
    prefix="/core/data-analysis",
    tags=["data-analysis"],
)
api_router.include_router(models.router, prefix="/aigc/models", tags=["models"])
