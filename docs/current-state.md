# 当前实现事实

核验基线：2026-08-21，工作树 `src/`、`tests/`、`Dockerfile`、`docker-compose.yml`、`requirements.txt`、CI 工作流、公开 git 标签，以及双语 README。本文只描述代码可证明的行为，不代表生产部署已经完成安全配置或人工验收。开源阶段规划见 [`roadmap.md`](roadmap.md)，不在本文展开目标状态。

## 1. 组件与数据流

| 组件 | 当前职责 | 代码位置 |
| --- | --- | --- |
| FastAPI 应用 | 生命周期、后台轮询、静态页面和统计 API | `src/main.py` |
| 播放会话追踪 | 进程内会话状态机、阈值结算与缺失 ID 过滤 | `src/sessions.py` |
| Navidrome 客户端 | 生成 Subsonic token/salt，探测 OpenSubsonic 扩展，调用 `getNowPlaying` | `src/client.py` |
| SQLite 层 | 建表、写入播放会话、聚合查询与隐私数据操作 | `src/database.py`、`src/privacy_ops.py` |
| Dashboard | 请求统计 API，使用 ECharts 展示图表和表格 | `src/static/index.html` |
| Dashboard 缓存 | 进程内短 TTL snapshot 缓存与写入失效 | `src/dashboard_cache.py` |
| 采集器协调 | 多服务器 collector 构造、替换、清理与失败汇总 | `src/collector_manager.py` |
| 导入体积上限 | 隐私导入按实际已读字节拒绝超限请求体 | `src/request_limits.py` |
| SQLite 连接策略 | WAL、busy timeout 与外键连接初始化 | `src/sqlite.py` |
| 设置页 | 连接、保留策略、按用户数据操作与本地偏好 | `src/static/settings.html`、`src/static/settings.js`、`src/static/localization.js` |
| 来源配置层 | GUI 保存的 Navidrome 连接配置持久化与解析（env 优先） | `src/source_config.py` |
| 容器配置 | Python 3.11 镜像、端口、数据库挂载和 `.env` 注入 | `Dockerfile`、`docker-compose.yml` |

运行数据流：

1. FastAPI lifespan 调用 `init_db()`，再由 `CollectorManager` 为启用且配置完整的服务器创建 client、tracker 与轮询任务。
2. 无多服务器记录时，lifespan 调用 `resolve_effective_source_config()`（环境变量 > 已保存 DB 值）解析兼容来源；多服务器记录由 `servers` 表提供。`NavidromeClient` 每次请求生成六位 salt 和 MD5 token。
3. `CollectorManager` 对完整的期望服务器配置做协调，并按服务器 ID 独立管理 `NavidromeClient`、`PlaybackSessionTracker`、task 与轮询健康状态。首次创建多服务器配置会移除 legacy collector，删除最后一项时可恢复完整的 legacy 配置；未变化的 collector 不重启。轮询先探测 `/rest/getOpenSubsonicExtensions`，上游声明 `playbackReport` 时使用 `state`、`positionMs`、`playbackRate`，否则保持 `getNowPlaying` 轮询兼容。`status=ok` 且 `nowPlaying` 缺失或为 JSON `null` 时按无人播放处理，不记为轮询失败。上游 `status=ok` 后会话落库失败只增加 save 计数，仍记 poll success，不触发轮询退避。
4. 同一播放器继续播放同一 `track_id` 时累加 `active_duration_sec`（每次活跃观测累加距上一次活跃观测的时间），更新 `last_active_at` 与 `last_seen_at`；暂停或缺失的轮询不累加时长也不更新 `last_active_at`；换曲立即结算旧会话。
5. 每个 poller 会话有随机 `session_id`。达到 `PLAY_THRESHOLD_SEC` 时以该 ID 创建幂等检查点，之后按 `CHECKPOINT_INTERVAL_SEC` 刷新，结束时更新同一行的最终活跃时长并标记 `finalized`，因此不会重复增加播放次数。启动时把遗留的未完成检查点按最后一次持久化时长标记为恢复完成，不推测中断后的时长。数据库临时失败不会把会话静默标成已保存；最多按 `SAVE_RETRY_ATTEMPTS` 重试，仍失败则保留内存状态供后续观测或关闭结算重试。时长同时登记 `reported` 或 `estimated` 置信度。
6. Dashboard 历史数据通过 `/api/stats/dashboard` 一次获取，进程内缓存 60 秒、最多 64 个键，播放与隐私写入后失效。缓存按 key 合并并发构建，不同 key 不因全局锁互相阻塞，失效期间完成的旧构建不会回填。页面可见时历史每 60 秒刷新、正在播放每 10 秒刷新；隐藏时暂停实时刷新并把历史间隔延长至 300 秒。预设/自定义日期、时区、排行指标和服务器筛选共同构成 snapshot 键。桌面顶部为无外层卡片的单行应用栏，标题、时间、服务器、状态、更新时间与操作同一基线；760px 以下才把筛选分组到第二行。自定义 listbox 保留键盘与可访问性语义；服务器选择器只接收 `id` 与 `display_name`，不会下发连接地址或凭据。最近播放在桌面使用固定比例六列表格且不产生横向滚动，640px 以下将同一六字段记录改排为纵向信息块；页脚左右展示产品名与公开 GitHub/MIT 链接。Tailwind CSS 与 ECharts 固定版本并由 `/static/vendor/` 同源提供。

