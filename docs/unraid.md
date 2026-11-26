# Unraid installation

[简体中文](unraid.zh-CN.md) · [Documentation](README.md)

The [Docker Manager template](../deploy/unraid/navidrome-stat.xml) uses the published `stepaniah/navidrome-statistic:latest` image. The `latest` tag follows stable releases. Navidrome must already be running and reachable from this container. Navidrome Stat connects through its API; it does not need a music-library mount, the Navidrome database, or the Docker socket. The dashboard requires a browser supported by Tailwind CSS 4: Chrome 111, Safari 16.4, Firefox 128, or later; older browsers may render it without styling.

## Prepare appdata

Use a dedicated directory on local Unraid storage, such as `/mnt/user/appdata/navidrome-stat`. Do not use an SMB or NFS mount for SQLite or share this directory with another running instance.

The image runs as UID/GID `1000:1000`. Before the first installation, open the Unraid terminal and create the directory with that ownership. This command only runs if the path does not already exist:

```bash
test ! -e /mnt/user/appdata/navidrome-stat && \
  install -d -m 0700 -o 1000 -g 1000 /mnt/user/appdata/navidrome-stat
```

If you choose another path, use it both here and in the **Appdata** field. For an existing directory, stop the application and back it up before adjusting ownership; UID/GID `1000:1000` must be able to read and write its contents. The image does not interpret `PUID` or `PGID` variables. Keep the container stopped while moving its appdata, including moves performed by Unraid's mover.

## Install from Community Applications

1. Open the **Apps** tab in Unraid and search for **Navidrome Stat** (or open its [Community Applications listing](https://ca.unraid.net/apps/navidrome-stat-0xfttrp0mywwfl)).
2. Select **Install**, review the fields below, enter a long, random **Administrator token**, and apply.
3. Enable **Autostart** for the container on the Docker page if it should start with the server.

| Field | Default or action |
| --- | --- |
| Repository | `stepaniah/navidrome-statistic:latest` |
| Network | `bridge`; leave privileged mode off |
| WebUI | Host port `39421` → container port `39421/tcp` |
| Appdata | `/mnt/user/appdata/navidrome-stat` → `/data`, read-write |
| Administrator token | Set `STATS_API_TOKEN` to a long, random value before applying |
| Database path | `/data/navidrome_stats.db`; shown in Advanced View |

If the host port is occupied, change only the host port. The WebUI shortcut uses the mapped port. Keep the administrator token non-empty: an empty token disables administrator authentication, and without a viewer token the dashboard and administrative APIs are public.

### Install the template manually

If you prefer not to use Community Applications:

1. Download [`navidrome-stat.xml`](../deploy/unraid/navidrome-stat.xml) from this repository.
2. Place it on the Unraid server at `/boot/config/plugins/dockerMan/templates-user/my-navidrome-stat.xml`. Choose a different filename if one already exists; preserve existing saved templates and their settings.
3. Open **Docker > Add Container** and select the template from the **Template** list.
4. Review the fields above, enter a long, random **Administrator token**, and apply.
5. Enable **Autostart** for the container on the Docker page if it should start with the server.

Unraid stores saved container templates in the directory above; see the [Community Applications documentation](https://docs.unraid.net/community-applications/).

## Connect Navidrome

Open the container's **WebUI**, sign in with the administrator token, and add a server in **Settings > Connections**. Enter its URL, username, and password, test the connection, then save it enabled. Repeat for additional servers.

Use an address reachable from the container. `localhost` refers to Navidrome Stat itself. For Navidrome on the same Unraid server, use the server's reachable address and Navidrome's published port, or attach both containers to the same user-defined Docker network and use Navidrome's container name and internal port. The default `bridge` network does not provide container-name lookup.

The template leaves the `NAVIDROME_*` environment fallback unset. Saved connections are the normal setup path. If you need an environment-only connection, add all three variables from the [configuration reference](configuration.md) and leave the saved connection list empty.

Run one instance per set of sources. Playback must be reported to Navidrome by the player; installing the service does not recover a complete past listening history. See [collection and counting](collection.md).

## Access and storage

- **Viewer token** in Advanced View optionally enables read-only access. Use a different random value from the administrator token. Add `STATS_READ_ONLY_SOURCE_ID` and/or `STATS_READ_ONLY_USERNAME` if viewers should have a fixed scope; see [configuration](configuration.md).
- **Protect metrics** defaults to `true` in this template, requiring administrator authentication for `/metrics`.
- For remote access, configure an HTTPS reverse proxy and set **Secure session cookie** to `true`. Leave it `false` for direct HTTP access.
- Unraid stores entered environment values in the saved container template and Docker configuration. Password masking only hides the field on screen. Keep saved templates and flash backups private.
- Appdata contains the SQLite database, its write-ahead-log files when present, `secret.key`, and the artwork cache. Saved Navidrome passwords are encrypted with that key. Back up the whole directory while the container is stopped. See [privacy](privacy.md) and [operations](operations.md#backup-and-restore).

## Update and recover

1. Read the [release notes](https://github.com/StepaniaH/navidrome-stat/releases), record the running version from the dashboard's About information, and stop the container.
2. Back up the complete appdata directory and keep a private copy of the saved container settings.
3. Use Unraid's container update action to pull the current `latest` image, then start the container if it is stopped. Preserve the appdata mapping and configured tokens.
4. Sign in, confirm the version, check saved connections and earlier history, and verify collection resumes.

To pin a release, change **Repository** to a published tag such as `stepaniah/navidrome-statistic:v0.9.5`. Unraid updates the configured tag; a pinned installation requires changing that field to move to another release. Public template edits do not replace the settings of an existing installation; review its saved configuration when adopting new fields.

For a rollback, stop the container and restore both the previous image tag and its matching pre-update appdata backup. Do not run an older version against a database migrated by a newer version without confirming compatibility.

## Check the installation

| Check | Expected result |
| --- | --- |
| Open WebUI in a private browser window | Login is required; the administrator token opens the dashboard and settings |
| Request `/health` | `{"status":"ok"}`; this only checks process liveness |
| Request `/health/ready` | Database is `ok`; readiness may be `degraded` before adding an enabled connection |
| Add a connection and play music | Connection succeeds and collection begins; counting follows the configured threshold |
| Restart or recreate the container with the same appdata mapping | Connections and listening history remain available |
| Change only the host port | The Unraid WebUI shortcut opens the new mapped port |

If SQLite cannot be opened or the key file cannot be written, check the Appdata mapping and ownership. A successful `/health` response alone does not verify authentication, upstream access, collection, or persistence.
