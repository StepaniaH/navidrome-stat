# Navidrome Statistic

[English](README.md)

Navidrome Statistic 汇总 Navidrome 上报的播放活动，并通过一个仪表盘统一展示。无论使用 Subsonic 兼容客户端、浏览器、手机、电脑，还是连接多个 Navidrome 服务器，都可以得到一致的统计视图，无需每个客户端单独实现统计功能。

服务通过轮询 `getNowPlaying`、在内存中追踪收听会话、将结果保存到 SQLite，并提供完整的本地网页界面。

## 功能

- 汇总不同客户端、设备、用户和 Navidrome 服务器的当前与历史播放活动。
- 展示收听时长、播放历史、小时与每日趋势、客户端使用、转码，以及艺人和专辑排行。
- 支持自定义播放阈值与暂停宽限期、持久化会话检查点，并在上游支持时使用 OpenSubsonic 播放进度。
- 支持按服务器筛选、连接管理、保留策略，以及按用户导出、导入和删除 JSON 数据。
- 可为仪表盘数据和接口启用 token 认证。
- 固定并自托管前端资源；发布的容器以非 root 用户运行。

## 重要限制

- 同一组数据源只能运行一个 Navidrome Statistic 实例。多个实例轮询同一数据源可能导致重复计数。
- 活跃会话只保存在单个进程中，不支持多 worker 的 Uvicorn 部署。
- SQLite 以及通过设置页保存的凭据均为明文存储。
- 应用本身不提供 TLS。远程访问时应使用可信网络或 HTTPS 反向代理。

## Docker 部署

### 前置条件

- Docker Engine 与 Docker Compose v2
- 容器能够访问每个 Navidrome 服务器
- 拥有可调用 Subsonic API 的 Navidrome 账户

### 1. 创建部署目录

```bash
mkdir navidrome-stat
cd navidrome-stat
```

### 2. 创建 `.env`

请为 `STATS_API_TOKEN` 使用足够长的随机值。不要提交此文件，也不要把它包含在排障日志中。

```dotenv
NAVIDROME_URL=https://navidrome.example.invalid
NAVIDROME_USER=example_user
NAVIDROME_PASS=<navidrome-password>
STATS_API_TOKEN=<long-random-token>

POLL_INTERVAL=10
PLAY_THRESHOLD_SEC=30
PAUSE_GRACE_SEC=30
```

没有已保存的服务器条目时，三个 `NAVIDROME_*` 变量提供一个回退连接。如需汇总多个服务器，请在启动后通过“设置 > 连接”逐个添加；其中保存的凭据会以明文写入 SQLite。如果不能接受这种存储方式，请只使用环境变量配置的单一连接，不要通过设置页保存连接。

### 3. 创建 `compose.yaml`

如需可复现的部署，请使用具体版本标签，不要使用 `latest`。

```yaml
services:
  navidrome-stat:
    image: stepaniah/navidrome-statistic:latest
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
      DATABASE_URL: /data/navidrome_stats.db
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
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

### 4. 启动服务

```bash
docker compose up -d
docker compose ps
```

打开 `http://localhost:39421`。配置 `STATS_API_TOKEN` 后，在登录界面输入该 token；浏览器保存的是 HttpOnly 会话 Cookie，而不是 token 本身。

`/health` 用于检查进程是否存活。`/health/ready` 还会检查数据库与采集器，因此上游短暂故障可能使就绪状态降级，但进程仍保持健康。

