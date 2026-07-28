# Navidrome Statistic

[English](README.md)

Navidrome Statistic 是一个自托管服务。它轮询 Subsonic 的 `getNowPlaying` 接口、追踪收听会话、将达到条件的播放记录写入 SQLite，并通过网页仪表盘展示统计结果。

本项目按单个应用实例设计。一个实例可以配置多个 Navidrome 服务器，但不支持多个 Navidrome Statistic 副本同时采集相同的数据源，否则可能重复计数。

## 功能

- 按可配置的播放阈值和暂停宽限期追踪活跃播放，通过幂等检查点保存并在结束时更新最终时长。
- 上游声明支持时使用 OpenSubsonic 播放报告并记录时长是上报值还是估算值；旧版服务器继续使用轮询兼容路径。
- 在一个仪表盘中管理多个 Navidrome 服务器，支持按服务器筛选和查看采集器健康状态。
- 展示正在播放、播放历史、客户端、转码、时间趋势以及艺人和专辑排行。
- 将未达到播放阈值的尝试与正式播放分开记录。
- 支持配置保留期，以及按用户导出、导入和删除 JSON 数据。
- 可通过 `STATS_API_TOKEN` 为仪表盘和接口启用认证。
- 固定并自托管前端资源；仪表盘正常使用时不会访问公共 CDN。
- 使用 Python 3.11 多阶段镜像，并以非 root 用户运行。

## Docker 部署

### 前置条件

- 安装了 Docker Engine 和 Docker Compose v2
- 容器能够访问每个 Navidrome 服务器
- 拥有可调用 Subsonic 接口的 Navidrome 账户

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

这三个 `NAVIDROME_*` 变量用于配置初始数据源或兼容旧配置。启动后可以在“设置 > 服务器连接”中添加其他服务器。通过设置页保存的值会以明文形式写入应用数据库；如果不能接受这种存储方式，请优先使用环境变量。

### 3. 创建 `compose.yaml`

如果部署可复现性比自动获取最新版本更重要，请使用具体版本标签，不要使用 `latest`。

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
      POLL_INTERVAL: ${POLL_INTERVAL:-10}
      PLAY_THRESHOLD_SEC: ${PLAY_THRESHOLD_SEC:-30}
      PAUSE_GRACE_SEC: ${PAUSE_GRACE_SEC:-30}
      SAVE_RETRY_ATTEMPTS: ${SAVE_RETRY_ATTEMPTS:-3}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
      DATABASE_URL: /data/navidrome_stats.db
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

打开 `http://localhost:39421`。设置 `STATS_API_TOKEN` 后，仪表盘会要求输入该令牌，浏览器只保存一个 HTTP-only 会话 Cookie。

`/health` 用于检查进程是否存活。`/health/ready` 还会报告数据库和采集器状态；上游短暂失败可能使就绪状态降级，但不要求重启容器。

## 日常运维

### 查看日志

```bash
docker compose logs -f --tail=100 navidrome-stat
```

应用日志会主动避免输出播放元数据和认证请求地址。不要启用或分享可能包含 Subsonic 认证查询参数的基础设施日志。

### 更新

```bash
docker compose pull
docker compose up -d
docker image prune
```

更新前应备份数据库。使用固定镜像标签时，请先阅读版本说明再修改标签。

### 备份与恢复

命名卷包含 SQLite 数据库、收听历史，以及通过设置页保存的服务器凭据。所有备份都应按敏感数据处理。

