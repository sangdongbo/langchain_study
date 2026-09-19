# 固定 Skills

这个目录保存 Agent 可以按需读取的 Skill 说明书：

- [procurement-review](procurement-review/README.md)：采购评审流程。
- [supplier-research](supplier-research/README.md)：供应商和库存风险调查流程。

每个 Skill 的真正入口是目录中的 `SKILL.md`。Skill 只告诉模型如何工作，不会自动创建工具，也不是可以单独运行的 Python 程序。

## 在哪里使用

| 文件 | 使用位置 | 作用 |
| --- | --- | --- |
| `procurement-review/SKILL.md` | [`deep_agent_examples/graphs.py`](../deep_agent_examples/graphs.py) | 读取为 `DYNAMIC_SKILL_FILES`，供统一 CLI 中的 `skill` 示例使用。 |
| `procurement-review/SKILL.md` | [`examples/dynamic_skills/run.py`](../examples/dynamic_skills/run.py) | `buyer + purchase` 或 `risk-reviewer + purchase` 时加载采购评审流程。 |
| `supplier-research/SKILL.md` | [`examples/dynamic_skills/run.py`](../examples/dynamic_skills/run.py) | `risk-reviewer + supplier-risk` 时加载供应商风险调查流程。 |
| 本文件及各 Skill 的 `README.md` | 不被程序读取 | 只用于人工阅读。运行时真正加载的是 `SKILL.md`。 |

动态示例的实际加载过程：

```text
服务端可信身份 role + task-type
  -> skill_files_for() 计算允许使用的 Skill
  -> 读取 skills/<名称>/SKILL.md
  -> 写入 StateBackend 的 /skills/session/<名称>/SKILL.md
  -> SkillsMiddleware 扫描名称、描述等 frontmatter
  -> 模型需要详细步骤时调用 read_file 读取完整正文
```

这里的 `/skills/session/...` 是 `StateBackend` 中的虚拟路径，不是本机上的真实目录。Skill 只能指导模型如何工作；模型真正能够调用哪些工具，仍由 `create_deep_agent(tools=[...])` 决定。

> `examples/skill_versioning` 不读取本目录。它在自己的 `run.py` 中内嵌两份 Skill 文本，专门演示不同 thread 的版本隔离和 metadata 缓存。

## 怎么使用

无需单独启动本目录。启动使用这些 Skill 的动态示例：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run python examples/dynamic_skills/run.py
```

上面的默认参数会以 `buyer + purchase` 加载 `procurement-review`。加载供应商调查 Skill：

```powershell
uv run python examples/dynamic_skills/run.py `
  --role risk-reviewer `
  --task-type supplier-risk
```

不调用真实模型的验证命令：

```powershell
uv run python examples/dynamic_skills/test.py
```

动态 Skill 的加载和缓存机制见 [dynamic_skills 示例](../examples/dynamic_skills/README.md)。
