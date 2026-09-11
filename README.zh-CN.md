<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icon-dark.svg">
  <img src="assets/icon.svg" alt="Navidrome Stat" width="140">
</picture>

# Navidrome Stat

<a href="https://www.producthunt.com/products/navidrome-stat/launches/navidrome-stat?embed=true&amp;utm_source=badge-featured&amp;utm_medium=badge&amp;utm_campaign=badge-navidrome-stat" target="_blank" rel="noopener noreferrer"><picture><source media="(prefers-color-scheme: dark)" srcset="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1207528&amp;theme=dark&amp;t=1787616376509"><img alt="Navidrome Stat - A self-hosted service track and display your Navidrome usage | Product Hunt" width="250" height="54" src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1207528&amp;theme=light&amp;t=1787616376509"></picture></a>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker Hub](https://img.shields.io/docker/v/stepaniah/navidrome-statistic/latest?label=Docker&logo=docker&logoColor=white)](https://hub.docker.com/r/stepaniah/navidrome-statistic)
[![Docker Pulls](https://img.shields.io/docker/pulls/stepaniah/navidrome-statistic?logo=docker&logoColor=white)](https://hub.docker.com/r/stepaniah/navidrome-statistic)

<img src="assets/screenshots/dashboard-frappe-top.png" alt="播放统计仪表盘：正在播放、总览、客户端与转码图表" width="640">

</div>

[English](README.md) · [文档](docs/README.zh-CN.md) · [更新记录](CHANGELOG.md)

**为 Navidrome 自托管的收听统计面板。** 把不同客户端和服务器上的播放汇总起来，查看收听历史、详细图表，以及每月或每年的音乐回顾。

Navidrome Stat 采集上报到 Navidrome 服务器的播放活动，将记录保存在 SQLite 中。继续使用你熟悉的 Subsonic 兼容播放器，需要查看统计时打开仪表盘即可。

## 功能

- **统一查看多个客户端和服务器**：正在播放、收听时长、历史记录、客户端使用和转码情况，支持按日期、服务器与用户筛选。
- **看清自己的收听习惯**：艺人、专辑和曲目排行，每日与小时趋势、热力图、详细记录，以及与上一个周期的对比。
- **月度与年度收听回顾**：连续收听天数、热门榜单、常听时段，以及本周期首次记录的曲目。
- **可调整的合作艺人归属**：合作歌手可合并或分别显示，整体播放总数保持一致。
- **管理访问权限和数据**：管理员与只读查看者 token、按服务器或用户限制查看范围、保留期设置，以及按用户导出、导入和删除 JSON 数据。
- **按自己的习惯使用**：七种语言，九个配色家族及对应深浅色、自定义颜色，适配桌面和手机。
- **部署在自己的服务器上**：提供 amd64 与 arm64 Docker 镜像，前端资源本地提供，无使用遥测，可选 ListenBrainz 兼容推送采集。

## 截图

| | |
| --- | --- |
| <img src="assets/screenshots/dashboard-frappe-charts.png" alt="小时、每日与星期 × 小时图表"> | <img src="assets/screenshots/data-relations.png" alt="艺人趋势、时段分布与周期对比"> |
| <img src="assets/screenshots/dashboard-frappe-rankings.png" alt="热门艺人、专辑与服务器统计"> | <img src="assets/screenshots/client-detail.png" alt="客户端详情、收听趋势与热门歌曲"> |
| <img src="assets/screenshots/theme-settings.png" alt="主题模式、调色板与自定义颜色"> | |

## 快速开始

需要 Docker Compose v2，以及容器能够访问的 Navidrome 账号。示例使用当前稳定版 [v0.9.3](https://github.com/StepaniaH/navidrome-stat/releases/tag/v0.9.3)。

新建一个目录，在其中保存下面两个文件。先创建 `.env`，替换示例值，并为仪表盘设置一个足够长的随机 token：

```dotenv
NAVIDROME_URL=https://navidrome.example.invalid
NAVIDROME_USER=example_user
NAVIDROME_PASS=replace-with-your-navidrome-password
STATS_API_TOKEN=replace-with-a-long-random-token
```

再创建 `compose.yaml`：

```yaml
services:
  navidrome-stat:
    image: stepaniah/navidrome-statistic:v0.9.3
    container_name: navidrome-stat
    ports:
      - "39421:39421"
    volumes:
      - navidrome-stat-data:/data
    environment:
      DATABASE_URL: /data/navidrome_stats.db
      NAVIDROME_URL: ${NAVIDROME_URL:?Set NAVIDROME_URL in .env}
      NAVIDROME_USER: ${NAVIDROME_USER:?Set NAVIDROME_USER in .env}
      NAVIDROME_PASS: ${NAVIDROME_PASS:?Set NAVIDROME_PASS in .env}
      STATS_API_TOKEN: ${STATS_API_TOKEN:?Set STATS_API_TOKEN in .env}
    restart: unless-stopped

volumes:
  navidrome-stat-data:
```

在该目录中启动服务：

```bash
docker compose up -d
```

打开 [localhost:39421](http://localhost:39421)，使用 `STATS_API_TOKEN` 登录。更多服务器可在**设置 > 连接**中添加。一旦存在已保存的连接，应用会使用保存的连接列表，替代环境变量中的备用连接。

每组来源只运行一个实例、一个 worker。统计依赖上报到 Navidrome 的播放活动，安装后无法还原完整的过去收听历史。远程访问请配置 HTTPS 反向代理。完整安装方式见[部署指南](docs/deployment.zh-CN.md)，计数规则见[采集说明](docs/collection.zh-CN.md)。

## 文档

| 文档 | 内容 |
| --- | --- |
| [部署指南](docs/deployment.zh-CN.md) | Docker 安装、连接管理、数据存储与运行要求 |
| [配置参考](docs/configuration.zh-CN.md) | 环境变量、默认值与查看者权限 |
| [使用指南](docs/usage.zh-CN.md) | 筛选、详情、收听回顾、主题和语言 |
| [采集与统计口径](docs/collection.zh-CN.md) | 播放阈值、时长质量、历史回填与 ListenBrainz |
| [运维指南](docs/operations.zh-CN.md) | 更新、备份、恢复与故障排查 |
| [隐私说明（英文）](docs/privacy.md) · [安全政策（英文）](SECURITY.md) | 数据存储、访问控制与漏洞报告 |

[文档目录](docs/README.zh-CN.md)还提供艺人归属、图表行为与兼容性说明。版本变化见[变更记录](CHANGELOG.md)。

## 参与贡献与反馈

欢迎提交问题、翻译和代码。[贡献指南](CONTRIBUTING.md)包含开发环境与检查步骤。Bug 与功能建议请提交到 [GitHub Issues](https://github.com/StepaniaH/navidrome-stat/issues)，安全漏洞请按[安全政策](SECURITY.md)私下报告。

## 许可证

[MIT](LICENSE)。随应用分发的 Tailwind CSS 与 Apache ECharts 在 `src/static/vendor/` 中保留各自的许可证和声明。
