# Using the dashboard

[简体中文](usage.zh-CN.md) · [Documentation](README.md)

## Filters and history

Choose a date range, timezone, server, and user to scope the dashboard. Filters persist in the URL, so reloading or copying a link retains the selected view. A link does not grant access: the recipient still needs the appropriate credential when authentication is configured.

Now Playing shows activity reported by Navidrome. History, totals, hourly and daily trends, the weekday × hour heatmap, and rankings use the stored records. History, rankings, and now-playing cards display cover art through the application's authenticated, cached proxy.

Recent Plays lets you choose visible columns separately for desktop and mobile; the choices stay in the browser. Its information control explains sessions that ended before the play threshold. See [collection and counting](collection.md) for what contributes to play counts and listening time.

## Rankings, relationships, and details

Artist, album, and track rankings help you find your most-played music. The relationship charts compare top artists, albums, or clients over time, across four dayparts, and against the immediately preceding equal-length period. Switch between play counts and recorded listening time.

Open an artist, album, or client to see scoped totals, average time per play, unique tracks, trends, first and latest plays, top tracks, recent plays, and prior-period ranks. Track rows show play counts and recorded listening time. Artist and album detail links preserve their scope; client details stay on the page and keep client names out of shared URLs.

Use **Settings > Preferences > Collaborating artists** to keep collaboration credits combined or count each artist separately. Separate mode credits each artist once per recording while preserving global plays, tracks, and listening time. Artist totals can therefore overlap. Read [artist attribution](artist-attribution.md) and [chart behavior](data-relations.md) for the counting details.

## Listening Review

Select a calendar month or year to see totals, listening streaks, top lists, time-of-day patterns, and comparisons with the previous period. Month mode shows daily buckets; year mode shows monthly buckets. Charts can display play counts or listening time.

The first-recorded list means the track first appears in the stored history during that period; it does not claim that this was your first-ever listen. Review links retain the calendar period, server, user, timezone, and artist-attribution scope.

## Appearance and language

Choose system, light, or dark mode independently of the palette. Nine families—Built-in, Gruvbox, Catppuccin, Solarized, Nord, Dracula, Tokyo Night, Macchiato, and Mocha—each have light and dark variants, for 18 presets in total.

Advanced appearance settings let you adjust six core colors with live preview, contrast checks, HEX copying, and protection for unsaved changes. Import or export one preset's custom colors as JSON. Preferences stay in the browser and apply to the dashboard, Listening Review, settings, and API reference.

The interface supports English, Simplified Chinese, Traditional Chinese, Japanese, German, Spanish, and French.

## Connections, access, and data controls

Administrators can add or disable servers in **Settings > Connections** and use the connection diagnosis to investigate authentication, TLS, network, timeout, or collector failures. The saved connection list replaces the environment fallback once any entry exists, even if all entries are disabled.

Administrators can also set retention and export, import, or delete a user's listening data. Records are retained indefinitely by default; a finite policy of 1–360 days enables automatic cleanup. See [privacy](privacy.md) and [operations](operations.md) before changing retention or restoring data.

A read-only viewer can browse the dashboard and Listening Review but cannot open settings or change data. Operators can restrict that credential to one server, one username, or both through the [configuration variables](configuration.md).
