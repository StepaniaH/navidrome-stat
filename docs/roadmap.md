# 开源版本开发路线

本文描述 Navidrome Statistic 作为开源、自托管项目的后续方向。它不是第二份待办清单：可执行工作仍只登记在 [`tasks.md`](tasks.md)。本文说明产品边界、阶段划分、刻意不做的事，以及阶段与任务 ID 的对应关系。

核验基线：2026-08-21 工作树 `main` @ `8e99f8b`，对照 `src/`、`tests/`、`Dockerfile`、CI 与 git 标签。未读取真实 `.env`、SQLite 或部署日志。

## 1. 产品定位

Navidrome Statistic 是 **Navidrome / Subsonic 的自托管伴侣**：轮询 `getNowPlaying`，在本进程内追踪会话，把达到阈值的播放写入本地 SQLite，再用同源网页展示统计。

当前已证明、开源版本应继续坚持的边界：

- 单应用实例。一个实例可管理多个 Navidrome 服务器；多个本服务副本采集同一数据源会重复计数（见 NDS-ARCH-001）。
- 行为数据默认按隐私数据处理，而不是匿名遥测。仓库不发送使用情况、崩溃报告或播放元数据到第三方。
- 不读取 Navidrome 私有数据库，不绑定未登记的私有 API。NDS-DATA-004（2026-08-21）结论：公开 Subsonic / OpenSubsonic 无只读播放历史端点，因此**不实施**原生历史导入，直到上游发布可验证的公开读接口。
- 可选共享口令 `STATS_API_TOKEN` 保护统计与设置 API；`/health` 始终匿名。`/metrics` 默认匿名，可用 `STATS_METRICS_AUTH` 在已配置令牌时改为需认证。TLS、反向代理和公网暴露由部署方负责（NDS-SEC-001）。
- 运行时契约是 **Python 3.11**（Dockerfile 与 CI）。其他解释器版本可能能跑，但不构成已验证承诺。

当前版本叙事（代码事实）：

| 项 | 事实 |
| --- | --- |
| 应用默认版本 | `APP_VERSION` 缺省 `0.7.0-dev`（`src/version.py`） |
| 已打 git 标签 | `v0.5.0`–`v0.7.0` |
| 领先标签的提交 | `v0.7.0` 之后还有 Dashboard UX 收敛（PR #7） |
| GitHub Releases | `v*` 镜像推送成功后由工作流创建；仓库核验时可能尚无历史 Release 对象 |
| 公开镜像 | `stepaniah/navidrome-statistic`（amd64/arm64） |
| `/api/about` 的 `project_url` | 公开仓库 `https://github.com/StepaniaH/navidrome-stat` |

## 2. 阶段

阶段按依赖和破坏半径划分，不按日历。后一阶段可以在前一阶段的人工确认仍为「待验收」时启动**不依赖该确认**的工程任务，但不能把待验收项改写成已完成。

### 阶段 A — 可被陌生人使用的 0.x

目标：外部贡献者和部署者只靠仓库文档就能安装、提问、报缺陷，且不会把真实凭据或播放历史带进 Git。

已具备：双语 README、MIT、CI（pytest / Ruff / Compose / Markdown 链接 / Docker smoke / Playwright）、Dependabot、按 tag 推镜像、可选认证、隐私导出/删除、自托管前端。

本阶段文档工作由 NDS-DOC-003 交付。工程收口：

| 任务 | 作用 |
| --- | --- |
| NDS-OSS-001 | git 标签发布时创建 GitHub Release；`/api/about` 返回公开仓库 URL |
| NDS-SEC-003 | `/metrics` 与 OpenAPI 可配置；默认保持兼容 |
| NDS-PRIV-002 | 空白告知模板已提供；正文须部署方审批后才算完成告知 |
| NDS-SEC-001、NDS-PRIV-001、NDS-DEP-001 | 保持待验收：仓库无法代替部署方确认访问范围、告知文案、卷权限 |

