# Research: OpenSubsonic capabilities, Navidrome history API status, ecosystem scan, scrobble forwarding

Date: 2026-08-24. Scope: inputs for navidrome-stat feature planning. All claims verified against primary sources (opensubsonic.netlify.app, navidrome.org, github.com/navidrome, project READMEs/docs).

---

## 1. OpenSubsonic / Subsonic API capabilities relevant to statistics

### `playbackReport` extension (new, March 2026)
- Extension name `playbackReport` v1, advertised via `getOpenSubsonicExtensions`. When supported, the server provides the `reportPlayback` endpoint **and** may expose timeline fields (`state`, `positionMs`, `playbackRate`) in `getNowPlaying` entries.
  - Spec: https://opensubsonic.netlify.app/docs/extensions/playbackreport/
  - Endpoint spec: https://raw.githubusercontent.com/opensubsonic/open-subsonic-api/master/content/en/docs/Endpoints/reportplayback.md (source commit: https://github.com/opensubsonic/open-subsonic-api/commit/b42b2f29249b7370b507151e737094439afefc1b)
- Client params: `mediaId`, `mediaType` (song|podcast), `positionMs`, `state` (`starting|playing|paused|stopped`), optional `playbackRate`, `ignoreScrobble`.
- Semantics useful to us: servers should estimate current position from `playbackRate` between calls; only a `stopped` state ends a session (server must not assume end-of-media at content end); servers stop tracking 30 min after planned end; offline clients fall back to plain `scrobble`.
- `ignoreScrobble=true` updates now-playing display/state without play-count/scrobble side effects — i.e. richer live telemetry *without* polluting play counts.
- Enriched `getNowPlaying`: https://raw.githubusercontent.com/opensubsonic/open-subsonic-api/master/content/en/docs/Endpoints/getnowplaying.md ("When the server supports extension `playbackReport`, entries can include `state`, `positionMs`, and `playbackRate`").
- **Navidrome implements it**: navidrome PR #5442 (merged) adds `reportPlayback`, server-side auto-scrobble on `stopped` when `positionMs >= min(duration*50%, 240s)`, enriched `getNowPlaying` including server-side position estimation, and legacy mapping of `scrobble` submissions to `state=playing, rate=1.0`. https://github.com/navidrome/navidrome/pull/5442 — tracked as done in the extensions checklist https://github.com/navidrome/navidrome/issues/2695

### `scrobble` endpoint
- Since 1.5.0; batchable ids since 1.8.0; params `id`, `time` (ms epoch), `submission` (default true). `submission=true` updates play count + last played (since 1.11.0) and feeds `getNowPlaying`; `submission=false` is a now-playing notification only.
  - https://opensubsonic.netlify.app/docs/endpoints/scrobble/
- Navidrome behavior: plays are recorded **only** via `scrobble` with `submission=true`; `/stream` never marks plays (deliberate). https://www.navidrome.org/docs/developers/subsonic-api/

