# 接口登记

本文登记当前代码实际提供或消费的接口。示例只使用非真实占位值；稳定性描述的是仓库维护约束，不表示已经存在版本兼容承诺。

## 1. 稳定性等级

| 等级 | 含义 |
| --- | --- |
| 稳定 | 使用者可依赖；破坏性变更需要迁移方案和明确记录 |
| 受支持但可演进 | 当前公开使用，但字段或约束可能在文档化兼容流程后扩展 |
| 实验性 | 尚无兼容承诺，变更前仍需记录影响 |
| 内部 | 实现细节，不应被外部调用方依赖 |
| 待确认 | 代码或部署信息不足，必须验证后才能承诺 |

## 2. 本服务 HTTP 接口

公开统计路由为 `GET`；认证相关为 `POST`/`GET`。未设置 `STATS_API_TOKEN` 时保持历史匿名访问；设置后统计 API 与 OpenAPI 需 Bearer 令牌（方案名大小写不敏感）或登录会话 Cookie。详见 [`security.md`](security.md)。

| 路径 | 方法 | 响应 | 稳定性 | 当前约束 |
| --- | --- | --- | --- | --- |
| `/` | GET | 存在静态文件时返回 `src/static/index.html`；否则 JSON message | 受支持但可演进 | 页面可加载；数据仍受 API 认证约束 |
| `/health` | GET | `{"status":"ok"}` | 稳定 | 存活探针；始终匿名 |
| `/health/ready` | GET | JSON：`status`、`checks`、`metrics` | 受支持但可演进 | 就绪探针；指标含 collector 总数/健康数/降级数；任一采集器异常不会被其他采集器成功状态掩盖；`not_ready` 时 HTTP 503；始终匿名 |
| `/metrics` | GET | Prometheus 文本格式指标 | 受支持但可演进 | 默认匿名；`STATS_METRICS_AUTH=true` 且已设置 `STATS_API_TOKEN` 时需 Bearer 或会话 Cookie。不含用户名或曲目标签。`navidrome_stat_polling_task_up` 为 1 当且仅当每个 collector 轮询任务都存活（无 collector 时回退到遗留 `polling_task`）。探针请使用 `/health` |
| `/api/auth/status` | GET | `{"auth_required": bool}` | 受支持但可演进 | 报告是否配置了 `STATS_API_TOKEN` |
| `/api/auth/login` | POST | `{"status":"ok"}` + 会话 Cookie | 受支持但可演进 | 请求体 token 长度 1–4096；每进程每来源摘要 5 次/分钟，超限返回 429；未启用认证时 404；`SESSION_COOKIE_SECURE` 控制 Secure 标记 |
| `/api/auth/logout` | POST | `{"status":"ok"}` | 受支持但可演进 | 清除会话 Cookie；删除时使用与登录相同的 path、HttpOnly、SameSite 与 Secure |
| `/api/stats/dashboard` | GET | 一次返回 `summary`、`players`、`transcoding`、`hourly`、`daily`、`heatmap`、`history`、`servers`、`available_servers`、`top_artists`、`top_albums` | 受支持但可演进 | 默认 `days=30`；可选 `timezone`、`metric`、`source_id`；可成对提供 `start_date`/`end_date`（`YYYY-MM-DD`、包含首尾、最长 366 天）覆盖预设窗口；缓存键包含日期范围；`available_servers` 仅含 `id` 与 `display_name` |
| `/api/stats/summary` | GET | JSON：`total_plays`、`total_listen_sec`、`unique_tracks`、`client_count`，以及窗口对比字段 `active_days`、`average_daily_plays`、`average_daily_listen_sec`、`previous_total_plays`、`previous_total_listen_sec`、`plays_change_pct`、`listen_change_pct`、`window_days`（见下） | 受支持但可演进 | 可选 `?days=0`（默认，全部历史）或 `7–90`；对比与日均价仅对有限窗口计算，`days=0` 时 `window_days=null` 且 `previous_*` 与百分比均为 `null`；启用认证时需授权 |
| `/api/stats/players` | GET | JSON 数组，元素为 `client_name`、`count`、`total_listen_sec`、`average_listen_sec`、`transcoded_count`、`transcoding_rate_pct` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；按 `count DESC, client_name ASC` 排序；启用认证时需授权 |
| `/api/stats/transcoding` | GET | JSON 数组，元素为 `is_transcoding`、`count`、`total_listen_sec`、`plays_pct`、`listen_sec_pct` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；百分比按当前窗口计算；启用认证时需授权 |
| `/api/stats/short-plays` | GET | JSON：`short_count`、`counted_count`、`attempt_count`、`short_listen_sec`、`short_play_rate_pct` | 受支持但可演进 | 可选 `days`/`timezone`；短播放记录独立于 `play_history`；这是短播放率，不代表用户主动跳过；启用认证时需授权 |
| `/api/stats/sources` | GET | JSON 数组，元素为 `source`、`count`、`total_listen_sec` | 受支持但可演进 | 正式播放来源为 `poller` 或 `import`；可选 `days`/`timezone`；启用认证时需授权 |
| `/api/stats/servers` | GET | JSON 数组，元素为 `source_id`、`source_name`、`count`、`total_listen_sec` | 受支持但可演进 | 按配置的服务器身份聚合正式播放；可选 `days`/`timezone`/`source_id`；启用认证时需授权 |
| `/api/stats/history` | GET | JSON 数组（见下） | 受支持但可演进 | `limit` 默认 10、范围 1–100；可选 `?days=0`（默认）或 `7–90`；启用认证时需授权 |
| `/api/stats/hourly` | GET | JSON 数组，元素为 `hour`（0–23）、`count` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；按一天内时段聚合；启用认证时需授权 |
| `/api/stats/heatmap` | GET | JSON 数组（168 行），元素为 `weekday`（0=周一 … 6=周日）、`hour`（0–23）、`count`（int） | 受支持但可演进 | 默认 `days=30`；接受 `0`（全部历史）或 `7–90`，中间值（1–6）返回 422；网格始终零填充为 7×24=168 单元；启用认证时需授权 |
| `/api/stats/daily` | GET | JSON 数组，元素为 `date`（`YYYY-MM-DD`）、`count` | 受支持但可演进 | 可选 `?days=` 默认 30；接受 `0`（全部历史）或 `7–90`（有限窗口），中间值（1–6）返回 422；按日聚合，`date` 升序；启用认证时需授权 |
| `/api/stats/top-artists` | GET | JSON 数组，元素为 `artist`、`count`、`total_listen_sec`、`value` | 受支持但可演进 | `limit` 默认 10、范围 1–50；可选 `metric=plays`（默认）或 `metric=listen_time`；`value` 分别表示次数或秒数；同值按名称升序；启用认证时需授权 |
| `/api/stats/top-albums` | GET | JSON 数组，元素为 `album`、`count`、`total_listen_sec`、`value` | 受支持但可演进 | 同 top-artists；启用认证时需授权 |
| `/api/stats/now-playing` | GET | JSON 数组，元素为 `username`、`title`、`artist`、`client_name`、`seconds_elapsed`、`source_name` | 受支持但可演进 | 可选 `source_id`；聚合运行时注册的所有服务器 tracker，仅返回非暂停会话且不访问数据库；不接受 `days`，永远是实时态 |
| `/settings` | GET | 连接、隐私、本地偏好与项目信息设置页 | 受支持但可演进 | 四分区导航；保留策略、按用户导出/导入/删除、连接管理与浏览器本地偏好 |
| `/api/privacy/settings` | GET/PUT | `retention_days`（`null`=永久）、`permanent` | 受支持但可演进 | PUT 接受 `null` 或 1–360 |
| `/api/privacy/storage` | GET | 数据库字节数、总记录数，以及 history/attempt 分表计数 | 受支持但可演进 | 不返回播放明细 |
| `/api/privacy/retention/preview` | GET | 总计和 history/attempt 分表待删条数、估算字节、保留期 | 受支持但可演进 | 可选 `?days=` 预览未保存策略；与实际清理使用相同两张表范围；过期比较为 `datetime(played_at) < datetime(?)`，cutoff 格式与统计窗口相同 |
| `/api/privacy/retention/apply` | POST | 总计和 history/attempt 分表删除条数、保留期 | 受支持但可演进 | 请求体 `{"confirm": true}` 必填 |
| `/api/privacy/users` | GET | 用户名与记录数列表 | 受支持但可演进 | 不含曲目明细 |
| `/api/privacy/users/{username}/export` | GET | JSON 导出包 | 受支持但可演进 | 固定附件名 `navidrome-stat-export.json`；格式版本 2 含正式播放、短播放尝试、来源与时长置信度，不含内部幂等 ID |
| `/api/privacy/users/{username}/import` | POST | `imported`、`attempts_imported`、`merge` | 受支持但可演进 | 兼容格式版本 1/2；请求最大 5 MiB、合计最多 10000 条；校验用户名、字段长度、带时区时间戳、0–7 天时长与转码值。中间件仅在存在 `Content-Length` 时提前 413；缺少该头时完整 body 仍会进入 JSON 解析后再量大小（NDS-CORE-008） |
| `/api/privacy/users/{username}/delete/preview` | GET | `records_to_delete` | 受支持但可演进 | 仅计数 |
| `/api/privacy/users/{username}/delete` | POST | `deleted` | 受支持但可演进 | 请求体 `{"confirm": true}` 必填 |
| `/api/source/config` | GET | `url`、`username`、`password_configured`（bool） | 受支持但可演进 | **永不返回 password**；返回 env > saved 的有效配置脱敏视图；启用认证时需授权 |
| `/api/source/config` | PUT | 同 GET | 受支持但可演进 | 接受 `url`、`username`、可选 `password`；URL 必须为 http/https；`username` 不得为空；`password` 仅在非空时更新；不回显 password；无 `servers` 记录时立即热更新兼容 collector，环境变量仍优先；启用认证时需授权 |
| `/api/source/test` | POST | `{ok: bool, message: str}` | 受支持但可演进 | 接受可选 `url`/`username`/`password`，解析顺序：请求值 > 环境变量 > 已保存 DB；用临时 `NavidromeClient` 调用 `getNowPlaying`，调用后立即 `close()`；仅返回通用成功/失败与简短中文消息，不返回上游响应体、凭据或异常详情；启用认证时需授权 |
| `/api/servers` | GET | 服务器数组，含脱敏配置与 `runtime_status`、`last_poll_ok`、`seconds_since_last_poll` | 受支持但可演进 | password 永不返回；运行状态按服务器隔离 |
| `/api/servers` | POST | `id`、`display_name`、`url`、`username`、`password_configured`、`enabled` 及运行状态 | 受支持但可演进 | 名称/用户名/URL/密码分别限制 255/255/2048/4096 字符；持久化后协调完整期望 collector 集合 |
| `/api/servers/{server_id}` | PUT | 同 POST | 受支持但可演进 | 持久化后立即替换、启用或禁用对应 collector；空 password 保留原值；替换前结算旧会话 |
| `/api/servers/{server_id}` | DELETE | `{"status":"ok"}` | 受支持但可演进 | 删除后立即结算并停止对应 collector；不存在返回 404 |
| `/api/servers/{server_id}/test` | POST | `{ok: bool, message: str}` | 受支持但可演进 | 使用请求体提交的 URL/用户名/密码测试 Subsonic envelope 状态；失败只返回通用文案 |
| `/api/about` | GET | 名称、应用版本、schema 版本、功能列表、许可、`project_url` | 受支持但可演进 | 应用版本来自 `APP_VERSION`，默认 `0.7.0-dev`；`project_url` 为公开仓库 `https://github.com/StepaniaH/navidrome-stat` |

