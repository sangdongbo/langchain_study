"""01：用 Playwright 打开本地网页并读取结构化内容。"""

import argparse

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer
from browser_examples.runtime import artifacts


def run_demo(headless: bool, pause: bool = False) -> list[str]:
    with DemoServer() as site, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=0 if headless else 250)
        page = browser.new_page()
        page.goto(f"{site.url}/index.html")
        print("页面标题：", page.title())
        expect(page.locator(".product")).to_have_count(6)
        names = page.locator(".product h2").all_text_contents()
        print("商品名称：", "、".join(names))
        screenshot = artifacts("01_playwright_basics") / "page.png"
        page.screenshot(path=screenshot, full_page=True)
        print("截图：", screenshot)
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        browser.close()
        return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="不显示浏览器窗口")
    parser.add_argument("--pause", action="store_true", help="演示结束后保留窗口直到按 Enter")
    args = parser.parse_args()
    run_demo(args.headless, args.pause)


if __name__ == "__main__":
    main()
