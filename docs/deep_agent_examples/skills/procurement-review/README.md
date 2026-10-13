# 采购评审 Skill

这个 Skill 定义企业采购评审流程，要求 Agent：

- 使用工具计算采购总额。
- 检查库存、部门预算和供应商风险。
- 区分阻断问题与普通建议。
- 根据工具结果给出中文结论。

具体规则见 [SKILL.md](SKILL.md)。

## 怎么使用

Skill 不能单独启动。运行动态 Skills 示例时，它会作为 State 文件注入并由 Agent 按需读取：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run python examples/dynamic_skills/run.py
```

离线验证：

```powershell
uv run python examples/dynamic_skills/test.py
```

成功时会输出“动态 Skills 离线测试通过”。
