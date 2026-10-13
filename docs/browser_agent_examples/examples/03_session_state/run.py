"""03：保存并复用登录状态，避免每次任务重复登录。"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer


def run_demo(headless: bool, state_path: Path, pause: bool = False) -> str:
    # 状态文件由调用者决定保存位置，测试可以使用自动清理的临时目录。
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with DemoServer() as site, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        # 第一个 context 从空白会话开始；固定账号仅用于演示，不是真实认证。
        login_context = browser.new_context()
        page = login_context.new_page()
        page.goto(f"{site.url}/login.html")
        page.get_by_test_id("username").fill("learner")
        page.get_by_test_id("password").fill("demo123")
        page.get_by_test_id("login").click()
        # 等登录脚本写入 localStorage 并完成跳转，再导出状态。
        expect(page).to_have_url(f"{site.url}/dashboard.html")
        # 保存 cookies 和各源的 localStorage；真实项目中该文件应按凭据保护。
        login_context.storage_state(path=state_path)
        login_context.close()

        # 创建全新隔离会话并导入状态，证明不是原页面仍保留着登录信息。
        # localStorage 按源隔离，因此仍使用同一服务器的协议、主机和端口。
        reused_context = browser.new_context(storage_state=state_path)
        reused_page = reused_context.new_page()
        reused_page.goto(f"{site.url}/dashboard.html")
        # 不再填写登录表单，直接用受保护页面的欢迎文字验证状态恢复。
        expect(reused_page.get_by_test_id("welcome")).to_have_text("欢迎，learner")
        welcome = reused_page.get_by_test_id("welcome").inner_text()
        print("复用会话：", welcome)
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        reused_context.close()
        browser.close()
        return welcome


def main() -> None:
    # CLI 演示会保留 auth.json 供学习；不要把真实登录状态提交到 Git。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()
    artifact = Path(__file__).resolve().parents[2] / ".artifacts" / "auth.json"
    run_demo(args.headless, artifact, args.pause)
    print("状态文件：", artifact)


def offline_check() -> None:
    # 检查结束自动移除临时认证文件，不污染 CLI 演示的状态文件。
    with TemporaryDirectory() as directory:
        welcome = run_demo(True, Path(directory) / "auth.json")
        assert welcome == "欢迎，learner"


if __name__ == "__main__":
    main()
