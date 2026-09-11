# 配置参考

[English](configuration.md) · [文档目录](README.zh-CN.md)

本页列出应用支持的环境变量。使用 Docker Compose 时，须在服务的 `environment` 或 `env_file` 中声明变量；仅写入用于插值的 `.env` 不会自动传入容器。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NAVIDROME_URL` | 无 | 回退连接使用的 Navidrome 基础 URL；仅在已保存的服务器列表为空时使用。 |
| `NAVIDROME_USER` | 无 | 回退 Subsonic 连接使用的用户名。 |
| `NAVIDROME_PASS` | 无 | 回退 Subsonic 连接使用的密码。 |
| `DATABASE_URL` | `.data/navidrome_stats.db` | 新本地检出默认使用的 SQLite 文件路径；若根目录已有 `navidrome_stats.db`，仍会继续使用。Docker Compose 设置为 `/data/navidrome_stats.db`。虽然名称中包含 URL，但不支持其他数据库。 |
| `STATS_API_TOKEN` | 空 | 设置后保护仪表盘数据、应用接口和 OpenAPI 路由。 |
| `STATS_READ_ONLY_TOKEN` | 空 | 启用只读查看凭据，可查看仪表盘/回顾，但不能打开设置或调用管理接口；必须与其他 token 使用不同值。 |
| `STATS_READ_ONLY_SOURCE_ID` | 空 | 查看者会话的可选固定服务器范围，由后端强制执行。 |
| `STATS_READ_ONLY_USERNAME` | 空 | 查看者会话的可选固定用户名范围，由后端强制执行。 |
| `STATS_METRICS_AUTH` | `false` | 启用后，`/metrics` 需要管理员认证。 |
| `STATS_QUERY_BUDGET_MS` | `250` | `/metrics` 使用的每个仪表盘子查询预算，限制在 10–60000 毫秒；用于监控查询性能回归，不会自动启用汇总表。 |
| `COVER_ART_RESPONSE_MAX_BYTES` | `10485760` | 封面代理接受的上游单响应大小上限，限制在 65536–67108864 字节。 |
| `OPENAPI_ENABLED` | `true` | 设为 `false` 时移除 `/docs`、`/redoc` 和 `/openapi.json`。 |
| `POLL_INTERVAL` | `10` | 轮询间隔，限制在 5–300 秒。 |
| `PLAY_THRESHOLD_SEC` | `30` | 计为一次播放所需的有效播放秒数，限制在 1–3600。 |
| `MAX_INFERRED_INTERVAL_SEC` | `30` | 可推断为连续收听的两次成功活跃观察最大间隔，限制在 1–3600 秒；为容纳正常请求耗时，实际值不会低于 `POLL_INTERVAL` 的两倍。更长的未观察缺口不增加时长，并把保存总量标记为下限。 |
| `PAUSE_GRACE_SEC` | `30` | 在内存中保留暂停或暂时消失会话的秒数，限制在 0–3600。 |
| `CHECKPOINT_INTERVAL_SEC` | `60` | 活跃会话持久化检查点的刷新间隔，限制在 10–3600 秒。 |
| `SAVE_RETRY_ATTEMPTS` | `3` | 会话数据库写入尝试次数，限制在 1–10。 |
| `MAX_POLL_BACKOFF_SEC` | `60` | 上游故障退避上限，限制在 1–3600 秒。 |
| `BACKFILL_INTERVAL_SEC` | `3600` | 已配置的智能播放列表回填复查间隔，限制在 300–86400 秒。 |
| `BACKFILL_CUTOFF_MARGIN_SEC` | `60` | 导入前从实时轮询覆盖边界回退的安全边距，限制在 0–3600 秒。 |
| `RETENTION_MAINTENANCE_SEC` | `86400` | 自动执行保留期清理的间隔，限制在 60–604800 秒。 |
| `SESSION_COOKIE_SECURE` | `false` | 为登录 Cookie 添加 Secure 标记；用户通过 HTTPS 访问时应启用。 |
| `LISTENBRAINZ_INGEST_TOKEN` | 空 | 与 `LISTENBRAINZ_INGEST_USERNAME` 同时设置时启用 ListenBrainz 兼容接收器；必须与管理员和查看者 token 使用不同值。 |
| `LISTENBRAINZ_INGEST_USERNAME` | 空 | 接收器写入记录所归属的用户名。 |
| `LISTENBRAINZ_INGEST_SOURCE_ID` | `listenbrainz` | 接收器记录及去重所用的稳定来源标识。 |
| `LISTENBRAINZ_INGEST_SOURCE_NAME` | `ListenBrainz receiver` | 接收器记录的展示名称。 |

环境变量在应用启动时解析。管理员、查看者或采集 token 使用相同值时，应用将拒绝启动。修改后需重启容器。
