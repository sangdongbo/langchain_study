"""本机认证接续：复用会话，等待用户在网页登录后再启动订单 Agent。"""

# 阅读顺序：order_browser 恢复状态 → ensure_login 判断是否要人工登录 → 返回业务页。
# 此模块在模型创建前执行；不提供“获取验证码”“填写验证码”或“点击登录”的自动化动作。
# 保存的状态包含凭据，不能与普通查询报告一样公开展示或提交到版本库。

import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, expect

from erp import ORDER_SEARCH_SELECTOR, ORDER_URL

TIMEOUT_MS = 30_000  # 普通页面加载/控件检查的等待上限，单位为毫秒。
MANUAL_LOGIN_TIMEOUT_MS = 300_000  # 人工接收短信、填写并登录的等待上限：5 分钟。


class LoginError(RuntimeError):
    """只携带安全提示，避免 Playwright 原始调用日志泄露账号或验证码。"""


async def terminal_input(prompt: str) -> str:
    # 终端只询问是否保存会话，不收集账号或验证码。
    try:
        # input 会阻塞线程；放到工作线程，避免阻塞 Playwright 的异步事件处理。
        return (await asyncio.to_thread(input, prompt)).strip()
    except EOFError:
        raise LoginError("需要可交互终端确认是否保存登录状态，请在本机 PowerShell 中运行。") from None


async def restore_auth(context: BrowserContext, auth_path: Path) -> None:
    """只用于新建的专用浏览器上下文，不影响用户日常浏览器或原文件。"""
    # context 是本次专用浏览器上下文；auth_path 是此前经用户确认保存的文件。
    # 无返回值：恢复的是浏览器的 cookies/localStorage，不是向调用者返回 token。
    if not auth_path.is_file():
        # 首次运行没有状态文件是正常情况，后续 ensure_login 会等待人工登录。
        return
    try:
        state = json.loads(auth_path.read_text(encoding="utf-8"))
        # 在传入浏览器前先检查顶层格式；此检查不能证明会话有效或账号有权限。
        if (not isinstance(state, dict) or not isinstance(state.get("cookies"), list)
                or not isinstance(state.get("origins"), list)):
            raise ValueError("登录状态结构不正确")
    except (OSError, ValueError):
        # 读取失败不删除旧文件，是否替换由重新登录后的保存确认决定。
        print("本机登录状态无法读取，将重新登录；原文件保留，确认保存后才会覆盖。")
        return
    try:
        # 一次性导入，不注册每次导航都写回旧 token 的 init script。
        # set_storage_state 会替换当前上下文存储，所以这里只能用于本次新建的专用上下文。
        await context.set_storage_state(state)
    except Exception:
        raise LoginError("恢复本机登录状态失败；请备份状态文件后重新登录。") from None


async def save_auth(context: BrowserContext, auth_path: Path) -> None:
    # 先完成临时文件再替换，保存失败不能截断原登录状态。
    # 调用者必须先验证订单页权限并取得保存确认；此函数只负责本机文件保存。
    temporary = None
    try:
        state = await context.storage_state()
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=auth_path.parent, delete=False) as output:
            # 临时文件与目标文件放在同一目录；退出 with 关闭句柄后再替换，兼容 Windows。
            temporary = Path(output.name)
            json.dump(state, output, ensure_ascii=False)
        os.replace(temporary, auth_path)
    finally:
        # 成功替换后临时路径已不存在；失败时只清理本函数创建的临时文件，不删除原文件。
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def require_origin(page: Page, url: str) -> None:
    # 人工操作期间页面也可能导航；填写账号和进入业务页前都检查来源。
    # urlsplit 的前两项是 scheme/netloc，要求协议、主机及显式端口一致；允许站内路由变化。
    # 这是几个关键节点上的检查，不是持续监控全部浏览器网络请求的防火墙。
    if urlsplit(page.url)[:2] != urlsplit(url)[:2]:
        raise LoginError("页面已离开允许站点，停止输入登录信息。")


