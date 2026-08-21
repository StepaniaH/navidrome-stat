# 后续任务清单

本文件是后续工作的**唯一执行清单**。已完成任务全文见 [`tasks-completed.md`](tasks-completed.md)。产品方向与阶段见 [`roadmap.md`](roadmap.md)；不要在 README 或其他文档再维护一份待办。

代码已完成不等于真实部署的访问、TLS、备份或用户告知已经获得人工验收。

## 状态与执行规则

- 状态流转：`待办 -> 进行中 -> 阻塞/待验收 -> 已完成`；也可标记 `已取消` 并记录原因。
- 领取任务前先核验依赖和当前代码。实施时只修改“涉及文件”及完成任务所必需的文档/测试。
- 完成记录必须填写实际日期、实施者、摘要、验证输出、提交或 PR（如有）和遗留风险。空白记录不能作为完成证据。
- 涉及真实部署、凭据或用户数据的步骤必须先完成 [`privacy.md`](privacy.md) 中对应人工确认。
- 优先级：P0 为上线前安全/数据正确性阻断，P1 为近期可靠性与质量，P2 为演进与维护性。
- 同一时间避免领取多个互不相关的任务。规划只改文档时不得修改业务代码。

## 任务总览

进行中 / 待验收 / 待办：

| ID | 领域 | 优先级 | 状态 | 依赖 |
| --- | --- | --- | --- | --- |
| NDS-DOC-003 | 文档整理与开源路线 | P1 | 已完成 | 无（只读代码与现有文档） |
| NDS-SEC-001 | 访问控制与部署边界 | P0 | 待验收 | 部署方确认访问范围与授权模型 |
| NDS-PRIV-001 | 保留、删除与用户告知 | P0 | 待验收 | 部署方确认告知文案与备份删除责任 |
| NDS-DEP-001 | 容器与依赖可复现性 | P1 | 待验收 | 部署方确认卷权限与备份演练 |
| NDS-UI-001 | Dashboard 运行状态与可访问性 | P2 | 待验收 | NDS-SEC-002（已完成）；剩余见 NDS-UI-010 |
| NDS-OSS-001 | 发布叙事与 about 对齐 | P1 | 已完成 | NDS-DOC-003 |
| NDS-PRIV-002 | 部署方可编辑的用户告知模板 | P1 | 已完成 | 模板已提供；正文仍须部署方审批后使用 |
| NDS-SEC-003 | 匿名观测面收敛 | P1 | 已完成 | 默认保持匿名 `/metrics` 与 OpenAPI 开启 |
| NDS-DEP-002 | 基础镜像 digest 与发布来源 | P2 | 待办 | NDS-DEP-001 |
| NDS-UI-010 | 分区加载状态与读屏核验 | P2 | 待办 | NDS-UI-001 |
| NDS-ARCH-001 | 多进程/多副本架构决策 | P2 | 待办 | 部署方确认拓扑；不在 1.0 范围 |
| NDS-DATA-004 | 原生历史适配器调研 | P2 | 已完成 | 公开接口确认；禁止私有库猜测 |
| NDS-CORE-006 | 认证与空闲轮询正确性 | P1 | 已完成 | 无 |
| NDS-CORE-007 | 采集、窗口、保留与观测正确性 | P1 | 已完成 | 无 |
| NDS-CORE-008 | 导入请求体流式上限 | P2 | 已完成 | 无 |

已完成（全文见档案；ID 保留）：NDS-SEC-002、NDS-CORE-001、NDS-CORE-002、NDS-CORE-003、NDS-CORE-004、NDS-CORE-005、NDS-DATA-001、NDS-DATA-002、NDS-DATA-003、NDS-API-001、NDS-REL-001、NDS-REL-002、NDS-OPS-001、NDS-TEST-001、NDS-DOC-001、NDS-DOC-002、NDS-CI-001、NDS-SRC-001、NDS-UI-002、NDS-UI-003、NDS-UI-004、NDS-UI-005、NDS-UI-006、NDS-UI-007、NDS-UI-008、NDS-UI-009。

