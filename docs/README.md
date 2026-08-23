# 项目文档索引

本目录记录仓库的当前实现事实、接口、隐私边界、开源路线和后续任务。文档不能替代源码与测试；发生冲突时先以当前代码为准，再在同一变更中修正文档。

## 按读者阅读

**部署 / 使用**

1. [`../README.md`](../README.md) 或 [`../README.zh-CN.md`](../README.zh-CN.md)
2. [`privacy.md`](privacy.md)、[`security.md`](security.md)、[`privacy-notice.template.md`](privacy-notice.template.md)
3. [`../CHANGELOG.md`](../CHANGELOG.md)

**贡献 / 开源协作**

1. [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
2. [`../SECURITY.md`](../SECURITY.md)
3. [`roadmap.md`](roadmap.md)（阶段与边界）
4. [`tasks.md`](tasks.md)（要改代码时领取的任务）

**Agent / 维护者**

1. [`../AGENTS.md`](../AGENTS.md)
2. [`current-state.md`](current-state.md)
3. [`interfaces.md`](interfaces.md)
4. [`privacy.md`](privacy.md)、[`security.md`](security.md)
5. [`tasks.md`](tasks.md)；已完成记录见 [`tasks-completed.md`](tasks-completed.md)
6. 历史设计笔记：[`superpowers/README.md`](superpowers/README.md)

## 文档职责

| 文档 | 记录内容 | 不记录内容 |
| --- | --- | --- |
| `current-state.md` | 可由代码、配置、测试直接证明的现状和差异 | 尚未实现的目标状态 |
| `interfaces.md` | 对内外接口字段、稳定性、约束和变更流程 | 真实密码、token、服务器地址或数据库内容 |
| `privacy.md` | 数据类别、处理路径、风险和人工确认项 | 对未知部署环境的推断 |
| `privacy-notice.template.md` | 部署方可复制的空白告知草稿 | 已填写的机构名、法规或联系方式 |
| `security.md` | 威胁模型、认证边界、CSP 与部署回滚 | 真实地址、令牌或代理配置 |
| `roadmap.md` | 开源阶段、产品边界、与任务 ID 的对应 | 第二份待办列表或日历工期 |
| `tasks.md` | 可执行步骤、依赖、验收、验证和状态 | 未经验证的“已完成”声明 |
| `tasks-completed.md` | 已完成任务的原始验收记录 | 新的待办 |

## 维护规则

- 从仓库根目录执行文档中的命令，除非命令前明确给出其他工作目录。
- 接口或数据处理发生变化时，同时更新 `current-state.md`、`interfaces.md` 和 `privacy.md` 中受影响的部分。
- 后续工作只在 `tasks.md` 维护，不在多个文档建立平行待办列表。`roadmap.md` 只能引用任务 ID。
- 文档示例只能使用明显的占位符，例如 `http://navidrome.example.invalid:4533` 和 `example_user`。
- 不复制真实 `.env`、SQLite 数据、请求 URL、日志或部署配置到版本控制。
- 未满足任务全部验收标准时，状态不得改为“已完成”。
- 进入 git 的文本必须经过隐私审查：无真实凭据、无真实播放明细、无未公开的联系邮箱。

## 链接检查

仓库根目录执行：

```bash
python3 scripts/check_md_links.py
```

`docs/README.md` 内嵌脚本已与 `scripts/check_md_links.py` 对齐；请使用脚本，避免两份检查逻辑分叉。
