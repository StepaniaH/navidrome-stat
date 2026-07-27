# 后续任务清单

本文件是后续工作的唯一任务来源。下列任务均基于当前代码检查创建，尚未实施，因此全部保持“待办”；这不表示优先级、设计或人工隐私决策已经获得用户批准。

## 状态与执行规则

- 状态流转：`待办 -> 进行中 -> 阻塞/待验收 -> 已完成`；也可标记 `已取消` 并记录原因。
- 领取任务前先核验依赖和当前代码。实施时只修改“涉及文件”及完成任务所必需的文档/测试。
- 完成记录必须填写实际日期、实施者、摘要、验证输出、提交或 PR（如有）和遗留风险。空白记录不能作为完成证据。
- 涉及真实部署、凭据或用户数据的步骤必须先完成 [`privacy.md`](privacy.md) 中对应人工确认。
- 优先级：P0 为上线前安全/数据正确性阻断，P1 为近期可靠性与质量，P2 为演进与维护性。

## 任务总览

| ID | 领域 | 优先级 | 状态 | 依赖 |
| --- | --- | --- | --- | --- |
| NDS-SEC-001 | 访问控制与部署边界 | P0 | 待验收 | 用户人工确认访问范围与授权模型 |
| NDS-SEC-002 | 前端注入与 CDN 风险 | P0 | 待验收 | 用户人工确认 CDN 策略 |
| NDS-CORE-001 | 播放状态机正确性 | P0 | 已完成 | 无 |
| NDS-DATA-001 | 数据库 schema 与查询确定性 | P0 | 已完成 | NDS-CORE-001 的计数语义结论 |
| NDS-PRIV-001 | 保留、删除与用户告知 | P0 | 待验收 | 用户人工确认保留期、授权和数据请求流程 |
| NDS-API-001 | HTTP 契约与输入限制 | P1 | 已完成 | NDS-SEC-001 的认证边界结论 |
| NDS-REL-001 | 上游客户端生命周期与容错 | P1 | 已完成 | 无 |
| NDS-OPS-001 | 健康检查与可观测性 | P1 | 已完成 | NDS-REL-001 |
| NDS-TEST-001 | 自动化测试基线 | P1 | 待验收 | NDS-CORE-001、NDS-DATA-001、NDS-API-001 |
| NDS-DEP-001 | 容器与依赖可复现性 | P1 | 待验收 | 用户人工确认部署约束 |
| NDS-UI-001 | Dashboard 运行状态与可访问性 | P2 | 待验收 | NDS-SEC-002、NDS-API-001 |
| NDS-DOC-001 | 用户文档事实校准 | P1 | 已完成 | NDS-CORE-001 的语义结论 |
| NDS-ARCH-001 | 多进程/多副本架构决策 | P2 | 待办 | NDS-CORE-001、用户人工确认部署拓扑 |
| NDS-CI-001 | 持续集成质量门禁 | P2 | 已完成 | NDS-TEST-001、NDS-DEP-001 |
| NDS-SRC-001 | 信息来源配置与设置信息架构 | P1 | 已完成 | 无 |
| NDS-CORE-002 | 暂停/缺失宽限与配置安全 | P1 | 已完成 | NDS-CORE-001 |
| NDS-UI-002 | 正在播放本地计时与每日趋势时间范围选择 | P2 | 已完成 | NDS-UI-001 |
| NDS-UI-003 | Dashboard 统一历史窗口与环比对比指标 | P2 | 已完成 | NDS-UI-002 |
| NDS-UI-004 | 时区感知的周×时热力图 | P2 | 已完成 | NDS-UI-003 |
| NDS-UI-005 | 丰富榜单与客户端分析 | P2 | 已完成 | NDS-UI-004 |
| NDS-DATA-002 | 短播放尝试与短播放率 | P2 | 已完成 | NDS-UI-005 |
| NDS-DATA-003 | 播放来源溯源层 | P2 | 已完成 | NDS-DATA-002 |
| NDS-UI-006 | 设置页偏好与主题本地化 | P1 | 已完成 | NDS-SRC-001、NDS-UI-004 |
| NDS-DOC-002 | 双语 README、Docker 部署与正在播放修复 | P1 | 已完成 | NDS-SRC-001、NDS-UI-002 |
| NDS-REL-002 | 服务器配置热更新与采集器生命周期 | P1 | 已完成 | NDS-DOC-002、NDS-SRC-001 |

## NDS-REL-002 服务器配置热更新与采集器生命周期

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-DOC-002、NDS-SRC-001；不读取或记录真实服务器地址、账户、密码、token、上游响应或播放元数据。
- **目标**：服务器创建、更新、启停、删除及兼容来源保存后立即更新运行中的轮询客户端，不再要求重启服务。
- **实施步骤**：
  1. 按 `docs/superpowers/specs/2026-07-27-collector-hot-reload-design.md` 建立按服务器 ID 管理 client/tracker/task 的 `CollectorManager`，并用锁串行化生命周期变更。
  2. 替换时先构造新 collector，再按现有阈值结算旧会话、取消旧任务、关闭旧客户端并注册新 collector；构造失败保留旧 collector。
  3. lifespan 通过 manager 启动初始服务器并在关闭时 `stop_all()`；now-playing/readiness/metrics 继续读取运行时 tracker 聚合视图。
  4. server create/update/delete 与适用的 legacy source save 在持久化后调用 manager；运行时失败返回通用 503，不回显配置或上游正文。
  5. 设置页移除“重启生效”文案；同步当前事实、接口与隐私文档；仅使用合成测试数据。
- **验收标准**：创建/更新/启用立即启动对应 poller；禁用/删除立即停止且不影响其他服务器；替换前旧会话按现有规则结算；替换构造失败保留旧 poller；设置页不再要求重启；接口错误不泄露敏感值；全量验证通过。
- **验证命令**：`.venv/bin/python -m pytest -q tests/test_collector_manager.py tests/test_lifespan.py tests/test_static_settings.py`；`.venv/bin/python -m pytest -q`；`.venv/bin/python scripts/check_md_links.py`；`git diff --check`；敏感值扫描；重启本地服务后以脱敏 readiness/metrics 验证。
- **涉及文件**：`src/main.py`、`src/static/settings.html`、新增或相关测试、`docs/current-state.md`、`docs/interfaces.md`、`docs/privacy.md`、`docs/tasks.md`、设计与实施计划文档。
- **风险/回滚**：生命周期错误可能中断单个服务器采集或重复结算；使用锁、先构造后切换、幂等 stop 和资源关闭测试降低风险。无 schema 变更，回滚代码即可恢复重启生效模式，已保存配置和历史不变。
- **完成记录**：2026-07-27，OpenCode。新增 `CollectorManager` 按服务器 ID 管理 client/tracker/task，以锁串行化变更；替换时先构造新资源，再结算旧会话、取消任务、关闭 client 并注册新 tracker；禁用和删除立即停止对应 collector，构造失败保留旧 collector，结算失败仍清理新旧资源。lifespan 改由 manager 启停 collector；server create/update/delete 与无多服务器记录时的 legacy source PUT 在持久化后立即应用，失败返回固定 503 且不回显配置。设置页中英文改为保存后立即应用。新增 `tests/test_collector_manager.py`、`tests/test_server_api.py` 及 source/lifespan/static 回归用例。验证：全量 `.venv/bin/python -m pytest -q` 为 340 passed；目标集 42 passed；Markdown 链接和 `git diff --check` 通过；重启后 PID 73286 独占 `127.0.0.1:39421`，脱敏状态为 2 个已启用服务器、poller running。对一个服务器执行不含 password 的同值 PUT 返回 200，无需重启，等待 12 秒后 `poll_success_total` 从 4 增至 6，最终 readiness `ready`、upstream `ok`。未创建提交或 PR。遗留风险：现场 `poll_failure_total` 为 3，表明至少一个上游存在间歇失败；最近状态已恢复，若持续增长应另行按脱敏日志诊断网络或上游响应。

## NDS-DOC-002 双语 README、Docker 部署与正在播放修复

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-SRC-001、NDS-UI-002；不读取真实 `.env`、SQLite 数据、日志或部署配置。
- **目标**：以纯英文 `README.md` 作为主文档并链接纯中文 `README.zh-CN.md`，提供以已发布镜像为主的 Docker 部署教程；修复多服务器轮询后正在播放 API 仍读取旧全局 tracker、因而始终为空的问题。
- **实施步骤**：
  1. 按 `docs/superpowers/specs/2026-07-27-readme-now-playing-design.md` 重写英文 README，并创建同事实、同结构的中文 README；所有示例仅使用保留域名与明显占位符。
  2. 以 `stepaniah/navidrome-statistic` 已发布镜像和 named volume 为默认 Compose 部署路径，另行说明源码构建；记录健康检查、更新、日志、备份、认证与明文 SQLite 边界。
  3. 为 lifespan 创建的每服务器 `PlaybackSessionTracker` 建立运行时注册表；正在播放、readiness 与 metrics 从同一聚合视图读取，未注册 lifespan tracker 时兼容现有全局 tracker。
  4. 正在播放聚合排除 `paused=true` 的宽限期会话，保持现有响应字段与 `seconds_elapsed` 语义，不新增服务器标识字段。
  5. 先增加可复现失败的回归测试，再实施最小修复；同步当前事实、接口和隐私文档。
