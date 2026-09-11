# Collection and counting

[简体中文](collection.zh-CN.md) · [Documentation](README.md)

By default, Navidrome Stat polls Navidrome’s `getNowPlaying` API for activity reported by clients. Coverage depends on what reaches the server; offline or unreported playback may be missing. Run one collector instance for a given set of sources.

## How plays are counted

A track counts once its accumulated active playback time reaches `PLAY_THRESHOLD_SEC`. Paused and missing intervals are excluded. An interval longer than the effective inference limit (the greater of `MAX_INFERRED_INTERVAL_SEC` and twice `POLL_INTERVAL`) is treated as an unobserved gap, adds no listening time, and leaves the saved duration marked as a lower bound. Reaching the threshold creates a checkpoint; later checkpoints and session finalization update the same database row instead of adding another play.

When a server advertises the OpenSubsonic `playbackReport` extension, position and playback-state fields improve duration accounting. Other servers continue to work through regular polling. Sessions that end below the play threshold are stored separately as playback attempts.

The Recent Plays information control reports these below-threshold sessions as a share of tracked playback attempts. Pre-install backfill and native-history imports are excluded because they do not represent live sessions collected by the application; records restored from a Navidrome Stat privacy archive retain their original accounting role.

## Recovering pre-install history

Optionally, a saved connection can watch a Navidrome smart playlist (an `.nsp` such as "Recently Played"). On each check the service reads that playlist through the public `getPlaylist` API and stores one timestamped play per track with unknown listened duration and transcoding state. Re-runs never duplicate rows, listens already covered by live polling are skipped, and only plays that actually happened before installation are imported — older repeats implied by a track's play count are never invented. Configure the playlist ID per connection on the settings page.

## Push collection from Navidrome

To collect scrobbles sent by Navidrome, set `LISTENBRAINZ_INGEST_TOKEN` and `LISTENBRAINZ_INGEST_USERNAME`, restart Navidrome Stat, and set Navidrome's [`ListenBrainz.BaseURL`](https://www.navidrome.org/docs/usage/features/scrobbling/) (or `ND_LISTENBRAINZ_BASEURL`) to `http://navidrome-stat:39421/1/`. Enter the ingestion token in that Navidrome user's ListenBrainz settings. Requests authenticate with the standard `Authorization: Token` header. The receiver stores `single` and `import` submissions; it validates but does not store `playing_now` submissions.

Exact retries are deduplicated using the source, username, timestamp, recording, and release identity. Records received through polling, playlist backfill, history import, and this endpoint remain separate. Do not enable more than one live collection method for the same user unless separate records are expected.

## Reading duration values

In details, `≈` denotes an estimate, `≥` a confirmed lower bound, and `—` an unrecorded duration. Dashboard and Listening Review totals show the stored listening time directly. Imported records without duration still count as plays but add no listening time.

Pre-install backfill only recovers records actually supplied by the upstream server; it cannot reconstruct a complete history. The `getSongHistory` adapter in v0.9.3 is experimental and attempts import only when a server advertises that endpoint; standard deployments should not depend on it.