当前 history 调用示例：

```text
GET /api/stats/history?limit=10
GET /api/stats/history?limit=10&days=30
```

每日趋势与全局统计窗口可选 `days` 参数示例（适用于 summary/players/transcoding/hourly/daily/top-artists/top-albums/history，默认值见各行）：

```text
GET /api/stats/daily?days=7
GET /api/stats/daily?days=30     # daily 默认
GET /api/stats/daily?days=90
GET /api/stats/daily?days=0      # 全部历史
GET /api/stats/summary?days=0    # 默认：全部历史
GET /api/stats/players?days=90
```

`days` 取值约定：

- `0` 表示全部历史（不附加时间过滤），仅在 daily 上保留默认 `30` 以兼容现有调用；
- `7–90` 表示有限滚动窗口；
- `1–6`、负数或大于 90 的值返回 422；
- `now-playing` 不接受 `days`。

Dashboard snapshot 自定义日期示例：

```text
GET /api/stats/dashboard?days=30&timezone=Asia/Shanghai&start_date=2026-01-01&end_date=2026-01-31
```

`start_date` 与 `end_date` 必须同时出现，开始日期不得晚于结束日期，包含首尾的跨度不得超过 366 天；违反约束返回 422。提供自定义日期后，`days` 仍用于保持旧请求兼容，但实际统计、日趋势零填充和等长前周期均按自定义范围计算。