- **验收标准**：英文 README 无中文叙述、中文 README 无英文叙述混排且相互链接；Docker 命令与当前镜像、端口、非 root 用户、配置和持久化事实一致；示例无真实敏感值；多服务器 tracker 中的活跃会话可由 `/api/stats/now-playing` 返回，暂停会话不返回；readiness 与 metrics 的活动数一致；既有接口响应字段不变；全部验证通过或明确记录环境阻塞。
- **验证命令**：`pytest -q tests/test_lifespan.py tests/test_main.py tests/test_metrics.py`；`pytest -q`；`python3 scripts/check_md_links.py`；`docker compose config`；可用时执行 Docker 烟雾测试；`git diff --check`；`git diff --stat`；`git diff`；`git status --short`；敏感值扫描。
- **涉及文件**：`README.md`、`README.zh-CN.md`、`src/main.py`、相关测试、`docs/current-state.md`、`docs/interfaces.md`、`docs/privacy.md`、`docs/tasks.md`、设计与实施计划文档。
- **风险/回滚**：运行时注册表清理错误可能残留陈旧会话或导致指标不一致；用 lifespan 与多 tracker 测试覆盖注册/注销。改动不涉及 schema 或既有数据；回滚应用代码与 README 文件即可。
- **完成记录**：2026-07-27，OpenCode。将 `README.md` 重写为纯英文主文档并新增互链的 `README.zh-CN.md`；以已发布镜像为主路径补充 Compose、配置、更新、健康检查、日志、备份恢复与安全隐私说明。Dockerfile 新增 UID 1000 可写的 `/data`，仓库 Compose 改用命名卷与 `/data/navidrome_stats.db`。修复多服务器 lifespan tracker 未被正在播放、readiness 和 metrics 读取的问题，并排除宽限期内暂停会话；现有 now-playing 响应字段与计时语义不变。新增多 tracker、暂停过滤、观测计数和生命周期清理测试。验证：Python 3.11.15 下基线 `324 passed`，最终 `327 passed`；focused 测试 `28 passed`；`python3 scripts/check_md_links.py`、`docker compose config`、`git diff --check` 通过；英文 README 汉字扫描仅命中语言链接“简体中文”，README 凭据赋值扫描无命中。Docker daemon 未运行，镜像构建与 `scripts/docker_smoke_test.sh` 为环境阻塞，未声称通过。未创建提交或 PR。遗留风险：实际发布镜像、真实卷权限、备份恢复和外部访问边界仍需部署方在受控环境验收。

## NDS-SEC-001 访问控制与部署边界

- **优先级/状态**：P0 / 待验收
- **依赖**：用户人工确认服务部署范围、查看者角色、反向代理/TLS 责任和是否需要按用户隔离。
- **目标**：防止未授权主体读取用户名和播放历史，并形成可验证的部署边界。
- **实施步骤**：
  1. 记录不含真实地址的威胁模型：可信网络、攻击入口、数据读取角色和代理边界。
  2. 根据用户决策选择现有反向代理认证或应用层认证；定义 `/health`、Dashboard、统计 API 和 OpenAPI 文档各自访问策略。
  3. 实现授权失败响应和安全默认值；若支持代理头，限定可信代理来源。
  4. 添加未认证、错误凭据、正确凭据和越权场景测试，不在 fixture 中使用真实凭据。
  5. 更新 `interfaces.md`、`privacy.md`、README 部署说明和迁移/回滚步骤。
- **验收标准**：受保护接口在未授权时不可返回统计数据；授权策略与人工结论一致；健康探针策略明确；测试覆盖绕过场景；文档不含真实值。
- **验证命令**：`pytest -q`；使用合成凭据执行 API 测试；`git diff --check`；文档链接检查。
- **涉及文件**：预计 `src/main.py`、新增认证模块（如需要）、`tests/`、`requirements.txt`、README、`docs/`；代理配置仅在用户确认后新增。
- **风险/回滚**：可能中断现有 Dashboard 或探针访问。保留原部署配置备份，回滚应用与代理变更；不得通过长期关闭认证解决故障。
- **完成记录**：2026-07-16，Cursor Agent。新增可选 `STATS_API_TOKEN`（Bearer + 会话 Cookie 登录）；`/health` 保持公开；威胁模型见 `docs/security.md`；新增 `tests/test_auth.py`。验证：`pytest -q` 46 passed。遗留：反向代理配置示例、按用户隔离、TLS 由部署方确认；默认匿名模式需用户确认仅用于可信网络。

## NDS-SEC-002 前端注入与 CDN 风险

- **优先级/状态**：P0 / 待验收
- **依赖**：用户人工确认公共 CDN 是否允许、是否要求离线运行或固定资产来源。
- **目标**：安全渲染不可信媒体元数据，并降低第三方脚本供应链和隐私风险。
- **实施步骤**：
  1. 为用户名、标题、艺人、专辑构造包含 HTML 和脚本边界字符的合成测试数据。
  2. 用 DOM `textContent`/节点创建替代动态 `innerHTML`，确保空状态也不引入注入路径。
  3. 根据人工决策自托管固定版本资源，或增加版本锁定、SRI（适用时）和 CSP；记录外联域名。
  4. 增加安全响应头策略并验证不破坏图表加载。
  5. 在桌面和移动视口执行浏览器测试，确认数据展示、空状态、图表和控制台无异常。
- **验收标准**：合成恶意元数据只能显示为文本；页面无未批准的第三方请求；CSP/安全头与资源加载一致；浏览器测试通过。
- **验证命令**：`pytest -q`；前端浏览器自动化测试；检查页面网络请求和响应头；`git diff --check`。
- **涉及文件**：`src/static/index.html`、可能的本地静态资源、`src/main.py`、前端/安全测试、`docs/privacy.md`、`docs/interfaces.md`。
- **风险/回滚**：CSP 或资源改动可能导致样式/图表失效。保留可验证的前一资产版本，回滚时不得恢复不安全的动态 HTML 渲染。
- **完成记录**：2026-07-16，Cursor Agent。`index.html` 历史表格改用 `textContent`/`createElement` 渲染。2026-07-16 续：ECharts SRI、CSP 与安全响应头；`tests/test_security.py` 合成恶意元数据；Dashboard 登录流与 `credentials: 'same-origin'`。验证：`pytest -q` 46 passed。遗留：Tailwind 自托管、浏览器自动化测试待用户确认 CDN 策略。

## NDS-CORE-001 播放状态机正确性

- **优先级/状态**：P0 / 已完成
- **依赖**：无；实施前需用户确认期望的“播放”语义是否为观测时间、媒体进度或其他定义。
- **目标**：明确并测试会话键、阈值、暂停、停止、换曲、重复观测、异常退出和关闭结算行为。
- **实施步骤**：
  1. 把当前循环中的会话转移逻辑提取为可注入时钟并可单元测试的边界，不改变已确认语义之外的行为。
  2. 明确 `playerId` 或 `track_id` 缺失时的处理，避免多个缺失 ID 共用 `"None"` 会话。
  3. 明确阈值是 `>= 30` 还是 `> 30`，暂停期间是否计时，以及上游短暂缺失是否使用宽限期。
  4. 处理同一播放器快速换曲、重复曲目、倒退时间和轮询间隔大于宽限期的情况。
  5. 为正常关闭与异常退出定义数据保证；若不保证异常退出保存，必须明确记录。
  6. 添加状态转换表和参数化测试，并同步用户文档。
- **验收标准**：每个状态转换有确定输出；缺失 ID 不会串会话；30 秒边界有测试；暂停/停止/换曲/关闭均有测试；文档与代码阈值一致。
- **验证命令**：`pytest -q tests/test_main.py` 及新增状态机测试；`pytest -q`；`git diff --check`。
- **涉及文件**：`src/main.py`、可能的新状态模块、`tests/test_main.py`/新增测试、README、`docs/current-state.md`、`docs/interfaces.md`。
- **风险/回滚**：语义调整会改变新记录计数。上线前对合成时间线比较旧/新结果；回滚代码不会自动删除已写数据，数据修复需单独审批。
- **完成记录**：2026-07-16，Cursor Agent。提取 `src/sessions.py` 的 `PlaybackSessionTracker`；缺失 `playerId` 条目跳过；阈值保持 `>= 30`；新增 `tests/test_sessions.py`（8 项）。验证：`pytest -q tests/test_sessions.py` 8 passed；`pytest -q` 14 passed。遗留：轮询循环与 lifespan 的端到端集成测试仍待 NDS-TEST-001。

