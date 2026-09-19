# 固定 Skills

这个目录保存 Agent 可以按需读取的 Skill 说明书：

- [procurement-review](procurement-review/README.md)：采购评审流程。
- [supplier-research](supplier-research/README.md)：供应商和库存风险调查流程。

每个 Skill 的真正入口是目录中的 `SKILL.md`。Skill 只告诉模型如何工作，不会自动创建工具，也不是可以单独运行的 Python 程序。

## 怎么使用

无需单独启动本目录。启动使用这些 Skill 的动态示例：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run python examples/dynamic_skills/run.py
```

不调用真实模型的验证命令：

```powershell
uv run python examples/dynamic_skills/test.py
```

动态 Skill 的加载和缓存机制见 [dynamic_skills 示例](../examples/dynamic_skills/README.md)。