## NDS-DOC-003 文档整理与开源版本路线

- **优先级/状态**：P1 / 已完成
- **依赖**：无。只根据仓库代码、测试、公开 git 标签与现有文档整理；不读取真实 `.env`、SQLite、日志、服务器地址、账户或播放元数据。
- **目标**：让文档地图、当前事实、接口登记与任务清单一致；把已完成任务移出执行面；写出开源 0.x / 1.0 / 后续演进路线；补齐贡献、安全报告与变更记录入口。不修改业务代码。
- **实施步骤**：
  1. 通读 `src/`、`tests/`、容器与 CI，对照 `docs/current-state.md`、`docs/interfaces.md`、`docs/privacy.md`、`docs/security.md` 登记差异。
  2. 将已完成任务全文移至 `docs/tasks-completed.md`，在本文件只保留可执行项与总览。
  3. 新增 `docs/roadmap.md`，用任务 ID 引用后续工作，不建立平行清单。
  4. 新增根目录 `CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md` 与 issue/PR 模板；所有示例使用占位符。
  5. 更新 `AGENTS.md`、`docs/README.md` 与双语 README 的文档索引。
  6. 隐私扫描本次将进入 git 的文本；运行链接检查与 `git diff --check`。
- **验收标准**：文档地图列出全部现行文档且相对链接可解析；接口漏登项已补；任务总览含 NDS-CORE-003；路线图不包含真实部署值；业务代码无改动；验证命令通过。
- **验证命令**：`.venv/bin/python scripts/check_md_links.py`；`git diff --check`；`git diff --stat`；敏感值扫描（本次 diff，不含 `.env`/数据库）。
- **涉及文件**：`docs/`、`AGENTS.md`、`README.md`、`README.zh-CN.md`、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`、`.github/ISSUE_TEMPLATE/`、`.github/PULL_REQUEST_TEMPLATE.md`、`.github/FUNDING.yml`。
- **风险/回滚**：仅文档与仓库元数据；回滚本提交即可。不改变运行时、schema 或认证行为。
- **完成记录**：2026-08-21，Cursor Agent。基于 `src/`、`tests/`、Dockerfile/CI 与公开 git 标签整理文档，未改业务代码。已完成任务全文移至 `docs/tasks-completed.md`；补登 `GET /api/stats/servers`、匿名 `/metrics`、`project_url=null`、Compose 环境变量注入范围；核销过期遗留（热更新、非 root）。新增 `docs/roadmap.md`（0.x / 1.0 / 后续演进，引用任务 ID）、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`、issue/PR 模板。验证：`scripts/check_md_links.py` 通过；`git diff --check` 通过；对新增文档做敏感值扫描，无真实邮箱/token/播放明细；`.venv/bin/python -m pytest -q` 为 `390 passed`（文档变更的回归基线）；`docker compose config` 因本环境无 Docker 二进制为环境阻塞。未创建业务功能 PR 之外的代码改动。遗留：GitHub 私有漏洞报告是否启用、用户告知正文、真实部署 TLS/访问范围仍须仓库所有者确认（NDS-SEC-001 / NDS-PRIV-001 / NDS-PRIV-002）。FUNDING 仅保留仓库中已有的公开 ko-fi 用户名。

## NDS-OSS-001 发布叙事与 about 对齐

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-DOC-003。不把真实 Docker Hub 凭据或私有邮箱写入仓库。
- **目标**：让 git 标签、CHANGELOG、GitHub Release 与 `/api/about` 描述同一版本；补上公开项目 URL（仅使用已公开的 GitHub 仓库地址）。
- **实施步骤**：
  1. 确认 `APP_VERSION` 与即将发布的标签一致；未发布提交保留 `-dev` 后缀。
  2. 为 `/api/about` 的 `project_url` 提供稳定公开地址或继续显式为 `null` 并在接口文档写明。
  3. 用现有 `v*` 工作流打标签时同步创建 GitHub Release 说明（可摘自 CHANGELOG）。
  4. 文档说明 `v0.5.0` 与 `v0.5.3` 指向同一提交，钉扎镜像时避开该歧义。