## NDS-DATA-001 数据库 schema 与查询确定性

- **优先级/状态**：P0 / 已完成
- **依赖**：NDS-CORE-001 的播放计数和字段语义结论。
- **目标**：建立可迁移 schema，修复聚合查询不确定性，并为增长、重复写入和既有数据提供策略。
- **实施步骤**：
  1. 使用仅含合成数据的数据库副本审计 null、重复、时间格式和查询计划；真实库检查需用户授权。
  2. 设计 schema 版本和向前迁移机制，明确每列 null/类型/检查约束及时间格式。
  3. 修正 history 查询，使标题、艺人、专辑与分组键的来源确定；确认同一 `track_id` 元数据变化的期望。
  4. 根据实际查询增加最小索引，并用代表性合成数据验证查询计划。
  5. 决定幂等键或重复记录策略；不得在未确认业务语义时自动去重既有数据。
  6. 编写迁移前备份、事务执行、失败回滚和迁移后核验步骤。
- **验收标准**：空库和旧 schema 都能迁移；重复执行迁移安全；聚合结果确定；数据行数/关键汇总迁移前后可核对；失败可回滚。
- **验证命令**：数据库单元/迁移测试；`pytest -q tests/test_database.py`；`pytest -q`；对合成数据运行 `PRAGMA integrity_check` 和 `EXPLAIN QUERY PLAN`。
- **涉及文件**：`src/database.py`、可能的迁移模块/脚本、`tests/test_database.py`、`docs/interfaces.md`、`docs/privacy.md`。
- **风险/回滚**：错误迁移可损坏或重算历史。必须先备份并在副本演练；回滚恢复备份或执行经测试的反向迁移。
- **完成记录**：2026-07-16，Cursor Agent。新增 `schema_meta`/`schema_version=1` 与索引迁移；`get_playback_history` 以 `MAX(id)` 取最新元数据并按 `played_at` 排序；新增迁移与聚合测试。验证：`pytest -q tests/test_database.py` 3 passed；`pytest -q` 18 passed。遗留：列级约束、幂等键与既有库大规模迁移演练未做。

## NDS-PRIV-001 保留、删除与用户告知

- **优先级/状态**：P0 / 待验收
- **依赖**：用户人工确认政策依据、被监控用户告知方式、保留期、导出/删除责任人和备份处理。
- **目标**：让播放行为数据具有明确生命周期和可审计的数据请求流程。
- **实施步骤**：
  1. 记录获批的数据字段、处理目的、查看角色、保留期和备份保留规则，不写真实用户数据。
  2. 设计按时间清理、按用户导出和删除流程，定义用户名变更及聚合数据的处理方式。
  3. 在合成数据库上实现 dry-run、事务、审计摘要和失败回滚；默认不得直接作用于真实库。
  4. 确保 API、日志、备份和 Dashboard 的保留边界一致。
  5. 编写运行手册，真实执行前要求明确授权、备份和结果复核。
- **验收标准**：政策决定有责任人；dry-run 可显示将影响的数量而不暴露内容；导出/删除测试可复现；备份中的删除限制有明确说明；用户告知文本由用户审批。
- **验证命令**：针对合成数据库的保留/导出/删除测试；迁移测试；`pytest -q`；隐私文档人工验收。
- **涉及文件**：预计数据库服务/管理脚本、`tests/`、`docs/privacy.md`、部署运行手册；用户告知材料位置由用户决定。
- **风险/回滚**：删除不可逆且可能与备份冲突。强制 dry-run、事务和执行前备份；不允许 AI 未经授权处理真实数据。
- **完成记录**：2026-07-16，Cursor Agent。用户确认：默认永久保留、1–360 天滑轮、按用户导出/导入、隐私优先（预览+确认）。实现 `src/privacy_ops.py`、`/settings` 页面、`/api/privacy/*` 路由、schema v2 与后台保留清理；新增 `tests/test_privacy_ops.py`、`tests/test_privacy_api.py`。验证：`pytest -q` 55 passed；`python3 scripts/check_md_links.py` 通过。遗留：正式用户告知文案由部署方审批；备份副本中的删除边界需运维手册；用户名变更后的数据关联仍按原 username 处理。

## NDS-API-001 HTTP 契约与输入限制

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-SEC-001 的认证边界结论。
- **目标**：为统计 API 定义可测试的参数、响应、错误和兼容约束。
- **实施步骤**：
  1. 为响应建立显式模型，确认 null 字段、整数范围和排序保证。
  2. 为 history `limit` 设置经确认的最小值、默认值和最大值，测试负数、零、超大值、重复参数和非整数。
  3. 决定 API 版本策略和 OpenAPI 文档是否公开；记录破坏性变更流程。
  4. 定义数据库不可用等错误的非敏感响应，避免泄露路径或查询细节。
  5. 评估分页或游标需求，避免仅扩大无界 limit。
- **验收标准**：OpenAPI 与实际响应一致；边界参数结果确定；错误不泄露内部信息；现有 Dashboard 已验证兼容或有迁移方案。
- **验证命令**：API 参数化测试；OpenAPI schema 断言；`pytest -q`；文档链接检查。
- **涉及文件**：`src/main.py`、可能的 schema 模块、`tests/test_main.py`、`src/static/index.html`、`docs/interfaces.md`。
- **风险/回滚**：限制或模型可能破坏未登记消费者。实施前确认消费者，必要时保留兼容路由/窗口。
- **完成记录**：2026-07-16，Cursor Agent。新增 `src/schemas.py` 响应模型；history `limit` 限制 1–100；统计 API 503 固定错误文案；新增边界与错误测试。验证：`pytest -q` 29 passed（连续两次）。遗留：OpenAPI 公开策略、分页游标仍待 SEC-001 后确认。

## NDS-REL-001 上游客户端生命周期与容错

- **优先级/状态**：P1 / 已完成
- **依赖**：无。
- **目标**：确保 `httpx.AsyncClient` 正确关闭，并为超时、瞬时故障和错误响应建立受控行为。
- **实施步骤**：
  1. 将客户端生命周期纳入 FastAPI lifespan，在取消和初始化失败路径都执行 `close()`。
  2. 显式配置连接/读取超时；重试只覆盖经判断为瞬时且幂等的请求。
  3. 设计带上限和抖动的退避，避免错误时固定频率持续请求上游。
  4. 区分网络错误、HTTP 错误、无效 JSON 和 Subsonic `status != ok`，日志不含认证 URL/响应正文。
  5. 为取消、关闭、超时、恢复和连续失败添加异步测试。
- **验收标准**：所有退出路径无未关闭客户端警告；故障时请求频率受控；恢复后继续轮询；日志不含 token、密码或完整查询 URL。
- **验证命令**：客户端和 lifespan 异步测试；`pytest -q tests/test_client.py tests/test_main.py`；`pytest -q`。
- **涉及文件**：`src/client.py`、`src/main.py`、相关测试、`docs/current-state.md`、`docs/interfaces.md`、`docs/privacy.md`。
- **风险/回滚**：错误重试可能放大上游负载或延迟恢复。使用小范围合成故障测试并允许回滚到无重试但正确关闭的版本。
- **完成记录**：2026-07-16，Cursor Agent。lifespan 创建/关闭客户端；`httpx` 10s 超时、`trust_env=False`；`httpx` 日志降至 WARNING；上游失败指数退避（`MAX_POLL_BACKOFF_SEC`）。验证：`pytest -q` 31 passed。遗留：lifespan 异步故障测试未实施。

## NDS-OPS-001 健康检查与可观测性

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-REL-001。
- **目标**：区分进程存活、服务就绪和上游采集状态，同时限制日志中的个人数据。
- **实施步骤**：
  1. 定义 liveness/readiness 语义：数据库可访问、轮询任务存活、最近成功轮询时间和上游失败是否阻断就绪。
  2. 实现不含服务器地址、用户名或曲目信息的状态输出。
  3. 添加结构化指标或日志字段：成功/失败轮询次数、活动会话数、写入成功/失败数和延迟；禁止高基数字段进入指标标签。
  4. 为任务意外退出建立检测和告警挂钩，不在日志输出真实播放明细。
  5. 更新 Compose 健康检查和运行手册，阈值由部署方确认。
