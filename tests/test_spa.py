"""The product UI and the API share one origin without stealing each other's routes."""

from httpx import AsyncClient


async def test_product_shell_coexists_with_api_docs_and_demo(client: AsyncClient) -> None:
    root = await client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert "AskData" in root.text

    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    demo = await client.get("/demo/")
    assert demo.status_code == 200
    assert "问数" in demo.text

    docs = await client.get("/openapi.json")
    assert docs.status_code == 200
    spec = docs.json()
    assert "/api/v1/datasources/{datasource_id}/structure" in spec["paths"]
    assert "put" in spec["paths"]["/api/v1/datasources/{datasource_id}/structure"]

    stolen = await client.get("/api/v1/datasources")
    assert stolen.status_code == 401