### Listen history via official APIs
- **None today (Aug 2026)** — see section 2. The `Child` object does carry `played` (last-played date) as an OpenSubsonic field that Navidrome fills (extensions list #2695), so per-track last-played is readable, but there is no event log endpoint.

### `getTopSongs` / `getSimilarSongs`
- `getTopSongs` (1.13.0): top songs for an artist, sourced from Last.fm; OpenSubsonic adds `topSongsByArtistId` extension so callers may pass artist `id` instead of name.
  - https://opensubsonic.netlify.app/docs/endpoints/gettopsongs/ , https://opensubsonic.netlify.app/docs/extensions/topsongsbyartistid/
- `getSimilarSongs(2)` (1.11.0): random songs from the artist + similar artists (Last.fm data).
  - https://opensubsonic.netlify.app/docs/endpoints/getsimilarsongs/
- Navidrome supports both **only when the admin enabled Last.fm integration** (external agents). https://www.navidrome.org/docs/developers/subsonic-api/
- Stats relevance: modest — could power "most-scrobbled track of artists you play" cards, but data comes from Last.fm, not the user's own plays.

### Cover art & artist images
- `getCoverArt` (1.0.0): binary image by `coverArt` id with `size` scaling param. Supported by Navidrome. Ideal for dashboard thumbnails via a caching reverse-proxy in front. https://opensubsonic.netlify.app/docs/endpoints/getcoverart/
- `getArtistInfo2` (1.11.0): bio, `musicBrainzId`, artist image URLs, similar artists. Navidrome support requires external integrations (Last.fm/Spotify/Deezer agents configured server-side). https://opensubsonic.netlify.app/docs/endpoints/getartistinfo2/ + compatibility notes above.

### `getUsers`
- Subsonic spec: returns all users (admin-only). **Navidrome deviation: returns only the user identified in the authentication** — user enumeration is intentionally impossible. Same for `getUser`.
  - Spec: https://opensubsonic.netlify.app/docs/endpoints/getusers/
  - Navidrome compat page: https://www.navidrome.org/docs/developers/subsonic-api/
- Consequence: per-user stats cannot discover users via `getUsers`; attribution must come from `getNowPlaying.username` and observed scrobble traffic. (Our multi-server aggregation already does this.)

---

## 2. Does Navidrome expose a native listening-history/stats API? (status Aug 2026)

Timeline of upstream decisions:

- 2021: issue #714 asked for a play-log table; closed as out-of-scope, users directed to Maloja / ListenBrainz-with-custom-URL. https://github.com/navidrome/navidrome/issues/714
- 2023: discussion #3093 confirmed "Navidrome does not keep a record of all scrobbles". https://github.com/navidrome/navidrome/discussions/3093
- Issue #1971: deluan noted plans to document/release a **native API** someday; meanwhile only `played` field was added. https://github.com/navidrome/navidrome/issues/1971
- **v0.59.0 (2025-12-06)**: native scrobble/listen history landed — PR #4770 adds a `scrobbles` table (`media_file_id`, `user_id`, `submission_time`), config `EnableScrobbleHistory` (default true). Release notes say this powers future statistics/"Navidrome Wrapped"-style features.
  - Release: https://github.com/navidrome/navidrome/releases/tag/v0.59.0
  - PR: https://github.com/navidrome/navidrome/pull/4770
  - Docs (Scrobbling → Scrobble History): https://www.navidrome.org/docs/usage/features/scrobbling/
  - Config reference: https://www.navidrome.org/docs/usage/configuration/options/
- **No public read endpoint ships yet.** Storage ≠ API. Current upstream activity:
  - Open PR #5650 `feat(subsonic): add getSongHistory endpoint` — proposed `GET /rest/getSongHistory` (count/offset, entries with `playedAt`). Not merged. https://github.com/navidrome/navidrome/pull/5650
  - Open PR #5651 "get most played songs". https://github.com/navidrome/navidrome/pull/5651
  - Follow-up work on playbackReport accounting still open (#5794 lost-stopped-report plays). https://github.com/navidrome/navidrome/issues/5794
- Undocumented interim surface (not recommended for us): the web-UI native API e.g. `/api/song?_end=20&_order=DESC&_sort=play_date&_start=0&recently_played=true`, JWT via `x-nd-authorization` obtained from a browser session. Documented by third parties: https://www.coryd.dev/posts/2025/tracking-listens-from-navidrome and multi-scrobbler PR #270 analysis https://github.com/FoxxMD/multi-scrobbler/pull/270 ; auth context: https://github.com/navidrome/navidrome/discussions/3765 . Reading Navidrome's private DB remains our explicit non-goal, and this private API sits in the same fragility category (unversioned, session-auth).
- **Conclusion:** keeping "native history import" closed until a public read API exists remains correct; `getSongHistory` (#5650) is the trigger to watch.

---

## 3. Comparable self-hosted projects (feature inspiration)

General-purpose scrobblers/stats:

- **multi-scrobbler** (FoxxMD, ~1.2k★): sources→clients scrobble forwarding incl. Subsonic source; supports the new `playbackReport` extension ("Enhanced Playback Reporting") with fallback; stale-player cleanup (`detectStaleNowPlayingFromMinutesAgo`) against servers returning dead entries; queued retries; regex transforms; duplicate guidance; health endpoints + Prometheus; multi-user silos.
  - https://github.com/FoxxMD/multi-scrobbler ; Subsonic source doc: https://docs.multi-scrobbler.app/configuration/sources/subsonic
- **Maloja** (krateng): self-hosted scrobble DB; **proxy-scrobble forwarding** to other services; associated-artists & multi-artist chart handling; custom rules engine; imports (Last.fm export, Spotify, ListenBrainz, other Maloja); manual scrobbling; ListenBrainz-compatible + native APIs; custom images. https://github.com/krateng/maloja
- **Koito** (gabehf, ~1k★): ListenBrainz-compatible endpoint scrobbler aimed at self-hosters; relay to existing scrobblers; imports from Maloja/LB/Last.fm/Spotify; configurable image sources; polished stats UI. https://github.com/gabehf/Koito
- **rescrobbled** (InputUsername): MPRIS desktop scrobbler daemon with pluggable targets (Last.fm, ListenBrainz, Libre.fm, Maloja…). https://github.com/InputUsername/rescrobbled
- `airsonic-stats`: **no active project found** under that name on GitHub (API searches return zero); references appear historical. Don't benchmark against it.

Navidrome-specific stats tools (closest competitors / validation):

- **rewind** (BernardoGiordano): "Spotify Wrapped"-style stories recap; requires Navidrome ≥0.59.0 and reads `navidrome.db` directly (SQLite read-only) — violates our architecture non-goal but proves demand for year-recap. https://github.com/BernardoGiordano/rewind
- **spindle** (xmorose): YourSpotify-style; a Navidrome **plugin** POSTs every play to its Fastify+SQLite backend; Vue dashboard with hour-of-day clock, weekday heatmap, sessions, year-in-review; one-time baseline import of existing play counts; Spotify Extended Streaming History import. https://github.com/xmorose/spindle
- **NaviStats** (ZortexSenpai): timespan dashboards, top sessions ranking, decade/year buckets, "On This Day", artist loyalty score, plus library-quality audits (format/bitrate/tagging). https://github.com/ZortexSenpai/NaviStats
- **Navidrome-Wrapped** (mdeik): purely client-side Subsonic-API Wrapped (play counts only — no timestamps available via public API), shareable 9:16 cards. https://github.com/mdeik/Navidrome-Wrapped

Cross-cutting distinctive features observed: scrobble forwarding/proxying, year-in-review/wrapped pages, calendar heatmaps + hour-of-day clocks, per-client/source breakdowns, import backfills (Spotify/LB exports), shareable summary cards, library-quality audits.

---

## 4. Scrobble forwarding feasibility (server-side, from observed `getNowPlaying`)

**ListenBrainz — easy (recommended first target).**
- Submit: `POST /1/submit-listens`, header `Authorization: Token <user token>` (token from https://listenbrainz.org/settings/ ), JSON body `{ "listen_type": "single" | "playing_now" | "import", "payload": [{ "listened_at": <unix>, "track_metadata": { "artist_name", "track_name", "album_name", "additional_info": { ... } } }] }`.
  - Core API: https://listenbrainz.readthedocs.io/en/latest/users/api/core.html ; JSON schema: https://listenbrainz.readthedocs.io/en/latest/users/json.html
- Limits: max 1000 listens/request; max payload 10 MB; `GET /1/validate-token` exists for setup UX.
- Submission rule: submit when ≥ half the track or 4 min listened, whichever is lower — identical to Navidrome's own auto-scrobble threshold (`min(50%, 240s)` in PR #5442), so we can mirror it.
- Bonus: Navidrome itself allows pointing `ListenBrainz.BaseURL` at Maloja etc.; the same LB wire format makes our forwarder compatible with Maloja/Koito for free. https://www.navidrome.org/docs/usage/features/scrobbling/

**Last.fm — heavier (defer).**
- Write services require user auth: register an API account (key + secret), then web flow `auth.getToken` → user authorizes at last.fm callback → `auth.getSession` with MD5 `api_sig` signature → persist session key; `track.scrobble` calls must be signed and carry `sk`.
  - Auth overview: https://www.last.fm/api/authentication ; web how-to: https://www.last.fm/api/webauth ; auth spec: https://www.last.fm/api/authspec ; scrobble: https://www.last.fm/api/show/track.scrobble
- Feasible (multi-scrobbler proves it) but adds key management, signature canonicalization, and a UI auth dance — effort roughly 2–3× ListenBrainz for a solo maintainer.

**Deduplication caveat:** most clients already scrobble to Last.fm/ListenBrainz themselves; blind forwarding causes double-scrobs. Forwarding must be opt-in per connection/user with duplicate suppression (see multi-scrobbler's duplicate guidance: https://docs.multi-scrobbler.app/configuration/duplicates/ ).

---

## 5. Known pitfalls of polling `getNowPlaying` frequently

- **Low server cost; no rate limits documented**: Navidrome serves `getNowPlaying` from an in-memory TTL cache of playback sessions (`playMap` keyed by clientId; TTL ≈ remaining track duration + 5 s, capped 30 min while paused). Source: `core/scrobbler/play_tracker.go` https://raw.githubusercontent.com/navidrome/navidrome/master/core/scrobbler/play_tracker.go . No rate limiting appears in docs/issues; 5–15 s intervals are common (multi-scrobbler class tools).
- **Stale entries / ghost plays**: servers keep returning entries after real playback stops; multi-scrobbler had to build stale detection (entry older than track length via `minutesAgo`) to avoid repeated scrobbles. We must expire sessions when an entry disappears or exceeds duration. https://docs.multi-scrobbler.app/configuration/sources/subsonic
- **Minute-granularity recency**: classic entries only expose `minutesAgo` (integer) — repeated plays of the same track within minutes are indistinguishable and sub-minute timing is impossible without `playbackReport` fields.
- **Session identity collisions**: sessions are keyed by client/player id; two devices reporting the same client name overwrite each other.
- **playbackReport accounting quirks (upstream, evolving)**: plays count only on explicit `stopped` past threshold — lost stop reports lose plays (#5794 open); out-of-order reports needed a fix (#5793). Handle `state=expired` and tolerate reordering. https://github.com/navidrome/navidrome/issues/5794 , https://github.com/navidrome/navidrome/pull/5793
- **Log spam**: Navidrome logs each API request (client/user at INFO); very aggressive polling floods server logs — keep intervals sane, add jitter/backoff, document expected log volume. (Perf problems reported upstream concern other endpoints, e.g. `getRandomSongs` #5558.)

---

## Ranked feature-extension shortlist

Ordered by (user value × feasibility for solo maintainer × architecture alignment). Effort: S ≤ a day-ish, M days, L weeks.

1. **Cover-art enrichment via cached `getCoverArt` proxy** — Every ranking/history row becomes recognizable; pure read-only Subsonic usage fits the architecture perfectly; no external accounts needed. **S**
2. **Year-in-review / "Wrapped" page computed from our own stored plays** — The single most-requested style of feature across Koito/spindle/NaviStats/rewind; we already own timestamped session data, so we don't need the DB-reading hacks competitors use. **M**
3. **Calendar heatmap + hour-of-day listening clock** — High visual payoff, simple SQL aggregation over existing tables; proven crowd-pleasers in spindle/NaviStats. **S**
4. **Opt-in ListenBrainz-format forwarder (covers Maloja/Koito via configurable base URL)** — Turns observed sessions into portable listens anywhere; single JSON POST design, token validation built in; must ship with dedupe/opt-in to avoid double-scrobs. **M**
5. **`playbackReport`-aware collector upgrade** — When clients send timeline data, capture exact duration, position, and transcoding state (and honor `ignoreScrobble`); otherwise continue using `minutesAgo` estimates. Aligns with the roadmap item "improve collector diagnostics". **M**
6. **Backfill bridge watching a Navidrome smart playlist ("Recently Played `.nsp`") through `getPlaylist`** — Recovers pre-install history within public APIs only, as a stopgap until upstream exposes history; documented technique from multi-scrobbler PR #270. **M**
7. **Upstream watch: `getSongHistory` (PR #5650) adapter** — Keep the integration isolated so the native-history importer can be enabled if the public endpoint merges. **S**
8. **Library-quality tiles from `search3` metadata (format/bitrate/decade distribution)** — Differentiator copied from NaviStats; zero extra polling (metadata already fetchable in bulk), complements transcode stats. **M**

Deliberately not shortlisted: Last.fm forwarding (auth complexity vs. value, see §4), `getArtistInfo2`/`getTopSongs` enrichments (require server-side Last.fm agent configuration many instances lack), anything touching the undocumented `/api/*` native API or `navidrome.db` (non-goal).