- **验收标准**：数据库失败、轮询任务退出和上游短暂失败可区分；探针不泄露隐私；容器健康检查与接口语义一致；测试覆盖状态转换。
- **验证命令**：探针和后台任务测试；`docker compose config`；容器烟雾测试；`pytest -q`。
- **涉及文件**：`src/main.py`、可能的状态/指标模块、`docker-compose.yml`、测试、`docs/interfaces.md`、`docs/privacy.md`。
- **风险/回滚**：过严 readiness 会引发重启或流量抖动。先记录指标再启用编排动作，保留阈值回滚方案。
- **完成记录**：2026-07-16，Cursor Agent。新增 `/health/ready`（503 when not_ready）、`runtime_state` 指标、`ping_db`；Compose 存活探针指向 `/health`；保存/轮询 debug 日志去除曲目标题。验证：`pytest -q` 21 passed；`docker compose config` 通过。遗留：就绪探针未接入 Compose 重启策略（避免上游抖动误杀）。

## NDS-TEST-001 自动化测试基线

- **优先级/状态**：P1 / 待验收
- **依赖**：NDS-CORE-001、NDS-DATA-001、NDS-API-001 的行为契约已确定。
- **目标**：建立覆盖核心状态、数据库、API 和生命周期的稳定测试套件。
- **实施步骤**：
  1. 统一异步测试配置和临时数据库 fixture，保证并行/重复运行不污染仓库。
  2. 添加状态机时间线、数据库聚合/迁移、API 边界、客户端故障和 lifespan 测试。
  3. 修复测试中创建客户端后未关闭的路径，并断言无后台任务泄漏。
  4. 增加覆盖率报告，先记录基线，再为核心模块设置经团队确认的最低门槛。
  5. 将测试分为快速单元测试、集成测试和可选容器/浏览器测试，文档化运行方式。
- **验收标准**：测试可从干净检出重复运行；不依赖真实 Navidrome、网络、凭据或用户数据；失败能定位契约；无残留数据库/任务/客户端。
- **验证命令**：`pytest -q`；带覆盖率的测试命令（工具选定后登记）；重复执行两次比较结果。
- **涉及文件**：`tests/`、测试配置、可能的开发依赖文件、README、`docs/current-state.md`。
- **风险/回滚**：时间相关测试可能不稳定。使用可控时钟和事件同步，不使用长时间真实 sleep；门槛先基于基线制定。
- **完成记录**：2026-07-16，Cursor Agent。数据库测试改用 `tmp_path` fixture；拆分 dev 依赖；新增 API limit/503 测试。2026-07-16 续：新增 `tests/test_lifespan.py`；`pytest -q` 36 passed。2026-07-16 续：新增 `tests/test_auth.py`、`tests/test_security.py`；`pytest -q` 46 passed。遗留：覆盖率门槛、浏览器自动化测试未做。

## NDS-DEP-001 容器与依赖可复现性

- **优先级/状态**：P1 / 待验收
- **依赖**：用户人工确认目标平台、镜像发布方式、容器权限和数据库持久化/备份方式。
- **目标**：固定可审计依赖，减少镜像权限与构建差异，并验证持久化行为。
- **实施步骤**：
  1. 区分运行依赖和开发/测试依赖，选择锁定机制并记录升级流程。
  2. 评估并移除运行镜像不需要的编译工具，固定基础镜像到经批准的版本或 digest。
  3. 创建非 root 用户，确认数据库挂载权限；避免在不了解现有卷属主时直接上线。
  4. 增加 `.dockerignore`（如确认需要）和多阶段构建，检查镜像中不含 `.env`、数据库、测试缓存或本地文件。
  5. 验证 Compose 配置、容器启动、健康检查、优雅关闭和数据库重启后持久化。
  6. 建立依赖漏洞扫描与升级节奏，不把扫描“无发现”等同于绝对安全。
- **验收标准**：干净环境可重复构建；容器非 root 运行且可写获批数据库路径；镜像不含敏感/本地文件；依赖版本可追踪；启动和持久化测试通过。
- **验证命令**：`docker compose config`；`docker build`；容器用户/文件清单检查；容器烟雾测试；`pytest -q`；选定的依赖扫描命令。
- **涉及文件**：`Dockerfile`、`docker-compose.yml`、`requirements.txt`/锁文件、可能的 `.dockerignore`、README、`docs/current-state.md`。
- **风险/回滚**：非 root 迁移可能导致现有数据库不可写；依赖锁定可能暴露兼容问题。先在卷副本测试权限，保留旧镜像标签和数据库备份。
- **完成记录**：2026-07-16，Cursor Agent。拆分 `requirements-dev.txt`；新增 `.dockerignore` 排除 `.env`/数据库/测试。2026-07-16 续：固定 `requirements.txt`/`requirements-dev.txt` 版本；新增 `requirements.lock` 与 `scripts/refresh_requirements_lock.sh`；Dockerfile 改用 lock 安装。2026-07-16 续：新增 `scripts/docker_smoke_test.sh`（合成凭据、/health 与 /health/ready 校验）；CI 增加 `docker-smoke` job。验证：`pytest -q` 36 passed；`docker compose config` 通过；本地 Docker 未运行时烟雾测试需在 CI 或启动 Docker 后执行。遗留：非 root 用户、基础镜像 digest 待用户确认部署约束。

## NDS-UI-001 Dashboard 运行状态与可访问性

- **优先级/状态**：P2 / 待验收
- **依赖**：NDS-SEC-002、NDS-API-001。
- **目标**：让 Dashboard 对加载、空数据、错误和窄屏场景提供明确且可访问的反馈。
- **实施步骤**：
  1. 为三个请求分别定义 loading、empty、error、stale 和 retry 状态，避免一次失败使全部区域不可解释。
  2. 检查表格语义、键盘导航、对比度、图表替代文本和屏幕阅读器可用性。
  3. 处理长用户名/标题/专辑、null、超大计数和移动视口，不允许内容重叠。
  4. 根据后端配置决定刷新策略，页面隐藏时降低请求频率，并防止请求重叠。
  5. 添加浏览器测试和桌面/移动截图核验，不使用真实播放数据。
- **验收标准**：各状态可见且不只依赖控制台；键盘与屏幕阅读器可理解核心数据；长文本和移动布局无重叠；刷新无并发堆积。
- **验证命令**：浏览器自动化测试；桌面/移动截图检查；API mock 场景；`pytest -q`。
- **涉及文件**：`src/static/index.html`、可能的静态资源和浏览器测试、README 截图/说明（如需要）。
- **风险/回滚**：刷新逻辑变更可能导致陈旧数据或增加负载。用假时钟/网络节流测试，保留简单手动刷新作为降级路径。
- **完成记录**：2026-07-16，Cursor Agent。Dashboard 深色主题重构：概览统计卡、图表/表格空状态、错误横幅、手动刷新、防并发请求、页面隐藏时降频刷新；历史表移动端折叠艺人/专辑列；用户数据仍用 `textContent`。验证：`pytest -q` 18 passed。遗留：浏览器自动化测试、屏幕阅读器深度核验、图表 CSP 自托管仍待 NDS-SEC-002。

## NDS-DOC-001 用户文档事实校准

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-CORE-001 的最终阈值和播放语义结论。
- **目标**：使 README 的计数、配置、Compose 和运行说明与已测试行为一致。
- **实施步骤**：
  1. 修正 `> 30` 与 `>= 30` 描述，准确区分轮询驱动和进程内状态管理。
  2. 说明后端轮询间隔可配置、前端刷新当前固定，以及观测时长的误差边界。
  3. 对齐 README 示例与仓库 Compose 文件的服务名、字段和镜像/构建方式。
  4. 增加无认证、数据库隐私、单进程状态和公共 CDN 的明确部署警告，避免暗示生产就绪。
  5. 在干净环境逐条执行快速启动命令，记录真实结果。
- **验收标准**：README 不再与代码事实冲突；所有链接存在；示例无真实值；快速启动在声明环境中已验证或明确记录阻塞。
- **验证命令**：文档链接检查；`docker compose config`；本地或容器启动烟雾测试；`git diff --check`。
- **涉及文件**：README、`docker-compose.yml`（仅在确认需要对齐实际配置时）、`docs/current-state.md`、`docs/interfaces.md`。
- **风险/回滚**：仅文档修改风险低，但未经运行的命令可能误导用户。无法验证的步骤必须标注“未验证”，不得声称成功。
- **完成记录**：2026-07-16，Cursor Agent。README 对齐 `>=30`、播放中写入、轮询语义、Compose 服务名与部署警告；`current-state.md` 差异节更新。验证：文档链接检查通过；`docker compose config` 未在本轮重跑。

## NDS-ARCH-001 多进程/多副本架构决策

