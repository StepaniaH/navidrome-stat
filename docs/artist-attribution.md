# Artist attribution

**Settings > Preferences > Collaborating artists** controls artist attribution in rankings, artist details, relationship charts, and Listening Review. The choice is saved in the browser. Shared dashboard and review URLs carry `artist_mode=combined` or `artist_mode=separate`; an explicit URL value takes precedence over the browser preference.

| Mode | One play credited to Alpha and Beta |
| --- | --- |
| Combined (default) | The full stored artist credit receives one play. |
| Separate | Alpha receives one play and Beta receives one play. |

Both artists receive the recorded listening time in separate mode. Artist values overlap, so adding artist totals can exceed the dashboard total. Global plays, total listening time, unique tracks, albums, clients, and playback history continue to count the original recording once. A repeated artist within a track's metadata receives one attribution.

The relationship charts use the same attribution as the artist ranking and detail view. `Other` counts each recording involving an artist outside the top five once, including collaborations between several such artists. A recording shared by a top-five artist and another artist appears in both relevant series. Duration coverage is calculated from distinct recording rows.

## Metadata

New playback sessions and supported history imports preserve the [OpenSubsonic `artists` array](https://opensubsonic.netlify.app/docs/responses/child/), including artist names and IDs. Explicit metadata takes precedence over punctuation in a display name. The original artist text remains available for combined mode and track labels.

When `getNowPlaying` omits a valid artist list, the collector requests it from `getSong` using the track ID. Each source has its own bounded in-memory cache. Successful lookups are cached for six hours, missing metadata for five minutes, and failed requests for 30 seconds. Each poll starts at most four lookups in parallel with a two-second timeout. Playback collection continues if a lookup fails or the server provides no artist list. A valid list received later updates the same playback session, including an already saved checkpoint or a short-play attempt.

The ListenBrainz-compatible receiver preserves `additional_info.artist_names` and pairs names with `artist_mbids` when both arrays have the same length. Missing or mismatched IDs do not prevent names from being stored. The receiver does not query MusicBrainz or use ListenBrainz's server-generated `mbid_mapping` as submission metadata.

Older records can use semicolons, spaced slashes (`Alpha / Beta`), and `feat.` or `ft.` credits. Commas, ampersands, and unspaced slashes remain part of a name, preserving names such as `Earth, Wind & Fire`, `Simon & Garfunkel`, and `AC/DC`. Existing records without structured metadata or these separators retain their original artist credit. Changing the preference does not rewrite history or fetch missing artist metadata.

For older Navidrome records with a saved track ID, use the [artist metadata backfill command](operations.md#fill-missing-artist-metadata) to preview and fill missing lists. If Navidrome's song details also lack separate names, attribution remains unchanged; phrases such as `with`, `and Band`, or `•` are not sufficient evidence to identify individual artists.

## Storage and API

Schema v14 adds nullable artist metadata to history and short-play rows. It preserves session IDs, import IDs, and existing deduplication rules. Privacy archive v5 includes the structured artist list in each record's fingerprint when available, so export and restore retain attribution. Formats v1–v4 remain importable with their original fingerprint field sets.

The dashboard, top-artists, entity-detail, relations, and review endpoints accept `artist_mode`. Its default is `combined`; unsupported values return HTTP 422. Snapshot and review cache keys include this option.