除 `now-playing` 仅接受 `source_id` 外，历史统计路由均可选 `source_id`（1–128 字符）。过滤按稳定的服务器 ID 执行；history 的身份键为 `(source_id, username, track_id)`，因此不同服务器的相同 track ID 不合并。省略该参数保持聚合全部服务器的兼容行为。

`timezone` 取值约定（适用于 summary/players/transcoding/hourly/heatmap/daily/top-artists/top-albums/history；`now-playing` 不接受）：

- 可选 `?timezone=IANANAME`，默认 `UTC`；
- 由 `src.database.resolve_timezone` 通过 `zoneinfo.ZoneInfo` 校验；非 IANA 名称返回 422，错误文案固定 `timezone must be a valid IANA timezone name`；
- 时区仅用于 Python 端的 weekday/hour/date 边界与有限窗口的 UTC 截止计算，从不字符串拼接进 SQL；时间戳仍以 UTC ISO 字符串存储；
- Dashboard 选择器仅保留 `browser`（启动时通过 `Intl.DateTimeFormat().resolvedOptions().timeZone` 解析为 IANA 名称并转发）与 `UTC` 两个选项，切换时复用 `fetchStats` 的 in-flight 防护重新拉取所有历史组件。
- Dashboard 与 `/settings` 使用浏览器 `localStorage` 共享 `navidrome-language`（`zh-CN`/`en`）、`navidrome-theme`（`frappe`/`latte`）、`navidrome-timezone`（`browser`/`UTC`）和 `navidrome-motion`（`system`/`reduced`）偏好；这些设置不写入服务端或 SQLite。语言值由共享本地化运行时规范化并在缺少翻译键时回退英语；切换语言和主题即时更新当前页面，统计时区变更重新请求历史统计，`reduced` 关闭两页的非必要动效。设置页“恢复默认值”只删除这四个本地键。

