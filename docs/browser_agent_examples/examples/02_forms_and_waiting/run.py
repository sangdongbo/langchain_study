"""02：填写筛选表单，等待页面状态并校验结果。"""

import argparse

from playwright.sync_api import expect, sync_playwright

from browser_examples.demo_server import DemoServer
from browser_examples.runtime import artifacts


def run_demo(headless: bool, pause: bool = False) -> list[str]:
    # 所有交互只发生在本地静态站点，不会提交真实订单。
    with DemoServer() as site, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, slow_mo=0 if headless else 250)
        # context 是隔离的浏览器会话，统一承载页面、存储状态和操作轨迹。
        context = browser.new_context()
        # 从操作前开始录制，便于回看截图、DOM 快照及对应源代码。
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.goto(f"{site.url}/index.html")
        # data-testid 不依赖布局或样式；fill 写文本，select_option 选择选项值。
        page.get_by_test_id("keyword").fill("32GB")
        page.get_by_test_id("category").select_option("计算设备")
        page.get_by_test_id("max-price").fill("6500")
        page.get_by_test_id("apply-filter").click()
        # click 的自动等待不代表筛选已完成；等待页面的最终状态而非固定 sleep。
        expect(page.get_by_test_id("result-status")).to_have_text("找到 1 件商品")
        # 筛选只是隐藏卡片，所以必须读取 :visible，不能统计全部 .product。
        names = page.locator(".product:visible h2").all_text_contents()
        print("筛选结果：", "、".join(names))
        directory = artifacts("02_forms_and_waiting")
        page.screenshot(path=directory / "page.png", full_page=True)
        # stop 将已录制的轨迹写入文件，可用 Playwright Trace Viewer 回放。
        context.tracing.stop(path=directory / "trace.zip")
        print("截图和操作轨迹：", directory)
        if pause and not headless:
            input("演示完成，按 Enter 关闭浏览器：")
        # 先关闭会话，再关闭浏览器，释放页面及其相关资源。
        context.close()
        browser.close()
        return names


def main() -> None:
    # 默认显示窗口；--headless 适合自动检查，--pause 适合课堂讲解。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", action="store_true")
    args = parser.parse_args()
    run_demo(args.headless, args.pause)


if __name__ == "__main__":
    main()
