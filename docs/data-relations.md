# Dashboard relationships and drill-downs

The relationship section derives chart values from the existing `play_history`
rows. It does not generate behavioral conclusions or scores. Every request uses
the dashboard's date, timezone, server, user, and metric scope.

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

Artist identities follow the existing name-based artist ranking. Album
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

## Candidate drill-downs

The remaining charts should gain click behavior only when the target contains
additional data rather than a restatement of the selected point:

1. A transcoding segment can open its daily trend, client distribution, and
   top tracks.
2. A weekday-and-hour cell can open client, artist, and track rankings for that
   local-time cell.
3. A daily point can open that date's client, artist, and album composition.
4. An hourly bar can open its weekday distribution and client composition.

Until those targets exist, the charts keep their normal cursor and tooltip
behavior. The dashboard currently keeps one shared scope across all sections.
If its length becomes a usability problem, a page-local Overview / Relationships
/ Records switch is preferable to pagination because pagination would separate
charts that share the same filters. That change should be evaluated after more
drill-downs are implemented.
