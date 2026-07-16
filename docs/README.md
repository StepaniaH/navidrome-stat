# 项目文档索引

本目录记录仓库的当前实现事实、接口、隐私边界和后续任务。文档不能替代源码与测试；发生冲突时先以当前代码为准，再在同一变更中修正文档。

## 推荐阅读顺序

1. [`../AGENTS.md`](../AGENTS.md)：AI Agent 的工作规则和交付约束。
2. [`current-state.md`](current-state.md)：当前架构、运行行为、测试覆盖和已知差异。
3. [`interfaces.md`](interfaces.md)：HTTP、Subsonic、环境变量和 SQLite 接口登记。
4. [`privacy.md`](privacy.md)：数据分类、敏感值处理和必须由用户确认的部署事项。
5. [`security.md`](security.md)：威胁模型、访问控制与前端安全策略。
6. [`tasks.md`](tasks.md)：唯一的后续任务清单；实施工作按任务 ID 领取和验收。
7. [`../README.md`](../README.md)：面向使用者的项目介绍和快速启动。

## 文档职责

| 文档 | 记录内容 | 不记录内容 |
| --- | --- | --- |
| `current-state.md` | 可由代码、配置、测试直接证明的现状和差异 | 尚未实现的目标状态 |
| `interfaces.md` | 对内外接口字段、稳定性、约束和变更流程 | 真实密码、token、服务器地址或数据库内容 |
| `privacy.md` | 数据类别、处理路径、风险和人工确认项 | 对未知部署环境的推断 |
| `security.md` | 威胁模型、认证边界、CSP 与部署回滚 | 真实地址、令牌或代理配置 |
| `tasks.md` | 可执行步骤、依赖、验收、验证和状态 | 未经验证的“已完成”声明 |

## 维护规则

- 从仓库根目录执行文档中的命令，除非命令前明确给出其他工作目录。
- 接口或数据处理发生变化时，同时更新 `current-state.md`、`interfaces.md` 和 `privacy.md` 中受影响的部分。
- 后续工作只在 `tasks.md` 维护，不在多个文档建立平行待办列表。
- 文档示例只能使用明显的占位符，例如 `http://navidrome.example.invalid:4533` 和 `example_user`。
- 不复制真实 `.env`、SQLite 数据、请求 URL、日志或部署配置到版本控制。
- 未满足任务全部验收标准时，状态不得改为“已完成”。

## 链接检查

以下脚本检查仓库 Markdown 中的本地相对链接是否存在，忽略网络链接和页内锚点：

```bash
python3 - <<'PY'
from pathlib import Path
import re
import sys

root = Path.cwd()
missing = []
pattern = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
for document in sorted(root.rglob("*.md")):
    if ".git" in document.parts:
        continue
    text = document.read_text(encoding="utf-8")
    for target in pattern.findall(text):
        target = target.strip().split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        path = (document.parent / target).resolve()
        if not path.exists():
            missing.append(f"{document.relative_to(root)} -> {target}")
if missing:
    print("Missing local Markdown links:")
    print("\n".join(missing))
    sys.exit(1)
print("All local Markdown links resolve.")
PY
```
