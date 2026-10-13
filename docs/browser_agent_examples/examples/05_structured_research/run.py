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
    # 这里只使用 Pydantic 定义数据契约，并不是 PydanticAI 的 Agent。
    # 禁止额外字段，避免模型悄悄生成契约之外的数据。
    model_config = ConfigDict(extra="forbid")

    # 字段约束检查形状和基本范围；价格是否真实还需要后面的事实验收。
    name: str = Field(min_length=1, description="商品名称")
    price_yuan: int = Field(gt=0, description="人民币整数价格")
    specs: str = Field(min_length=1, description="页面展示的规格")
    details: str = Field(min_length=1, description="详情页的使用说明")
    source_url: str = Field(min_length=1, description="该商品详情页 URL")


class ResearchResult(BaseModel):
    # 嵌套 Product 模型使最终输出拥有一致结构，不再依靠自由文本解析。
    model_config = ConfigDict(extra="forbid")

    requirement: str = Field(min_length=1)
    products: list[Product] = Field(min_length=1)
    recommendation: str = Field(min_length=1)


def build_task(site_url: str) -> str:
    # URL 保持独立成行；要求逐个访问详情页，而不是只从目录页猜使用说明。
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
    # 注入模型和会话，离线替身与真实模型共用同一执行入口。
    return Agent(
        task=build_task(site_url),
        llm=llm,
        browser_session=session,
        output_model_schema=ResearchResult,  # 约束完成动作的数据，生成可校验的模型对象。
        use_vision=False,  # 页面文字及 DOM 足以完成练习，无需多模态模型。
        use_judge=False,  # 结果由本地事实规则验收，不额外调用模型评审。
        enable_planning=False,  # 关闭额外规划阶段，保留逐步执行浏览器动作的能力。
        max_failures=2,  # 限制失败重试，避免无限循环。
        llm_timeout=60,  # 单次模型调用的等待上限。
        save_conversation_path=output_dir / "conversation",  # 与轨迹一起保留运行证据。
    )


def validate_demo_result(
    result: ResearchResult, site_url: str, visited_urls: list[str | None]
) -> None:
    """对这个固定练习做外部验收，不把模型自报成功当作事实证明。"""
    # 固定目录的标准答案：这是教学验收规则，不是适用于任意网站的商品校验器。
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
    # 数量和名称集合一起检查，才能同时拒绝漏项、重复项和额外商品。
    if len(result.products) != 2 or {product.name for product in result.products} != expected.keys():
        raise ValueError("结果漏项、重复或包含不符合条件的商品。")
    for product in result.products:
        # schema 合法不代表事实正确；逐字段对照页面固定数据，不接受编造。
        observed = (product.price_yuan, product.specs, product.details, product.source_url)
        if observed != expected[product.name]:
            raise ValueError(f"{product.name} 的价格、规格、说明或来源与演示页不符。")
        # 另查实际导航轨迹，不能仅因答案里写了一个来源 URL 就认定已访问。
        if product.source_url not in visited_urls:
            raise ValueError(f"轨迹中没有访问 {product.name} 的详情页。")


async def run_demo(
    headless: bool, max_steps: int, llm: BaseChatModel | None = None
) -> ResearchResult:
    # 同一专题多次运行的结果隔离；目录创建时状态先记为 running。
    directory = run_artifacts("05_structured_research")
    agent = None
    try:
        # 测试注入固定响应模型，正常演示才加载 .env 创建真实模型客户端。
        llm = llm or build_llm()
        with DemoServer() as site:
            session = await create_session(headless)
            run_error = None
            try:
                agent = build_agent(llm, session, site.url, directory)
                # 步数限制控制执行规模；保留轨迹后再验收最终结构化输出。
                history = await agent.run(max_steps=max_steps)
                history.save_to_file(directory / "history.json")
                # 直接取得 ResearchResult，而不是自己从自由文本里截取 JSON。
                result = history.structured_output
                if history.is_successful() is not True or result is None:
                    raise RuntimeError(f"Agent 未完成结构化研究：{history.final_result()}")
                # 验收分两层：结构由 schema 检查，事实及访问来源由外部规则检查。
                validate_demo_result(result, site.url, history.urls())
                output = result.model_dump_json(indent=2)
                print(output)
            except Exception as exc:
                # 保留原始任务错误，避免资源清理失败覆盖验收失败等关键信息。
                run_error = exc
                raise
            finally:
                # 会话设置了 keep_alive，所以由入口显式关闭浏览器。
                try:
                    await session.kill()
                except Exception as cleanup_error:
                    if run_error is None:
                        raise
                    # 原任务已失败时，清理错误只附加到该异常，不替换它。
                    run_error.add_note(f"关闭浏览器失败：{cleanup_error}")
        # 只有事实验收通过且资源正常清理后才写 result.json；此前失败则不写结果。
        (directory / "result.json").write_text(output, encoding="utf-8")
        write_run_status(directory, "success")
        print("验收通过；本次结果和轨迹：", directory)
        return result
    except Exception as exc:
        # 尽量落盘未完成运行的部分轨迹，为复盘模型错误或页面错误提供线索。
        if agent is not None and agent.history.history and not (directory / "history.json").exists():
            try:
                agent.history.save_to_file(directory / "history.json")
            except Exception as history_error:
                exc.add_note(f"保存失败轨迹时出错：{history_error}")
        # 失败状态和异常向外传播；上一轮成功结果因目录隔离而不受影响。
        write_run_status(directory, "failed", exc)
        print("运行失败；本次轨迹：", directory)
        raise


def main() -> None:
    # 多页面研究比 04 预留更多步骤；命令行仍可指定正整数步数上限。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--max-steps", type=int, default=20)
    args = parser.parse_args()
    if args.max_steps < 1:
        parser.error("--max-steps 必须大于 0")
    asyncio.run(run_demo(args.headless, args.max_steps))


if __name__ == "__main__":
    main()