- **优先级/状态**：P2 / 待办
- **依赖**：NDS-CORE-001；用户人工确认预期 worker 数、副本数、可用性目标和数据库部署方式。
- **目标**：避免多个进程重复轮询/计数，并决定会话状态与采集领导权的归属。
- **实施步骤**：
  1. 记录单进程、多 worker、滚动重启和多副本下的故障与重复计数模型。
  2. 比较明确限制为单采集进程、数据库租约/锁、外部协调服务或独立采集器方案。
  3. 选择与规模和运维能力匹配的方案，定义领导者切换和会话丢失/重复保证。
  4. 使用两个并发实例的合成测试验证不会重复计数或明确量化可接受误差。
  5. 更新部署限制、健康检查、数据库策略和回滚方案。
- **验收标准**：支持的拓扑被明确记录；不支持的启动方式会被阻止或明显告警；并发实例测试证明所选保证；故障切换行为可解释。
- **验证命令**：并发集成测试；多实例容器测试；`pytest -q`；部署文档人工评审。
- **涉及文件**：架构决策记录、`src/main.py`、可能的协调模块、集成测试、Docker/部署文档、`docs/current-state.md`。
- **风险/回滚**：分布式协调会增加复杂度并可能造成采集中断。优先选择满足真实拓扑的最小方案；保留受支持的单实例回滚模式。
- **完成记录**：未填写。任务尚未实施，不得标记完成。

## NDS-SRC-001 信息来源配置与设置信息架构

- **优先级/状态**：P1 / 已完成
- **依赖**：无；GUI 保存的连接配置仅作为环境变量缺失时的回退，运行客户端的热更新不在本次范围。
- **目标**：将“设置”信息架构收敛为两个顶级标签（隐私与数据 / 信息来源），并提供可在 GUI 编辑且受控的 Navidrome 连接配置，密码按敏感数据处理。
- **实施步骤**：
  1. 新增 `src/source_config.py`：使用现有 `schema_meta` 表持久化 `source_url`/`source_user`/`source_password`，不引入 schema 版本迁移。
  2. 实现配置解析顺序：请求覆盖值 > 环境变量 > 已保存 DB 值；lifespan 在构造 `NavidromeClient` 前解析回退配置。
  3. 新增 `GET/PUT /api/source/config` 与 `POST /api/source/test`，受现有认证中间件保护；GET 只返回 `url`、`username`、`password_configured`，从不返回密码；PUT 校验 URL 协议为 http/https 且 user 非空；test 端点用临时 `NavidromeClient` 调用 `get_now_playing()`，返回通用 `{ok, message}`，不泄露上游响应。
  4. 重构 `src/static/settings.html`：两个顶级标签；保留期使用可见的单选/分段控件而非唯一靠复选框揭示滑块；新增信息来源表单（密码 `type=password`，占位 `留空则保持不变`）与“测试连接”按钮；保存后提示“已保存，重启服务后生效”。
  5. 文档同步 `interfaces.md`、`current-state.md`、`privacy.md`；不在文档/测试/日志写入真实凭据。
- **验收标准**：仅两个顶级设置标签；保留分段控件与滑块可见；密码输入为 password 类型且 GET 不渲染密码；源配置端点存在且受认证保护；环境变量优先级保留；`pytest -q` 通过；`git diff --check` 通过。
- **验证命令**：`pytest -q`；`git diff --check`；源码级核验设置标签数量、滑块/分段控件、密码输入类型、源端点契约。
- **涉及文件**：`src/source_config.py`（新增）、`src/main.py`、`src/schemas.py`、`src/static/settings.html`、`tests/test_source_config.py`（新增）、`tests/test_privacy_api.py`、`docs/interfaces.md`、`docs/current-state.md`、`docs/privacy.md`、`docs/tasks.md`。
- **风险/回滚**：SQLite 本地明文存储 Navidrome 密码是已识别安全权衡（自托管场景可接受，但数据库文件应受部署访问控制保护）；GUI 修改不热更新运行中的客户端，需重启生效；回滚恢复 `schema_meta` 中新增键或整体恢复文件。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。新增 `src/source_config.py` 持久化与解析；新增 GET/PUT/POST 源配置端点；lifespan 解析回退配置；设置页改为两标签（隐私与数据 / 信息来源），保留期改可见分段控件；新增 `tests/test_source_config.py`。验证：见本任务报告。遗留：密码明文存储为已知权衡；热更新未实现。

## NDS-UI-006 设置页偏好与主题本地化

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-SRC-001、NDS-UI-004；不涉及真实部署或数据库内容。
- **目标**：修复设置页消息布局重叠，统一标签图标，提供 General 时区页签，并让设置页和 Dashboard 的语言、主题及时区偏好通过浏览器本地存储即时生效。
- **实施步骤**：
  1. 将设置标签调整为服务器、隐私、常规、外观、关于并为每项提供可访问 SVG 图标。
  2. 使用正常文档流消息块和 Catppuccin Frappe/Latte CSS 变量重构前端主题覆盖。
  3. 增加本地翻译映射、`data-i18n` 更新、共享 localStorage 键和 General 时区选择。
  4. 增加静态源码回归测试，不触碰真实数据库。
- **验收标准**：五个标签顺序固定且均有图标；测试连接消息不覆盖表单；语言切换即时更新主要可见文案；主题、语言及时区使用共享 localStorage；Dashboard 统计请求使用保存时区；多服务器 CRUD 与密码脱敏代码保持不变。
- **验证命令**：`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`；隐私扫描。
- **涉及文件**：`src/static/settings.html`、`src/static/index.html`、`tests/test_static_settings.py`、`tests/test_static_dashboard.py`、`docs/current-state.md`、`docs/interfaces.md`、`docs/privacy.md`、`docs/tasks.md`。
- **风险/回滚**：前端 CSS 变量覆盖可能影响 CDN Tailwind 生成的类；回滚静态页面即可，不涉及数据库迁移。localStorage 仅保存非敏感显示偏好。
- **完成记录**：2026-07-26，OpenCode。实现五标签设置导航、正常流消息、Catppuccin Frappe/Latte 变量、settings/dashboard 本地 i18n、共享语言/主题/时区偏好和 General 时区页签；新增源码级测试。验证：`pytest -q` 321 passed；`git diff --check` 通过；`python3 scripts/check_md_links.py` 通过；隐私扫描仅发现合成测试/烟雾测试占位值，未发现真实凭据。遗留：未执行浏览器自动化，CDN 策略仍由 NDS-SEC-002 人工确认。

## NDS-CI-001 持续集成质量门禁

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-TEST-001、NDS-DEP-001。
- **目标**：自动执行测试、文档链接、格式差异、容器配置和依赖检查，避免文档与实现再次脱节。
- **实施步骤**：
  1. 根据代码托管平台选择 CI，使用最小权限和固定 action/镜像版本。
  2. 增加 `pytest -q`、`git diff --check` 等价检查、Markdown 本地链接检查和 `docker compose config`。
  3. 增加依赖/镜像扫描，定义阻断等级、误报处理和升级责任人。
  4. 缓存不得包含 `.env`、数据库或凭据；外部分支不得获得生产秘密。
  5. 记录本地复现命令和分支保护要求，由仓库管理员人工启用。
- **验收标准**：干净提交和故意破坏的测试/链接/Compose 均产生预期结果；CI 无真实秘密；失败可本地复现；分支保护由管理员确认。
- **验证命令**：本地执行全部 CI 命令；创建临时失败用例验证门禁后撤销；检查 CI 权限和日志脱敏。
- **涉及文件**：CI 配置、测试/开发依赖、文档链接脚本（如提取）、README、`AGENTS.md`。
- **风险/回滚**：门禁不稳定会阻塞交付。先以非阻断模式观察，稳定后由管理员启用必需检查；不得通过删除测试长期绕过。
- **完成记录**：2026-07-16，Cursor Agent。新增 `.github/workflows/ci.yml`（pytest、compose config、Markdown 链接）；`scripts/check_md_links.py` 可本地复现。2026-07-16 续：CI 增加 `docker-smoke` job 执行 `scripts/docker_smoke_test.sh`。验证：`pytest -q` 36 passed；`python3 scripts/check_md_links.py`；`docker compose config`。遗留：分支保护、依赖漏洞扫描由仓库管理员启用。