## 2. 播放计数语义

- 默认上游轮询间隔是 10 秒，可通过 `POLL_INTERVAL` 改变；环境变量在模块导入时通过 `src.config.env_int` 安全解析并钳制到 5–300，非数字或缺失回退到默认。
- 播放阈值可通过 `PLAY_THRESHOLD_SEC` 配置（默认 30，钳制 1–3600）；代码判断为 `duration >= play_threshold_sec`。有效值通过 `PlaybackSessionTracker` 构造参数注入。
- 暂停/缺失宽限期可通过 `PAUSE_GRACE_SEC` 配置（默认 30，钳制 0–3600）。
- 检查点刷新间隔可通过 `CHECKPOINT_INTERVAL_SEC` 配置（默认 60，钳制 10–3600）。
- 达到阈值活跃观测时长时立即写入一条可更新的 `play_history` 检查点；持续播放时周期刷新，结束时同一 `session_id` 更新为最终活跃时长，重复保存不增加行数。
- 上游连续失败时轮询间隔指数退避，上限由 `MAX_POLL_BACKOFF_SEC` 控制（默认 60 秒，钳制 1–3600）。
- `isPlaying` 缺失时按正在播放处理；明确为假且与内存会话同曲时进入暂停状态，否则该条目被跳过。
- 消失或暂停的播放器在距最后一次**活跃**观测超过 `PAUSE_GRACE_SEC` 后清理；超期未结算会话 finalize 一次，已结算会话直接移除不重复写入。超期前会话保留在内存中（无论是否已结算）。
- 切换为不同的活跃曲目会立即结算旧会话。
- `listen_duration_sec` 为活跃观测时长（向下取整），不含暂停后的挂钟时间。
- 活跃会话由 `PlaybackSessionTracker` 维护，只存在于单个进程内。已达到阈值的会话有数据库检查点；未达到阈值的内存会话在异常退出时仍可能丢失。多 worker 或多副本之间不共享状态。
- `NavidromeClient` 由 `CollectorManager` 创建；配置替换、禁用、删除或 lifespan 关闭时执行 `close()`。`replace`/`reconcile` 在旧会话 finalize 失败后仍启动替换采集器，只记录脱敏错误；`stop`/`stop_all` 会继续清理其余 collector，完成后再汇总抛出脱敏错误。上游轮询失败时指数退避后继续下一轮，上限由 `MAX_POLL_BACKOFF_SEC` 控制；落库失败不走该退避。

## 3. 持久化与查询

