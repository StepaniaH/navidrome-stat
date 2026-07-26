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

公开统计路由为 `GET`；认证相关为 `POST`/`GET`。未设置 `STATS_API_TOKEN` 时保持历史匿名访问；设置后统计 API 与 OpenAPI 需 Bearer 令牌或登录会话 Cookie。详见 [`security.md`](security.md)。

| 路径 | 方法 | 响应 | 稳定性 | 当前约束 |
| --- | --- | --- | --- | --- |
| `/` | GET | 存在静态文件时返回 `src/static/index.html`；否则 JSON message | 受支持但可演进 | 页面可加载；数据仍受 API 认证约束 |
| `/health` | GET | `{"status":"ok"}` | 稳定 | 存活探针；始终匿名 |
| `/health/ready` | GET | JSON：`status`、`checks`、`metrics` | 受支持但可演进 | 就绪探针；`not_ready` 时 HTTP 503；始终匿名 |
| `/metrics` | GET | Prometheus text format metrics | 受支持但可演进 | Always anonymous; Prometheus exposition format |
| `/api/auth/status` | GET | `{"auth_required": bool}` | 受支持但可演进 | 报告是否配置了 `STATS_API_TOKEN` |
| `/api/auth/login` | POST | `{"status":"ok"}` + 会话 Cookie | 受支持但可演进 | 请求体 `{"token":"..."}`；未启用认证时 404 |
| `/api/auth/logout` | POST | `{"status":"ok"}` | 受支持但可演进 | 清除会话 Cookie |
| `/api/stats/summary` | GET | JSON：`total_plays`、`total_listen_sec`、`unique_tracks`、`client_count`，以及窗口对比字段 `active_days`、`average_daily_plays`、`average_daily_listen_sec`、`previous_total_plays`、`previous_total_listen_sec`、`plays_change_pct`、`listen_change_pct`、`window_days`（见下） | 受支持但可演进 | 可选 `?days=0`（默认，全部历史）或 `7–90`；对比与日均价仅对有限窗口计算，`days=0` 时 `window_days=null` 且 `previous_*` 与百分比均为 `null`；启用认证时需授权 |
| `/api/stats/players` | GET | JSON 数组，元素为 `client_name`、`count` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；启用认证时需授权 |
| `/api/stats/transcoding` | GET | JSON 数组，元素为 `is_transcoding`、`count` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；启用认证时需授权 |
| `/api/stats/history` | GET | JSON 数组（见下） | 受支持但可演进 | `limit` 默认 10、范围 1–100；可选 `?days=0`（默认）或 `7–90`；启用认证时需授权 |
| `/api/stats/hourly` | GET | JSON 数组，元素为 `hour`（0–23）、`count` | 受支持但可演进 | 可选 `?days=0`（默认）或 `7–90`；按一天内时段聚合；启用认证时需授权 |
| `/api/stats/daily` | GET | JSON 数组，元素为 `date`（`YYYY-MM-DD`）、`count` | 受支持但可演进 | 可选 `?days=` 默认 30；接受 `0`（全部历史）或 `7–90`（有限窗口），中间值（1–6）返回 422；按日聚合，`date` 升序；启用认证时需授权 |
| `/api/stats/top-artists` | GET | JSON 数组，元素为 `artist`（str）、`count`（int） | 受支持但可演进 | `limit` 默认 10、范围 1–50；可选 `?days=0`（默认）或 `7–90`；跳过空 artist；按 `count` 降序；启用认证时需授权 |
| `/api/stats/top-albums` | GET | JSON 数组，元素为 `album`（str）、`count`（int） | 受支持但可演进 | `limit` 默认 10、范围 1–50；可选 `?days=0`（默认）或 `7–90`；跳过空 album；按 `count` 降序；启用认证时需授权 |
| `/api/stats/now-playing` | GET | JSON 数组，元素为 `username`、`title`、`artist`、`client_name`、`seconds_elapsed`（int） | 受支持但可演进 | 来自内存 `session_tracker.active_sessions`，不访问数据库；不接受 `days`，永远是实时态；`seconds_elapsed` 从会话首次发现时间起算；启用认证时需授权 |
| `/settings` | GET | `settings.html` 隐私与数据管理页 | 受支持但可演进 | 保留策略、按用户导出/导入/删除 |
| `/api/privacy/settings` | GET/PUT | `retention_days`（`null`=永久）、`permanent` | 受支持但可演进 | PUT 接受 `null` 或 1–360 |
| `/api/privacy/retention/preview` | GET | `records_to_delete`、`retention_days` | 受支持但可演进 | 可选 `?days=` 预览未保存策略 |
| `/api/privacy/retention/apply` | POST | `deleted`、`retention_days` | 受支持但可演进 | 请求体 `{"confirm": true}` 必填 |
| `/api/privacy/users` | GET | 用户名与记录数列表 | 受支持但可演进 | 不含曲目明细 |
| `/api/privacy/users/{username}/export` | GET | JSON 导出包 | 受支持但可演进 | `Content-Disposition` 附件 |
| `/api/privacy/users/{username}/import` | POST | `imported`、`merge` | 受支持但可演进 | 校验 `format_version` 与用户名 |
| `/api/privacy/users/{username}/delete/preview` | GET | `records_to_delete` | 受支持但可演进 | 仅计数 |
| `/api/privacy/users/{username}/delete` | POST | `deleted` | 受支持但可演进 | 请求体 `{"confirm": true}` 必填 |
| `/api/source/config` | GET | `url`、`username`、`password_configured`（bool） | 受支持但可演进 | **永不返回 password**；返回 env > saved 的有效配置脱敏视图；启用认证时需授权 |
| `/api/source/config` | PUT | 同 GET | 受支持但可演进 | 接受 `url`、`username`、可选 `password`；URL 必须为 http/https；`username` 不得为空；`password` 仅在非空时更新；不回显 password；启用认证时需授权 |
| `/api/source/test` | POST | `{ok: bool, message: str}` | 受支持但可演进 | 接受可选 `url`/`username`/`password`，解析顺序：请求值 > 环境变量 > 已保存 DB；用临时 `NavidromeClient` 调用 `getNowPlaying`，调用后立即 `close()`；仅返回通用成功/失败与简短中文消息，不返回上游响应体、凭据或异常详情；启用认证时需授权 |

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

