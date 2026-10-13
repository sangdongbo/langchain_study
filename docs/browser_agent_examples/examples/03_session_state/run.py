"""03：保存并复用登录状态，避免每次任务重复登录。"""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer


def run_demo(headless: bool, state_path: Path, pause: bool = False) -> str:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with DemoServer() as site, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        login_context = browser.new_context()
        page = login_context.new_page()
        page.goto(f"{site.url}/login.html")
        page.get_by_test_id("username").fill("learner")
        page.get_by_test_id("password").fill("demo123")
        page.get_by_test_id("login").click()
        expect(page).to_have_url(f"{site.url}/dashboard.html")
        login_context.storage_state(path=state_path)
        login_context.close()

        reused_context = browser.new_context(storage_state=state_path)
        reused_page = reused_context.new_page()
        reused_page.goto(f"{site.url}/dashboard.html")
        expect(reused_page.get_by_test_id("welcome")).to_have_text("欢迎，learner")
        welcome = reused_page.get_by_test_id("welcome").inner_text()
        print("复用会话：", welcome)
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        reused_context.close()
        browser.close()
        return welcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()
    artifact = Path(__file__).resolve().parents[2] / ".artifacts" / "auth.json"
    run_demo(args.headless, artifact, args.pause)
    print("状态文件：", artifact)


def offline_check() -> None:
    with TemporaryDirectory() as directory:
        welcome = run_demo(True, Path(directory) / "auth.json")
        assert welcome == "欢迎，learner"


if __name__ == "__main__":
    main()
