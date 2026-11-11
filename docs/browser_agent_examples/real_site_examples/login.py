"""01：仅演示网页人工登录后自动接续；正常订单任务不必先单独运行此入口。"""

# 这是可选的认证练习入口。run.py/agent.py 已包含同一流程，不要求先执行本文件。
# 用户在网页主动获取验证码并登录；程序只等待成功并询问是否保存本机会话。

import argparse
import asyncio

from auth import ensure_login
from erp import AUTH_PATH, order_browser


async def login(account: str | None, headless: bool = False) -> None:
    # 与两个业务入口复用同一认证流程；此入口不创建模型、不查询订单。
    # account=None 时由用户在网页填写账号；headless=True 时必须已存在有效登录态。
    async with order_browser(headless, AUTH_PATH) as (_, page):
        # 无需继续使用返回业务页：本入口确认权限并完成保存选择后就结束。
        await ensure_login(page, AUTH_PATH, account, headless=headless)
        print("已确认可以访问订单页，登录演示完成。")


if __name__ == "__main__":
    # 仅直接运行文件才解析命令并启动浏览器，导入 login() 不会产生外部操作。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", help="可选：仅预填测试账号；省略时在网页填写")
    parser.add_argument("--headless", action="store_true", help="仅用于复用已有有效登录态")
    args = parser.parse_args()
    asyncio.run(login(args.account, args.headless))
