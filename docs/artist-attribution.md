# Artist attribution

**Settings > Preferences > Collaborating artists** controls artist attribution in rankings, artist details, relationship charts, and year-in-review. The choice is saved in the browser. Shared dashboard and review URLs carry `artist_mode=combined` or `artist_mode=separate`; an explicit URL value takes precedence over the browser preference.

| Mode | One play credited to Alpha and Beta |
| --- | --- |
| Combined (default) | The full stored artist credit receives one play. |
| Separate | Alpha receives one play and Beta receives one play. |

Both artists receive the recorded listening time in separate mode. Artist values overlap, so adding artist totals can exceed the dashboard total. Global plays, total listening time, unique tracks, albums, clients, and playback history continue to count the original recording once. A repeated artist within a track's metadata receives one attribution.

The relationship charts use the same attribution as the artist ranking and detail view. `Other` counts each recording involving an artist outside the top five once, including collaborations between several such artists. A recording shared by a top-five artist and another artist appears in both relevant series. Duration coverage is calculated from distinct recording rows.

## Metadata

New playback sessions and supported history imports preserve the [OpenSubsonic `artists` array](https://opensubsonic.netlify.app/docs/responses/child/), including artist names and IDs. Explicit metadata takes precedence over punctuation in a display name. The original artist text remains available for combined mode and track labels.

Older records can use semicolons, spaced slashes (`Alpha / Beta`), and `feat.` or `ft.` credits. Commas, ampersands, and unspaced slashes remain part of a name, preserving names such as `Earth, Wind & Fire`, `Simon & Garfunkel`, and `AC/DC`. Existing records without structured metadata or these separators retain their original artist credit. Changing the preference does not rewrite history or fetch missing artist metadata.

## Storage and API

Schema v14 adds nullable artist metadata to history and short-play rows. It preserves session IDs, import IDs, and existing deduplication rules. Privacy archive v5 includes the structured artist list in each record's fingerprint when available, so export and restore retain attribution. Formats v1–v4 remain importable with their original fingerprint field sets.

The dashboard, top-artists, entity-detail, relations, and review endpoints accept `artist_mode`. Its default is `combined`; unsupported values return HTTP 422. Snapshot and review cache keys include this option.
