# 文档目录

[English](README.md) · [项目简介](../README.zh-CN.md)

## 安装与运行

- [Docker 部署](deployment.zh-CN.md)：安装发布镜像、连接服务器、持久化数据。
- [配置参考](configuration.zh-CN.md)：环境变量、默认值与访问 token。
- [运维指南](operations.zh-CN.md)：更新、备份、恢复与故障排查。

## 查看与管理收听数据

- [使用指南](usage.zh-CN.md)：筛选、排行、详情、收听回顾与外观。
- [采集与统计口径](collection.zh-CN.md)：播放阈值、时长质量、历史回填与 ListenBrainz 采集。
- [艺人归属（英文）](artist-attribution.md)：合作艺人的合并与分别计数。
- [图表与详情（英文）](data-relations.md)：分组、对比周期与统计范围。
- [隐私说明（英文）](privacy.md)：数据存储、保留期、归档、凭据与浏览器行为。

## 项目参考

- [兼容性政策（英文）](compat.md)
- [变更记录（英文）](../CHANGELOG.md)
- [安全政策（英文）](../SECURITY.md)
- [贡献指南（英文）](../CONTRIBUTING.md)
- [添加界面语言（英文）](translations.md)

应用运行后可通过 `/docs`（或 `/redoc`）查看可搜索的 API 文档，`/openapi.json` 提供接口结构。启用认证时需要管理员权限；设置 `OPENAPI_ENABLED=false` 可关闭这些路由。