- 默认数据库路径为运行目录下的 `navidrome_stats.db`；`DATABASE_URL` 实际被当作 SQLite 文件路径，不是通用数据库 URL。
- `init_db()` 创建基础表并执行版本迁移（当前 schema 版本 7）；版本 2 引入默认 `retention_days=permanent`，版本 3–4 引入短播放与来源字段，版本 5 引入多服务器配置及服务器来源字段，版本 6 引入会话/尝试幂等键、时长置信度、最终状态和跨来源查询索引，版本 7 增加检查点更新时间与启动恢复。
- 每次写入或查询仍打开独立 aiosqlite 连接，但统一启用 5 秒 busy timeout、外键检查与 `synchronous=NORMAL`；初始化时选择 WAL。该策略只面向单机 SQLite，不支持共享网络文件系统或多副本。
- `played_at` 保存结算时 `last_seen_at` 的 ISO 8601 字符串，当前由应用产生时包含 UTC 偏移。
- 播放器和转码统计按已落库记录数聚合，不按监听秒数聚合。
- 历史窗口由 `_window_predicate(...)`/`_previous_window_predicate(...)` 输出参数化 SQL 谓词；`days<=0` 表示全部历史，有限预设按所选时区的本地自然日计算，上一窗口也是紧挨着的等长本地日历日（跨 DST 不按当前窗口 UTC 时长前移）。Dashboard snapshot 还支持成对的 `start_date`/`end_date`，以包含首尾日期的本地日期闭区间查询，前周期为前一个等长日期段，最大 366 天；日期和时区从不字符串拼接进 SQL。
- `get_daily_stats(days=30)`（API `GET /api/stats/daily?days=`，默认 30，接受 `0` 或 `7–90`）按日聚合，`days=0` 不附加日期过滤。
- `get_summary(days=0)` 返回 `/api/stats/summary` 的窗口对比字段（`active_days`、`average_daily_*`、`previous_total_*`、`*_change_pct`、`window_days`）；有限窗口按 `active_days` 平均，`days=0` 按最早至最晚播放日的包含天数平均。
- `get_player_stats()` 返回每个客户端的播放次数、总/平均收听秒数、转码次数与转码率；`get_transcoding_stats()` 同时返回播放占比与收听时长占比。
- `get_top_artists()` / `get_top_albums()` 支持 `metric=plays|listen_time`，返回 `value` 作为当前排序值，并保留 `count` 与 `total_listen_sec`；结果按值降序、名称升序确定性排序。
- schema 版本 3–4 新增 `play_attempts` 表记录未达到播放阈值的短播放尝试，并为正式播放增加 `source` 溯源字段；版本 5 另含 `servers` 表及 `source_id`/`source_name`。`get_short_play_stats()` 与 `/api/stats/short-plays` 返回短播放率，`get_source_stats()` 与 `/api/stats/sources` 返回 `poller`/`import` 来源分布。短播放率不等同于跳过率，因为轮询无法证明用户是否主动跳过；Navidrome 原生历史尚未绑定未确认的私有读取接口。
- Dashboard snapshot 的 hourly/daily/heatmap 通过 `get_time_bucket_stats()` 一次读取和解析时间戳；10 万条合成记录基准为独立三次查询约 296.8 ms、合并查询约 54.6 ms（本机单次测量，仅作回归参考）。
- `get_weekday_hour_stats(days=30, timezone_name="UTC")` 返回 7×24=168 个 `{weekday,hour,count}` 行，始终零填充；weekday 遵循 Python `date.weekday()`（0=周一 … 6=周日），hour 与 weekday 按 `zoneinfo.ZoneInfo(timezone_name)` 转换后的本地时间取；无效时区抛 `ValueError`，从不字符串拼接进 SQL。
- 所有聚合查询（summary/players/transcoding/hourly/heatmap/daily/top-artists/top-albums/history）都接受可选 `timezone_name` 参数（默认 `UTC`），仅用于 Python 端 bucket 边界与有限窗口的 UTC 截止计算；时间戳仍以 UTC ISO 字符串存储。
- history 接口按 `source_id, username, track_id` 聚合；跨服务器相同 track ID 不合并。`title`/`artist`/`album` 取自最新插入行（`MAX(id)`），按最近 `played_at` 排序。
- 播放历史**默认永久保留**；可通过 `/settings` 将保留期设为 1–360 天或恢复永久。
- 后台任务按 `RETENTION_MAINTENANCE_SEC`（默认 24 小时）自动清理超出保留期的记录；启动时也会执行一次。预览与删除用 `datetime(played_at) < datetime(?)` 比较，cutoff 格式与统计窗口相同，避免带偏移的 ISO 字符串按字典序漏删。
- 按用户导出格式版本 2 同时包含正式播放与短播放尝试，并保留来源与置信度；导入兼容版本 1/2，限制 5 MiB、10000 条，校验字段长度、带时区时间戳、转码值和 0–7 天时长。导入请求由 ASGI 中间件按实际已读字节累计，超过 5 MiB 返回 413 且不进入 JSON 解析；JSON 层仍保留二次长度检查。删除与过期清理的预览及执行统一覆盖两张表。
- poller `session_id` 与 `attempt_id` 使用部分唯一索引提供幂等写入；导入/旧记录没有这些 ID，仍保留追加语义。