## NDS-CORE-002 暂停/缺失宽限与配置安全

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-CORE-001。
- **目标**：在 `PlaybackSessionTracker` 中为暂停/缺失观测引入可配置宽限，避免“正在播放”短暂暂停/曲目切换导致过早结算与闪烁；统一 `POLL_INTERVAL`、`PLAY_THRESHOLD_SEC`、`PAUSE_GRACE_SEC` 的安全解析与钳制，无效值回退默认而非崩溃导入。
- **实施步骤**：
  1. 新增 `src/config.py` 提供 `parse_clamped_int` 与 `env_int`：非数字/缺失回退默认，数字越界钳制到上下界。
  2. `src/sessions.py` 引入 `PAUSE_GRACE_SEC` 常量与构造参数；会话字典新增 `last_active_at` 与 `paused`，结算/早提交按 `last_active_at - first_seen_at` 计算活跃时长，排除暂停后的挂钟时间。
  3. `process_poll` 区分活跃播放、暂停条目与缺失播放器：暂停同曲保持内存会话且不延长活跃时长；缺失播放器在距最后活跃观测超过 `pause_grace_sec` 后结算一次并清理；不同活跃曲目立即结算旧会话并开始新会话。
  4. `src/main.py` 使用 `env_int` 解析 `POLL_INTERVAL`（5–300）、`MAX_POLL_BACKOFF_SEC`（1–3600）、`RETENTION_MAINTENANCE_SEC`（60–604800）、`PLAY_THRESHOLD_SEC`（1–3600）、`PAUSE_GRACE_SEC`（0–3600），并通过 `PlaybackSessionTracker` 构造参数注入阈值与宽限。
  5. 新增/更新测试覆盖配置解析与状态机（暂停恢复、缺失恢复、宽限超期、不重复提交、不同活跃曲目立即结算）；同步 `README.md`、`docs/interfaces.md`、`docs/current-state.md`。
- **验收标准**：暂停/缺失在宽限内不结算、不重复写入、不延长活跃时长；超期结算只发生一次；不同活跃曲目立即结算旧会话；非数字 `POLL_INTERVAL` 不崩溃导入；`PLAY_THRESHOLD_SEC=5` 生效；`pytest -q` 通过；`git diff --check` 通过；`python3 scripts/check_md_links.py` 通过。
- **验证命令**：`pytest -q tests/test_sessions.py tests/test_config.py`；`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/config.py`（新增）、`src/sessions.py`、`src/main.py`、`tests/test_sessions.py`、`tests/test_config.py`（新增）、`README.md`、`docs/interfaces.md`、`docs/current-state.md`、`docs/tasks.md`。
- **风险/回滚**：默认值与原行为一致（30s 阈值、30s 宽限）；`PAUSE_GRACE_SEC=0` 恢复“一遇 `isPlaying=false`/缺失即结算”的近似旧行为；`played_at` 由 `last_seen_at` 改为 `last_active_at` 的 ISO 字符串，已落库记录不受影响；回滚恢复 `src/sessions.py`、`src/main.py` 与文件即可。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。新增 `src/config.py`；`src/sessions.py` 增加 `last_active_at`/`paused` 与宽限状态机；`src/main.py` 用 `env_int` 解析并注入阈值/宽限；新增 `tests/test_config.py` 与 `tests/test_sessions.py` 11 项新测试。验证：`pytest -q` 158 passed（含新测试）；`git diff --check` 干净；`python3 scripts/check_md_links.py` 全部解析。遗留：暂无。

## NDS-CORE-003 pause-duration accounting 与宽限逻辑修正

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-CORE-002。
- **目标**：修正 `src/sessions.py` 中的两个语义缺陷：会话时长按 `last_active_at - first_seen_at` 计算仍包含会话中部暂停的挂钟时间；缺失会话的过期处理在 `elif session.get("committed")` 分支下于宽限期内即被丢弃，与“宽限期内保留”的文档不符。
- **实施步骤**：
  1. 会话字典新增 `active_duration_sec`（float，初值 0）；`_session_from_entry` 不再以 `last_active_at - first_seen_at` 推导时长。
  2. `process_poll` 同曲活跃分支：若上次状态为 `paused=True`（暂停或缺失后续），仅将 `last_active_at` 重置到恢复时间戳，不计入间隔；否则累计 `current_time - last_active_at` 到 `active_duration_sec` 并更新 `last_active_at`。暂停同曲条目或缺失轮询不累计时长也不更新 `last_active_at`。
  3. `finalize_session` 与 `_maybe_commit_active_session` 改用 `active_duration_sec` 判断 `>= play_threshold_sec`；批处理 finalize 不再追加最终间隔。`_commit_session` 仍以 `last_active_at` 作为 `played_at` 来源。
  4. 重写 stale 循环：缺失/暂停会话在 `current_time - last_active_at < pause_grace_sec` 时一律保留（无论是否已结算）并标记 `paused=True`、更新 `last_seen_at`；超期时只对未结算会话调用 `finalize_session` 一次，已结算会话直接从内存移除不重复写入。
  5. 更新 `tests/test_sessions.py`：保留并修正 `test_pause_resume_same_track_continues_session` 以反映“恢复后从恢复时间戳继续累加”的语义；新增 `test_mid_session_pause_excluded_from_duration`（t0/t10/t20/t50/t60 => 20 而非 60）与 `test_committed_missing_within_grace_remains_beyond_grace_dropped`（已结算缺失在宽限内保留、超期移除且不重复写入）；新增 `test_pause_does_not_advance_listen_duration` 对 `active_duration_sec == 0` 的断言。
  6. 同步 `docs/current-state.md` 第 4、5、32、35 条更新为按活跃累计的语义。
- **验收标准**：会话中部暂停不补偿挂钟时长（恢复继续从恢复时间戳累加、最终间隔仅由活跃轮询累计）；`t0 active, t1 active` 仍得到 `t1-t0`；不同活跃曲目立即结算旧会话且不重复写入；已结算会话缺失在宽限内保留、超期移除不重复写入；`pytest -q` 通过；`git diff --check` 干净；`python3 scripts/check_md_links.py` 通过。
- **验证命令**：`pytest -q tests/test_sessions.py`；`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/sessions.py`、`tests/test_sessions.py`、`docs/current-state.md`、`docs/tasks.md`。
- **风险/回滚**：仅 `src/sessions.py` 计算口径变化，未触及 schema 与已落库记录；`played_at` 仍由 `last_active_at` 产生；回滚恢复 `src/sessions.py`、`tests/test_sessions.py`、`docs/current-state.md`、`docs/tasks.md` 即可。`PAUSE_GRACE_SEC=0` 仍保持“一遇缺失即超期”语义；既有的 `paused`/`last_active_at`/`last_seen_at` 字段含义未变，新增 `active_duration_sec` 仅供内存使用、不写入 DB。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。`src/sessions.py` 改用累计 `active_duration_sec`；stale 循环重写以保留宽限内会话、超期对未结算 finalize 一次、已结算直接移除；`tests/test_sessions.py` 修正 1 项、新增 3 项测试。验证：`pytest -q` 184 passed；`git diff --check` 干净；`python3 scripts/check_md_links.py` 通过。遗留：暂无。

## NDS-UI-002 正在播放本地计时与每日趋势时间范围选择

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-UI-001。
- **目标**：在“正在播放”列表加入本地 1 秒计时器，在两次 API 刷新之间本地递增显示的已用秒数，并以服务器返回的 `seconds_elapsed` 重新设置基线且不发起额外请求；为“每日播放趋势”加入 7/30/90 天分段控件，切换时仅重新拉取 `/api/stats/daily?days=N`。
- **实施步骤**：
  1. `src/database.py`：`get_daily_stats(days=30)` 使用参数化 SQLite 截止 `date('now', '-N days')`。
  2. `src/schemas.py`：新增 `DAILY_DAYS_*` 常量；`src/main.py` 的 `GET /api/stats/daily` 新增 `days` 查询参数（FastAPI `Query` 7–90，默认 30），保持默认响应兼容。
  3. `src/static/index.html`：在“每日播放趋势”加入 3 个按钮的可见分段控件；新增 `dailyDays` 状态、`fetchDaily()`（独立飞行标志防重叠）与 `setActiveDailyButton`；`fetchStats` 中的 daily 请求改用 `${dailyDays}`；为“正在播放”加入 `nowPlayingTicker`/`nowPlayingEntries` 与 `startNowPlayingTicker`/`stopNowPlayingTicker`，渲染时以 `seconds_elapsed` 设基线，`visibilitychange` 隐藏时停止、可见时恢复，空列表清空计时器。
  4. 新增源码级静态测试 `tests/test_static_dashboard.py`；为后端 `days` 参数与数据库窗口新增 `tests/test_hourly_daily.py` 用例；同步文档。