`/api/stats/heatmap` 调用示例：

```text
GET /api/stats/heatmap?days=30
GET /api/stats/heatmap?days=7&timezone=Asia/Shanghai
GET /api/stats/heatmap?days=0&timezone=America/New_York
```

`/api/stats/summary` 返回的对比字段语义：

- `active_days`：当前窗口内出现播放的不同日期数。
- `average_daily_plays` / `average_daily_listen_sec`：有限窗口按 `active_days` 平均；`days=0` 时按最早播放日到最晚播放日的包含天数（`max - min + 1`）平均；无数据时为 `0`。
- `previous_total_plays` / `previous_total_listen_sec`：与当前窗口等长的前一窗口合计；预设 `days` 与自定义日期范围都按所选时区的本地日历日计算（不把当前窗口的 UTC 时长直接前移）；`days=0` 时为 `null`。
- `plays_change_pct` / `listen_change_pct`：`(current - previous) / previous * 100`，`previous` 为 0 或 `days=0` 时为 `null`。
- `window_days`：有限窗口回显请求的 `days`；`days=0` 时为 `null`。

FastAPI 默认还生成 OpenAPI JSON 和交互文档路由（`/openapi.json`、`/docs`、`/redoc`）。未设置 `STATS_API_TOKEN` 时匿名可访问；设置后需认证。`OPENAPI_ENABLED=false` 时这些路由不注册，返回 404。该开关稳定性为「受支持但可演进」。

### 错误行为

