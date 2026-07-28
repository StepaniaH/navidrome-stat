# 安全与部署边界

本文记录 Navidrome Statistic 的威胁模型与访问控制策略，不含真实部署地址、账户或令牌值。人工确认的部署细节见 [`privacy.md`](privacy.md)。

## 1. 威胁模型（合成场景）

| 角色 | 能力 | 关注数据 |
| --- | --- | --- |
| 局域网访客 | 可访问未受保护 HTTP 端口 | 用户名、曲名、播放历史 |
| 互联网扫描器 | 可探测公网暴露端口 | 同上 + OpenAPI 结构 |
| 容器编排探针 | 仅访问 `/health` | 无个人数据 |
| 运维人员 | 持有 `STATS_API_TOKEN` 或反向代理凭据 | 全部统计与 Dashboard |

**攻击入口**：未授权 HTTP 读取 `/api/stats/*`、OpenAPI 文档、Dashboard 静态页触发的 API 调用。

**当前不覆盖**：按查看者隔离不同 Navidrome 用户数据；TLS 终止；上游 Navidrome 凭据轮换（由部署方负责）。

## 2. 访问控制策略

### 默认（未设置 `STATS_API_TOKEN`）

- 与历史行为兼容：所有路由可匿名访问。
- **仅适用于可信网络**（本机或受控局域网）。不得直接暴露到公网。

### 启用应用层认证（设置 `STATS_API_TOKEN`）

| 路径 | 策略 |
| --- | --- |
| `/health`、`/health/ready` | 始终公开，供存活/就绪探针使用 |
| `/api/auth/status`、`/api/auth/login` | 公开；login 需正确令牌 |
| `/api/auth/logout` | 公开；清除会话 Cookie |
| `/api/stats/*` | 需 `Authorization: Bearer <token>` 或有效会话 Cookie |
| `/api/privacy/*` | 需认证（与统计 API 相同策略） |
| `/`、`/settings`、`/static/*` | 可加载页面；数据请求仍受 API 保护 |
| `/docs`、`/redoc`、`/openapi.json` | 需认证 |

**反向代理替代方案**：可在代理层统一做 Basic/OIDC 认证，此时可不设置 `STATS_API_TOKEN`，但须确保代理覆盖所有外部入口。

登录失败按客户端地址的进程内 HMAC 摘要限制为 5 次/分钟。摘要使用每次进程启动生成的随机盐，不保存原始地址，也不作为持久化审计日志。该措施只用于降低在线猜测速度，不替代反向代理限流。HTTPS 部署应设置 `SESSION_COOKIE_SECURE=true`；应用无法自动判断代理外部协议。

## 3. 前端与供应链

- 用户数据通过 `textContent` 渲染，服务端不执行 HTML 转义（由浏览器安全插入文本节点）。
- Tailwind CSS 与 ECharts 使用固定版本构建并随应用从 `/static/vendor/` 提供；正常页面加载不依赖公共 CDN。
- CSP 的脚本和样式来源仅允许 `'self'`，并保留当前页面所需的内联脚本/样式许可；同时发送 `X-Content-Type-Options`、`X-Frame-Options` 与 `Referrer-Policy`。
- 合成恶意媒体元数据、服务器筛选和移动视口由 Playwright 浏览器测试覆盖；CI 重新构建本地资产后执行。

## 4. 数据生命周期（隐私）

- 播放历史和短播放尝试默认永久保留；保留策略存于 `schema_meta.retention_days`。
- 设置页 `/settings` 与 `/api/privacy/*` 提供保留预览/清理、按用户导出/导入/删除。
- 删除与过期清理需 `confirm: true`；预览与实际操作统一覆盖两张表，只返回总数与分表条数。
- 导出固定文件名且内容不写入日志；导入限制 5 MiB、10000 条并做字段边界校验。部署方仍须自行管理数据库备份中的残留数据。

## 5. 迁移与回滚

**启用认证**

1. 生成高强度随机 `STATS_API_TOKEN`（勿写入版本控制）。
2. 写入运行环境或 `.env`，重启服务。
3. Dashboard 首次访问时输入令牌；API 客户端使用 Bearer 头。

**回滚**

1. 移除 `STATS_API_TOKEN` 并重启（恢复匿名访问）。
2. 或保留令牌并修复代理/客户端配置，不得长期关闭认证作为生产方案。

## 6. 验证清单

1. 未配置令牌时统计 API 可访问；配置后未授权返回 401。
2. `/health` 在两种模式下均可匿名访问。
3. 合成恶意元数据经 API 原样返回，Dashboard 以文本显示。
4. 响应头包含 CSP 与 `nosniff`。
5. 页面网络请求不包含公共 CDN，移动视口无页面级横向溢出。
6. 登录限流返回 429，HTTPS 部署配置下 Cookie 带 Secure。

对应任务：NDS-SEC-001、NDS-SEC-002、NDS-PRIV-001。
