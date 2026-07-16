# 当前实现事实

核验基线：当前工作树中的 `src/`、`tests/`、`Dockerfile`、`docker-compose.yml`、`requirements.txt` 和 `README.md`。本文只描述代码可证明的行为，不代表生产部署已经完成安全配置或人工验收。

## 1. 组件与数据流

| 组件 | 当前职责 | 代码位置 |
| --- | --- | --- |
| FastAPI 应用 | 生命周期、后台轮询、静态页面和统计 API | `src/main.py` |
| 播放会话追踪 | 进程内会话状态机、阈值结算与缺失 ID 过滤 | `src/sessions.py` |
| Navidrome 客户端 | 生成 Subsonic token/salt，调用 `getNowPlaying` | `src/client.py` |
| SQLite 层 | 建表、写入播放会话、执行三类聚合查询 | `src/database.py` |
| Dashboard | 请求统计 API，使用 ECharts 展示图表和表格 | `src/static/index.html` |
| 容器配置 | Python 3.11 镜像、端口、数据库挂载和 `.env` 注入 | `Dockerfile`、`docker-compose.yml` |

运行数据流：

1. FastAPI lifespan 调用 `init_db()`，随后创建 `polling_loop()` 后台任务。
2. `NavidromeClient` 从构造参数或环境变量读取连接信息，每次请求生成六位 salt 和 MD5 token。
3. 轮询循环调用上游 `/rest/getNowPlaying`，由 `PlaybackSessionTracker` 按 `playerId` 追踪会话；缺失 `playerId` 的条目被跳过。
4. 同一播放器继续播放同一 `track_id` 时只更新 `last_seen_at`；换曲、停止后超过 30 秒或应用关闭时尝试结算。
5. 结算以 `last_seen_at - first_seen_at` 计算观测时长。时长大于等于 30 秒才写入一条 `play_history` 记录。
6. Dashboard 初次加载并每 10 秒请求三个统计 API（标签页隐藏时降为 30 秒）；含概览卡片、加载/空/错误状态与深色响应式布局。

## 2. 播放计数语义

- 默认上游轮询间隔是 10 秒，可通过 `POLL_INTERVAL` 改变；环境变量在模块导入时使用 `int()` 解析。
- 播放阈值固定为 30 秒，不可配置，代码判断为 `duration >= 30`。
- 达到 30 秒观测时长时立即写入一条 `play_history` 记录（同一曲目会话不重复写入）；换曲、停止或关闭时仅清理内存会话。
- `isPlaying` 缺失时按正在播放处理；明确为假时该条目被跳过。
- 消失或暂停的播放器只有在距最后一次观测至少 30 秒后结算；换曲会立即结算旧会话。
- 活跃会话由 `PlaybackSessionTracker` 维护，只存在于单个进程内。异常退出会丢失未结算会话；多 worker 或多副本之间不共享状态。
- `NavidromeClient` 在 lifespan 中创建并在关闭时 `close()`；轮询失败时仍继续下一轮，当前没有退避、熔断或持久化重试。

## 3. 持久化与查询

- 默认数据库路径为运行目录下的 `navidrome_stats.db`；`DATABASE_URL` 实际被当作 SQLite 文件路径，不是通用数据库 URL。
- `init_db()` 创建 `play_history` 与 `schema_meta`，并执行版本迁移（当前 schema 版本 1：聚合索引）。
- 每次写入或查询都会打开一个新的 aiosqlite 连接。
- `played_at` 保存结算时 `last_seen_at` 的 ISO 8601 字符串，当前由应用产生时包含 UTC 偏移。
- 播放器和转码统计按已落库记录数聚合，不按监听秒数聚合。
- history 接口按 `username, track_id` 聚合；`title`/`artist`/`album` 取自最新插入行（`MAX(id)`），按最近 `played_at` 排序。
- 表没有唯一约束、外键、索引、保留期清理或重复写入防护。

完整字段和 API 响应见 [`interfaces.md`](interfaces.md)。

## 4. HTTP 与前端

- 应用包含 `/`、`/health` 和三个只读统计路由，未实现应用层认证或授权。
- `/health` 返回 `{"status": "ok"}`，作为存活探针。
- `/health/ready` 返回数据库、轮询任务与上游状态的聚合结果（`ready`/`degraded`/`not_ready`），`not_ready` 时 HTTP 503；指标不含个人数据。
- FastAPI 自动提供默认 OpenAPI 路由（通常为 `/openapi.json`、`/docs` 和 `/redoc`），代码未显式关闭或定制。
- history 的 `limit` 使用 FastAPI 整数解析，但没有最小值、最大值或业务校验。
- Dashboard 的 Tailwind CSS 和 ECharts 从公共 CDN 加载，离线或 CDN 不可达时样式/图表会受影响。
- 页面提供可见的错误横幅、手动刷新按钮和上次更新时间；历史表格用户数据用 `textContent` 渲染。

## 5. 部署与配置

- Docker 镜像基于 `python:3.11-slim`，安装 `build-essential`，以默认容器用户运行。
- Uvicorn 在容器和 `src/main.py` 直接运行路径中绑定 `0.0.0.0:39421`。
- Compose 将宿主机 `39421` 映射到容器同端口，加载 `.env`，并把单个数据库文件挂载到 `/app/navidrome_stats.db`。
- Compose 声明存活健康检查（`GET /health`），未将上游失败配置为容器重启条件。
- `requirements.txt` 未固定版本，也未区分运行依赖和测试依赖。
- 代码没有 TLS 终止、反向代理、访问控制或备份实现；这些只能由实际部署环境提供，当前仓库无法证明。

## 6. 测试现状

当前测试覆盖：

- `/health`、播放器统计路由和转码统计路由的基本响应。
- Subsonic token/salt 的长度及 `getNowPlaying` 请求参数。
- SQLite 建表后保存一条会话记录。
- 播放会话状态机：同曲续播、换曲结算、暂停跳过、缺失 `playerId`、30 秒阈值、陈旧会话与关闭批量结算。

当前测试未覆盖：

- 轮询循环与 lifespan 的集成、上游错误和关闭结算端到端路径。
- history 路由及三类数据库聚合查询的边界行为。
- lifespan 启动失败、后台任务存活和 HTTP 客户端关闭。
- 输入限制、XSS、认证、隐私、并发、多进程和数据库迁移。
- 容器启动验证与 CDN 失败场景。

## 7. 文档与代码差异

- README 已与当前实现对齐（2026-07-16）：`>= 30` 秒计入、播放中写入、轮询驱动、Compose 服务名与端口。
- Dashboard 的 Tailwind/ECharts 仍从公共 CDN 加载；自托管与 CSP 决策待 NDS-SEC-002 人工确认。
- 服务仍无应用层认证；部署边界待 NDS-SEC-001 人工确认。

历史差异修正记录见 [`tasks.md`](tasks.md) 中 NDS-DOC-001 完成记录。