- 非整数或超出 1–100 的 `limit`（history）或 1–50 的 `limit`（top-artists/top-albums）由 FastAPI 返回 422 请求验证错误。
- `days` 不是整数、小于 0、大于 90，或位于 1–6 之间（包括 daily）由 FastAPI 路由校验或 `_validate_stats_days` 返回 422 请求验证错误。
- 统计 API 数据库异常返回 503 与固定文案 `Stats temporarily unavailable`，不泄露路径或查询细节。
- 启用认证时未授权访问统计 API 或 OpenAPI 返回 401 与 `Unauthorized`。
- 登录接口有进程内限流；其他接口没有通用速率限制或版本化错误码 schema。

### 安全响应头

所有 HTTP 响应附加 `Content-Security-Policy`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。前端依赖由 `/static/vendor/` 同源提供；CSP 的 `script-src` 与 `style-src` 不允许公共 CDN。

## 3. 上游 Subsonic 接口

`NavidromeClient` 消费以下接口，稳定性为“受支持但可演进”，最终兼容性受目标 Navidrome/Subsonic 服务影响。

```text
GET {NAVIDROME_URL}/rest/getOpenSubsonicExtensions
GET {NAVIDROME_URL}/rest/getNowPlaying
```

请求查询参数：

| 参数 | 当前来源或值 | 敏感性 |
| --- | --- | --- |
| `u` | `NAVIDROME_USER` 或构造参数 `user` | 个人/账户标识 |
| `t` | `md5(password + salt)` 的十六进制字符串 | 凭据派生值，敏感 |
| `s` | 每次生成的六位 ASCII 字母数字 salt | 与 token 一并按敏感请求数据处理 |
| `v` | 固定 `1.16.1` | 非敏感 |
| `c` | 固定 `navidrome-statistic` | 非敏感 |
| `f` | 固定 `json` | 非敏感 |

客户端实际读取的响应字段：

- `subsonic-response.status`
- `subsonic-response.error`
- `subsonic-response.nowPlaying.entry`
- extensions 中的 `name`（检查 `playbackReport`）
- entry 中的 `isPlaying`、`state`、`positionMs`、`playbackRate`、`playerId`、`id`、`username`、`playerName`、`title`、`artist`、`album`、`transcodedContentType`

单个 `entry` 对象会转换为一元素列表；缺失或非对象的 `nowPlaying`（含 JSON `null`）在 `status=ok` 时当作无人播放，不记为轮询失败。缺失 `isPlaying`/`state` 时按正在播放兼容。缺失 `playerId` 的条目跳过。扩展探测失败或未声明 `playbackReport` 时使用轮询时间估算，并把置信度登记为 `estimated`；声明支持时使用位置、状态和速率并登记 `reported`。连接测试同时校验 HTTP 与 `subsonic-response.status == "ok"`。

`httpx.AsyncClient` 使用 `trust_env=False`、10 秒超时与默认 TLS 行为。服务 URL 会移除末尾 `/`；代码没有限制协议，也没有自定义证书、代理或重试配置。应用将 `httpx` 日志级别设为 WARNING，避免 INFO 请求行泄露认证查询参数。

## 4. 环境变量

