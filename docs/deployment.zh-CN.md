# Docker 部署

[English](deployment.md) · [文档目录](README.zh-CN.md)

## 前置条件

- Docker Engine 与 Docker Compose v2
- 容器能够访问每个 Navidrome 服务器
- 拥有可调用 Subsonic API 的 Navidrome 账户

## 1. 创建部署目录

```bash
mkdir navidrome-stat
cd navidrome-stat
```

## 2. 创建 `.env`

请为 `STATS_API_TOKEN` 使用足够长的随机值。不要提交此文件，也不要把它包含在排障日志中。

```dotenv
NAVIDROME_URL=https://navidrome.example.invalid
NAVIDROME_USER=example_user
NAVIDROME_PASS=<navidrome-password>
STATS_API_TOKEN=<long-random-token>
# 可选的只读凭据与固定范围：
# STATS_READ_ONLY_TOKEN=<different-long-random-token>
# STATS_READ_ONLY_SOURCE_ID=server-id
# STATS_READ_ONLY_USERNAME=example_user

POLL_INTERVAL=10
PLAY_THRESHOLD_SEC=30
MAX_INFERRED_INTERVAL_SEC=30
PAUSE_GRACE_SEC=30
```

没有已保存的服务器条目时，三个 `NAVIDROME_*` 变量提供一个回退连接。对于该连接，每个非空环境变量都会优先于 SQLite 中已保存的对应值。一旦“设置 > 连接”中存在任何条目，应用只采集列表中已启用的连接；即使全部条目都被禁用，也不会重新启用回退连接。

如需汇总多个服务器，请在启动后通过“设置 > 连接”逐个添加；保存的凭据会以 AES-256-GCM 静态加密，密钥存放在数据库旁的 `secret.key`（随安装生成）。请把该文件与数据库一并备份，否则仅恢复数据库副本后需要重新输入密码；该加密可避免数据库文件与备份被直接查看，但不能防御主机完全失控。如果不能接受这种存储方式，请只使用环境变量配置的单一连接，不要通过设置页保存连接。

## 3. 创建 `compose.yaml`

示例固定使用当前稳定版 `v0.9.3`；`latest` 会随稳定版更新。

```yaml
services:
  navidrome-stat:
    image: stepaniah/navidrome-statistic:v0.9.3
    container_name: navidrome-stat
    user: "1000:1000"
    ports:
      - "39421:39421"
    volumes:
      - navidrome-stat-data:/data
    environment:
      NAVIDROME_URL: ${NAVIDROME_URL}
      NAVIDROME_USER: ${NAVIDROME_USER}
      NAVIDROME_PASS: ${NAVIDROME_PASS}
      STATS_API_TOKEN: ${STATS_API_TOKEN}
      STATS_READ_ONLY_TOKEN: ${STATS_READ_ONLY_TOKEN:-}
      STATS_READ_ONLY_SOURCE_ID: ${STATS_READ_ONLY_SOURCE_ID:-}
      STATS_READ_ONLY_USERNAME: ${STATS_READ_ONLY_USERNAME:-}
      LISTENBRAINZ_INGEST_TOKEN: ${LISTENBRAINZ_INGEST_TOKEN:-}
      LISTENBRAINZ_INGEST_USERNAME: ${LISTENBRAINZ_INGEST_USERNAME:-}
      DATABASE_URL: /data/navidrome_stats.db
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
      MAX_INFERRED_INTERVAL_SEC: ${MAX_INFERRED_INTERVAL_SEC:-30}
      PAUSE_GRACE_SEC: ${PAUSE_GRACE_SEC:-30}
      CHECKPOINT_INTERVAL_SEC: ${CHECKPOINT_INTERVAL_SEC:-60}
      SAVE_RETRY_ATTEMPTS: ${SAVE_RETRY_ATTEMPTS:-3}
      MAX_POLL_BACKOFF_SEC: ${MAX_POLL_BACKOFF_SEC:-60}
      RETENTION_MAINTENANCE_SEC: ${RETENTION_MAINTENANCE_SEC:-86400}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
      STATS_METRICS_AUTH: ${STATS_METRICS_AUTH:-false}
      OPENAPI_ENABLED: ${OPENAPI_ENABLED:-true}
    restart: unless-stopped
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:39421/health')"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  navidrome-stat-data:
```

## 4. 启动服务

```bash
docker compose up -d
docker compose ps
```

打开 `http://localhost:39421`。配置管理员或查看者 token 后，在登录界面输入对应 token；浏览器保存的是带角色的 HttpOnly 会话 Cookie，而不是 token 本身。

`/health` 用于检查进程是否存活。`/health/ready` 还会检查数据库、采集器、上游轮询与播放记录持久化。上游或数据库故障可能使就绪状态降级或未就绪，但进程仍保持存活。

## 运行要求

- 同一组数据源只能运行一个 Navidrome Stat 实例。多个实例轮询同一数据源可能导致重复计数。
- 活跃会话只保存在单个进程中，不支持多 worker 的 Uvicorn 部署。
- SQLite 中的收听记录为未加密存储；已保存的服务器凭据使用随库生成的本地密钥文件（`secret.key`）静态加密，该方案不抵御主机被完全攻陷的情形。
- 应用本身不提供 TLS。远程访问时应使用可信网络或 HTTPS 反向代理。
- SQLite 数据目录应放在本机存储上，不支持共享网络文件系统。

完整变量见[配置参考](configuration.zh-CN.md)。`.env` 中的额外变量还需在 `compose.yaml` 的 `environment` 中传入容器。更新、备份和故障排查见[运维指南](operations.zh-CN.md)。
