"""Descriptive review highlights, based only on locally recorded history."""

import aiosqlite

from src.artist_credits import artist_query_source
from src.sqlite import connect_db


async def review_highlights(
    path,
    identity_pred,
    identity_params,
    window_params,
    previous_pred,
    previous_params,
    top_artists,
    artist_mode,
):
    start, end = window_params
    async with connect_db(path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""WITH first_tracks AS (
                SELECT COALESCE(source_id, 'legacy') AS source_id, track_id,
                       MAX(id) AS representative_id,
                       COUNT(*) AS count, SUM(listen_duration_sec) AS total_listen_sec
                FROM play_history WHERE ({identity_pred}) AND played_at_epoch < ?
                  AND track_id IS NOT NULL AND track_id != ''
                GROUP BY COALESCE(source_id, 'legacy'), track_id
                HAVING MIN(played_at_epoch) >= ?
            ) SELECT f.source_id, f.track_id, f.count, f.total_listen_sec,
                     p.title AS name, p.artist, p.album, p.album_id,
                     COUNT(*) OVER () AS all_count
              FROM first_tracks f JOIN play_history p ON p.id = f.representative_id
              ORDER BY f.count DESC, name, f.source_id, f.track_id LIMIT 10""",
            [*identity_params, end, start],
        ) as cursor:
            new_tracks = [dict(row) for row in await cursor.fetchall()]
        async with db.execute(
            f"""WITH albums AS (
                SELECT COALESCE(source_id, 'legacy') AS source_id,
                       MAX(CASE WHEN played_at_epoch >= ? THEN id END) AS representative_id,
                       SUM(CASE WHEN played_at_epoch >= ? THEN 1 ELSE 0 END) AS count,
                       SUM(CASE WHEN played_at_epoch >= ? THEN listen_duration_sec END) AS total_listen_sec,
                       MIN(CASE WHEN played_at_epoch >= ? THEN played_at_epoch END) AS first_return,
                       MAX(CASE WHEN played_at_epoch < ? THEN played_at_epoch END) AS previous_play
                FROM play_history WHERE ({identity_pred}) AND played_at_epoch < ?
                  AND album IS NOT NULL AND album != ''
                GROUP BY COALESCE(source_id, 'legacy'),
                         CASE WHEN album_id IS NOT NULL AND album_id != '' THEN album_id
                              ELSE album || char(31) || COALESCE(artist, '') END
                HAVING first_return - previous_play >= 7776000
            ) SELECT a.source_id, a.count, a.total_listen_sec, a.first_return, a.previous_play,
                     p.album_id, p.album AS name, p.artist
              FROM albums a JOIN play_history p ON p.id = a.representative_id
              ORDER BY a.count DESC, name, a.source_id, p.album_id LIMIT 5""",
            [start, start, start, start, start, *identity_params, end],
        ) as cursor:
            returning_albums = [dict(row) for row in await cursor.fetchall()]
        rising = None
        if top_artists:
            source, column, _ = artist_query_source(artist_mode)
            names = [entry["name"] for entry in top_artists]
            async with db.execute(
                f"SELECT {column}, COUNT(*) FROM {source} WHERE ({previous_pred}) "
                f"AND {column} IN ({','.join('?' for _ in names)}) GROUP BY {column}",
                [*previous_params, *names],
            ) as cursor:
                previous = dict(await cursor.fetchall())
            candidate = max(
                top_artists, key=lambda item: item["count"] - previous.get(item["name"], 0)
            )
            if candidate["count"] > previous.get(candidate["name"], 0):
                rising = {**candidate, "previous_count": previous.get(candidate["name"], 0)}
    return {
        "first_recorded_tracks": new_tracks[0]["all_count"] if new_tracks else 0,
        "new_tracks": [
            {key: value for key, value in row.items() if key != "all_count"} for row in new_tracks
        ],
        "returning_albums": returning_albums,
        "rising_artist": rising,
    }
