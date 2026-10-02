import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.artist_metadata import ArtistMetadataResolver
from src.client import NavidromeClient

CREDITS = [{"name": "Alpha", "id": "a"}, {"name": "Beta", "id": "b"}]


def song(track_id="duet", artists=CREDITS):
    return {"subsonic-response": {"status": "ok", "song": {
        "id": track_id, "artists": artists,
    }}}


def entry(track_id="duet", **kwargs):
    return {"playerId": "player", "id": track_id, "artist": "Alpha with Beta", **kwargs}


@pytest.mark.asyncio
async def test_lookup_uses_get_song_with_the_source_credentials():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=song())

    client = NavidromeClient("http://navidrome.example.invalid", "listener", "synthetic")
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await ArtistMetadataResolver(client).get_artists("duet") == CREDITS
        assert requests[0].url.path == "/rest/getSong"
        assert requests[0].url.params["id"] == "duet"
        assert requests[0].url.params["u"] == "listener"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_valid_poll_metadata_wins_and_populates_the_cache():
    client = AsyncMock()
    resolver = ArtistMetadataResolver(client)
    original = entry(artists=CREDITS)
    enriched = await resolver.enrich_entries([entry(), original])
    assert [row["artists"] for row in enriched] == [CREDITS, CREDITS]
    assert (await resolver.enrich_entries(entry()))[0]["artists"] == CREDITS
    client.get_song.assert_not_awaited()
    enriched[0]["artists"][0]["name"] = "Changed"
    assert original["artists"] == CREDITS
    assert (await resolver.get_artists("duet")) == CREDITS


@pytest.mark.asyncio
async def test_lookups_are_shared_but_sources_are_isolated():
    first, second = AsyncMock(), AsyncMock()
    first.get_song.return_value = song()
    second.get_song.return_value = song(artists=[{"name": "Gamma", "id": "g"}])
    resolver = ArtistMetadataResolver(first)
    original = entry()
    result = await resolver.enrich_entries([original, entry(playerId="other")])
    assert [row["artists"] for row in result] == [CREDITS, CREDITS]
    assert "artists" not in original
    assert (await resolver.enrich_entries(entry()))[0]["artists"] == CREDITS
    first.get_song.assert_awaited_once_with("duet")
    assert (await ArtistMetadataResolver(second).get_artists("duet")) == [
        {"name": "Gamma", "id": "g"},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    None, {"subsonic-response": {"status": "failed"}},
    song(artists=None), song(artists=[{"name": ""}]), song(track_id="other"),
    httpx.ReadTimeout("synthetic upstream timeout"), ValueError("invalid JSON"),
])
async def test_missing_or_failed_lookup_preserves_the_observation_and_retries(result, monkeypatch):
    client = AsyncMock()
    if isinstance(result, Exception):
        client.get_song.side_effect = result
    else:
        client.get_song.return_value = result
    resolver = ArtistMetadataResolver(client)
    now = [0.0]
    monkeypatch.setattr("src.artist_metadata.time.monotonic", lambda: now[0])
    original = entry()
    assert await resolver.enrich_entries(original) == [original]
    assert await resolver.enrich_entries(original) == [original]
    client.get_song.assert_awaited_once()
    now[0] = 301
    client.get_song.side_effect = None
    client.get_song.return_value = song()
    assert (await resolver.enrich_entries(original))[0]["artists"] == CREDITS


@pytest.mark.asyncio
async def test_cache_expires_and_is_bounded(monkeypatch):
    client = AsyncMock()

    async def get_song(track_id):
        return song(track_id)

    client.get_song.side_effect = get_song
    resolver = ArtistMetadataResolver(client)
    resolver.CACHE_SIZE = 2
    now = [0.0]
    monkeypatch.setattr("src.artist_metadata.time.monotonic", lambda: now[0])
    for track_id in ["one", "two", "three", "one"]:
        assert await resolver.get_artists(track_id) == CREDITS
    assert client.get_song.await_count == 4
    assert len(resolver._cache) == 2
    now[0] += resolver.CACHE_TTL_SEC
    await resolver.get_artists("one")
    assert client.get_song.await_count == 5


@pytest.mark.asyncio
async def test_poll_lookup_budget_does_not_starve_later_tracks():
    client = AsyncMock()
    client.get_song.side_effect = lambda track_id: song(track_id)
    resolver = ArtistMetadataResolver(client)
    entries = [entry(str(index)) for index in range(6)]
    first = await resolver.enrich_entries(entries)
    assert sum(bool(row.get("artists")) for row in first) == 4
    assert client.get_song.await_count == 4
    second = await resolver.enrich_entries(entries)
    assert all(row.get("artists") == CREDITS for row in second)
    assert client.get_song.await_count == 6


@pytest.mark.asyncio
async def test_lookup_timeout_is_bounded_and_cancellation_propagates():
    client = AsyncMock()

    async def never_finishes(_track_id):
        await asyncio.Event().wait()

    client.get_song.side_effect = never_finishes
    resolver = ArtistMetadataResolver(client)
    resolver.LOOKUP_TIMEOUT_SEC = 0.01
    assert await asyncio.wait_for(resolver.enrich_entries(entry()), timeout=1) == [entry()]
    client.get_song.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await resolver.get_artists("different-track")
