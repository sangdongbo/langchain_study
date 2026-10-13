"""05：用 Pydantic 约束 Browser Agent 的最终研究结果。"""

import argparse
import asyncio
from pathlib import Path

from browser_examples.runtime import create_session, run_artifacts, write_run_status

from browser_use import Agent, BrowserSession
from browser_use.llm.base import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from browser_examples.config import build_llm
from browser_examples.demo_server import DemoServer


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="商品名称")
    price_yuan: int = Field(gt=0, description="人民币整数价格")
    specs: str = Field(min_length=1, description="页面展示的规格")
    details: str = Field(min_length=1, description="详情页的使用说明")
    source_url: str = Field(min_length=1, description="该商品详情页 URL")


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1)
    products: list[Product] = Field(min_length=1)
    recommendation: str = Field(min_length=1)


def build_task(site_url: str) -> str:
    return f"""
访问本地商品页：
{site_url}/index.html
只研究这个本地网站。
找出“计算设备”中价格不超过 6500 元的商品，记录名称、整数价格和页面规格。
必须分别打开每个符合条件的商品详情页，原样记录规格、使用说明和详情页 URL。
基于价格与规格给出一句推荐，不得编造页面没有的信息，也不要执行登录或购买。
""".strip()


def build_agent(
    llm: BaseChatModel, session: BrowserSession, site_url: str, output_dir: Path
) -> Agent:
    return Agent(
        task=build_task(site_url),
        llm=llm,
        browser_session=session,
        output_model_schema=ResearchResult,
        use_vision=False,
        use_judge=False,
        enable_planning=False,
        max_failures=2,
        llm_timeout=60,
        save_conversation_path=output_dir / "conversation",
    )


def validate_demo_result(
    result: ResearchResult, site_url: str, visited_urls: list[str | None]
) -> None:
    """对这个固定练习做外部验收，不把模型自报成功当作事实证明。"""
    expected = {
        "数据分析笔记本": (
            5999, "32GB 内存 · 1TB SSD", "便携机型，适合移动办公与数据分析。",
            f"{site_url}/detail.html?id=laptop",
        ),
        "开发者迷你主机": (
            4299, "24GB 内存 · 512GB SSD", "桌面机型，适合固定工位；不含显示器。",
            f"{site_url}/detail.html?id=mini",
        ),
    }
    if len(result.products) != 2 or {product.name for product in result.products} != expected.keys():
        raise ValueError("结果漏项、重复或包含不符合条件的商品。")
    for product in result.products:
        observed = (product.price_yuan, product.specs, product.details, product.source_url)
        if observed != expected[product.name]:
            raise ValueError(f"{product.name} 的价格、规格、说明或来源与演示页不符。")
        if product.source_url not in visited_urls:
            raise ValueError(f"轨迹中没有访问 {product.name} 的详情页。")


async def run_demo(
    headless: bool, max_steps: int, llm: BaseChatModel | None = None
) -> ResearchResult:
    directory = run_artifacts("05_structured_research")
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
                result = history.structured_output
                if history.is_successful() is not True or result is None:
                    raise RuntimeError(f"Agent 未完成结构化研究：{history.final_result()}")
                validate_demo_result(result, site.url, history.urls())
                output = result.model_dump_json(indent=2)
                print(output)
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
        (directory / "result.json").write_text(output, encoding="utf-8")
        write_run_status(directory, "success")
        print("验收通过；本次结果和轨迹：", directory)
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
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")
    asyncio.run(run_demo(args.headless, args.max_steps))


if __name__ == "__main__":
    main()