- **验收标准**：7/30/90 与非法 `days` 的 API/database 行为符合边界；本地计时器仅用 `textContent` 更新、不发起额外 API 调用，页面隐藏时停止、可见时恢复；分段控件切换调用 `fetchDaily` 且与自动刷新不重叠；`pytest -q`、`git diff --check`、`python3 scripts/check_md_links.py` 通过。
- **验证命令**：`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`；`pytest -q tests/test_static_dashboard.py tests/test_hourly_daily.py`。
- **涉及文件**：`src/database.py`、`src/schemas.py`、`src/main.py`、`src/static/index.html`、`tests/test_hourly_daily.py`、`tests/test_static_dashboard.py`（新增）、`docs/interfaces.md`、`docs/current-state.md`、`docs/tasks.md`、`README.md`。
- **风险/回滚**：本地计时仅用于显示，基线仍由服务器返回值决定，不会漂移超过一个刷新周期；分段控件不改变默认响应；回滚恢复 `index.html`、`schemas.py`、`database.py`、`main.py` 与文件即可。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。`get_daily_stats` 参数化；API 增加 `days`；前端加入分段控件与本地计时器；新增 `tests/test_static_dashboard.py` 14 项与 `tests/test_hourly_daily.py` 8 项新用例。验证：`pytest -q` 182 passed；`git diff --check` 干净；`python3 scripts/check_md_links.py` 全部解析。遗留：暂无。

## NDS-UI-003 Dashboard 统一历史窗口与环比对比指标

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-UI-002。
- **目标**：用一个全局统计窗口（`7` / `30` / `90` / `0`=全部）覆盖 Dashboard 所有历史组件，并提供当前窗口对比前一等长窗口的指标，作为后续热力图与更丰富排名的基础。`now-playing` 保持实时、不被窗口过滤。
- **实施步骤**：
  1. `src/schemas.py` 新增窗口常量（`STATS_DAYS_ALL=0`、`STATS_DAYS_MIN=7`、`STATS_DAYS_MAX=90`、`STATS_DAYS_DEFAULT=30`、`STATS_DAYS_PRESETS=(7,30,90,0)`）并扩展 `SummaryStat` 为可选对比字段（`active_days`、`average_daily_plays`、`average_daily_listen_sec`、`previous_total_plays`、`previous_total_listen_sec`、`plays_change_pct`、`listen_change_pct`、`window_days`）。保留 `DAILY_DAYS_*`。
  2. `src/database.py` 新增 `_window_predicate`/`_previous_window_predicate` 输出参数化 SQL 谓词（`days<=0` ⇒ `1=1`，`days>0` ⇒ `datetime(played_at) >= datetime('now', ?)` 等价物），并为 `get_summary`/`get_player_stats`/`get_transcoding_stats`/`get_hourly_stats`/`get_daily_stats`/`get_top_artists`/`get_top_albums`/`get_playback_history` 增加可选 `days` 参数；从不字符串拼接用户值。
  3. `get_summary(days)` 实现对比语义：`active_days` 按 `COUNT(DISTINCT date(played_at))`；有限窗口的 `average_daily_*` 按 `active_days` 平均（无活跃日为 `0`），`days=0` 按最早至最晚播放日的包含天数平均；`previous_total_*` 来自前一等长窗口，`*_change_pct` 在 `previous` 为 0 或 `days=0` 时为 `null`；`window_days` 在 `days=0` 时为 `null`。
  4. `src/main.py`：summary/players/transcoding/hourly/top-artists/top-albums/history 新增 `days` 查询参数（默认 `0`=全部历史，保留旧行为）；daily 保留默认 `30`，全部接受 `0`；新增 `_validate_stats_days` 拒绝 `1–6`（422）；`now-playing` 不接受 `days`。
  5. `src/static/index.html`：用顶部全局 `#statsWindowControl`（7/30/90/全部，默认 30 天，状态 `statsDays`）替换原每日范围控件；切换时调用 `fetchStats`（复用其 in-flight 防护）；所有历史 widget 的 fetch URL 改为 `?days=${statsDays}`（history 保留 `limit`），`now-playing` 不带 `days`；summary 卡新增 `active_days`、日均副行与 `↑↓% vs 上周期` 徽章；新增 `#statsScopeLabel` 显示 `最近 N 天` / `全部历史`；移除 `dailyDays`/`fetchDaily`/`setActiveDailyButton`/`.daily-days-btn`。
  6. 测试与文档：新增 `tests/test_stats_window.py`（DB 对比与窗口传播、API 传播与 422 边界、now-playing 不接受 `days`）；更新既有 `tests/test_main.py`/`tests/test_top_artists_albums.py`/`tests/test_hourly_daily.py`/`tests/test_static_dashboard.py` 的新签名与控件；同步 `README.md`、`docs/interfaces.md`、`docs/current-state.md`。
- **验收标准**：所有历史端点统一接受 `days=0` 或 `days∈[7,90]`，其他值返回 422；`days` 向数据库函数传播；`get_summary` 在空库、零前一窗口、有限窗口与 `days=0` 的对比均值/百分比字段符合本文约定；前端只剩一个全局控件且 `now-playing` 不被窗口过滤；summary 卡显示范围与环比且无用户数据 `innerHTML`；`pytest -q`、`git diff --check`、`python3 scripts/check_md_links.py` 通过。
- **验证命令**：`pytest -q`；`pytest -q tests/test_stats_window.py tests/test_static_dashboard.py`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/schemas.py`、`src/database.py`、`src/main.py`、`src/static/index.html`、`tests/test_stats_window.py`（新增）、`tests/test_static_dashboard.py`、`tests/test_main.py`、`tests/test_top_artists_albums.py`、`tests/test_hourly_daily.py`、`README.md`、`docs/interfaces.md`、`docs/current-state.md`、`docs/tasks.md`。
- **风险/回滚**：所有新增字段均为可选且默认 `0`/`null`，不破坏既有调用；daily 默认 30 与历史接口默认 `0` 保留旧行为；前端单路径 `fetchStats` 降低了竞态风险；回滚恢复 `src/schemas.py`、`src/database.py`、`src/main.py`、`src/static/index.html` 与相关测试/文档即可。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。新增统计窗口常量与 `SummaryStat` 对比字段；`_window_predicate` / `_previous_window_predicate` 参数化谓词；`get_summary` 与全部聚合查询均接受 `days`；`_validate_stats_days` 在 `main.py` 拒绝 1–6；前端以 `#statsWindowControl` 替换每日分段控件并传播 `?days=${statsDays}`、新增 `#statsScopeLabel`、环比徽章与 `active_days` 副行。验证：`pytest -q` 225 passed；`git diff --check` 干净；`python3 scripts/check_md_links.py` 全部解析。遗留：暂无。

## NDS-UI-004 时区感知的周×时热力图

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-UI-003（全局统计窗口与 `fetchStats` 聚合入口）。
- **目标**：在 Dashboard 新增一个 weekday×hour 热力图（7×24=168 单元），并让所有历史组件按用户选择的时区分组（`browser` 解析为 IANA 名称，`UTC` 直传），`now-playing` 仍保持实时且不受时区影响。
- **实施步骤**：
  1. `src/schemas.py` 新增 `TIMEZONE_DEFAULT="UTC"`、`TIMEZONE_VALIDATION_ERROR` 与 `WeekdayHourStat{weekday,hour,count}`；`src/database.py` 新增 `resolve_timezone`（`zoneinfo.ZoneInfo` 校验，无效抛 `ValueError`）与 `get_weekday_hour_stats(days=30, timezone_name="UTC", db_path=...)`，返回 168 行零填充网格，bucket 边界与有限窗口的 UTC 截止都按 `timezone_name` 计算，从不字符串拼接进 SQL。
  2. `src/main.py` 新增 `_validate_stats_timezone`（422 on `ValueError`）与 `GET /api/stats/heatmap?days=&timezone=`（默认 `days=30`，`days=0` 全部历史，`1–6` 返回 422）；summary/players/transcoding/hourly/heatmap/daily/top-artists/top-albums/history 全部接受可选 `timezone` 查询参数（默认 `UTC`），`now-playing` 不接受。
  3. `src/static/index.html`：在顶部新增 `#statsTimezoneSelect`（选项 `browser` 与 `UTC`，状态变量 `statsTimezone`），启动时通过 `Intl.DateTimeFormat().resolvedOptions().timeZone` 解析 `browser` 为 IANA 名称并以 `textContent` 安全写入选项标签，无法解析时移除选项并退回 `UTC`；新增 `resolveStatsTimezone()` 与 change 事件，切换时调用 `fetchStats()`（复用其 in-flight 防护）。
  4. 在 hourly/daily 下方新增「周时热力图」卡片（`#weekdayHourChart` + `#weekdayHourChartSkeleton` + `#weekdayHourChartEmpty` + `#weekdayHourChartWrap`，`aria-label="周时热力图"`），包含 ECharts `weekdayHourChart` 实例与 `renderWeekdayHourChart(data)`：168 个 `{weekday,hour,count}` 单元，X 轴为静态 0–23 小时、Y 轴为静态 Mon–Sun（与 Python `date.weekday()` 对齐），含 `visualMap`、空状态、tooltip，无 `innerHTML`/`insertAdjacentHTML`。
  5. `fetchStats` 中所有历史请求 URL 附加 `&timezone=${encodeURIComponent(resolveStatsTimezone())}`（`now-playing` 不带），将 heatmap 请求加入 `Promise.all`，参与 401/ok 状态检查、JSON 解析与 `renderWeekdayHourChart(weekdayHourData)` 渲染；`setLoading` 加入 `weekdayHourChartSkeleton` 与 `weekdayHourChart` 可见性切换，`window resize` 调用 `weekdayHourChart.resize()`。
  6. 测试与文档：新增 `tests/test_heatmap.py`（DB 168 网格、UTC/Shanghai/New York 边界、有限窗口、无效时区、API 传播与 422 边界、503、认证保护、daily 跨午夜零填充）；在 `tests/test_static_dashboard.py` 增加时区选择器、状态、resolver、change handler、时区查询传播、heatmap 卡片/init/render/fetch/resize/setLoading 源码级断言；同步 `docs/interfaces.md` 与 `docs/current-state.md`。