阶段出口：打一枚包含 CHANGELOG 的版本标签，并创建对应 GitHub Release；文档声明「单实例 / 明文 SQLite / 可选口令」而不是「生产即开即用」。建议版本为 **0.8.0**（含标签后未发布的 Dashboard 变更），而不是直接宣称 1.0。

### 阶段 B — 可信的 1.0

目标：语义稳定、发布可复现、安全默认值对公网部署足够诚实。1.0 表示「计数语义与 HTTP 契约按 [`interfaces.md`](interfaces.md) 维护」，不是高可用或多租户。

| 任务 | 作用 |
| --- | --- |
| NDS-SEC-003 | `/metrics` 默认仍匿名；生产若公网暴露指标口应打开 `STATS_METRICS_AUTH` |
| NDS-DEP-002 | 钉扎基础镜像 digest、记录发布来源 |
| NDS-UI-001 / NDS-UI-010 | 分区加载状态与读屏核验已由 NDS-UI-010 交付；浏览器合成测试覆盖空数据、401 与部分失败 |
| NDS-API-001 遗留 | 明确 OpenAPI 公开策略（关闭、仅认证后可见、或保持现状并写入兼容承诺） |

1.0 刻意不包含：多副本采集、按查看者隔离、托管 SaaS、加密凭据存储的强制迁移。明文 GUI 密码是已记录的自托管权衡；1.0 只需在 README 与安全文档中继续写清楚，并把「仅环境变量、禁止 GUI 落库」列为可选部署模式（若做，新建任务，不要塞进 NDS-SEC-003）。

### 阶段 C — 兼容演进

只在 1.0 契约冻结后做。每项都可能扩展接口或 schema，必须走 [`interfaces.md`](interfaces.md) 变更流程。

| 方向 | 任务 | 约束 |
| --- | --- | --- |
| 原生历史导入 | NDS-DATA-004 | 2026-08-21 结论：**不实施**。公开 Subsonic / OpenSubsonic 无只读历史端点；Navidrome 0.59+ 内部存储未提供公开 HTTP。待公开 API 后新建任务，禁止猜测私有库路径 |
| 多进程/多副本 | NDS-ARCH-001 | 依赖部署方确认拓扑；默认仍是单实例 |
| 更多语言 | 新建 `NDS-UI-*` | 只扩 `localization.js` 消息表，不改数据模型 |
| 外部 scrobble / ListenBrainz | 未立项 | 会把行为数据送出本机，必须先过隐私确认 |

## 3. 刻意不做（除非新建任务并完成隐私确认）

- 把本服务做成多租户云或收集匿名用量。
- 为了「更准」去读 Navidrome 服务器磁盘上的数据库文件。
- 在未确认拓扑前引入领导者选举、Redis 或共享网络 SQLite。
- 在 issue、PR、截图、日志或测试里放入真实服务器地址、账户、token 或播放明细。
- 用 TODO 注释替代 [`tasks.md`](tasks.md)。

## 4. 版本与兼容

- 标签格式 `vX.Y.Z`，与现有 Docker Hub 工作流一致。
- PATCH：缺陷、文档、依赖补丁，不改统计语义。
- MINOR：新增可选字段、端点或配置，旧客户端仍可用。
- MAJOR：计数语义、认证默认值、schema 回滚不兼容或删除端点。数据库只向前迁移；破坏性变更先建任务。
- Docker 镜像同时推 `vX.Y.Z` 与 `latest`。部署文档继续建议钉扎版本标签。

## 5. 文档如何配合

| 读者 | 从哪里读 |
| --- | --- |
| 部署者 | [`README.md`](../README.md) / [`README.zh-CN.md`](../README.zh-CN.md)，再按需看隐私与安全 |
| 贡献者 | [`CONTRIBUTING.md`](../CONTRIBUTING.md)、[`CHANGELOG.md`](../CHANGELOG.md) |
| Agent | [`AGENTS.md`](../AGENTS.md) → [`current-state.md`](current-state.md) → [`tasks.md`](tasks.md) |
| 安全报告 | [`SECURITY.md`](../SECURITY.md)（不要把凭据发到公开 issue） |