## 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NAVIDROME_URL` | 无 | 初始 Navidrome 基础 URL；数据库已有完整连接时可以不设置。 |
| `NAVIDROME_USER` | 无 | 初始 Subsonic 用户名。 |
| `NAVIDROME_PASS` | 无 | 初始 Subsonic 密码。 |
| `DATABASE_URL` | `navidrome_stats.db` | SQLite 文件路径；虽然名称中包含 URL，但不支持其他数据库。 |
| `STATS_API_TOKEN` | 空 | 设置后保护仪表盘数据、应用接口和 OpenAPI 路由。 |
| `STATS_METRICS_AUTH` | `false` | 本项与 `STATS_API_TOKEN` 同时设置时，`/metrics` 需要认证。 |
| `OPENAPI_ENABLED` | `true` | 设为 `false` 时移除 `/docs`、`/redoc` 和 `/openapi.json`。 |
| `POLL_INTERVAL` | `10` | 轮询间隔，限制在 5–300 秒。 |
| `PLAY_THRESHOLD_SEC` | `30` | 计为一次播放所需的活跃观测秒数，限制在 1–3600。 |
| `PAUSE_GRACE_SEC` | `30` | 在内存中保留暂停或暂时消失会话的秒数，限制在 0–3600。 |
| `CHECKPOINT_INTERVAL_SEC` | `60` | 活跃会话持久化检查点的刷新间隔，限制在 10–3600 秒。 |
| `SAVE_RETRY_ATTEMPTS` | `3` | 会话数据库写入尝试次数，限制在 1–10。 |
| `MAX_POLL_BACKOFF_SEC` | `60` | 上游故障退避上限，限制在 1–3600 秒。 |
| `RETENTION_MAINTENANCE_SEC` | `86400` | 自动执行保留期清理的间隔，限制在 60–604800 秒。 |
| `SESSION_COOKIE_SECURE` | `false` | 为登录 Cookie 添加 Secure 标记；用户通过 HTTPS 访问时应启用。 |

环境变量在应用启动时解析。修改后需重启容器。

## 播放计数方式

当累计活跃观测时长达到 `PLAY_THRESHOLD_SEC` 时，一首曲目计为一次播放。暂停或暂时消失的时间不计入时长。达到阈值时会创建检查点，之后的检查点与会话结算只更新同一条数据库记录，不会重复增加播放次数。

服务器声明支持 OpenSubsonic `playbackReport` 扩展时，媒体位置和播放状态可提高时长统计质量；其他服务器继续使用常规轮询。未达到播放阈值便结束的会话会单独记录为播放尝试。

详细原理见[架构说明](docs/architecture.md)。

## 日常运维

### 日志

```bash
docker compose logs -f --tail=100 navidrome-stat
```

应用日志会避免输出播放元数据和上游请求 URL。反向代理与 Navidrome 仍可能记录 Subsonic 认证查询参数，分享日志前请检查相关日志配置。

### 更新

```bash
docker compose pull
docker compose up -d
```

更新固定版本前，请备份数据库并阅读变更记录。

### 备份与恢复

数据卷包含收听历史，也可能包含已保存的 Navidrome 凭据。所有备份都应按敏感数据处理。

复制 SQLite 文件前先停止服务：

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  --volumes-from navidrome-stat:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  cp /data/navidrome_stats.db /backup/navidrome_stats.db
docker compose start navidrome-stat
```

恢复时应先停止服务、保留当前数据库、把已验证的备份复制到 `/data/navidrome_stats.db`，确认 UID 和 GID `1000:1000` 具有写权限，然后启动服务。请先在生产卷之外验证恢复流程。

## 安全与隐私

- 未设置 `STATS_API_TOKEN` 时，仪表盘数据和接口允许匿名访问，只应在可信网络中使用。
- `/health` 与 `/health/ready` 始终公开。`/metrics` 默认公开；设置 token 并启用 `STATS_METRICS_AUTH=true` 后可要求认证。
- 启用认证后，仪表盘静态文件仍可加载，但数据请求需要授权。
- 浏览器策略会阻止公共脚本和样式来源，同时允许页面使用的内联代码。
- 收集播放活动前应告知受影响的用户，并选择适当的保留期。

详细说明见[隐私文档](docs/privacy.md)与[安全政策](SECURITY.md)。

## 开发

项目支持 Python 3.11。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
pytest -q --cov=src --cov-report=term-missing --cov-fail-under=80
uvicorn src.main:app --host 127.0.0.1 --port 39421
```

仓库还提供用于构建当前本地检出的 [`docker-compose.yml`](docker-compose.yml)：

```bash
git clone https://github.com/StepaniaH/navidrome-stat.git
cd navidrome-stat
docker compose up -d --build
```

前端资源和浏览器测试使用 Node.js：

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

测试使用临时数据库和合成 API 数据，不需要连接真实 Navidrome 服务器。

## 项目信息

- [架构说明](docs/architecture.md)
- [隐私说明](docs/privacy.md)
- [贡献指南](CONTRIBUTING.md)
- [变更记录](CHANGELOG.md)
- [安全政策](SECURITY.md)

## 许可证

Navidrome Statistic 使用 [MIT License](LICENSE)。随应用分发的 Tailwind CSS 与 Apache ECharts 在 `src/static/vendor/` 中保留各自的许可证和声明文件。
