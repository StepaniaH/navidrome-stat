"""Checks for the self-hosted OpenAPI reference."""

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.version import PROJECT_NAME

STATIC_DIR = Path(__file__).resolve().parent.parent / "src" / "static"


def test_api_reference_uses_only_local_assets():
    html = (STATIC_DIR / "api-docs.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/api-docs.css">' in html
    assert '<link rel="stylesheet" href="/static/themes.css">' in html
    assert '<script type="module" src="/static/theme-bootstrap.js"></script>' in html
    assert '<script src="/static/api-docs.js" defer></script>' in html
    assert "https://" not in html
    assert "<style" not in html
    assert html.count("<script") == 2


def test_api_reference_renders_schema_without_html_injection():
    script = (STATIC_DIR / "api-docs.js").read_text(encoding="utf-8")
    assert "fetch('/openapi.json', { credentials: 'same-origin' })" in script
    assert "textContent" in script
    assert "createTextNode" in script
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script


@pytest.mark.asyncio
async def test_api_reference_routes_serve_the_same_local_page():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        docs = await client.get("/docs")
        redoc = await client.get("/redoc")
    assert docs.status_code == 200
    assert redoc.status_code == 200
    assert docs.text == redoc.text
    assert "/static/api-docs.js" in docs.text


@pytest.mark.asyncio
async def test_openapi_schema_uses_project_metadata():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == PROJECT_NAME