- **验收标准**：一次标签发布后，镜像标签、CHANGELOG 标题与 about 版本一致；文档无真实凭据。
- **验证命令**：`pytest -q tests/test_about.py`；`python3 scripts/check_md_links.py`；`git diff --check`。
- **涉及文件**：预计 `src/version.py`、`src/main.py`、`CHANGELOG.md`、`.github/workflows/docker-publish.yml`、`docs/interfaces.md`。
- **风险/回滚**：about 增加公开仓库 URL 不是敏感值；版本字符串变化只影响展示。回滚代码与文档即可。
- **完成记录**：2026-08-21，Cursor Agent。`project_url` 改为公开仓库地址常量；tag `v*` 在镜像推送成功后创建 GitHub Release。`APP_VERSION` 仍为 `0.7.0-dev`。未打新版本标签。验证：`.venv/bin/python -m pytest -q tests/test_about.py` 通过；全量 `.venv/bin/python -m pytest -q` 为 `396 passed`。提交 `584be4d`、`56bc852`，PR #27。遗留：真正打 `v0.8.0` 标签仍由仓库所有者触发。

## NDS-PRIV-002 部署方可编辑的用户告知模板

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-PRIV-001。告知正文必须由部署方审批；AI 不得代填机构名、法规名称或承诺条款。
- **目标**：提供一份不含真实用户与地址的告知草稿，部署方复制后自行编辑。
- **实施步骤**：
  1. 在 `docs/` 增加模板，只描述本服务会轮询正在播放、将用户名与曲目写入本地 SQLite、默认永久保留、可导出/删除。
  2. 所有机构名、联系方式和保留期填空，标为「需用户人工确认/编辑」。
  3. README 链接该模板并声明它不是法律意见。
- **验收标准**：模板无真实个人数据；空白项未被猜测填入；隐私文档交叉引用。
- **验证命令**：`python3 scripts/check_md_links.py`；`git diff --check`。
- **涉及文件**：预计 `docs/privacy-notice.template.md`、`docs/privacy.md`、README。
- **风险/回滚**：仅文档。不得把模板写成已生效的合规声明。
- **完成记录**：2026-08-21，Cursor Agent。新增 `docs/privacy-notice.template.md`，空白项均标「需用户人工确认/编辑」，未填写机构、法规或联系方式。双语 README 与 `docs/privacy.md` 已链接并声明非法律意见。验证：`.venv/bin/python scripts/check_md_links.py` 通过。提交 `56bc852`，PR #27。遗留：部署方编辑后的文本不得提交含真实个人信息的版本；NDS-PRIV-001 仍待验收。

## NDS-SEC-003 匿名观测面收敛

- **优先级/状态**：P1 / 已完成
- **依赖**：NDS-SEC-001。不改变未设置 `STATS_API_TOKEN` 时的可信网络匿名模式，除非部署方确认新的安全默认值。
- **目标**：让 `/metrics` 与 FastAPI OpenAPI 路由的匿名暴露成为可配置行为，并登记兼容策略。
- **实施步骤**：
  1. 记录当前事实：`AUTH_EXEMPT_PATHS` 含 `/metrics`；`/docs`、`/redoc`、`/openapi.json` 在启用令牌时需认证。
  2. 增加可选配置（环境变量）以要求指标认证或关闭 OpenAPI 路由；默认保持现有行为。
  3. 测试匿名、令牌、关闭文档三种组合；错误响应不泄露内部路径。
  4. 更新 `docs/security.md` 与 `docs/interfaces.md`。
