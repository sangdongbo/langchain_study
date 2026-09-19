# 供应商调查 Skill

这个 Skill 用于调查供应商交付、质量和库存风险，要求 Agent 区分已取得的工具证据与推测，并给出风险、缓解措施和缺失证据。

具体规则见 [SKILL.md](SKILL.md)。

## 怎么使用

Skill 不能单独启动。通过可信角色和任务类型选择该 Skill：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run python examples/dynamic_skills/run.py --role risk-reviewer --task-type supplier-risk
```

离线验证：

```powershell
uv run python examples/dynamic_skills/test.py
```

成功时会输出“动态 Skills 离线测试通过”。