| 名称 | 必需性 | 默认值 | 读取位置 | 稳定性 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `NAVIDROME_URL` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游基础 URL；env 优先级高于 GUI 保存值；GUI 保存时会明文入库，真实值不得写入仓库 |
| `NAVIDROME_USER` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游账户名，按敏感标识处理 |
| `NAVIDROME_PASS` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游密码，必须由运行环境注入；GUI 也可保存到 `schema_meta` 作为回退（见来源配置章节） |
| `POLL_INTERVAL` | 可选 | `10` | `src/main.py`、`src/config.py` | 受支持但可演进 | 秒数；模块导入时通过 `env_int` 安全解析并钳制到 5–300；非数字或缺失回退到默认 |
| `MAX_POLL_BACKOFF_SEC` | 可选 | `60` | `src/main.py`、`src/config.py` | 受支持但可演进 | 上游连续失败时轮询退避上限（秒）；钳制到 1–3600 |
| `PLAY_THRESHOLD_SEC` | 可选 | `30` | `src/main.py`、`src/sessions.py`、`src/config.py` | 受支持但可演进 | 计入播放的最低**活跃**观测秒数；钳制到 1–3600；非数字/缺失回退默认 |
| `PAUSE_GRACE_SEC` | 可选 | `30` | `src/main.py`、`src/sessions.py`、`src/config.py` | 受支持但可演进 | 暂停或缺失条目保持内存会话的宽限秒数；钳制到 0–3600；`0` 表示一遇 `isPlaying=false` 或缺失即按原行为结算 |
| `CHECKPOINT_INTERVAL_SEC` | 可选 | `60` | `src/main.py`、`src/sessions.py`、`src/config.py` | 受支持但可演进 | 已达到阈值的活跃会话刷新幂等检查点的间隔；钳制到 10–3600 秒 |
| `DATABASE_URL` | 可选 | `navidrome_stats.db` | `src/database.py` | 受支持但可演进 | 当前语义是 SQLite 文件路径，不是 URL |
| `STATS_API_TOKEN` | 可选 | 无（匿名访问） | `src/auth.py` | 受支持但可演进 | 设置后保护统计 API 与 OpenAPI；`/health` 与默认的 `/metrics` 仍公开；值不得入库 |
| `STATS_METRICS_AUTH` | 可选 | `false` | `src/main.py`、`src/config.py` | 受支持但可演进 | 真值为 `1/true/yes/on` 时，若同时设置了 `STATS_API_TOKEN`，`/metrics` 需要与统计 API 相同的认证；未设置令牌时该开关无效 |
| `OPENAPI_ENABLED` | 可选 | `true` | `src/main.py`、`src/config.py` | 受支持但可演进 | 假值（非 `1/true/yes/on`）时不注册 `/docs`、`/redoc`、`/openapi.json` |
| `SESSION_COOKIE_SECURE` | 可选 | `false` | `src/auth.py` | 受支持但可演进 | 真值为 `1/true/yes/on` 时登录 Cookie 增加 Secure；应只在 HTTPS 访问路径启用 |
| `SAVE_RETRY_ATTEMPTS` | 可选 | `3` | `src/main.py`、`src/config.py` | 受支持但可演进 | 数据库会话保存尝试次数；钳制到 1–10，最终失败会话仍保持可重试 |
| `RETENTION_MAINTENANCE_SEC` | 可选 | `86400` | `src/main.py` | 内部 | 后台保留期清理间隔（秒）；钳制到 60–604800 |
| `APP_VERSION` | 可选 | `0.7.0-dev` | `src/version.py` | 受支持但可演进 | `/api/about` 与镜像发布注入的应用版本 |

本地开发通过 `python-dotenv` 在导入 `src/client.py` 时加载 `.env`。构造 `NavidromeClient` 时传入的非空参数优先于环境变量。

## 5. SQLite schema

数据库接口为“内部”。`schema_meta` 表记录 `schema_version`（当前 **7**）及 `retention_days`（`permanent` 或 1–360）；`init_db()` 在启动时向前迁移、创建索引，并把遗留的未完成 poller 检查点按最后一次持久化时长标记为恢复完成。连接统一使用 5 秒 busy timeout、外键检查和 `synchronous=NORMAL`，初始化时选择 WAL。兼容来源配置仍复用 `schema_meta`，多服务器配置存储于 `servers` 表。

表：`schema_meta`

| 键 | 说明 |
| --- | --- |
| `schema_version` | 当前为 `7` |
| `retention_days` | `permanent`（默认）或 `1`–`360` 的字符串 |
| `source_url` | GUI 保存的 Navidrome URL，作为 `NAVIDROME_URL` 缺失时的回退（内部，部署敏感信息） |
| `source_user` | GUI 保存的 Navidrome 用户名，作为 `NAVIDROME_USER` 缺失时的回退（内部，账户标识） |
| `source_password` | GUI 保存的 Navidrome 密码明文，作为 `NAVIDROME_PASS` 缺失时的回退（内部，高敏感凭据；不得出现在 API 响应或日志中） |

表：`play_history`