- **验收标准**：默认兼容；开启新选项后未授权无法读指标或 OpenAPI；文档说明探针仍用 `/health`。
- **验证命令**：`pytest -q tests/test_auth.py tests/test_metrics.py tests/test_security.py`；`pytest -q`；`git diff --check`。
- **涉及文件**：预计 `src/main.py`、`src/auth.py`、相关测试、`docs/security.md`、`docs/interfaces.md`。
- **风险/回滚**：错误默认值会让现有 Prometheus 抓取失败。新选项默认关闭（保持匿名 `/metrics`）可回滚。
- **完成记录**：2026-08-21，Cursor Agent。新增 `STATS_METRICS_AUTH`（默认 false）与 `OPENAPI_ENABLED`（默认 true）。启用令牌且打开指标认证时，未授权 `/metrics` 返回 401。关闭 OpenAPI 后 `/docs` 与 `/openapi.json` 为 404。仓库 Compose 补齐 `SESSION_COOKIE_SECURE` 等注入。验证：`.venv/bin/python -m pytest -q` 为 `396 passed`；`.venv/bin/ruff check .` 通过；`.venv/bin/python scripts/check_md_links.py` 通过。提交 `584be4d`、`56bc852`，PR #27。遗留：公网部署是否打开 `STATS_METRICS_AUTH` 仍由部署方决定。

## NDS-CORE-006 认证与空闲轮询正确性

- **优先级/状态**：P1 / 已完成
- **依赖**：无。不改变认证默认值，不要求部署方确认。
- **目标**：修复已能从代码证明的错误：非 ASCII 凭据使 `compare_digest` 抛错变成 500；登出 Cookie 未带与登录相同的 Secure/HttpOnly 属性；上游 `status=ok` 且 `nowPlaying` 为 null 被当成轮询失败。
- **实施步骤**：
  1. 认证比较改为 UTF-8 字节的恒定时间比较；登出删除 Cookie 时使用与登录相同的 path/Secure/HttpOnly/SameSite。
  2. 轮询在 `status=ok` 时把缺失或非对象的 `nowPlaying` 当作无人播放。
  3. 测试：非 ASCII Cookie/Bearer 返回 401、小写 `bearer`、Secure 登出、`nowPlaying: null` 记成功空轮询。
  4. 更新接口/安全文档中受影响的行为描述。
- **验收标准**：上述输入不再 500；空闲 ok 响应不增加 poll failure；默认匿名模式不变；验证命令通过。
- **验证命令**：`.venv/bin/python -m pytest -q tests/test_auth.py tests/test_polling_integration.py tests/test_client.py`；`.venv/bin/python -m pytest -q`；`.venv/bin/ruff check .`；`git diff --check`。
- **涉及文件**：`src/auth.py`、`src/main.py`、`src/client.py`、相关测试、`docs/interfaces.md`、`docs/security.md`、`docs/current-state.md`、`CHANGELOG.md`、本文件。
- **风险/回滚**：只收紧错误路径与空闲轮询解释。回滚本提交即可。
- **完成记录**：2026-08-21，Cursor Agent。认证改为 UTF-8 字节恒定时间比较；Bearer 方案名大小写不敏感；登出删除 Cookie 使用与登录相同的 path/HttpOnly/SameSite/Secure。`status=ok` 且 `nowPlaying` 为 null 记空闲成功。验证：`.venv/bin/python -m pytest -q` 为 `402 passed`；`.venv/bin/ruff check .` 通过；`.venv/bin/python scripts/check_md_links.py` 通过。提交 `2560449`，PR #27。遗留：未改变默认匿名模式。

## NDS-CORE-007 采集、窗口、保留与观测正确性

