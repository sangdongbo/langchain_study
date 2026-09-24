# CompositeBackend 路由

本例演示如何按虚拟路径把文件分发给不同 Backend：

```text
/work/**      -> StateBackend：当前 thread 的临时工作文件
/memories/**  -> StoreBackend：跨 thread、按租户 namespace 持久化
其他路径      -> StateBackend
```

这适合“工作草稿很短期、用户偏好或项目知识需要长期保存”的 Agent。路由由
应用配置决定，不是模型自己选择存储位置。

## 执行流程

```text
模型调用 write_file("/work/evidence.md")
  -> StateBackend
模型调用 write_file("/memories/decision.md")
  -> CompositeBackend 去掉 /memories/ 前缀
  -> StoreBackend(namespace=tenant-a)
```

`StateBackend` 的文件跟随 thread checkpoint；`StoreBackend` 的文件跟随 Store
namespace。生产环境需要保证 namespace 来自可信租户身份，并使用持久化 Store。

## 运行

```powershell
# 需要模型 Key
uv run python examples/composite_backend/run.py

# Fake Model，不需要 Key、不访问网络
uv run python examples/composite_backend/test.py
```

离线测试会同时检查 State 中的临时文件和 Store 中的长期文件，证明两条路由没有
混在一起。