| 列 | SQLite 声明 | 写入来源 | 数据分类 |
| --- | --- | --- | --- |
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | SQLite | 内部标识 |
| `played_at` | `TEXT` | 会话最后观测时间的 ISO 字符串 | 行为时间数据 |
| `username` | `TEXT` | 上游 `username` | 账户标识/个人数据 |
| `client_name` | `TEXT` | 上游 `playerName` | 设备或客户端行为数据 |
| `track_id` | `TEXT` | 上游 `id` | 媒体标识/行为数据 |
| `title` | `TEXT` | 上游 `title` | 媒体与行为数据 |
| `artist` | `TEXT` | 上游 `artist` | 媒体与行为数据 |
| `album` | `TEXT` | 上游 `album` | 媒体与行为数据 |
| `is_transcoding` | `INTEGER` | 是否存在 `transcodedContentType` | 使用行为数据 |
| `listen_duration_sec` | `INTEGER` | 活跃观测时长向下取整（排除暂停与缺失后的挂钟时间） | 使用行为数据 |
| `session_id` | `TEXT` | poller 随机会话幂等 ID；导入/旧记录为空 | 内部标识 |
| `duration_confidence` | `TEXT` | `reported` 或 `estimated` | 数据质量元数据 |
| `finalized` / `finalized_at` | `INTEGER` / `TEXT` | 检查点是否完成及完成时间 | 内部状态/行为时间 |
| `checkpointed_at` | `TEXT` | 最近一次持久化检查点对应的活跃观测时间；启动恢复使用 | 内部状态/行为时间 |

`play_attempts` 保存未达到播放阈值的短播放尝试，字段与 `play_history` 的媒体元数据相同，并额外包含 `duration_sec`、`outcome`、`attempt_id` 与 `duration_confidence`。它用于短播放率分析，不计入正式播放次数。`play_history.source` 为 `poller` 或 `import`。

版本 6 对非空 poller `session_id` 与 `attempt_id` 建立部分唯一索引，并增加 `(source_id, username, track_id)` 查询索引；旧记录和导入记录允许空 ID，因此不被自动去重。版本 7 增加 `checkpointed_at`；启动恢复只更新同一行的 `finalized`/`finalized_at`，不会增加播放次数或推测中断后的时长。

## 6. 内部 Python 接口

以下函数被仓库模块或测试直接调用，登记为“内部”：

- `src.client.generate_auth(password)`
- `src.client.NavidromeClient(...)`、`get_auth_params()`、`get_open_subsonic_extensions()`、`supports_playback_report()`、`get_now_playing()`、`close()`
- `src.database.init_db(db_path=...)`
- `src.database.save_play_session(session, db_path=...)`、`save_play_attempt(attempt, db_path=...)`
- `src.database.get_player_stats(days=0, db_path=...)`（`days<=0` 表示全部历史）
- `src.database.get_transcoding_stats(days=0, db_path=...)`
- `src.database.get_hourly_stats(days=0, db_path=...)`
- `src.database.get_daily_stats(days=30, db_path=...)`（`days<=0` 表示全部历史）
- `src.database.get_summary(days=0, db_path=...)`（返回窗口对比字段，见上文 API 登记）
- `src.database.get_top_artists(limit=..., days=0, db_path=...)`
- `src.database.get_top_albums(limit=..., days=0, db_path=...)`
- `src.database.get_playback_history(limit=..., days=0, db_path=...)`
- `src.database.get_short_play_stats(...)`、`get_source_stats(...)`、`get_server_stats(...)`
- `src.database.get_weekday_hour_stats(days=30, timezone_name="UTC", db_path=...)`（返回 168 个零填充 `{weekday,hour,count}` 行）
- `src.database.get_time_bucket_stats(days=30, timezone_name="UTC", db_path=...)`（一次扫描返回 hourly/daily/heatmap）
- `src.database.recover_incomplete_sessions(db_path=...)`（将遗留未完成检查点按最后持久化时长标记完成）
- `src.database.resolve_timezone(timezone_name)`（通过 `zoneinfo.ZoneInfo` 校验 IANA 名称；无效则 `ValueError`）
- `src.sessions.PlaybackSessionTracker(...)`、`set_playback_report_supported(...)`、`process_poll(...)`、`finalize_session(...)`、`finalize_all()`（构造参数含 `play_threshold_sec`、`pause_grace_sec`、`stale_threshold_sec`、`checkpoint_interval_sec`、`supports_playback_report`；批量结算尽力处理全部会话后汇总失败）
- `src.config.parse_clamped_int(...)`、`env_int(...)`、`env_flag(...)`
- `src.main.finalize_session(player_id)`、`polling_loop(client)`
- `src.source_config.get_saved_source_config(...)`、`set_saved_source_config(...)`、`resolve_source_config(...)`、`resolve_effective_source_config(...)`、`validate_source_url(...)`、`has_full_config(...)`、`redacted_view(...)`

