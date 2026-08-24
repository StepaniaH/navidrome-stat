"""Cover art cache, album resolution, and the proxy endpoint."""

from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from src.coverart import CoverArtService, album_key
from src.database import init_db
from src.main import app


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "covers"


@pytest.fixture
def client_factory():
    factory = Mock()
    client = AsyncMock()
    client.get_cover_art = AsyncMock(return_value=(b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg"))
    client.search3 = AsyncMock(return_value=[])
    client.close = AsyncMock()
    factory.return_value = client
    factory.client = client
    return factory


@pytest.fixture
def synthetic_credentials(monkeypatch):
    import src.coverart as coverart_module

    async def fake_credentials(source_id):
        return {"url": "http://navidrome.example.invalid", "user": "synthetic", "password": "synthetic"}

    monkeypatch.setattr(coverart_module, "credentials_for_source", fake_credentials)


@pytest.fixture
def service(cache_dir, client_factory, synthetic_credentials):
    return CoverArtService(cache_dir=cache_dir, max_bytes=10 * 1024 * 1024, client_factory=client_factory)


@pytest.mark.asyncio
async def test_load_fetches_once_for_same_key(cache_dir, client_factory, service):
    first = await service.load("src-1", "tr-1", 300)
    second = await service.load("src-1", "tr-1", 300)
    assert first == (b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")
    assert second == first
    assert client_factory.client.get_cover_art.await_count == 1
    assert (cache_dir / "covers").exists() is False  # lazily created under cache_dir


@pytest.mark.asyncio
async def test_load_returns_none_when_upstream_fails(service, client_factory):
    client_factory.client.get_cover_art.side_effect = RuntimeError("upstream unavailable")
    assert await service.load("src-1", "tr-1", 300) is None


@pytest.mark.asyncio
async def test_lru_evicts_oldest_when_over_budget(tmp_path, client_factory, synthetic_credentials):
    service = CoverArtService(cache_dir=tmp_path, max_bytes=20, client_factory=client_factory)
    for index in range(3):
        client_factory.client.get_cover_art.return_value = (bytes([index]) * 10, "image/jpeg")
        await service.load("src", f"tr-{index}", 300)
    remaining = sorted(p.name for p in tmp_path.glob("*.img"))
    assert len(remaining) == 2


@pytest.mark.asyncio
async def test_resolve_album_id_caches_positive(isolated_db, client_factory, service):
    await init_db(isolated_db)
    client_factory.client.search3.return_value = [
        {"id": "al-1", "name": "Nightlife", "artist": "Synth Duo"},
    ]
    first = await service.resolve_album_id("src-1", "Nightlife", "Synth Duo")
    second = await service.resolve_album_id("src-1", "Nightlife", "Synth Duo")
    assert first == "al-1"
    assert second == "al-1"
    assert client_factory.client.search3.await_count == 1


@pytest.mark.asyncio
async def test_resolve_album_id_negative_cache_within_ttl(isolated_db, client_factory, service):
    await init_db(isolated_db)
    client_factory.client.search3.return_value = []
    assert await service.resolve_album_id("src-1", "Ghost Album", None) is None
    assert await service.resolve_album_id("src-1", "Ghost Album", None) is None
    assert client_factory.client.search3.await_count == 1


@pytest.mark.asyncio
async def test_resolve_album_id_retries_negative_after_ttl(isolated_db, client_factory, synthetic_credentials):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    ticks = iter([now, now + timedelta(hours=25)])
    service = CoverArtService(
        cache_dir=None, client_factory=client_factory, now=lambda: next(ticks)
    )
    await init_db(isolated_db)
    client_factory.client.search3.return_value = []
    await service.resolve_album_id("src-1", "Ghost Album", None)
    await service.resolve_album_id("src-1", "Ghost Album", None)
    assert client_factory.client.search3.await_count == 2


def test_album_key_normalizes_case_and_whitespace():
    assert album_key(" Nightlife ", "Synth Duo") == album_key("nightlife", "synth duo")


@pytest.mark.asyncio
async def test_cover_art_endpoint_serves_cached_bytes(isolated_db, monkeypatch):
    await init_db(isolated_db)
    import src.routes.stats as stats_routes

    monkeypatch.setattr(
        stats_routes.cover_art_service,
        "load",
        AsyncMock(return_value=(b"\x89PNG fake", "image/png")),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/coverart", params={"source_id": "s1", "id": "al-9"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert "private" in response.headers["cache-control"]
    assert "max-age=2592000" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_cover_art_endpoint_returns_404_when_unavailable(isolated_db, monkeypatch):
    await init_db(isolated_db)
    import src.routes.stats as stats_routes

    monkeypatch.setattr(stats_routes.cover_art_service, "load", AsyncMock(return_value=None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/coverart", params={"source_id": "s1", "id": "al-9"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cover_art_endpoint_validates_params(isolated_db):
    await init_db(isolated_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        missing = await ac.get("/api/coverart", params={"source_id": "s1"})
        bad_size = await ac.get(
            "/api/coverart", params={"source_id": "s1", "id": "a", "size": 9999}
        )
    assert missing.status_code == 422
    assert bad_size.status_code == 422
