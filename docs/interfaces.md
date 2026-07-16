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

所有显式路由均为 `GET`。代码未增加应用层认证、版本前缀、自定义错误模型或缓存头。

| 路径 | 响应 | 稳定性 | 当前约束 |
| --- | --- | --- | --- |
| `/` | 存在静态文件时返回 `src/static/index.html`；否则返回 JSON message | 受支持但可演进 | 返回类型取决于文件是否存在 |
| `/health` | `{"status":"ok"}` | 受支持但可演进 | 仅表示请求处理成功，不验证依赖 |
| `/api/stats/players` | JSON 数组，元素为 `client_name`、`count` | 受支持但可演进 | 按播放记录数降序；名称可为 null |
| `/api/stats/transcoding` | JSON 数组，元素为 `is_transcoding`、`count` | 受支持但可演进 | `is_transcoding` 通常为 0 或 1，也可能因既有数据为 null |
| `/api/stats/history` | JSON 数组，元素为 `username`、`title`、`artist`、`album`、`play_count` | 受支持但可演进 | 查询参数 `limit` 默认 10，仅做整数解析；按 `username, track_id` 聚合，`title`/`artist`/`album` 取自最新一条记录（`MAX(id)`），按最近 `played_at` 降序 |

当前 history 调用示例：

```text
GET /api/stats/history?limit=10
```

FastAPI 默认还生成 OpenAPI JSON 和交互文档路由。因为代码没有显式配置其路径或可用性，这些接口登记为“待确认”，不应在外部集成中视为稳定契约。

### 错误行为

- 非整数 `limit` 由 FastAPI 返回请求验证错误。
- 数据库异常未在路由层捕获，交由 FastAPI 默认异常处理。
- 代码没有定义 API 级错误码、错误响应 schema 或速率限制。

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
| `NAVIDROME_URL` | 客户端初始化时必需 | 无 | `src/client.py` | 稳定 | 上游基础 URL；真实值不得入库 |
| `NAVIDROME_USER` | 客户端初始化时必需 | 无 | `src/client.py` | 稳定 | 上游账户名，按敏感标识处理 |
| `NAVIDROME_PASS` | 客户端初始化时必需 | 无 | `src/client.py` | 稳定 | 上游密码，必须由运行环境注入 |
| `POLL_INTERVAL` | 可选 | `10` | `src/main.py` | 受支持但可演进 | 秒数；模块导入时解析为整数，当前无范围校验 |
| `DATABASE_URL` | 可选 | `navidrome_stats.db` | `src/database.py` | 受支持但可演进 | 当前语义是 SQLite 文件路径，不是 URL |

本地开发通过 `python-dotenv` 在导入 `src/client.py` 时加载 `.env`。构造 `NavidromeClient` 时传入的非空参数优先于环境变量。

## 5. SQLite schema

数据库接口为“内部”。`schema_meta` 表记录 `schema_version`（当前 **1**）；`init_db()` 在启动时向前迁移并创建索引。任何字段、约束或索引变更都必须先建立任务并提供既有数据迁移与回滚方案。

表：`schema_meta`

| 列 | SQLite 声明 | 说明 |
| --- | --- | --- |
| `key` | `TEXT PRIMARY KEY` | 元数据键，当前使用 `schema_version` |
| `value` | `TEXT NOT NULL` | 版本号字符串 |

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
| `listen_duration_sec` | `INTEGER` | 观测时长向下取整 | 使用行为数据 |

除主键外各列没有显式 `NOT NULL`、默认值、检查约束或唯一约束。迁移版本 1 创建索引 `idx_play_history_user_track`、`idx_play_history_played_at`。

## 6. 内部 Python 接口

以下函数被仓库模块或测试直接调用，登记为“内部”：

- `src.client.generate_auth(password)`
- `src.client.NavidromeClient(...)`、`get_auth_params()`、`get_now_playing()`、`close()`
- `src.database.init_db(db_path=...)`
- `src.database.save_play_session(session, db_path=...)`
- `src.database.get_player_stats(db_path=...)`
- `src.database.get_transcoding_stats(db_path=...)`
- `src.database.get_playback_history(limit=..., db_path=...)`
- `src.sessions.PlaybackSessionTracker(...)`、`process_poll(...)`、`finalize_session(...)`、`finalize_all()`
- `src.main.finalize_session(player_id)`、`polling_loop(client)`

## 7. 变更流程

1. 在 [`tasks.md`](tasks.md) 创建或领取接口变更任务，列出消费者和敏感数据影响。
2. 对公开 HTTP 或环境变量接口给出兼容策略；对数据库给出迁移、备份和回滚步骤。
3. 实现代码和自动化测试，同一变更更新本文与 [`current-state.md`](current-state.md)。
4. 若数据类别、日志或暴露范围变化，同步更新 [`privacy.md`](privacy.md) 并完成所需人工确认。
5. 运行任务验证命令、全量测试、链接检查和 `git diff --check`，记录实际结果后才能标记完成。
