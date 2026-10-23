"""Data-analysis (智能问数) schemas."""

from typing import Any

from pydantic import BaseModel, Field


class AnalysisChatRequest(BaseModel):
    datasource_id: str = Field(alias="datasourceId")
    question: str
    table_names: list[str] = Field(default_factory=list, alias="tableNames")
    model_id: str | None = Field(default=None, alias="modelId")

    model_config = {"populate_by_name": True}


class CatalogTable(BaseModel):
    name: str
    comment: str | None = None
    imported: bool = True
    enabled: bool = True
    columns: list[dict[str, Any]] | None = None


class CatalogOut(BaseModel):
    datasource_id: str = Field(alias="datasourceId")
    tables: list[CatalogTable] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
