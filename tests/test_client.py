import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.client import NavidromeClient, generate_auth


def test_generate_auth():
    token, salt = generate_auth("password")
    assert len(token) == 32
    assert len(salt) == 6

@pytest.mark.asyncio
@patch.dict(os.environ, {
    "NAVIDROME_URL": "http://testserver",
    "NAVIDROME_USER": "testuser",
    "NAVIDROME_PASS": "testpass"
})
@patch("httpx.AsyncClient.get")
async def test_get_now_playing(mock_get):
    # Mocking httpx response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {
                "entry": [
                    {
                        "id": "1",
                        "title": "Song Title",
                        "artist": "Artist Name",
                        "album": "Album Name",
                        "username": "admin",
                        "playerName": "Feishin",
                        "bitRate": 320
                    }
                ]
            }
        }
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    client = NavidromeClient()
    data = await client.get_now_playing()

    assert data["subsonic-response"]["status"] == "ok"
    assert len(data["subsonic-response"]["nowPlaying"]["entry"]) == 1
    assert data["subsonic-response"]["nowPlaying"]["entry"][0]["title"] == "Song Title"

    args, kwargs = mock_get.call_args
    params = kwargs.get("params")
    assert params["u"] == "testuser"
    assert params["v"] == "1.16.1"
    assert params["c"] == "navidrome-statistic"
    assert params["f"] == "json"
    assert "t" in params
    assert "s" in params

    await client.close()


@pytest.mark.asyncio
async def test_detects_playback_report_extension():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    client.get_open_subsonic_extensions = AsyncMock(return_value={
        "subsonic-response": {
            "status": "ok",
            "openSubsonicExtensions": {
                "openSubsonicExtension": [
                    {"name": "playbackReport", "versions": [1]},
                ]
            },
        }
    })
    assert await client.supports_playback_report() is True
    await client.close()


@pytest.mark.asyncio
async def test_missing_extension_falls_back_without_failure():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    client.get_open_subsonic_extensions = AsyncMock(
        side_effect=ValueError("synthetic malformed response")
    )
    assert await client.supports_playback_report() is False
    await client.close()


def test_subsonic_error_response_is_not_success():
    assert NavidromeClient.response_is_ok({
        "subsonic-response": {
            "status": "failed",
            "error": {"code": 40},
        }
    }) is False


def test_now_playing_entries_treat_null_as_idle():
    assert NavidromeClient.now_playing_entries({
        "subsonic-response": {"status": "ok", "nowPlaying": None}
    }) == []
    assert NavidromeClient.now_playing_entries({
        "subsonic-response": {"status": "ok"}
    }) == []
    assert NavidromeClient.now_playing_entries({
        "subsonic-response": {"status": "ok", "nowPlaying": {"entry": None}}
    }) == []
    assert NavidromeClient.now_playing_entries({
        "subsonic-response": {
            "status": "ok",
            "nowPlaying": {"entry": [{"id": "synthetic-track"}]},
        }
    }) == [{"id": "synthetic-track"}]


@pytest.mark.asyncio
async def test_song_history_probe_detects_available_endpoint():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    client._get_json = AsyncMock(return_value={
        "subsonic-response": {"status": "ok", "songHistory": {"entry": []}},
    })
    assert await client.supports_song_history() is True
    await client.close()


@pytest.mark.asyncio
async def test_song_history_probe_survives_unknown_endpoint():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    client._get_json = AsyncMock(return_value={
        "subsonic-response": {
            "status": "failed",
            "error": {"code": 0, "message": "Not found"},
        },
    })
    assert await client.supports_song_history() is False

    client._get_json = AsyncMock(side_effect=RuntimeError("connection refused"))
    assert await client.supports_song_history() is False
    await client.close()


@pytest.mark.asyncio
async def test_get_playlist_passes_id_and_returns_envelope():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    envelope = {
        "subsonic-response": {"status": "ok", "playlist": {"entry": []}}
    }
    client._get_json = AsyncMock(return_value=envelope)
    assert await client.get_playlist("pl-77") is envelope
    client._get_json.assert_awaited_once_with("getPlaylist", id="pl-77")
    await client.close()


@pytest.mark.asyncio
async def test_get_song_history_page_passes_pagination_params():
    client = NavidromeClient(
        url="http://navidrome.example.invalid",
        user="synthetic-user",
        password="synthetic-password",
    )
    envelope = {
        "subsonic-response": {"status": "ok", "songHistory": {"entry": []}}
    }
    client._get_json = AsyncMock(return_value=envelope)
    page = await client.get_song_history(size=200, offset=400)
    assert page == envelope
    client._get_json.assert_awaited_once_with("getSongHistory", size="200", offset="400")
    await client.close()