完整字段和 API 响应见 [`interfaces.md`](interfaces.md)。

## 4. HTTP 与前端

- 应用包含 `/`、`/settings`、存活/就绪/指标、认证、统计、隐私、兼容来源、多服务器与 about API。可选 `STATS_API_TOKEN` 保护业务 API。
- `/health` 与 `/health/ready` 始终公开。`/metrics` 默认公开；设置 `STATS_METRICS_AUTH=true` 且配置了 `STATS_API_TOKEN` 时需认证。`navidrome_stat_polling_task_up` 在存在 collector 时要求全部轮询任务存活，与就绪探针一致。启用令牌后 `/docs`、`/redoc`、`/openapi.json` 与 `/api/*`（登录/状态除外）需要认证。`OPENAPI_ENABLED=false` 时 OpenAPI 路由不存在。
- `GET /api/stats/servers` 按配置的服务器身份聚合正式播放次数与收听秒数；Dashboard snapshot 的 `servers` 字段使用同一数据。`available_servers` 仅含 `id` 与 `display_name`。
- `GET /api/about` 返回名称、`APP_VERSION`（缺省 `0.7.0-dev`）、schema 版本、功能列表、MIT 与公开 `project_url`（GitHub 仓库地址）。
- `POST /api/auth/login` 在启用认证时设置 httpOnly、SameSite=Lax 会话 Cookie；`SESSION_COOKIE_SECURE=true` 时增加 Secure。`POST /api/auth/logout` 删除 Cookie 时使用同一组属性。Bearer 方案名大小写不敏感。非 ASCII 凭据返回 401，不会因 `compare_digest` 抛错变成 500。登录有每进程每来源摘要 5 次/分钟限制，摘要使用进程随机盐且不保存原始客户端地址。
- 响应附加 CSP、`nosniff`、`DENY` 框架与 `no-referrer` 策略。
- FastAPI 在 `OPENAPI_ENABLED` 为真（默认）时提供 `/openapi.json`、`/docs` 和 `/redoc`；为假时不注册这些路由。
- history 的 `limit` 使用 FastAPI `Query` 校验，范围 1–100，默认 10。统计窗口 `days` 使用 FastAPI `Query` 校验（`ge=0, le=90`）并由 `_validate_stats_days` 进一步拒绝 `1–6`；`0` 表示全部历史。`daily` 默认 `30`，其他历史端点默认 `0`（全部历史）以保留既有调用方行为；`now-playing` 不接受 `days`。所有历史端点还接受可选 `timezone` 查询参数（IANA 名称，默认 `UTC`），经 `_validate_stats_timezone` 与 `zoneinfo.ZoneInfo` 校验，非法值返回 422；`now-playing` 不接受 `timezone`。`/api/stats/heatmap` 默认 `days=30`，返回 168 行零填充网格。
- Dashboard 的 Tailwind CSS 和 ECharts 固定版本并同源加载；CSP 的脚本与样式来源仅为 `'self'`（保留既有内联脚本/样式许可）。
- 页面提供可见的错误横幅、手动刷新按钮和上次更新时间；历史表格与客户端图例的用户数据用 `textContent` 渲染。客户端饼图的 ECharts HTML tooltip 对 `client_name` 做实体转义。
- 设置页（`/settings`）按「连接、隐私、偏好、关于」提供四个顶级分区；桌面使用带分组标签的左侧导航，760px 以下改排为四列顶部导航。每个分区只有一个主表面，内部用分隔行组织状态、配置与危险操作，不再使用多层卡片。设置页不存在原生 `<select>`：语言、主题、时区和动态用户选择均使用同一个可键盘操作的 listbox 控制器，支持方向键、Home/End、Escape、外部点击与 ARIA 选中态。连接分区包含多服务器 CRUD、Navidrome URL/用户名/密码表单、保存和测试连接；变更保存后立即应用。隐私策略以 `loading/ready/error` 动态状态独立渲染，不带静态翻译键，因此成功加载或切换语言后不会被覆盖回“加载中…”，失败时显示可重试状态。偏好合并原常规与外观，提供语言、Catppuccin Frappe/Latte、浏览器/UTC 时区、减少动态效果与恢复默认值；这些偏好只在浏览器 `localStorage` 中。密码输入为 `type=password`，GET 仅返回 `password_configured: bool`，从不渲染密码。
- Dashboard 与设置页共同加载 `src/static/localization.js`：语言值先按支持列表规范化，缺失键回退英语，动态值使用具名占位插值，`data-i18n` 只用于静态文案。两页的动态操作、状态、数值单位和错误文案均通过翻译键生成，不保留中英文文字二选一函数；新增语言时只需补齐该语言消息表。`navidrome-motion=reduced` 同时关闭两页的脉冲、骨架和过渡动画。

