import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from src.client import generate_auth, NavidromeClient

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
