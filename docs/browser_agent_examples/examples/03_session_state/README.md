# 03 会话状态

这一节学习浏览器上下文与登录状态。先在一个上下文中登录，将状态保存到文件，关闭
旧上下文，再用文件创建新上下文，直接进入控制台。代码见 [run.py](run.py)，不需要
模型 Key。

## 运行

从 `docs/browser_agent_examples` 执行：

```powershell
uv run python examples/03_session_state/run.py --pause
uv run python examples/03_session_state/run.py --headless
uv run python examples/03_session_state/test.py
```

终端应输出 `复用会话：欢迎，learner`，新页面直接显示控制台，无需再次填写账号。
演示账号是 `learner / demo123`。

## 读懂代码

1. `browser.new_context()` 创建独立上下文，它隔离 cookie、localStorage 等状态。
2. 登录页写入 localStorage 并跳转，`expect(page).to_have_url()` 等待完成。
3. `login_context.storage_state(path=...)` 保存状态，随后关闭旧上下文。
4. `browser.new_context(storage_state=...)` 恢复状态，再访问控制台。
5. `expect(welcome).to_have_text(...)` 验证恢复成功。

`storage_state` 可保存 cookie 和 localStorage；本练习实际使用 localStorage，cookie
列表可以为空。控制台检查的是一个浏览器中的标记，账号与密码写在本地 HTML 中，
只用于展示状态流转，不能作为真实认证方案。

## 状态文件的边界

默认生成 `.artifacts/auth.json`，该目录已被 Git 忽略。真实网站的状态文件可能包含
登录凭据，需要按凭据管理。[test.py](test.py) 在临时目录中写入状态，检查后自动清理。

本地服务器每次选择随机端口，localStorage 绑定完整 origin（协议、域名、端口）。
因此这里演示的是**同一次运行中两个上下文之间的复用**；上一次运行生成的文件不能
直接用于下一次随机端口的服务器。真实网站若 origin 固定，还需考虑登录过期。

## 小练习

去掉新上下文的 `storage_state=state_path`，观察它是否跳回登录页、欢迎断言是否失败。
再把参数恢复，理解「同一个 browser」并不表示「所有 context 共用登录状态」。

下一节：[browser-use Agent](../04_browser_use_agent/README.md)。