## 5. 部署与配置

- Docker 镜像采用多阶段构建：builder 阶段基于 `python:3.11-slim` 安装 `build-essential` 并在 `/opt/venv` 中安装 `requirements.lock`；runner 阶段同样基于 `python:3.11-slim`，仅复制 `/opt/venv`，不保留 `build-essential`，并以非 root 用户 `appuser`（UID 1000）运行；镜像预建由该用户拥有的 `/data` 持久化目录。
- Uvicorn 在容器和 `src/main.py` 直接运行路径中绑定 `0.0.0.0:39421`。
- 仓库 [`docker-compose.yml`](../docker-compose.yml) 将宿主机 `39421` 映射到容器同端口，以命名卷挂载 `/data`，容器内数据库路径默认为 `/data/navidrome_stats.db`。Compose 会读取项目目录 `.env` 做**文件内变量替换**，并且把 `environment:` 中列出的键注入容器（含 `SESSION_COOKIE_SECURE`、`STATS_METRICS_AUTH`、`OPENAPI_ENABLED`）。未列出的变量不会自动注入。
- Compose 声明存活健康检查（`GET /health`），未将上游失败配置为容器重启条件。
- `requirements.txt`、`requirements.lock` 与 `requirements-dev.txt` 固定运行与测试依赖版本；Docker 使用 `requirements.lock` 安装。
- 仓库提供 `.dockerignore`，构建上下文排除 `.env`、数据库、测试与文档。
- 代码提供可选 `STATS_API_TOKEN` 访问控制，但没有 TLS 终止、反向代理或备份自动化；这些部署边界仍需由实际环境提供，当前仓库无法证明。
- 支持的运行时是 Python 3.11（Dockerfile 与 CI）。仓库可在其他 3.x 上启动，但不构成已验证矩阵。
- 公开 git 标签有 `v0.5.0`–`v0.7.0`；`v0.5.0` 与 `v0.5.3` 指向同一提交。`v0.7.0` 之后 `main` 仍有未打标签的 Dashboard 变更，因此缺省 `APP_VERSION` 为 `0.7.0-dev`。tag `v*` 会推送 Docker Hub 多架构镜像并尝试创建 GitHub Release。

