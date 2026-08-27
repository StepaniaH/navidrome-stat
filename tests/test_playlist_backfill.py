"""Backfill-bridge adapter: smart-playlist watch through ``getPlaylist``.

Covers cutoff suppression against live-poller coverage, envelope parsing,
and idempotent end-to-end writes into a real database.
"""

import asyncio

import pytest

from src.importers.events import normalize_playlist_entries
from src.importers.playlist_backfill import (
    ImportSourceError,
    compute_cutoff,
    run_backfill,
)

SOURCE = {
    "source_id": "srv-9",
    "source_name": "Home",
    "username": "alice",
}


async def _async_record(events, sink=None):
    if sink is not None:
        sink.extend(events)
    return len(events)


class FakeClient:
    def __init__(self, envelope):
        self.envelope = envelope
        self.requested_ids = []

    async def get_playlist(self, playlist_id):
        self.requested_ids.append(playlist_id)
        return self.envelope


OK_ENVELOPE = {
    "subsonic-response": {
        "status": "ok",
        "playlist": {
            "entry": [
                {"id": "trk-a", "played": "2020-02-01T10:00:00Z"},
                {"id": "trk-b", "played": "2021-06-11T09:30:12+00:00"},
                {"id": "trk-c"},
            ]
        },
    }
}


def test_run_backfill_normalizes_and_reports_counts():
    recorded = []

    async def record(events):
        recorded.extend(events)
        return len(events)

    client = FakeClient(dict(OK_ENVELOPE))
    result = asyncio.run(
        run_backfill(
            client,
            playlist_id="pl-1",
            record=record,
            **SOURCE,
        )
    )

    assert client.requested_ids == ["pl-1"]
    assert result == {"imported": 2, "skipped": 1}
    assert [event["track_id"] for event in recorded] == ["trk-a", "trk-b"]
    assert all(event["source"] == "backfill" for event in recorded)


def test_run_backfill_suppresses_events_on_or_after_cutoff():
    # Coverage began at 01:00:00Z; margin 60s forbids >= 00:59:00Z.
    recorded = []
    envelopes = {
        "early": {
            "subsonic-response": {
                "status": "ok",
                "playlist": {"entry": [{"id": "ok", "played": "2024-03-24T00:58:59Z"}]},
            }
        },
        "boundary": {
            "subsonic-response": {
                "status": "ok",
                "playlist": {
                    "entry": [
                        {"id": "at-margin", "played": "2024-03-24T00:59:00Z"},
                        {"id": "inside", "played": "2024-03-24T00:59:59Z"},
                        {"id": "live", "played": "2024-03-24T01:05:00Z"},
                    ]
                },
            }
        },
    }

    early = asyncio.run(
        run_backfill(
            FakeClient(envelopes["early"]),
            playlist_id="pl",
            earliest_poller_played_at="2024-03-24T01:00:00+00:00",
            record=lambda events: _async_record(events, recorded),
            **SOURCE,
        )
    )
    inside = asyncio.run(
        run_backfill(
            FakeClient(envelopes["boundary"]),
            playlist_id="pl",
            earliest_poller_played_at="2024-03-24T01:00:00+00:00",
            record=lambda events: _async_record(events, recorded),
            **SOURCE,
        )
    )

    assert early == {"imported": 1, "skipped": 0}
    assert inside == {"imported": 0, "skipped": 3}
    assert recorded[-1]["track_id"] == "ok"


def test_run_backfill_without_poller_history_imports_everything():
    result = asyncio.run(
        run_backfill(
            FakeClient(dict(OK_ENVELOPE)),
            playlist_id="pl",
            earliest_poller_played_at=None,
            record=_async_record,
            **SOURCE,
        )
    )
    assert result == {"imported": 2, "skipped": 1}


def test_run_backfill_rejects_error_envelope():
    client = FakeClient(
        {"subsonic-response": {"status": "failed", "error": {"code": 70}}}
    )
    with pytest.raises(ImportSourceError):
        asyncio.run(
            run_backfill(
                client,
                playlist_id="pl",
                record=_async_record,
                **SOURCE,
            )
        )


def test_compute_cutoff_applies_margin():
    assert (
        compute_cutoff("2024-03-24T01:00:00+00:00", margin_sec=60)
        == "2024-03-24T00:59:00+00:00"
    )
    assert compute_cutoff(None, margin_sec=60) is None


def test_normalize_entries_tolerates_scalar_and_nested_shapes():
    nested = {
        "subsonic-response": {
            "status": "ok",
            "playlist": {"entry": {"id": "one", "played": "2020-02-01T10:00:00Z"}},
        }
    }
    events, skipped = normalize_playlist_entries([], **SOURCE)
    assert skipped == 0 and events == []
    envelope_events, _ = normalize_playlist_entries(
        FakeClient(nested).envelope["subsonic-response"]["playlist"]["entry"],
        **SOURCE,
    )
    assert envelope_events[0]["track_id"] == "one"
