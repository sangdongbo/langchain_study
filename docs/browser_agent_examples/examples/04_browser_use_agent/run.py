"""04：让 browser-use Agent 自己完成本地商品筛选。"""

import argparse
import asyncio
from pathlib import Path

from browser_examples.runtime import create_session, run_artifacts, write_run_status

from browser_use import Agent, BrowserSession
from browser_use.llm.base import BaseChatModel

from browser_examples.config import build_llm
from browser_examples.demo_server import DemoServer


def build_task(site_url: str) -> str:
    return f"""
打开本地商品页：
{site_url}/index.html
只在这个本地网站内操作。
在商品页选择“计算设备”，把最高价格设为 6500 元，点击“应用筛选”。
读取筛选后仍然可见的全部商品名称和价格，然后用中文回答。
不要登录，不要购买，不要访问其他网站。完成条件是回答包含商品名称和价格。
""".strip()


def build_agent(
    llm: BaseChatModel, session: BrowserSession, site_url: str, output_dir: Path
) -> Agent:
    return Agent(
        task=build_task(site_url),
        llm=llm,
        browser_session=session,
        use_vision=False,
        use_judge=False,
        enable_planning=False,
        max_failures=2,
        llm_timeout=60,
        save_conversation_path=output_dir / "conversation",
    )


async def run_demo(
    headless: bool, max_steps: int, llm: BaseChatModel | None = None
) -> str:
    directory = run_artifacts("04_browser_use_agent")
    agent = None
    try:
        llm = llm or build_llm()
        with DemoServer() as site:
            session = await create_session(headless)
            run_error = None
            try:
                agent = build_agent(llm, session, site.url, directory)
                history = await agent.run(max_steps=max_steps)
                history.save_to_file(directory / "history.json")
                result = history.final_result()
                print("\nAgent 最终结果：\n", result)
                print("步骤数：", history.number_of_steps())
                print("Agent 自报成功：", history.is_successful())
                if history.is_successful() is not True or not result:
                    raise RuntimeError("Agent 未完成任务，请查看 history.json 和 conversation 轨迹。")
            except Exception as exc:
                run_error = exc
                raise
            finally:
                try:
                    await session.kill()
                except Exception as cleanup_error:
                    if run_error is None:
                        raise
                    run_error.add_note(f"关闭浏览器失败：{cleanup_error}")
        write_run_status(directory, "success")
        print("本次结果与轨迹：", directory)
        return result
    except Exception as exc:
        if agent is not None and agent.history.history and not (directory / "history.json").exists():
            try:
                agent.history.save_to_file(directory / "history.json")
            except Exception as history_error:
                exc.add_note(f"保存失败轨迹时出错：{history_error}")
        write_run_status(directory, "failed", exc)
        print("运行失败；本次轨迹：", directory)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")
    asyncio.run(run_demo(args.headless, args.max_steps))


if __name__ == "__main__":
    main()
