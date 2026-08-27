"""Normalization of upstream history-like payloads into importable events.

Covers ``src.importers.events``: deterministic external event keys, tolerant
timestamp parsing (ISO strings, epoch seconds/milliseconds), and the
one-event-per-track contract for playlist backfill.
"""

from src.importers.events import (
    normalize_playlist_entries,
    normalize_song_history_entries,
)

SOURCE_KWARGS = {
    "source_id": "srv-1",
    "source_name": "Home",
    "username": "alice",
}


def _assert_event_shape(event):
    assert event["username"] == "alice"
    assert event["client_name"] is None
    assert event["is_transcoding"] == 0
    assert event["listen_duration_sec"] is None
    assert event["duration_confidence"] == "estimated"
    assert event["source_id"] == "srv-1"
    assert event["source_name"] == "Home"
    for key in (
        "external_event_key",
        "played_at",
        "track_id",
        "title",
        "artist",
        "artist_id",
        "album",
        "source",
    ):
        assert key in event


def test_playlist_entry_becomes_one_estimated_event():
    entries = [
        {
            "id": "trk-9",
            "title": "Song Nine",
            "artist": "Artist A",
            "artistId": "art-3",
            "album": "Album X",
            "played": "2024-03-24T01:00:00.000Z",
        }
    ]
    events, skipped = normalize_playlist_entries(entries, **SOURCE_KWARGS)
    assert skipped == 0
    assert len(events) == 1
    event = events[0]
    _assert_event_shape(event)
    assert event["source"] == "backfill"
    assert event["track_id"] == "trk-9"
    assert event["title"] == "Song Nine"
    assert event["artist"] == "Artist A"
    assert event["artist_id"] == "art-3"
    assert event["album"] == "Album X"
    assert event["played_at"] == "2024-03-24T01:00:00+00:00"
    assert event["external_event_key"] == (
        "backfill:srv-1:trk-9:2024-03-24T01:00:00+00:00"
    )


def test_playlist_entry_without_played_or_id_is_skipped():
    entries = [
        {"id": "trk-ok", "title": "Ok", "played": 1711242000},
        {"title": "No played", "id": "trk-bad"},
        {"id": None, "played": "2024-03-24T01:00:00Z"},
        {"id": "trk-nop"},
    ]
    events, skipped = normalize_playlist_entries(entries, **SOURCE_KWARGS)
    assert skipped == 3
    assert len(events) == 1
    assert events[0]["track_id"] == "trk-ok"


def test_song_history_epoch_millis_maps_to_keyed_event():
    entries = [
        {
            "id": "trk-7",
            "title": "Past Song",
            "artist": "Artist B",
            "album": "Album Y",
            "playedAt": 1711242000123,
        }
    ]
    events, skipped = normalize_song_history_entries(entries, **SOURCE_KWARGS)
    assert skipped == 0
    assert len(events) == 1
    event = events[0]
    _assert_event_shape(event)
    assert event["source"] == "song_history"
    assert event["played_at"].startswith("2024-03-24")
    assert event["external_event_key"].startswith("gsh:srv-1:trk-7:")
    assert event["external_event_key"].endswith("+00:00")


def test_single_dict_payload_is_accepted_like_list():
    single = {"id": "trk-2", "played": "2024-05-01T10:30:00+02:00"}
    from_dict = normalize_playlist_entries(single, **SOURCE_KWARGS)[0]
    from_list = normalize_playlist_entries([single], **SOURCE_KWARGS)[0]
    assert from_dict == from_list


def test_non_string_track_ids_are_stringified():
    entries = [{"id": 98123, "played": 1711242000}]
    events, _skipped = normalize_playlist_entries(entries, **SOURCE_KWARGS)
    assert events[0]["track_id"] == "98123"
    assert "backfill:srv-1:98123:" in events[0]["external_event_key"]
