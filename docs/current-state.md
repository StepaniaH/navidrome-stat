# 当前实现事实

核验基线：当前工作树中的 `src/`、`tests/`、`Dockerfile`、`docker-compose.yml`、`requirements.txt` 和 `README.md`。本文只描述代码可证明的行为，不代表生产部署已经完成安全配置或人工验收。

## 1. 组件与数据流

| 组件 | 当前职责 | 代码位置 |
| --- | --- | --- |
| FastAPI 应用 | 生命周期、后台轮询、静态页面和统计 API | `src/main.py` |
| 播放会话追踪 | 进程内会话状态机、阈值结算与缺失 ID 过滤 | `src/sessions.py` |
| Navidrome 客户端 | 生成 Subsonic token/salt，调用 `getNowPlaying` | `src/client.py` |
| SQLite 层 | 建表、写入播放会话、聚合查询与隐私数据操作 | `src/database.py`、`src/privacy_ops.py` |
| Dashboard | 请求统计 API，使用 ECharts 展示图表和表格 | `src/static/index.html` |
| 隐私设置页 | 保留策略、按用户导出/导入/删除 | `src/static/settings.html` |
| 容器配置 | Python 3.11 镜像、端口、数据库挂载和 `.env` 注入 | `Dockerfile`、`docker-compose.yml` |

运行数据流：

1. FastAPI lifespan 调用 `init_db()`，随后创建 `polling_loop()` 后台任务。
2. `NavidromeClient` 从构造参数或环境变量读取连接信息，每次请求生成六位 salt 和 MD5 token。
3. 轮询循环调用上游 `/rest/getNowPlaying`，由 `PlaybackSessionTracker` 按 `playerId` 追踪会话；缺失 `playerId` 的条目被跳过。
4. 同一播放器继续播放同一 `track_id` 时只更新 `last_seen_at`；换曲、停止后超过 30 秒或应用关闭时尝试结算。
5. 结算以 `last_seen_at - first_seen_at` 计算观测时长。时长大于等于 30 秒才写入一条 `play_history` 记录。
6. Dashboard 初次加载并每 10 秒请求四个统计 API（含 `/api/stats/summary`）；标签页隐藏时降为 30 秒；含概览卡片、加载/空/错误状态与深色响应式布局。

## 2. 播放计数语义

- 默认上游轮询间隔是 10 秒，可通过 `POLL_INTERVAL` 改变；环境变量在模块导入时使用 `int()` 解析。
- 播放阈值固定为 30 秒，不可配置，代码判断为 `duration >= 30`。
- 达到 30 秒观测时长时立即写入一条 `play_history` 记录（同一曲目会话不重复写入）；`isPlaying=false` 时结算当前曲目会话；换曲、停止或关闭时清理内存会话。
- 上游连续失败时轮询间隔指数退避，上限由 `MAX_POLL_BACKOFF_SEC` 控制（默认 60 秒）。
- `isPlaying` 缺失时按正在播放处理；明确为假时该条目被跳过。
- 消失或暂停的播放器只有在距最后一次观测至少 30 秒后结算；换曲会立即结算旧会话。
- 活跃会话由 `PlaybackSessionTracker` 维护，只存在于单个进程内。异常退出会丢失未结算会话；多 worker 或多副本之间不共享状态。
- `NavidromeClient` 在 lifespan 中创建并在关闭时 `close()`；轮询失败时指数退避后继续下一轮，上限由 `MAX_POLL_BACKOFF_SEC` 控制。

## 3. 持久化与查询

- 默认数据库路径为运行目录下的 `navidrome_stats.db`；`DATABASE_URL` 实际被当作 SQLite 文件路径，不是通用数据库 URL。
- `init_db()` 创建 `play_history` 与 `schema_meta`，并执行版本迁移（当前 schema 版本 2：默认 `retention_days=permanent`）。
- 每次写入或查询都会打开一个新的 aiosqlite 连接。
- `played_at` 保存结算时 `last_seen_at` 的 ISO 8601 字符串，当前由应用产生时包含 UTC 偏移。
- 播放器和转码统计按已落库记录数聚合，不按监听秒数聚合。
- history 接口按 `username, track_id` 聚合；`title`/`artist`/`album` 取自最新插入行（`MAX(id)`），按最近 `played_at` 排序。
- 播放历史**默认永久保留**；可通过 `/settings` 将保留期设为 1–360 天或恢复永久。
- 后台任务按 `RETENTION_MAINTENANCE_SEC`（默认 24 小时）自动清理超出保留期的记录；启动时也会执行一次。
- 支持按用户导出 JSON、导入（合并或覆盖）与删除；删除与过期清理前提供条数预览，执行需 `confirm: true`。
- 表没有唯一约束、外键或重复写入防护；有 `username`/`track_id` 与 `played_at` 索引。