## 6.1 来源配置解析顺序

`src.source_config.resolve_source_config(overrides, saved)` 按字段独立解析，优先级（高 → 低）：

1. 请求提交的非空覆盖值（用于 `POST /api/source/test` 测试给定值）；
2. 环境变量 `NAVIDROME_URL` / `NAVIDROME_USER` / `NAVIDROME_PASS`；
3. 已保存 DB `schema_meta` 中的 `source_url` / `source_user` / `source_password`。

无 `servers` 记录时，lifespan 在构造兼容 collector 前调用 `resolve_effective_source_config()`（仅 env > saved），若三者不齐全则不启动该 collector。兼容来源 PUT 仅在无多服务器记录时立即热更新，并继续遵循环境变量优先级。`servers` 表的创建、更新、启停与删除由 `CollectorManager` 立即应用；每个服务器独立拥有 client/tracker/task。替换/协调时旧会话 finalize 失败只记录脱敏错误，仍会启动新 collector；`stop`/`stop_all` 仍在清理后汇总抛出。构造或激活失败才返回 503 固定文案 `Saved configuration could not be applied`，不包含配置或上游正文；已持久化配置在后续成功更新或进程启动时重试。`/api/source/test` 构造的临时客户端调用 `get_now_playing()` 后于 `finally` 中 `close()`。

## 7. 变更流程

1. 在 [`tasks.md`](tasks.md) 创建或领取接口变更任务，列出消费者和敏感数据影响。
2. 对公开 HTTP 或环境变量接口给出兼容策略；对数据库给出迁移、备份和回滚步骤。
3. 实现代码和自动化测试，同一变更更新本文与 [`current-state.md`](current-state.md)。
4. 若数据类别、日志或暴露范围变化，同步更新 [`privacy.md`](privacy.md) 并完成所需人工确认。
5. 运行任务验证命令、全量测试、链接检查和 `git diff --check`，记录实际结果后才能标记完成。

近期兼容结论：

- 2026-08-21（NDS-OSS-001）：`GET /api/about` 的 `project_url` 从 `null` 改为公开仓库 URL。把 `null` 当作缺失的旧客户端仍可工作；这是字段填充，不是删除。无 schema 变更。
- 2026-08-21（NDS-SEC-003）：新增 `STATS_METRICS_AUTH`（默认 `false`）与 `OPENAPI_ENABLED`（默认 `true`）。未设置时行为与此前一致：匿名 `/metrics`、OpenAPI 路由存在（启用令牌时 OpenAPI 仍需认证）。无数据库迁移。
- 2026-08-21（NDS-CORE-006）：非 ASCII 的 Bearer/Cookie 由可能 500 改为 401；`Authorization` 方案名大小写不敏感；登出 Cookie 带上与登录相同的 Secure/HttpOnly。`getNowPlaying` 在 `status=ok` 且 `nowPlaying` 为 null 时记空闲成功。无 schema 变更。
- 2026-08-21（NDS-CORE-007）：预设 `days` 的上一窗口改为本地日历日（DST 下不再按当前窗口 UTC 时长前移）。保留清理改为 `datetime(played_at)` 比较。上游 `status=ok` 后落库失败不再增加 poll failure 或退避。`navidrome_stat_polling_task_up` 与就绪探针一样要求全部 collector 任务存活。服务器替换在旧会话 finalize 失败后仍启动新采集器，不再仅因此返回 503。无 schema 变更。导入 5 MiB 提前拒绝仍依赖 `Content-Length`，流式上限见 NDS-CORE-008。
