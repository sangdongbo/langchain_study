# 共享配置

这个包只处理模型配置，专题中的 Agent、工具、schema 和离线测试保留在各自目录，
方便按课独立阅读。安装项目后，各课通过 `from pydantic_examples.config import build_model`
复用同一套配置。

## 文件与职责

| 文件 | 职责 |
| --- | --- |
| `__init__.py` | 标记 Python 包；导入时不创建 Agent 或模型 |
| `config.py` | 加载环境变量，选择供应商，创建 `OpenAIChatModel` |

`import`、`build_agent(test_model)` 都不会读取 `.env` 或发出模型请求。
`build_model()` 才加载配置并创建客户端；真正的 API 请求发生在 Agent 运行时。
离线 `test.py` 直接传官方 `TestModel` / `FunctionModel`，同时关闭真实模型请求。

## 两层配置优先级

同名变量按以下顺序加载，已有变量不覆盖：

1. 进程环境变量。
2. 本项目 `docs/pydantic_ai_examples/.env`。
3. 仓库根目录 `.env`。
4. 参考项目 `docs/deep_agent_examples/.env`，只补充缺失变量。

随后按第一个非空 Key 选择供应商：

| Key 优先级 | 同组地址与模型变量 | 未配置地址和模型时的默认值 |
| --- | --- | --- |
| `LLM_API_KEY` | `LLM_BASE_URL`、`LLM_MODEL` | OpenAI 官方 `/v1`、`gpt-4o-mini` |
| `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL` | DeepSeek 官方 `/v1`、`deepseek-chat` |
| `OPENAI_API_KEY` | `OPENAI_BASE_URL`、`OPENAI_MODEL` | OpenAI 官方 `/v1`、`gpt-4o-mini` |

不同前缀不混用：DeepSeek Key 不读取 `OPENAI_BASE_URL`。同一前缀的值可以来自不同
文件，所以更换该供应商账号/服务时，建议在同一配置来源完整指定 Key、地址与模型。
空字符串也会占用一个同名环境变量，只是在选择供应商时空 Key 会被跳过。

所有供应商都走 Chat Completions 接口，模型要支持示例使用的工具调用。
共享配置设置 `temperature=0`、单次请求超时 60 秒；请求次数上限由各专题指定。
配置不包含 LangSmith、数据库或自动开启的外部追踪。

## 如何检查

```powershell
# 从本项目根目录执行；不调用真实模型
uv run python scripts_smoke.py
```

配置检查使用占位 Key 并隔离环境变量，验证供应商选择、地址匹配及缺少凭据的错误。
还检查 `.env` 文件加载顺序及 `override=False`，保证已有环境变量不被文件覆盖。
它不验证真实 Key 是否有效；真实演示与配置入口见[项目总览](../README.md)。