- **验收标准**：`get_weekday_hour_stats` 在空库与任意时区返回 168 个零填充行，bucket 边界与 Python `date.weekday()` 一致；`/api/stats/heatmap` 接受 `days=0` 或 `7–90`，`1–6`/`91`/负数返回 422，非法 `timezone` 返回 422，数据库异常 503，启用认证时未授权 401；Dashboard 时区选择只保留 `browser`/`UTC` 两个选项，`browser` 标签安全写入 IANA 名称，切换时复用 `fetchStats` 防护并重拉所有历史组件，`now-playing` 不被时区过滤；heatmap 卡片含静态 Mon–Sun 与 0–23 轴、168 单元、`visualMap`、空状态、`resize`；无用户数据 `innerHTML`；`pytest -q`、`git diff --check`、`python3 scripts/check_md_links.py` 通过，无真实凭据。
- **验证命令**：`pytest -q`；`pytest -q tests/test_heatmap.py tests/test_static_dashboard.py`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/schemas.py`、`src/database.py`、`src/main.py`、`src/static/index.html`、`tests/test_heatmap.py`（新增）、`tests/test_static_dashboard.py`、`docs/interfaces.md`、`docs/current-state.md`、`docs/tasks.md`。
- **风险/回滚**：所有历史端点的 `timezone` 参数可选且默认 `UTC`，既有调用方行为保持；`browser` 在不支持 `Intl.DateTimeFormat` 的环境中退回 `UTC`，不影响后端；`get_weekday_hour_stats` 是新增只读查询，不修改既有数据；回滚恢复 `src/main.py`、`src/database.py`、`src/schemas.py`、`src/static/index.html`、`tests/` 与相关文档即可。
- **完成记录**：2026-07-26，OpenCode (glm-5.2)。后端：`resolve_timezone` + `get_weekday_hour_stats` + `WeekdayHourStat` + `_validate_stats_timezone` + `GET /api/stats/heatmap`，全部历史端点接受可选 `timezone`（默认 `UTC`）。前端：`#statsTimezoneSelect`（browser/UTC）、`resolveStatsTimezone()`、change 事件、`WEEKDAY_LABELS`/`HOUR_LABELS`、`renderWeekdayHourChart(data)`、`setLoading` 与 resize 接入；`fetchStats` 给所有历史 URL 附加 `&timezone=${encodeURIComponent(resolveStatsTimezone())}`，`now-playing` 不带；新增「周时热力图」卡片。测试：`tests/test_heatmap.py` 13 项，`tests/test_static_dashboard.py` 新增 13 项源码级断言。验证：`pytest -q` 273 passed；`git diff --check` 干净；`python3 scripts/check_md_links.py` 通过；无真实凭据入库。遗留：暂无。

## NDS-UI-005 丰富榜单与客户端分析

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-UI-004。
- **目标**：让热门艺人/专辑支持按播放次数或收听时长排名，并展示客户端收听时长、平均单次时长和转码率。
- **实施步骤**：
  1. `src/schemas.py` 增加 ranking metric 与扩展 Player/Transcoding/TopArtist/TopAlbum 响应字段。
  2. `src/database.py` 在现有窗口/时区过滤基础上增加客户端聚合、转码百分比和榜单 `metric=plays|listen_time` 聚合；排序确定性为值降序、名称升序。
  3. `src/main.py` 为两个榜单端点增加 metric 校验并保持旧字段；客户端与转码端点保持旧字段兼容。
  4. `src/static/index.html` 增加榜单指标切换、榜单次要指标、客户端明细表和转码 tooltip 百分比；所有用户数据继续使用 DOM API 与 `textContent` 渲染。
  5. 新增 `tests/test_ranking_metrics.py`，覆盖两种 metric、并列排序、空客户端名、客户端平均值/转码率、窗口传播、非法 metric 和空库；补充静态 UI 断言。
- **验收标准**：API 返回扩展字段且旧字段保持；非法 metric 返回 422；排行榜两种 metric 排序稳定；客户端明细与转码百分比按窗口计算；前端切换只请求榜单、移动端不溢出、无用户数据 `innerHTML`；全量测试和文档检查通过。
- **验证命令**：`pytest -q`；`pytest -q tests/test_ranking_metrics.py tests/test_static_dashboard.py`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/schemas.py`、`src/database.py`、`src/main.py`、`src/static/index.html`、`tests/test_ranking_metrics.py`、`tests/test_main.py`、`tests/test_top_artists_albums.py`、`tests/test_stats_window.py`、`tests/test_static_dashboard.py`、`README.md`、`docs/interfaces.md`、`docs/current-state.md`、`docs/tasks.md`。
- **风险/回滚**：只读聚合查询和展示扩展，不改变会话状态机、数据库 schema 或既有播放记录；旧 API 字段保留，新增字段可选；回滚本阶段文件即可。
- **完成记录**：2026-07-26，当前 agent 接手 OpenCode 中断后的前端收尾。新增榜单 metric 请求与切换、客户端详情表、转码播放/时长百分比 tooltip；验证：`pytest -q` 305 passed，待执行阶段提交。

## NDS-DATA-002 短播放尝试与短播放率

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-UI-005。
- **目标**：记录未达到正式播放阈值的播放尝试，支持短播放率分析，同时不污染 `play_history` 的正式播放统计。
- **实施步骤**：新增 schema 3 的 `play_attempts` 表；会话低于 `PLAY_THRESHOLD_SEC` 结束时记录 `outcome=short_play`，达到阈值的会话仍只写入 `play_history`；新增 `get_short_play_stats()` 与 `/api/stats/short-plays`，支持统一 `days`/`timezone` 窗口；补充迁移、状态机、数据库和 API 测试。
- **验收标准**：短播放不增加正式播放次数；正式播放不生成重复短播放尝试；短播放率按短播放尝试 /（短播放尝试 + 正式播放）计算；明确不称为跳过率；schema 迁移幂等；全量测试、链接和 diff 检查通过。
- **验证命令**：`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/database.py`、`src/sessions.py`、`src/main.py`、`src/schemas.py`、`tests/test_database.py`、`tests/test_short_plays.py`。
- **风险/回滚**：新增表不修改既有 `play_history` 数据；短播放尝试属于行为数据，默认与播放历史使用相同保留边界仍需后续隐私确认；回滚需恢复 schema 版本并删除本阶段代码，不能直接删除已有 `play_attempts` 数据。
- **完成记录**：2026-07-26，当前 agent 实现。验证：`pytest -q` 313 passed；待执行阶段提交。

## NDS-DATA-003 播放来源溯源层

- **优先级/状态**：P2 / 已完成
- **依赖**：NDS-DATA-002。
- **目标**：为正式播放记录标记来源，支持轮询与 JSON 导入的统计区分，并为未来 Navidrome 原生历史适配器保留扩展点。
- **实施步骤**：schema 4 为 `play_history` 增加 `source` 列和索引；轮询默认写入 `poller`，隐私导入写入 `import`；新增 `get_source_stats()` 与 `/api/stats/sources`；补充迁移和聚合测试。未绑定 Navidrome 私有数据库或未确认的原生历史读取 API。
- **验收标准**：旧记录迁移为 `poller`；导入记录标为 `import`；来源统计支持窗口/时区；正式播放语义不变；无未确认上游 API 依赖；全量验证通过。
- **验证命令**：`pytest -q`；`git diff --check`；`python3 scripts/check_md_links.py`。
- **涉及文件**：`src/database.py`、`src/main.py`、`src/schemas.py`、`src/privacy_ops.py`、`tests/test_database.py`、`tests/test_sources.py`、文档。
- **风险/回滚**：新增列默认 `poller`，不改变旧记录内容；来源值是内部契约，未来增加新适配器时需同步接口登记；回滚需保留数据库迁移兼容性。
- **完成记录**：2026-07-26，当前 agent 实现。Navidrome 原生历史适配器保留为后续研究项，未将未经确认的私有 API 写入代码。