- **优先级/状态**：P1 / 已完成
- **依赖**：无。不改变认证默认值，不钉扎镜像 digest，不引入多副本。
- **目标**：修复已能从代码证明的错误：collector 替换在 finalize 失败后停掉采集且不拉起新任务；预设 `days` 的上一窗口在 DST 下偏离本地午夜；保留清理用字符串比较 `played_at`；上游成功但落库失败被记成轮询失败并退避；`/metrics` 的 polling-up 与就绪探针 `all` 语义不一致；客户端饼图 tooltip 把 `client_name` 当 HTML。
- **实施步骤**：
  1. `replace`/`reconcile` 在旧 collector 拆除后仍启动替换；finalize 失败只记录脱敏错误，不把采集器集合留空。
  2. 预设窗口的上一周期改为本地日历日，与自定义日期范围一致。
  3. 保留预览/删除使用 `datetime(played_at)`，cutoff 格式与统计窗口相同。
  4. 上游 `status=ok` 后先记 poll success；落库失败走 save 计数，不增加 poll 退避。
  5. `polling_task_alive` 与就绪探针一样要求全部 collector 任务存活。
  6. Dashboard 对 ECharts HTML tooltip 中的动态名称做转义。
- **验收标准**：对应测试覆盖上述路径；默认匿名访问不变；无 schema 变更。
- **验证命令**：`.venv/bin/python -m pytest -q tests/test_collector_manager.py tests/test_stats_window.py tests/test_privacy_ops.py tests/test_polling_integration.py tests/test_metrics.py tests/test_static_dashboard.py`；`.venv/bin/python -m pytest -q`；`.venv/bin/ruff check .`；`git diff --check`。
- **涉及文件**：`src/collector_manager.py`、`src/database.py`、`src/privacy_ops.py`、`src/main.py`、`src/runtime_state.py`、`src/metrics.py`、`src/static/index.html`、相关测试、`docs/interfaces.md`、`docs/current-state.md`、`docs/security.md`、`CHANGELOG.md`、本文件。
- **风险/回滚**：替换失败时 HTTP 不再因旧会话 finalize 失败而 503（配置已应用）。回滚本提交即可。
- **完成记录**：2026-08-21，Cursor Agent。`replace`/`reconcile` 在旧会话 finalize 失败后仍启动新 collector；预设上一窗口改为本地日历日；保留预览/删除使用 `datetime(played_at)`；上游 `status=ok` 后落库失败只记 save/脱敏错误，不增加 poll failure 或退避；`polling_task_alive` 与就绪探针一样要求全部 collector 任务存活；客户端饼图 HTML tooltip 转义 `client_name`。无 schema 或认证默认值变更。验证：`.venv/bin/python -m pytest -q tests/test_collector_manager.py tests/test_stats_window.py tests/test_privacy_ops.py tests/test_polling_integration.py tests/test_metrics.py tests/test_static_dashboard.py` 通过；全量 `.venv/bin/python -m pytest -q` 为 `406 passed`；`.venv/bin/ruff check .` 通过；`.venv/bin/python scripts/check_md_links.py` 通过；`git diff --check` 通过。提交 `380c4ce`、`ae7c80c`，PR #27。遗留：请求体 5 MiB 上限仍只作用在 `Content-Length` 与已缓冲 JSON，见 NDS-CORE-008。DST 验证使用合成 `America/New_York` 2024-03-12，不是生产时区配置。

## NDS-CORE-008 导入请求体流式上限

- **优先级/状态**：P2 / 已完成
- **依赖**：无。不改变认证默认值；不放宽 5 MiB / 10000 条校验。
- **目标**：让隐私导入的 5 MiB 上限在缺少 `Content-Length`（例如 chunked）时仍然在读取请求体过程中生效，而不是只在 JSON 已全部进入内存后由 `json.dumps` 再量一次。
- **实施步骤**：
  1. 核验 `security_headers_middleware` 仅在存在 `Content-Length` 时提前 413，以及 `import_user_data` 对已解析 payload 的二次长度检查。
  2. 在 ASGI `receive` 路径对 `/api/privacy/users/{username}/import` 累计已读字节，超过 `IMPORT_MAX_PAYLOAD_BYTES` 返回 413 并停止继续读取。
  3. 测试：带过大 `Content-Length` 仍 413；省略 `Content-Length` 的超限 body 也 413；合法小 payload 仍 200。错误响应不含请求体或用户名以外的路径细节。
  4. 更新 `docs/interfaces.md` 兼容说明：仍是 5 MiB，只是执行点前移。
