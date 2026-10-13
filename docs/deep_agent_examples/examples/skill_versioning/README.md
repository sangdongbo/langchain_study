# Skill 版本管理

本例展示如何让不同 thread 使用不同版本的 `SKILL.md`，以及为什么不能在同一个
已运行 thread 中直接热替换技能文件。

## 版本放在哪里

两个版本使用相同的虚拟路径和 Skill 名称，版本号写入 frontmatter：

```yaml
---
name: procurement-review
description: Procurement review procedure
metadata:
  version: "v2"
---
```

应用层根据租户、灰度策略或任务类型选择版本，再把对应内容写入新 thread 的
`state["files"]`。模型不能决定自己获得哪个版本。

## 为什么切换版本需要新 thread

`SkillsMiddleware.before_agent` 在一个 thread 第一次运行时扫描目录，并把结果保存到
私有 `skills_metadata` State。后续运行会复用这个索引，不会因为 `files` 改变而自动
重扫。这样可以保证一个长任务执行期间使用的规则稳定，不会中途改变语义。

```text
thread A 首次输入 v1 -> metadata=v1
thread A 再覆盖为 v2 -> metadata 仍为 v1
thread B 首次输入 v2 -> metadata=v2
```

生产升级流程应是：发布新 Skill 内容 -> 新请求分配新 thread -> 旧 thread 继续使用
旧版本直到结束。需要强制升级历史任务时，应显式迁移 State，而不是偷偷覆盖文件。

## 运行

```powershell
# 需要模型 Key；每次默认创建新 thread
uv run python examples/skill_versioning/run.py --version v1
uv run python examples/skill_versioning/run.py --version v2

# Fake Model，不需要 Key，不访问网络
uv run python examples/skill_versioning/test.py
```
