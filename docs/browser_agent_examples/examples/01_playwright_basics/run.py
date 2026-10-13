"""01：用 Playwright 打开本地网页并读取结构化内容。"""

import argparse

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer
from browser_examples.runtime import artifacts


def run_demo(headless: bool, pause: bool = False) -> list[str]:
    # 同时管理本地服务器和 Playwright 生命周期，示例不依赖互联网或模型。
    with DemoServer() as site, sync_playwright() as playwright:
        # 有窗口时放慢操作便于观察；headless 模式用于自动检查。
        browser = playwright.chromium.launch(headless=headless, slow_mo=0 if headless else 250)
        page = browser.new_page()
        page.goto(f"{site.url}/index.html")
        print("页面标题：", page.title())
        # expect 会重试到条件满足或超时；先等商品渲染完成，再读取文本。
        expect(page.locator(".product")).to_have_count(6)
        # locator 描述如何查找元素；all_text_contents 取得所有匹配标题的文本。
        names = page.locator(".product h2").all_text_contents()
        print("商品名称：", "、".join(names))
        screenshot = artifacts("01_playwright_basics") / "page.png"
        # full_page 保存整页而不只是当前视口，方便展示和排查定位问题。
        page.screenshot(path=screenshot, full_page=True)
        print("截图：", screenshot)
        # 无界面的检查不能等待人工输入，只有可视演示才允许暂停。
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        browser.close()
        return names


def main() -> None:
    # 命令行参数只控制演示方式，run_demo 的返回值同时供 test.py 验收。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true", help="不显示浏览器窗口")
    parser.add_argument("--pause", action="store_true", help="演示结束后保留窗口直到按 Enter")
    args = parser.parse_args()
    run_demo(args.headless, args.pause)


if __name__ == "__main__":
    # 直接运行时进入 CLI；被 test.py 导入时不会自动弹出浏览器。
    main()