## 6. 测试现状

当前测试覆盖：

- `/health`、逐采集器 readiness、认证、统计 snapshot、来源筛选、隐私与服务器 API；history `limit` 边界；可选授权、安全响应头、登录限流和 Secure Cookie。
- Subsonic token/salt 的长度及 `getNowPlaying` 请求参数。
- SQLite 建表、迁移、聚合查询与 summary。
- 播放会话状态机：同曲续播、换曲结算、暂停进入宽限、缺失 `playerId`、配置阈值与宽限期、暂停恢复续接、缺失恢复续接、宽限超期结算、周期检查点、异常恢复和批量结算失败隔离 (`tests/test_sessions.py`)。配置安全解析与钳制由 `tests/test_config.py` 覆盖。
- lifespan 启动/关闭、轮询退避、认证与会话 Cookie、合成恶意元数据 API 返回。
- OpenSubsonic 能力声明、轮询、tracker 和 SQLite 检查点的合成集成路径；Dashboard cache 的同 key single-flight、跨 key 并发与失效竞态。
- 隐私：保留预览/清理、按用户导出/导入/删除（`tests/test_privacy_ops.py`、`tests/test_privacy_api.py`）。
- 时区与热力图：`get_weekday_hour_stats` 在空库 / UTC 边界 / Asia/Shanghai 与 America/New_York 跨边界 / 有限窗口过滤下返回正确的 168 个零填充单元；`/api/stats/heatmap` 的 `days`/`timezone` 传播、422 边界、503 与认证保护由 `tests/test_heatmap.py` 覆盖；`get_daily_stats` 在非 UTC 时区跨午夜零填充由同一文件覆盖。前端时区选择器、 时区查询传播、热力图卡片/init/render/fetch/resize 与 `setLoading` 由 `tests/test_static_dashboard.py` 源码级断言覆盖。

当前测试边界：

- 轮询到数据库集成使用合成 `getNowPlaying` 响应，不连接真实 Navidrome。
- 浏览器回归只使用合成或空数据，覆盖 Dashboard 恶意元数据安全渲染、服务器过滤和移动布局，以及设置页隐私策略成功/失败收敛、自定义 listbox 键盘操作、语言切换、偏好持久化/重置和 390px 无横向溢出；CI 独立 browser job 构建本地资产并运行同一测试。
- 容器烟雾测试在本地需 Docker 守护进程；CI 通过 `scripts/docker_smoke_test.sh` 执行。
- Python CI 执行 Ruff 与分支覆盖率，门槛 80%；依赖更新由 Dependabot 登记。覆盖率以 CI 或本地 `pytest --cov` 当次输出为准，不在本文固化过期百分数。

## 7. 文档与代码差异

- README 计数语义（`>= PLAY_THRESHOLD_SEC`）、播放中检查点、轮询驱动、Compose 服务名与端口已与代码对齐。
- 前端公共 CDN 已移除并有合成浏览器回归；真实部署的 TLS、授权和网络暴露仍需部署方验收。
- 默认匿名访问仍可用；公网暴露需设置 `STATS_API_TOKEN` 或反向代理（见 `docs/security.md`）。
- 2026-08-21 已补登 `GET /api/stats/servers`。`/metrics` 默认仍匿名，可用 `STATS_METRICS_AUTH` 在已配置令牌时改为需认证。`project_url` 现返回公开 GitHub 仓库地址。
- NDS-SRC-001 完成记录中的「热更新未实现」已被 NDS-REL-002 取代；NDS-DEP-001 中「非 root 未做」已被 Dockerfile `appuser` 取代。仍待验收的是部署方确认项，不是这些代码缺口。

已完成任务全文见 [`tasks-completed.md`](tasks-completed.md)。后续开源阶段见 [`roadmap.md`](roadmap.md)。