- **验收标准**：缺少 `Content-Length` 的超限导入不会把完整 body 交给 JSON 解析；默认匿名模式不变；无 schema 变更。
- **验证命令**：`.venv/bin/python -m pytest -q tests/test_privacy_api.py tests/test_privacy_ops.py`；`.venv/bin/python -m pytest -q`；`.venv/bin/ruff check .`；`git diff --check`。
- **涉及文件**：`src/request_limits.py`、`src/main.py`、`tests/test_request_limits.py`、`tests/test_privacy_api.py`、`docs/interfaces.md`、`docs/current-state.md`、`docs/security.md`、`docs/privacy.md`、`CHANGELOG.md`、本文件。
- **风险/回滚**：错误截断合法流式客户端。保留 JSON 层二次校验作为回滚安全网。
- **完成记录**：2026-08-21，Cursor Agent。新增 `PrivacyImportBodyLimitMiddleware`：导入 POST 按实际已读字节累计，超过 `IMPORT_MAX_PAYLOAD_BYTES` 或非法/`Content-Length` 过大时返回 413，并排空剩余 chunk，不调用 `import_user_data`。合法小于上限的分块请求仍 200。JSON 层 `json.dumps` 检查保留。无 schema 或认证默认值变更。验证：`.venv/bin/python -m pytest -q tests/test_privacy_api.py tests/test_privacy_ops.py tests/test_request_limits.py` 通过；全量 `.venv/bin/python -m pytest -q` 为 `414 passed`；`.venv/bin/ruff check .` 通过；`.venv/bin/python scripts/check_md_links.py` 通过；`git diff --check` 通过。提交 `7a7e8e3`，PR #27。遗留：上限只作用于隐私导入路径，其他 POST 仍无通用请求体封顶。

## NDS-DEP-002 基础镜像 digest 与发布来源

- **优先级/状态**：P2 / 待办
- **依赖**：NDS-DEP-001 的部署约束确认。
- **目标**：生产 Dockerfile 钉扎 `python:3.11-slim` digest，并在文档中说明如何验证镜像来源。
- **实施步骤**：
  1. 记录当前 builder/runner 使用浮动标签 `python:3.11-slim`。
  2. 选择经部署方确认的 digest；更新 Dockerfile 与刷新说明。
  3. 确认 CI docker-smoke 与多架构发布仍通过。
- **验收标准**：Dockerfile 含 digest；刷新步骤可从仓库根目录执行；不含 registry 凭据。
- **验证命令**：`docker compose config`；CI docker-smoke（或记录环境阻塞）；`git diff --check`。
- **涉及文件**：`Dockerfile`、README、`docs/current-state.md`。
- **风险/回滚**：过期 digest 会阻断构建。保留浮动标签回滚路径。
- **完成记录**：未填写。

## NDS-UI-010 分区加载状态与读屏核验

- **优先级/状态**：P2 / 待办
- **依赖**：NDS-UI-001。只使用合成 API 数据。
- **目标**：补齐 NDS-UI-001 仍未验收的部分：图表/表格分区的独立 loading-empty-error，以及键盘与读屏可理解性。Playwright 合成回归和 CSP 自托管已由后续任务完成，不重复当作缺口。
- **实施步骤**：
  1. 对照 Dashboard 各卡片，确认单请求失败不会让全部区域失去含义。
  2. 为图表补充可见的文本替代或 `aria` 摘要（不使用真实曲目）。
  3. 扩展 Playwright：空数据、401、部分失败、390px 无横向溢出。
- **验收标准**：分区状态可区分；无用户数据 `innerHTML`；合成浏览器测试通过。
- **验证命令**：`.venv/bin/python -m pytest -q tests/test_static_dashboard.py`；`npx playwright test`；`git diff --check`。
- **涉及文件**：`src/static/index.html`、`tests/e2e/dashboard.spec.js`、`tests/test_static_dashboard.py`、`docs/current-state.md`。
- **风险/回滚**：仅前端与测试。回滚静态文件即可。
- **完成记录**：未填写。