`/api/stats/summary` 返回的对比字段语义：

- `active_days`：当前窗口内出现播放的不同日期数。
- `average_daily_plays` / `average_daily_listen_sec`：有限窗口按 `active_days` 平均；`days=0` 时按最早播放日到最晚播放日的包含天数（`max - min + 1`）平均；无数据时为 `0`。
- `previous_total_plays` / `previous_total_listen_sec`：与当前窗口等长的前一窗口合计；`days=0` 时为 `null`。
- `plays_change_pct` / `listen_change_pct`：`(current - previous) / previous * 100`，`previous` 为 0 或 `days=0` 时为 `null`。
- `window_days`：有限窗口回显请求的 `days`；`days=0` 时为 `null`。

FastAPI 默认还生成 OpenAPI JSON 和交互文档路由。因为代码没有显式配置其路径或可用性，这些接口登记为“待确认”，不应在外部集成中视为稳定契约。

### 错误行为

- 非整数或超出 1–100 的 `limit`（history）或 1–50 的 `limit`（top-artists/top-albums）由 FastAPI 返回 422 请求验证错误。
- `days` 不是整数、小于 0、大于 90，或位于 1–6 之间（包括 daily）由 FastAPI 路由校验或 `_validate_stats_days` 返回 422 请求验证错误。
- 统计 API 数据库异常返回 503 与固定文案 `Stats temporarily unavailable`，不泄露路径或查询细节。
- 启用认证时未授权访问统计 API 或 OpenAPI 返回 401 与 `Unauthorized`。
- 代码没有定义 API 级错误码、错误响应 schema 或速率限制。

