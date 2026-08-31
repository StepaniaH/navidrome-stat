"""getSongHistory adapter (upstream Navidrome PR #5650, unmerged).

The live endpoint does not exist yet; these tests drive the adapter through
fakes so the pipeline is fully exercised and only flips on capability probe.
"""

import asyncio

import pytest

from src.importers.song_history import run_song_history

SOURCE = {
    "source_id": "srv-7",
    "source_name": "Home",
    "username": "alice",
}


def _page(entries, status="ok"):
    return {
        "subsonic-response": {"status": status, "songHistory": {"entry": entries}}
    }


class FakeHistoryClient:
    def __init__(self, pages, *, page_size=200):
        self.pages = list(pages)
        self.page_size = page_size
        self.calls = []

    async def get_song_history(self, *, size, offset):
        self.calls.append((size, offset))
        index = offset // size if size else 0
        return self.pages[index] if 0 <= index < len(self.pages) else _page([])


async def _record(events):
    return len(events)


def test_paginates_until_short_page():
    full = [
        {"id": f"trk-{index}", "playedAt": 1700000000000 + index * 1000}
        for index in range(200)
    ]
    tail = [{"id": "trk-final", "playedAt": 1790000000000}]
    client = FakeHistoryClient([_page(full), _page(tail), _page([])], page_size=200)

    result = asyncio.run(
        run_song_history(client, record=_record, **SOURCE)
    )

    assert client.calls[0] == (200, 0)
    assert client.calls[1] == (200, 200)
    # Short tail page (< PAGE_SIZE) ends the loop; no third request.
    assert client.calls[-1][1] == 200
    assert result == {
        "imported": 201,
        "skipped": 0,
        "next_offset": 201,
        "complete": True,
    }


def test_error_envelope_raises():
    client = FakeHistoryClient([_page([], status="failed")])
    from src.importers.playlist_backfill import ImportSourceError

    with pytest.raises(ImportSourceError):
        asyncio.run(run_song_history(client, record=_record, **SOURCE))


def test_cutoff_suppression_shares_playlist_bridge_logic():
    """Song-history imports reuse the playlist bridge's cutoff filter."""
    from src.importers.events import apply_cutoff
    from src.importers.playlist_backfill import run_backfill  # noqa: F401

    assert apply_cutoff.__module__ == "src.importers.events"
    entries = [
        {"id": "old", "playedAt": 1699999999000},
        {"id": "new", "playedAt": 1790000000000},
    ]
    client = FakeHistoryClient([_page(entries)])

    result = asyncio.run(
        run_song_history(
            client,
            record=_record,
            earliest_poller_played_at="2024-03-24T01:00:00+00:00",
            **SOURCE,
        )
    )

    # 'old' = 2023-11-14, before the 01:00:00Z coverage bound minus margin.
    assert result == {
        "imported": 1,
        "skipped": 1,
        "next_offset": 2,
        "complete": True,
    }


def test_empty_first_page_yields_zero_counts():
    client = FakeHistoryClient([])
    result = asyncio.run(run_song_history(client, record=_record, **SOURCE))
    assert result == {
        "imported": 0,
        "skipped": 0,
        "next_offset": 0,
        "complete": True,
    }


def test_commits_each_page_and_resumes_from_persisted_offset(monkeypatch):
    import src.importers.song_history as history_module

    monkeypatch.setattr(history_module, "PAGE_SIZE", 2)
    monkeypatch.setattr(history_module, "MAX_EVENTS_PER_RUN", 2)
    pages = {
        0: _page([
            {"id": "first", "playedAt": 1700000000000},
            {"id": "second", "playedAt": 1700000001000},
        ]),
        2: _page([{"id": "third", "playedAt": 1700000002000}]),
    }

    class OffsetClient:
        def __init__(self):
            self.calls = []

        async def get_song_history(self, *, size, offset):
            self.calls.append((size, offset))
            return pages[offset]

    recorded_pages = []
    checkpoints = []

    async def record_page(events):
        recorded_pages.append([event["track_id"] for event in events])
        return len(events)

    async def checkpoint(next_offset, complete):
        checkpoints.append((next_offset, complete))

    first_client = OffsetClient()
    first = asyncio.run(
        run_song_history(
            first_client,
            record=record_page,
            checkpoint=checkpoint,
            start_offset=0,
            **SOURCE,
        )
    )
    assert first == {
        "imported": 2,
        "skipped": 0,
        "next_offset": 2,
        "complete": False,
    }
    assert recorded_pages == [["first", "second"]]
    assert checkpoints == [(2, False)]

    monkeypatch.setattr(history_module, "MAX_EVENTS_PER_RUN", 10)
    second_client = OffsetClient()
    second = asyncio.run(
        run_song_history(
            second_client,
            record=record_page,
            checkpoint=checkpoint,
            start_offset=first["next_offset"],
            **SOURCE,
        )
    )
    assert second["complete"] is True
    assert second["next_offset"] == 3
    assert second_client.calls == [(2, 2)]
    assert recorded_pages == [["first", "second"], ["third"]]
