"""02：填写筛选表单，等待页面状态并校验结果。"""

import argparse

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer
from browser_examples.runtime import artifacts


def run_demo(headless: bool, pause: bool = False) -> list[str]:
    with DemoServer() as site, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=0 if headless else 250)
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.goto(f"{site.url}/index.html")
        page.get_by_test_id("keyword").fill("32GB")
        page.get_by_test_id("category").select_option("计算设备")
        page.get_by_test_id("max-price").fill("6500")
        page.get_by_test_id("apply-filter").click()
        expect(page.get_by_test_id("result-status")).to_have_text("找到 1 件商品")
        names = page.locator(".product:visible h2").all_text_contents()
        print("筛选结果：", "、".join(names))
        directory = artifacts("02_forms_and_waiting")
        page.screenshot(path=directory / "page.png", full_page=True)
        context.tracing.stop(path=directory / "trace.zip")
        print("截图和操作轨迹：", directory)
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        context.close()
        browser.close()
        return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()
    run_demo(args.headless, args.pause)


if __name__ == "__main__":
    main()