### 安全响应头

所有 HTTP 响应附加 `Content-Security-Policy`、`X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer`。CSP 允许 `cdn.tailwindcss.com` 与 `cdn.jsdelivr.net` 脚本来源。

## 3. 上游 Subsonic 接口

`NavidromeClient` 消费以下接口，稳定性为“受支持但可演进”，最终兼容性受目标 Navidrome/Subsonic 服务影响。

```text
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
- entry 中的 `isPlaying`、`playerId`、`id`、`username`、`playerName`、`title`、`artist`、`album`、`transcodedContentType`

兼容处理仅包括：单个 `entry` 对象会转换为一元素列表；缺失 `isPlaying` 时默认为真。当前没有对其余字段做 schema 验证，缺失 `playerId` 会被字符串化为 `"None"` 并作为会话键。

`httpx.AsyncClient` 使用 `trust_env=False`、10 秒超时与默认 TLS 行为。服务 URL 会移除末尾 `/`；代码没有限制协议，也没有自定义证书、代理或重试配置。应用将 `httpx` 日志级别设为 WARNING，避免 INFO 请求行泄露认证查询参数。

## 4. 环境变量

| 名称 | 必需性 | 默认值 | 读取位置 | 稳定性 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `NAVIDROME_URL` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游基础 URL；真实值不得入库；env 优先级高于 GUI 保存值，按字段独立覆盖 |
| `NAVIDROME_USER` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游账户名，按敏感标识处理 |
| `NAVIDROME_PASS` | 客户端初始化时必需（无 env 时回退到 GUI 保存值） | 无 | `src/source_config.py`、`src/client.py` | 稳定 | 上游密码，必须由运行环境注入；GUI 也可保存到 `schema_meta` 作为回退（见来源配置章节） |
| `POLL_INTERVAL` | 可选 | `10` | `src/main.py`、`src/config.py` | 受支持但可演进 | 秒数；模块导入时通过 `env_int` 安全解析并钳制到 5–300；非数字或缺失回退到默认 |
| `MAX_POLL_BACKOFF_SEC` | 可选 | `60` | `src/main.py`、`src/config.py` | 受支持但可演进 | 上游连续失败时轮询退避上限（秒）；钳制到 1–3600 |
| `PLAY_THRESHOLD_SEC` | 可选 | `30` | `src/main.py`、`src/sessions.py`、`src/config.py` | 受支持但可演进 | 计入播放的最低**活跃**观测秒数；钳制到 1–3600；非数字/缺失回退默认 |
| `PAUSE_GRACE_SEC` | 可选 | `30` | `src/main.py`、`src/sessions.py`、`src/config.py` | 受支持但可演进 | 暂停或缺失条目保持内存会话的宽限秒数；钳制到 0–3600；`0` 表示一遇 `isPlaying=false` 或缺失即按原行为结算 |
| `DATABASE_URL` | 可选 | `navidrome_stats.db` | `src/database.py` | 受支持但可演进 | 当前语义是 SQLite 文件路径，不是 URL |
| `STATS_API_TOKEN` | 可选 | 无（匿名访问） | `src/auth.py` | 受支持但可演进 | 设置后保护统计 API 与 OpenAPI；`/health` 保持公开；值不得入库 |
| `RETENTION_MAINTENANCE_SEC` | 可选 | `86400` | `src/main.py` | 内部 | 后台保留期清理间隔（秒）；钳制到 60–604800 |

本地开发通过 `python-dotenv` 在导入 `src/client.py` 时加载 `.env`。构造 `NavidromeClient` 时传入的非空参数优先于环境变量。

## 5. SQLite schema

数据库接口为“内部”。`schema_meta` 表记录 `schema_version`（当前 **2**）及 `retention_days`（`permanent` 或 1–360）；`init_db()` 在启动时向前迁移并创建索引。来源配置（`source_url`/`source_user`/`source_password`）直接复用 `schema_meta` 作为键值存储，未引入新表或 schema 版本迁移，既有库无需迁移即可读写。任何字段、约束或索引变更都必须先建立任务并提供既有数据迁移与回滚方案。

表：`schema_meta`

| 键 | 说明 |
| --- | --- |
| `schema_version` | 当前为 `2` |
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

除主键外各列没有显式 `NOT NULL`、默认值、检查约束或唯一约束。迁移版本 1 创建索引 `idx_play_history_user_track`、`idx_play_history_played_at`。

## 6. 内部 Python 接口

以下函数被仓库模块或测试直接调用，登记为“内部”：

- `src.client.generate_auth(password)`
- `src.client.NavidromeClient(...)`、`get_auth_params()`、`get_now_playing()`、`close()`
- `src.database.init_db(db_path=...)`
- `src.database.save_play_session(session, db_path=...)`
- `src.database.get_player_stats(days=0, db_path=...)`（`days<=0` 表示全部历史）
- `src.database.get_transcoding_stats(days=0, db_path=...)`
- `src.database.get_hourly_stats(days=0, db_path=...)`
- `src.database.get_daily_stats(days=30, db_path=...)`（`days<=0` 表示全部历史）
- `src.database.get_summary(days=0, db_path=...)`（返回窗口对比字段，见上文 API 登记）
- `src.database.get_top_artists(limit=..., days=0, db_path=...)`
- `src.database.get_top_albums(limit=..., days=0, db_path=...)`
- `src.database.get_playback_history(limit=..., days=0, db_path=...)`
- `src.sessions.PlaybackSessionTracker(...)`、`process_poll(...)`、`finalize_session(...)`、`finalize_all()`（构造参数 `play_threshold_sec`、`pause_grace_sec`、`stale_threshold_sec`）
- `src.config.parse_clamped_int(...)`、`env_int(...)`
- `src.main.finalize_session(player_id)`、`polling_loop(client)`
- `src.source_config.get_saved_source_config(...)`、`set_saved_source_config(...)`、`resolve_source_config(...)`、`resolve_effective_source_config(...)`、`validate_source_url(...)`、`has_full_config(...)`、`redacted_view(...)`

## 6.1 来源配置解析顺序

`src.source_config.resolve_source_config(overrides, saved)` 按字段独立解析，优先级（高 → 低）：

1. 请求提交的非空覆盖值（用于 `POST /api/source/test` 测试给定值）；
2. 环境变量 `NAVIDROME_URL` / `NAVIDROME_USER` / `NAVIDROME_PASS`；
3. 已保存 DB `schema_meta` 中的 `source_url` / `source_user` / `source_password`。

lifespan 在构造运行中的 `NavidromeClient` 前调用 `resolve_effective_source_config()`（仅 env > saved），若三者不齐全则记录错误并将 `client_initialized` 置为 false，不启动轮询。GUI 保存配置不会热更新运行客户端，需重启服务生效。`/api/source/test` 构造的临时客户端调用 `get_now_playing()` 后于 `finally` 中 `close()`。

## 7. 变更流程

1. 在 [`tasks.md`](tasks.md) 创建或领取接口变更任务，列出消费者和敏感数据影响。
2. 对公开 HTTP 或环境变量接口给出兼容策略；对数据库给出迁移、备份和回滚步骤。
3. 实现代码和自动化测试，同一变更更新本文与 [`current-state.md`](current-state.md)。
4. 若数据类别、日志或暴露范围变化，同步更新 [`privacy.md`](privacy.md) 并完成所需人工确认。
5. 运行任务验证命令、全量测试、链接检查和 `git diff --check`，记录实际结果后才能标记完成。
