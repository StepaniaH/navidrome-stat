# Unraid 安装

[English](unraid.md) · [文档目录](README.zh-CN.md)

[Docker Manager 模板](../deploy/unraid/navidrome-stat.xml)使用已发布的 `stepaniah/navidrome-statistic:latest` 镜像，`latest` 随稳定版更新。需要已有一个容器可访问的 Navidrome 服务。Navidrome Stat 通过 API 连接，不需要挂载音乐库、Navidrome 数据库或 Docker socket。仪表盘需要 Tailwind CSS 4 所支持的浏览器：Chrome 111、Safari 16.4、Firefox 128 及以上；更旧的浏览器可能以无样式呈现。

## 准备 appdata

在 Unraid 本机存储上使用专用目录，例如 `/mnt/user/appdata/navidrome-stat`。SQLite 不应放在 SMB 或 NFS 挂载中，也不能与另一个正在运行的实例共用此目录。

镜像以 UID/GID `1000:1000` 运行。首次安装前，在 Unraid 终端中创建归属于该用户和组的目录。以下命令只在路径尚不存在时执行：

```bash
test ! -e /mnt/user/appdata/navidrome-stat && \
  install -d -m 0700 -o 1000 -g 1000 /mnt/user/appdata/navidrome-stat
```

如果选择其他路径，请同时修改这里的路径和模板的 **Appdata** 字段。对于已有目录，先停止应用并备份，再调整所有权，确保 UID/GID `1000:1000` 能读写其中的内容。镜像不处理 `PUID` 或 `PGID` 变量。移动 appdata 时应停止容器，Unraid mover 执行的迁移也一样。

## 从 Community Applications 安装

1. 在 Unraid 中打开 **Apps** 标签页，搜索 **Navidrome Stat**（或直接查看 [Community Applications 页面](https://ca.unraid.net/apps/navidrome-stat-0xfttrp0mywwfl)）。
2. 点击 **Install**，核对下表中的字段，填写足够长的随机 **Administrator token**，然后应用。
3. 如果需要随服务器启动，在 Docker 页面为该容器开启 **Autostart**。

| 字段 | 默认值或操作 |
| --- | --- |
| Repository | `stepaniah/navidrome-statistic:latest` |
| Network | `bridge`，保持特权模式关闭 |
| WebUI | 主机端口 `39421` → 容器端口 `39421/tcp` |
| Appdata | `/mnt/user/appdata/navidrome-stat` → `/data`，读写 |
| Administrator token | 应用前为 `STATS_API_TOKEN` 设置足够长的随机值 |
| Database path | `/data/navidrome_stats.db`，在 Advanced View 中显示 |

如果主机端口已被占用，只修改主机端口，WebUI 快捷入口会使用映射后的端口。管理员 token 必须保持非空：清空它会关闭管理员认证；如果也没有查看者 token，仪表盘和管理 API 将公开可访问。

### 手动安装模板

如果不使用 Community Applications，也可以手动安装模板：

1. 从本仓库下载 [`navidrome-stat.xml`](../deploy/unraid/navidrome-stat.xml)。
2. 将文件放到 Unraid 服务器的 `/boot/config/plugins/dockerMan/templates-user/my-navidrome-stat.xml`。如果已有同名文件，请使用其他文件名，保留原有模板及其设置。
3. 打开 **Docker > Add Container**，从 **Template** 列表选择模板。
4. 核对上表中的字段，填写足够长的随机 **Administrator token**，然后应用。
5. 如果需要随服务器启动，在 Docker 页面为该容器开启 **Autostart**。

Unraid 将保存的容器模板存放在上述目录，参见 [Community Applications 文档](https://docs.unraid.net/community-applications/)。

## 连接 Navidrome

打开容器的 **WebUI**，使用管理员 token 登录，在**设置 > 连接**中添加服务器。填写 URL、用户名和密码，测试连接后保存并启用。其他服务器也按此方式添加。

请使用容器能够访问的地址。`localhost` 指向 Navidrome Stat 容器本身。同一台 Unraid 服务器上的 Navidrome，可以使用服务器可访问的地址及 Navidrome 映射到主机的端口；也可以把两个容器放到同一个自定义 Docker 网络，使用 Navidrome 的容器名及内部端口。默认 `bridge` 网络不提供容器名解析。

模板未设置 `NAVIDROME_*` 环境变量回退连接，默认通过界面保存连接。如果需要仅通过环境变量连接，请按[配置参考](configuration.zh-CN.md)添加全部三个变量，并保持已保存的连接列表为空。

每组来源只运行一个实例。播放器必须向 Navidrome 上报播放活动，安装服务无法还原完整的过去收听历史，详见[采集与统计口径](collection.zh-CN.md)。

## 访问与存储

- Advanced View 中的 **Viewer token** 可启用只读访问，必须使用与管理员 token 不同的随机值。如需限制查看者范围，可添加 `STATS_READ_ONLY_SOURCE_ID` 和/或 `STATS_READ_ONLY_USERNAME`，参见[配置参考](configuration.zh-CN.md)。
- 模板中的 **Protect metrics** 默认为 `true`，访问 `/metrics` 需要管理员认证。
- 远程访问时配置 HTTPS 反向代理，并将 **Secure session cookie** 设为 `true`。直接通过 HTTP 访问时保持 `false`。
- Unraid 会将填写的环境变量保存在容器模板和 Docker 配置中。密码遮罩只隐藏屏幕上的输入内容，请妥善保护保存的模板和启动盘备份。
- Appdata 包含 SQLite 数据库、运行时可能存在的预写日志文件、`secret.key` 和封面缓存。保存的 Navidrome 密码使用该密钥加密。备份整个目录时应停止容器，参见[隐私说明（英文）](privacy.md)和[运维指南](operations.zh-CN.md#备份与恢复)。

## 更新与恢复

1. 阅读[发布说明](https://github.com/StepaniaH/navidrome-stat/releases)，从仪表盘的“关于”信息记录当前版本，然后停止容器。
2. 备份完整 appdata 目录，并私下保存容器设置的副本。
3. 使用 Unraid 的容器更新操作拉取当前 `latest` 镜像，如果容器处于停止状态则启动它。保留 appdata 映射及已配置的 token。
4. 登录后确认版本，检查已保存的连接和历史记录，并确认采集恢复。

如需固定版本，可把 **Repository** 改为已发布标签，例如 `stepaniah/navidrome-statistic:v0.9.5`。Unraid 更新的是已配置标签对应的镜像；固定版本后，需要修改该字段才能切换版本。公开模板的修改不会替换已有安装的设置，采用新字段时请检查保存的容器配置。

如需回滚，停止容器，同时恢复旧镜像标签及更新前与之匹配的 appdata 备份。未经兼容性确认，不要让旧版本直接使用由新版本迁移过的数据库。

## 检查安装

| 检查 | 预期结果 |
| --- | --- |
| 在无痕窗口中打开 WebUI | 需要登录；管理员 token 可打开仪表盘和设置 |
| 请求 `/health` | 返回 `{"status":"ok"}`，仅证明进程存活 |
| 请求 `/health/ready` | 数据库为 `ok`；添加启用的连接之前，就绪状态可能为 `degraded` |
| 添加连接并播放音乐 | 连接成功并开始采集，计数遵循已配置的阈值 |
| 保持 appdata 映射不变，重启或重建容器 | 连接和收听历史仍可使用 |
| 只修改主机端口 | Unraid WebUI 快捷入口打开新的映射端口 |

如果 SQLite 无法打开或密钥文件无法写入，请检查 Appdata 映射和所有权。`/health` 成功不足以证明认证、上游访问、采集或持久化均正常。