复制数据库前先停止应用：

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  -v navidrome-stat_navidrome-stat-data:/data:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  cp /data/navidrome_stats.db /backup/navidrome_stats.db
docker compose start navidrome-stat
```

实际卷名可通过 `docker volume ls` 查看；Compose 通常会加上部署目录名称作为前缀。备份应保存在受访问控制的位置，并设置合适的保留策略。

恢复时应先停止服务、保留当前卷、把已验证的备份复制到 `/data/navidrome_stats.db`，确认 UID 和 GID `1000:1000` 具有写权限，然后再启动服务。请先在生产卷之外验证恢复流程。

## 配置

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `NAVIDROME_URL` | 无 | 初始 Navidrome 基础地址；除非数据库中已有完整数据源，否则必需。 |
| `NAVIDROME_USER` | 无 | 初始 Subsonic 用户名。 |
| `NAVIDROME_PASS` | 无 | 初始 Subsonic 密码。 |
| `DATABASE_URL` | `navidrome_stats.db` | SQLite 文件路径；Docker 示例使用 `/data/navidrome_stats.db`。 |
| `STATS_API_TOKEN` | 空 | 设置后保护仪表盘、统计接口、设置接口和 OpenAPI 路由。 |
| `POLL_INTERVAL` | `10` | 轮询间隔，限制在 5 至 300 秒。 |
| `PLAY_THRESHOLD_SEC` | `30` | 计为一次播放所需的活跃观测秒数，限制在 1 至 3600。 |
| `PAUSE_GRACE_SEC` | `30` | 在内存中保留暂停或暂时消失会话的秒数，限制在 0 至 3600。 |
| `MAX_POLL_BACKOFF_SEC` | `60` | 上游故障退避上限，限制在 1 至 3600 秒。 |
| `SAVE_RETRY_ATTEMPTS` | `3` | 会话数据库写入尝试次数，限制在 1 至 10；失败后会话仍可重试。 |
| `SESSION_COOKIE_SECURE` | `false` | 应用通过 HTTPS 访问时设为 `true`，使登录 Cookie 带 Secure 标记。 |
| `RETENTION_MAINTENANCE_SEC` | `86400` | 保留期清理间隔，限制在 60 至 604800 秒。 |

当累计活跃时长大于等于 `PLAY_THRESHOLD_SEC` 时，一首曲目计为一次播放。达到阈值时写入幂等检查点；会话结束时更新同一行的最终活跃时长，不会再增加一次播放。服务器声明支持 OpenSubsonic 播放报告时，会结合媒体位置和播放状态提高估算质量；否则继续按轮询间隔估算。暂停区间不计入时长。

## 安全与隐私

- 未设置 `STATS_API_TOKEN` 时，仪表盘和接口允许匿名访问，只应在可信网络中使用。
- 应用本身不终止 TLS。远程访问前，应部署配置正确的 HTTPS 反向代理。
- SQLite 以明文保存用户名、媒体元数据、收听时间，以及通过设置页保存的凭据。
- 收集播放活动前应告知受影响的 Navidrome 用户，并在“设置 > 隐私与数据”中选择适当的保留期。
- 应保护 `.env`、Docker 卷、备份、浏览器访问和反向代理日志。
- Tailwind CSS 和 ECharts 固定版本并由应用自身提供；浏览器 CSP 只允许同源脚本和样式。
- 用户导出使用固定文件名，包含正式播放与短播放尝试；可导入第 1 或第 2 版格式。导入限制为 5 MiB、10000 条，并校验时间、字段长度和时长范围。

通用 Compose 示例无法替你确定授权规则、TLS 终止、备份安全或公网暴露策略，这些事项必须由部署负责人决定。

## 从源码构建

仓库中的 [`docker-compose.yml`](docker-compose.yml) 用于构建当前本地检出：

```bash
git clone https://github.com/StepaniaH/navidrome-stat.git
cd navidrome-stat
docker compose up -d --build
```

运行 Compose 前，请根据 Docker 部署章节中的占位示例创建 `.env`。不要把真实凭据写入受版本控制的文件。

## 开发

项目支持 Python 3.11。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
uvicorn src.main:app --host 127.0.0.1 --port 39421
```

直接运行依赖固定在 `requirements.txt`，Docker 使用完整解析后的 `requirements.lock`，测试依赖位于 `requirements-dev.txt`。

重建固定版本的前端资源并运行合成浏览器测试：

```bash
npm ci
npx playwright install chromium
npm run test:e2e
```

浏览器测试使用临时 SQLite 数据库和拦截后的合成接口数据，不需要真实 Navidrome 账户。

## 项目文档

- [项目文档索引](docs/README.md)
- [当前实现事实](docs/current-state.md)
- [接口与配置](docs/interfaces.md)
- [隐私边界](docs/privacy.md)
- [安全模型](docs/security.md)
- [Agent 任务登记](docs/tasks.md)

## 许可证

Navidrome Statistic 使用 [MIT License](LICENSE)。
随应用分发的 Tailwind CSS 与 Apache ECharts 在 `src/static/vendor/` 中保留各自的许可证和声明文件。