## NDS-DATA-004 原生历史适配器调研

- **优先级/状态**：P2 / 已完成
- **依赖**：公开接口确认；禁止私有库猜测。不读取真实 `.env`、SQLite、日志、服务器地址或播放明细。
- **目标**：只依据公开 Subsonic / OpenSubsonic / Navidrome 文档，判断能否在不扩大隐私面的前提下导入上游收听历史。结论写入当前事实与接口登记。不实现适配器。
- **实施步骤**：
  1. 只依据公开规范与本仓库已登记的 `getNowPlaying` / OpenSubsonic 扩展列出候选接口。
  2. 对每个候选标记稳定性：稳定 / 待确认；待确认项列出验证步骤。
  3. 若无公开接口，将本任务标为完成（结论：不实施）并关闭该方向，直到接口公开。
- **验收标准**：文档结论可被源码外的公开链接或「无公开接口」证明；无真实库路径；无业务代码。
- **验证命令**：`python3 scripts/check_md_links.py`；`git diff --check`。
- **涉及文件**：`docs/current-state.md`、`docs/interfaces.md`、本文件。
- **风险/回滚**：调研文档若被误当成承诺，会误导实现。必须使用「待确认」或「不实施」。
- **完成记录**：2026-08-21，Cursor Agent。对照公开 [Subsonic API](https://www.subsonic.org/pages/api.jsp)、[OpenSubsonic Endpoints](https://opensubsonic.netlify.app/docs/endpoints/)（当日抓取完整列表）、[Navidrome Subsonic compatibility](https://www.navidrome.org/docs/developers/subsonic-api/)、[Navidrome Scrobbling](https://www.navidrome.org/docs/usage/features/scrobbling/)。公开规范无只读播放历史方法；`scrobble`/`reportPlayback` 为写入；专辑/收藏/队列/曲目 `playCount` 不是事件日志。Navidrome 0.59+ 内部 listen 历史未提供公开 HTTP。结论：**不实施**适配器，不读取私有库或内部表。无业务代码、无 schema/环境变量/本服务 API 变更。验证：`python3 scripts/check_md_links.py`；`git diff --check`。提交与 PR 见本轮记录。遗留：若上游日后发布公开只读历史 API，新建任务再评估，不复活本 ID。

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
- **涉及文件**：`src/auth.py`、`src/main.py`、`tests/test_auth.py`、`docs/security.md`、README。
- **风险/回滚**：可能中断现有 Dashboard 或探针访问。保留原部署配置备份；不得通过长期关闭认证解决故障。
- **完成记录**：2026-07-16，Cursor Agent。新增可选 `STATS_API_TOKEN`（Bearer + 会话 Cookie 登录）；`/health` 保持公开；威胁模型见 `docs/security.md`；新增 `tests/test_auth.py`。验证：`pytest -q` 46 passed。
- **后续核验（2026-08-21）**：应用层认证、登录限流与 Secure Cookie 已在代码中。`/metrics` 仍匿名（见 NDS-SEC-003）。按查看者隔离、TLS 终止、反向代理示例仍须部署方确认后才能把本任务改为已完成。默认匿名模式不得称为公网安全。

## NDS-PRIV-001 保留、删除与用户告知

- **优先级/状态**：P0 / 待验收
- **依赖**：用户人工确认政策依据、被监控用户告知方式、保留期、导出/删除责任人和备份处理。
- **目标**：让播放行为数据具有明确生命周期和可审计的数据请求流程。
- **实施步骤**：见档案中的原始步骤；代码侧预览/导出/导入/删除已落地。
- **验收标准**：政策决定有责任人；dry-run 可显示将影响的数量而不暴露内容；导出/删除测试可复现；备份中的删除限制有明确说明；用户告知文本由用户审批。
- **验证命令**：针对合成数据库的保留/导出/删除测试；`pytest -q`；隐私文档人工验收。
- **涉及文件**：`src/privacy_ops.py`、`docs/privacy.md`、设置页。
- **风险/回滚**：删除不可逆且可能与备份冲突。强制 dry-run、事务和执行前备份。
- **完成记录**：2026-07-16，Cursor Agent。用户确认默认永久保留、1–360 天、按用户导出/导入、预览+确认。实现隐私 API 与 schema v2。
- **后续核验（2026-08-21）**：预览/清理已覆盖 `play_history` 与 `play_attempts`，导出格式版本 2。仍待部署方：正式告知文案、备份副本删除、用户名变更后的身份策略。工程模板见 NDS-PRIV-002。

## NDS-DEP-001 容器与依赖可复现性

- **优先级/状态**：P1 / 待验收
- **依赖**：用户人工确认目标平台、镜像发布方式、容器权限和数据库持久化/备份方式。
- **目标**：固定可审计依赖，减少镜像权限与构建差异，并验证持久化行为。
- **实施步骤**：见完成记录；digest 钉扎改由 NDS-DEP-002 跟踪。
- **验收标准**：干净环境可重复构建；容器非 root 运行且可写获批数据库路径；镜像不含敏感/本地文件；依赖版本可追踪。
- **验证命令**：`docker compose config`；`docker build`；`scripts/docker_smoke_test.sh`；`pytest -q`。
- **涉及文件**：`Dockerfile`、`docker-compose.yml`、`requirements.lock`、`.dockerignore`。
- **风险/回滚**：非 root 迁移可能导致现有数据库不可写。先在卷副本测试权限。
- **完成记录**：2026-07-16 起分步完成 lock 文件、多阶段镜像、CI smoke。
- **后续核验（2026-08-21）**：Dockerfile 已使用 `appuser` UID 1000，Compose 示例 `user: "1000:1000"`；「非 root 未做」的旧遗留作废。仍待部署方验收真实卷属主、备份恢复，以及是否钉扎基础镜像 digest（NDS-DEP-002）。仓库 Compose 只把列出的变量传入容器；未列出的键即使写在 `.env` 也不会自动成为容器环境变量。

## NDS-UI-001 Dashboard 运行状态与可访问性

- **优先级/状态**：P2 / 待验收
- **依赖**：NDS-SEC-002、NDS-API-001。
- **目标**：让 Dashboard 对加载、空数据、错误和窄屏场景提供明确且可访问的反馈。
- **验收标准**：各状态可见且不只依赖控制台；键盘与屏幕阅读器可理解核心数据；长文本和移动布局无重叠；刷新无并发堆积。
- **验证命令**：`npx playwright test`；`pytest -q tests/test_static_dashboard.py`。
- **涉及文件**：`src/static/index.html`、`tests/e2e/`。
- **风险/回滚**：刷新逻辑变更可能导致陈旧数据或增加负载。
- **完成记录**：2026-07-16，Cursor Agent。空状态、错误横幅、手动刷新、隐藏降频。
- **后续核验（2026-08-21）**：Playwright 合成回归、CSP 自托管、自定义 listbox 与移动布局已由 NDS-SEC-002 / NDS-UI-007–009 覆盖。本任务剩余不可声称完成的部分移交 NDS-UI-010（分区失败态与读屏）。在 NDS-UI-010 验收前保持待验收，避免把「有浏览器测试」等同于读屏完成。

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
- **验收标准**：支持的拓扑被明确记录；不支持的启动方式会被阻止或明显告警；并发实例测试证明所选保证。
- **验证命令**：并发集成测试；多实例容器测试；`pytest -q`；部署文档人工评审。
- **涉及文件**：架构决策记录、`src/main.py`、可能的协调模块、集成测试、Docker/部署文档、`docs/current-state.md`。
- **风险/回滚**：分布式协调会增加复杂度。优先选择满足真实拓扑的最小方案；保留单实例回滚。
- **范围说明（2026-08-21）**：开源 1.0 继续承诺单实例。未确认拓扑前不实施本任务。
- **完成记录**：未填写。任务尚未实施，不得标记完成。
