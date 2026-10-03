# Using the dashboard

[简体中文](usage.zh-CN.md) · [Documentation](README.md)

## Filters and history

Choose a date range, timezone, server, and user to scope the dashboard. Filters persist in the URL, so reloading or copying a link retains the selected view. A link does not grant access: the recipient still needs the appropriate credential when authentication is configured.

Now Playing shows activity reported by Navidrome. History, totals, hourly and daily trends, the weekday × hour heatmap, and rankings use the stored records. History, rankings, and now-playing cards display cover art through the application's authenticated, cached proxy.

Recent Plays lets you choose visible columns separately for desktop and mobile; the choices stay in the browser. Its information control explains sessions that ended before the play threshold. See [collection and counting](collection.md) for what contributes to play counts and listening time.

Choose **View all** beside Recent Plays to browse individual listening records. The page inherits the selected date range, timezone, server, and user. Search by track, artist, or album, and use **Load more** for older records. Repeated listens appear as separate rows; new records arriving while you browse do not shift the older pages. Artist and album links open details within the same scope. Unknown durations display as a dash; estimated and lower-bound durations retain their labels.

The header reports the collection state separately from successful statistics requests. Healthy polling shows live collection; starting, interrupted, disabled, and unconfigured collection have distinct labels. **Receiver enabled** means ListenBrainz ingestion is configured, not that recent submissions have arrived. If polling and ingestion are both enabled, the header warns about possible duplicate counts. Records are not deduplicated across collection methods.

## Daily average

Choose **Settings > Preferences > Daily average** to divide plays by calendar days (the default) or active days. Calendar days include days with no recorded plays; active days count only dates with recorded plays. For all history, calendar days cover the inclusive first-to-last recorded date span. For a finite or custom range, they cover the entire selected window, including dates without records. The dashboard labels both modes as a daily average. This browser preference changes display only and does not change stored history or shared URLs; a day without records does not prove that collection was running that day.

The API returns explicit active-day and calendar-day averages. The existing `average_daily_plays` and `average_daily_listen_sec` fields retain their earlier definitions: active days for finite windows, and the recorded date span for all history.

## Rankings, relationships, and details

Artist, album, and track rankings help you find your most-played music. The relationship charts compare top artists, albums, or clients over time, across four dayparts, and against the immediately preceding equal-length period. Switch between play counts and recorded listening time.

Open an artist, album, or client to see scoped totals, average time per play, unique tracks, trends, first and latest plays, top tracks, recent plays, and prior-period ranks. Track rows show play counts and recorded listening time. Artist and album detail links preserve their scope; client details stay on the page and keep client names out of shared URLs.

Use **Settings > Preferences > Collaborating artists** to keep collaboration credits combined or count each artist separately. Separate mode credits each artist once per recording while preserving global plays, tracks, and listening time. Artist totals can therefore overlap. Read [artist attribution](artist-attribution.md) and [chart behavior](data-relations.md) for the counting details.

## Listening Review

Select a calendar month or year to see totals, listening streaks, top lists, time-of-day patterns, and comparisons with the previous period. Month mode shows daily buckets; year mode shows monthly buckets. Charts can display play counts or listening time.

The first-recorded list means the track first appears in the stored history during that period; it does not claim that this was your first-ever listen. Review links retain the calendar period, server, user, timezone, and artist-attribution scope.

Review highlights show up to ten first-recorded tracks, up to five albums recorded again after a gap of at least 90 days, and the largest increase in play counts among the current top ten artists. The artist comparison uses the immediately preceding calendar month or year; it is omitted when that period has no records or no artist has a positive increase. These highlights describe saved records, so imports, deletion, retention, and collection gaps can affect them.

## Appearance and language

Choose system, light, or dark mode independently of the palette. Nine families—Built-in, Gruvbox, Catppuccin, Solarized, Nord, Dracula, Tokyo Night, Macchiato, and Mocha—each have light and dark variants, for 18 presets in total.

Advanced appearance settings let you adjust six core colors with live preview, contrast checks, HEX copying, and protection for unsaved changes. Import or export one preset's custom colors as JSON. Preferences stay in the browser and apply to the dashboard, Listening Review, settings, and API reference.

The interface supports English, Simplified Chinese, Traditional Chinese, Japanese, German, Spanish, and French.

## Connections, access, and data controls

Administrators can add or disable servers in **Settings > Connections** and use the connection diagnosis to investigate authentication, TLS, network, timeout, or collector failures. The saved connection list replaces the environment fallback once any entry exists, even if all entries are disabled.

Administrators can also set retention and export, import, or delete a user's listening data. Records are retained indefinitely by default; a finite policy of 1–360 days enables automatic cleanup. See [privacy](privacy.md) and [operations](operations.md) before changing retention or restoring data.

A read-only viewer can browse the dashboard, individual listening records, and Listening Review but cannot open settings or change data. Operators can restrict that credential to one server, one username, or both through the [configuration variables](configuration.md).
