"""02：固定流程查询订单、统计待回款金额，核对待回款最多的一张订单详情。"""

# 这是 Agent 的确定性对照组：相同任务、相同底层适配器，但动作顺序由 Python 写定。
# 本入口不创建模型；便于先排除登录、页面定位和金额解析的问题，再演示模型规划。

import argparse
import asyncio
from pathlib import Path

from browser_examples.runtime import run_artifacts, write_run_status

from auth import ensure_login
from erp import AUTH_PATH, OrderReader, order_browser
from reporting import RunLog


async def run_demo(keyword: str, limit: int, headless: bool, pause: bool,
                   account: str | None = None) -> Path:
    # keyword/limit 指定本轮允许采集范围，account 仅用于可选预填；返回成功产物目录。
    # headless 只能复用有效会话；pause 在有窗口时保留浏览器，方便人工查看最终页面。
    directory = run_artifacts("erp_order_query")
    print("本次产物目录：", directory)
    log = RunLog()
    # 首份日志覆盖认证前失败；认证成功后重置，业务指标不包含人工输入等待。
    try:
        async with order_browser(headless, AUTH_PATH) as (_, page):
            page = await ensure_login(page, AUTH_PATH, account, headless=headless)
            # 从业务阶段重新计时，排除输入验证码等人工等待。
            log = RunLog()
            reader = OrderReader(page, keyword, limit, log=log)
            report = await reader.query()
            # query 返回本页前 N 条及 Decimal 合计，不翻页、不读取接口正文。
            await page.screenshot(path=directory / "orders.png", full_page=True)
            if report.orders:
                # 与 Agent 完成同一任务，避免用不同目标对比耗时或结果。
                selected = max(report.orders, key=lambda item: item.outstanding_yuan)
                await reader.verify(selected.number)
                # verify 会把真实详情证据追加到同一个 report，后续序列化包含核对结果。
                await page.screenshot(path=directory / "detail.png", full_page=True)
            log.stop()
            output = report.model_dump_json(indent=2)
            # Decimal 以字符串保留精度；空搜索结果也会产生合法的零合计报告。
            print(output)
            if pause and not headless:
                await asyncio.to_thread(input, "演示完成，按 Enter 关闭浏览器：")
        # 浏览器正常清理且全部检查通过，才生成成功结果。
        log.save(directory, "script", "success", keyword, limit, 0)
        (directory / "result.json").write_text(output, encoding="utf-8")
        write_run_status(directory, "success")
        return directory
    except Exception as exc:
        # 失败只保留动作/指标和 failed 状态，不写 result.json 冒充本轮成功结果。
        try:
            log.save(directory, "script", "failed", keyword, limit, 0)
        except Exception as log_error:
            # 日志错误作为附加说明，不替换更重要的原始业务异常。
            exc.add_note(f"保存动作或指标失败：{log_error}")
        write_run_status(directory, "failed", exc)
        raise


def parser_for_demo(description: str) -> argparse.ArgumentParser:
    # 两个执行入口共享业务参数，关键词必须显式给出，避免无意读取整页订单。
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--keyword", required=True, help="非空订单编号片段或客户关键词")
    parser.add_argument("--limit", type=int, default=5, help="当前页最多统计 1–15 条")
    parser.add_argument("--headless", action="store_true", help="仅在已有有效登录态时使用；需人工登录时去掉此参数")
    # --pause 不影响认证等待；它只在任务完成后暂停供用户观看。
    parser.add_argument("--pause", action="store_true")
    parser.add_argument("--account", help="可选：仅预填测试账号；省略时在网页填写，不自动获取验证码或点击登录")
    return parser


def validate_args(parser, args) -> None:
    # 命令行边界先校验，参数错误不应启动浏览器或创建模型。
    if not args.keyword.strip() or not 1 <= args.limit <= 15:
        parser.error("--keyword 不能为空，--limit 必须在 1–15 之间。")


if __name__ == "__main__":
    # asyncio.run 管理异步事件循环；导入本文件时不自动查询，供 Agent 和测试复用函数。
    parser = parser_for_demo(__doc__)
    args = parser.parse_args()
    validate_args(parser, args)
    asyncio.run(run_demo(args.keyword.strip(), args.limit, args.headless, args.pause, args.account))