完整字段和 API 响应见 [`interfaces.md`](interfaces.md)。

## 4. HTTP 与前端

- 应用包含 `/`、`/settings`、`/health`、`/health/ready`、认证路由、四个统计 API 与隐私管理 API。可选 `STATS_API_TOKEN` 保护统计与隐私 API。
- `/health` 与 `/health/ready` 始终公开，供探针使用。
- `POST /api/auth/login` 在启用认证时设置 httpOnly 会话 Cookie；Dashboard 支持令牌登录。
- 响应附加 CSP、`nosniff`、`DENY` 框架与 `no-referrer` 策略。
- FastAPI 自动提供默认 OpenAPI 路由（通常为 `/openapi.json`、`/docs` 和 `/redoc`），代码未显式关闭或定制。
- history 的 `limit` 使用 FastAPI `Query` 校验，范围 1–100，默认 10。
- Dashboard 的 Tailwind CSS 和 ECharts 从公共 CDN 加载；ECharts 5.5.0 带 SRI；CSP 限制脚本来源。
- 页面提供可见的错误横幅、手动刷新按钮和上次更新时间；历史表格用户数据用 `textContent` 渲染。

## 5. 部署与配置

- Docker 镜像基于 `python:3.11-slim`，安装 `build-essential`，以默认容器用户运行。
- Uvicorn 在容器和 `src/main.py` 直接运行路径中绑定 `0.0.0.0:39421`。
- Compose 将宿主机 `39421` 映射到容器同端口，加载 `.env`，并把单个数据库文件挂载到 `/app/navidrome_stats.db`。
- Compose 声明存活健康检查（`GET /health`），未将上游失败配置为容器重启条件。
- `requirements.txt`、`requirements.lock` 与 `requirements-dev.txt` 固定运行与测试依赖版本；Docker 使用 `requirements.lock` 安装。
- 仓库提供 `.dockerignore`，构建上下文排除 `.env`、数据库、测试与文档。
- 代码没有 TLS 终止、反向代理、访问控制或备份实现；这些只能由实际部署环境提供，当前仓库无法证明。

## 6. 测试现状

当前测试覆盖：

- `/health`、`/health/ready`、认证与四个统计 API；history `limit` 边界；可选 `STATS_API_TOKEN` 授权；安全响应头。
- Subsonic token/salt 的长度及 `getNowPlaying` 请求参数。
- SQLite 建表、迁移、聚合查询与 summary。
- 播放会话状态机：同曲续播、换曲结算、暂停跳过、缺失 `playerId`、30 秒阈值、陈旧会话与关闭批量结算。
- lifespan 启动/关闭、轮询退避、认证与会话 Cookie、合成恶意元数据 API 返回。
- 隐私：保留预览/清理、按用户导出/导入/删除（`tests/test_privacy_ops.py`、`tests/test_privacy_api.py`）。

当前测试未覆盖：

- 轮询循环与数据库写入的端到端集成（真实 `getNowPlaying` 响应驱动落库）。
- 浏览器自动化与 CDN 失败场景。
- 容器烟雾测试在本地需 Docker 守护进程；CI 通过 `scripts/docker_smoke_test.sh` 执行。

## 7. 文档与代码差异

- README 已与当前实现对齐（2026-07-16）：`>= 30` 秒计入、播放中写入、轮询驱动、Compose 服务名与端口。
- Dashboard 的 Tailwind CDN 仍无法 SRI；完全自托管与浏览器自动化待 NDS-SEC-002 验收。
- 默认匿名访问仍可用；公网暴露需设置 `STATS_API_TOKEN` 或反向代理（见 `docs/security.md`）。

历史差异修正记录见 [`tasks.md`](tasks.md) 中 NDS-DOC-001 完成记录。
