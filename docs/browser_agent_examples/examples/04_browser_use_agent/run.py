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
    # URL 单独成行，避免 browser-use 提取起始 URL 时把中文标点一起吞入。
    # 任务描述限定目标和禁止事项；真正的导航限制还由 BrowserProfile 执行。
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
    # 将模型、浏览器会话和输出目录显式传入，离线测试可以替换模型而不改主流程。
    return Agent(
        task=build_task(site_url),
        llm=llm,
        browser_session=session,
        use_vision=False,  # 依靠页面 DOM 信息，不要求模型支持截图输入。
        use_judge=False,  # 基础演示不发起额外的结果评审请求。
        enable_planning=False,  # 关闭额外规划阶段，Agent 仍逐步选择浏览器动作。
        max_failures=2,  # 对失败重试设限，避免一直尝试无法执行的动作。
        llm_timeout=60,  # 限制单次模型调用等待时间，不是整个任务的总时长。
        save_conversation_path=output_dir / "conversation",  # 保留每步对话用于复盘。
    )


async def run_demo(
    headless: bool, max_steps: int, llm: BaseChatModel | None = None
) -> str:
    # 每次运行单独保存产物和状态，失败时不会覆盖之前的成功结果。
    directory = run_artifacts("04_browser_use_agent")
    agent = None
    try:
        # 默认使用 .env 模型；测试传入 ScriptedModel 时不会创建真实模型客户端。
        llm = llm or build_llm()
        with DemoServer() as site:
            session = await create_session(headless)
            run_error = None
            try:
                agent = build_agent(llm, session, site.url, directory)
                # 步数上限控制 Agent 循环；一个步骤可能包含多个浏览器动作。
                history = await agent.run(max_steps=max_steps)
                # 先保留动作轨迹，再判断是否完成，便于分析失败原因。
                history.save_to_file(directory / "history.json")
                result = history.final_result()
                print("\nAgent 最终结果：\n", result)
                print("步骤数：", history.number_of_steps())
                print("Agent 自报成功：", history.is_successful())
                # 本节只要求自报成功且回答非空；商品事实的独立验收放在 05 展示。
                if history.is_successful() is not True or not result:
                    raise RuntimeError("Agent 未完成任务，请查看 history.json 和 conversation 轨迹。")
            except Exception as exc:
                # 记住原始任务异常，防止随后关闭浏览器的异常掩盖真正原因。
                run_error = exc
                raise
            finally:
                # keep_alive=True 的会话由这里统一回收，成功或失败都执行。
                try:
                    await session.kill()
                except Exception as cleanup_error:
                    if run_error is None:
                        raise
                    # 清理异常作为附加说明，仍向调用者抛出原始任务异常。
                    run_error.add_note(f"关闭浏览器失败：{cleanup_error}")
        # 浏览器和本地服务器都完成正常清理后，才把运行标记为成功。
        write_run_status(directory, "success")
        print("本次结果与轨迹：", directory)
        return result
    except Exception as exc:
        # run 中途抛错时尽量保存已有轨迹；已保存的 history 不重复改写。
        if agent is not None and agent.history.history and not (directory / "history.json").exists():
            try:
                agent.history.save_to_file(directory / "history.json")
            except Exception as history_error:
                exc.add_note(f"保存失败轨迹时出错：{history_error}")
        # 不吞掉失败：留下失败状态后重新抛出，使 CLI 或测试感知本次失败。
        write_run_status(directory, "failed", exc)
        print("运行失败；本次轨迹：", directory)
        raise


def main() -> None:
    # 入口负责校验参数，并用 asyncio.run 执行异步的 Agent/浏览器流程。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=12)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")
    asyncio.run(run_demo(args.headless, args.max_steps))


if __name__ == "__main__":
    # 导入 build_agent 或 run_demo 做测试时，不自动请求真实模型。
    main()
