# 运维指南

[English](operations.md) · [文档目录](README.zh-CN.md)

## 日志

```bash
docker compose logs -f --tail=100 navidrome-stat
```

发布容器会关闭请求访问日志，避免将应用 URL 中的仪表盘筛选条件、用户名、数据源标识和可分享的艺人或专辑详情名称写入容器日志；应用日志也不会输出播放元数据和上游请求 URL。自定义应用服务器、反向代理与 Navidrome 可能仍有各自的访问日志，分享日志前请检查相关配置。

## 故障排查

| 现象 | 检查项 |
| --- | --- |
| `/health` 正常，但 `/health/ready` 显示降级或未就绪 | 查看 `/health/ready` 中的数据库、采集器、上游与持久化检查；确认至少有一个配置完整且已启用的连接、数据目录可写，并检查容器到 Navidrome 的网络连接。 |
| 已保存的连接没有采集播放活动 | 打开“设置 > 连接”，按诊断结果排查认证、TLS、超时、网络或采集器问题。确认连接已启用；如问题仍存在，再检查 `docker compose logs`。 |
| 反复出现登录页或 API 返回 `401`/`403` | 输入当前管理员或查看者 token。查看者访问设置或其他服务器/用户时返回 `403` 属于预期行为。通过 HTTPS 访问时设置 `SESSION_COOKIE_SECURE=true`；普通 HTTP 保持为 `false`。 |
| SQLite 无法打开或写入 | 确认 `DATABASE_URL` 指向已挂载的数据卷，并确认 UID 和 GID `1000:1000` 对目录和数据库文件具有写权限。 |

## 更新

更新固定版本时，先在 `compose.yaml` 中把镜像标签改为目标版本，再执行下面的命令。保持 `v0.9.3` 不变会继续运行 v0.9.3；`latest` 则跟随最新稳定版。

```bash
docker compose pull
docker compose up -d
```

更新固定版本前，请备份数据卷并阅读变更记录。

## 备份与恢复

数据卷包含收听历史与凭据密钥文件，也可能包含已保存的 Navidrome 凭据。所有备份都应按敏感数据处理。

先停止服务并归档完整数据卷，使数据库与对应的 `secret.key` 始终保存在同一份备份中：

```bash
mkdir -p backups
docker compose stop navidrome-stat
docker run --rm \
  --volumes-from navidrome-stat:ro \
  -v "$PWD/backups:/backup" \
  alpine:3.20 \
  tar -C /data -czf /backup/navidrome-stat-data.tar.gz .
docker compose start navidrome-stat
```

依赖备份前，应先在生产卷之外解压，并对恢复副本执行 SQLite 完整性检查：

```bash
mkdir -p restore-test
docker run --rm \
  -v "$PWD/backups:/backup:ro" \
  -v "$PWD/restore-test:/restore" \
  alpine:3.20 \
  tar -C /restore -xzf /backup/navidrome-stat-data.tar.gz
test -f restore-test/navidrome_stats.db
test -f restore-test/secret.key || echo "此备份中没有凭据密钥"
docker compose run --rm --no-deps \
  -e DATABASE_URL=/restore/navidrome_stats.db \
  -v "$PWD/restore-test:/restore:ro" \
  navidrome-stat \
  python -c "import sqlite3; db = sqlite3.connect('file:/restore/navidrome_stats.db?mode=ro', uri=True); result = db.execute('PRAGMA integrity_check').fetchone()[0]; assert result == 'ok', result; print(result)"
```

恢复生产环境时，应停止服务、保留当前数据卷、把已验证的归档解压到空的替代卷，并确认 UID 和 GID `1000:1000` 可写恢复后的文件。使用原先固定的应用版本启动，验证 `/health/ready` 并测试已保存的连接。若归档中没有 `secret.key`，需要在设置页重新输入密码。不要把归档合并到正在使用或已有内容的数据卷中。

## 安全与隐私

- 两种仪表盘 token 均未设置时，仪表盘数据和管理接口允许匿名访问，只应在可信网络中使用。
- `STATS_API_TOKEN` 授予管理员权限；`STATS_READ_ONLY_TOKEN` 只能读取统计、回顾和相关封面，后端会拒绝设置、连接、导入、保留期、删除、OpenAPI、受保护指标及越界请求。
- 查看者的固定服务器/用户名范围由后端强制执行。按用户名限制后，只会返回包含该用户历史的服务器选项和封面。
- 管理员、查看者与 ListenBrainz 采集 token 必须使用不同值。
- `/health` 与 `/health/ready` 始终公开。`/metrics` 默认公开；设置 token 并启用 `STATS_METRICS_AUTH=true` 后可要求认证。
- `/metrics` 除轮询与持久化健康外，还包含仪表盘构建/缓存、固定子查询耗时与预算超限、SQLite busy 重试、导入耗时和封面缓存指标。
- 启用认证后，仪表盘静态文件仍可加载，但数据请求需要授权。
- 浏览器策略只允许加载本服务的脚本与样式，禁止可执行的内联脚本、嵌入对象和跨域表单目标，同时允许页面所需的内联样式。
- 播放记录默认永久保留；保存 1–360 天的有限策略，即授权服务在启动和后台维护时自动清理超期记录。
- 收集播放活动前应告知受影响的用户，并选择适当的保留期。

详细说明见[隐私文档](privacy.md)与[安全政策](../SECURITY.md)。