async def ensure_login(page: Page, auth_path: Path, account: str | None = None,
                       *, url: str = ORDER_URL, headless: bool = False) -> Page:
    """返回已确认有订单页权限的页面；整个函数完成前不创建模型或 Agent。"""
    # 参数：page 为当前页，account 仅用于可选预填；url 在离线测试中替换为虚构站点。
    # headless 必须与调用方启动模式一致，避免在不可见的浏览器中等待用户手动登录。
    # 始终返回原标签页：新标签页不共享 sessionStorage，也无法继承当前 SPA 的内存状态。
    # step 只记录安全的阶段提示；底层错误即使包含账号，也不会原样写入失败状态。
    step = "无法确认登录状态，请检查网络、订单权限或页面结构；订单区域只能有一个可见搜索框。"
    try:
        await page.goto(url, wait_until="domcontentloaded")
        # Locator 是定位规则，不会在创建时立即读取元素；后续等待负责确认元素可见。
        # 真实站全页有多个同名输入框；必须与 OrderReader 一样限定订单区域和可见性。
        search = page.locator(f"{ORDER_SEARCH_SELECTOR}:visible")
        account_box = page.get_by_placeholder("请输入手机号/邮箱", exact=True)
        # 同时等待两种已知入口，避免先等订单框超时才发现需要登录。
        await page.locator(f'{ORDER_SEARCH_SELECTOR}:visible, '
                           'input[placeholder="请输入手机号/邮箱"]:visible').first.wait_for(timeout=TIMEOUT_MS)
        require_origin(page, url)
        if await search.is_visible():
            # 页面可以访问才视为会话有效；不因为“存在状态文件”就跳过权限检查。
            print("登录状态有效，直接进入订单任务。")
            return page

        if headless:
            # 有效会话可无窗口运行；需要人工认证时必须让用户能看到并操作页面。
            raise LoginError("当前需要人工网页登录，请去掉 --headless 后重新运行；程序不会获取验证码。")
        if account is not None:
            # 只保留旧入口支持的账号预填能力，省略参数时完全由用户在网页输入。
            account = account.strip()
            if not account or len(account) > 254 or any(character.isspace() for character in account):
                raise LoginError("预填账号为空或格式不正确，请在网页中填写有效账号。")
            step = "预填账号失败，请检查登录页面；程序不会获取验证码。"
            require_origin(page, url)
            await account_box.fill(account)
        print("请在浏览器中填写账号，自己点击「获取验证码」、输入验证码并点击「登录」。")
        print("程序不会发送或填写验证码；等待登录完成（最多 5 分钟，Ctrl+C 可取消）。")
        step = "等待人工登录未完成、超时或页面已关闭；请在网页完成登录后重试，程序不会获取验证码。"
        # 登录提交时表单可能短暂隐藏，不能仅以 hidden 判定登录成功。
        # 同时等待原页出现已知业务路由与可见性信号；只读路由/DOM，不读取任何输入值或 token。
        # shortcut: 仅识别已观察的工作台/订单入口；站点登录落地路由变更时更新此判据和 fixture。
        await page.wait_for_function("""({orderUrl, searchSelector}) => {
            const visible = element => element && element.getClientRects().length > 0
                && getComputedStyle(element).visibility !== 'hidden';
            const account = document.querySelector('input[placeholder="请输入手机号/邮箱"]');
            // 原生 DOM 不支持 Playwright 的 :visible；逐个判断，不能只检查第一个隐藏副本。
            const hasSearch = [...document.querySelectorAll(searchSelector)].some(visible);
            const order = new URL(orderUrl);
            const route = location.hash.split('?')[0];
            return location.origin === order.origin && !visible(account)
                && (route === '#/workBench' || (location.href === orderUrl && hasSearch));
        }""", arg={"orderUrl": url, "searchSelector": ORDER_SEARCH_SELECTOR}, timeout=MANUAL_LOGIN_TIMEOUT_MS)
        require_origin(page, url)

        print("已检测到原标签页进入业务路由，正在同一页面确认订单页。")
        step = "已检测到业务路由，但未能确认订单区域内唯一可见的搜索框；可能仍在加载、回到登录页、存在多个可见控件或定位规则已变化，不代表一定没有权限。"
        # 保留已登录标签页；hash 路由切换不另开窗口，已在订单页时也不重复导航。
        if page.url != url:
            await page.goto(url, wait_until="domcontentloaded")
        require_origin(page, url)
        await expect(search).to_be_visible(timeout=TIMEOUT_MS)
        step = "订单搜索框已出现，但登录输入框仍残留在页面 DOM；为避免把认证信息交给模型，已停止。"
        # 不再靠新标签页隔离秘密，而是确认原页路由已卸载认证输入框；隐藏仍不够安全。
        await expect(page.locator('input[placeholder="请输入手机号/邮箱"], '
                                  'input[placeholder="验证码"]')).to_have_count(0, timeout=TIMEOUT_MS)
        # 确认通过再决定是否落盘；回答非 yes 只是拒绝保存，不取消本次已登录任务。
        answer = await terminal_input("将登录状态保存/覆盖到本机 .artifacts/erp_auth.json？输入 yes（其他输入仅本次使用）：")
        if answer.lower() == "yes":
            step = "已登录，但保存状态失败；原状态文件未被不完整内容覆盖。"
            await save_auth(page.context, auth_path)
            print("已保存本机登录状态；请勿提交、上传或共享该文件。")
        else:
            print("未保存登录状态，继续本次订单任务。")
        return page
    except LoginError:
        # 已经转换过的业务提示直接保留，避免被后面的通用错误提示再次覆盖。
        raise
    except PlaywrightTimeoutError:
        # 只报告安全的定位状态，不打印可能携带凭据的完整 URL、DOM 或原始调用日志。
        if page.is_closed():
            raise LoginError("登录接续时原标签页已关闭；程序没有另开标签页，请保持登录页打开。") from None
        require_origin(page, url)
        if await page.get_by_placeholder("请输入手机号/邮箱", exact=True).is_visible():
            raise LoginError("原标签页仍显示登录表单；请在网页完成登录，程序不会获取验证码。") from None
        raise LoginError(f"{step}（等待超时）") from None
    except Exception:
        # 不附带原异常：fill() 的调用日志可能包含秘密，不能进入 status.json。
        raise LoginError(step) from None
