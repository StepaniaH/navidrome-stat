# Dashboard relationships and drill-downs

The relationship section derives chart values from the existing `play_history`
rows. It does not generate behavioral conclusions or scores. Every request uses
the dashboard's date, timezone, server, user, metric, and artist-attribution scope.

## Charts

| Chart | Grouping | Visible rows | Time handling |
| --- | --- | --- | --- |
| Trend | Artist, album, or client × time | Top five plus `Other` | Daily through 45 days, weekly through 180 days, monthly after that |
| Daypart | Artist, album, or client × four six-hour periods | Top eight | Hours are calculated in the selected timezone |
| Period comparison | Artist, album, or client × current/previous period | Top eight by combined value | Uses the immediately preceding equal-length period; unavailable for all history |

The charts can display play count or recorded listening time. When listening
time is selected, the section also reports the share of rows with a duration
and the share whose duration was reported by the upstream client. Missing
durations contribute zero seconds and still count as plays.

Artist identities follow the name-based artist ranking and the selected [collaboration mode](artist-attribution.md). In separate mode, artist series can overlap; `Other` and duration coverage each count an underlying recording once. Album
identities use `(source, album_id)` when an upstream ID exists and fall back to
`(source, album, artist)` for older rows. `Other` and unknown-client groups do
not open a detail view because they do not identify one entity.

## Detail behavior

- Artist and album details remain addressable through scoped URL parameters.
- Client details open in the current page and send the client name in a POST
  body. The name is not added to browser history, copied links, or request query
  strings.
- Every detail request retains the selected date, timezone, server, user, and
  metric scope.
- Track rows use play count and total recorded listening time. Detail durations
  preserve whether a value was reported, estimated, a lower bound from older
  checkpoints, or unavailable.
