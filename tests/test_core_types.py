from dataclasses import FrozenInstanceError

import pytest

from src.core_types import PlaybackObservation, ServerConfig


def test_server_config_detaches_and_normalizes_mutable_input():
    source = {
        "id": "living-room",
        "display_name": "Living Room",
        "url": "https://music.example.test",
        "username": "listener",
        "password": "secret",
        "enabled": 1,
        "backfill_playlist_id": "",
    }

    config = ServerConfig.from_mapping(source)
    source["display_name"] = "Changed later"

    assert config.display_name == "Living Room"
    assert config.enabled is True
    assert config.backfill_playlist_id is None
    with pytest.raises(FrozenInstanceError):
        config.display_name = "Cannot mutate"  # type: ignore[misc]


def test_playback_observation_is_immutable_and_maps_upstream_names():
    observation = PlaybackObservation.from_mapping(
        {
            "playerId": "web-1",
            "id": "track-1",
            "playerName": "Web Player",
            "positionMs": 1_500,
            "isPlaying": False,
        }
    )

    assert observation.player_id == "web-1"
    assert observation.track_id == "track-1"
    assert observation.player_name == "Web Player"
    assert observation.position_ms == 1_500
    assert observation.is_playing is False
    with pytest.raises(FrozenInstanceError):
        observation.track_id = "track-2"  # type: ignore[misc]
