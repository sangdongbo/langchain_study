"""05 离线检查：字段/事实校验，以及真实浏览器的多页面结构化结果。"""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

import run as demo

import browser_examples.runtime as runtime
from browser_examples.demo_server import DemoServer
from browser_examples.testing import ScriptedModel


def expected_result(site_url: str) -> demo.ResearchResult:
    # 独立列出页面固定事实；随机端口只影响来源 URL，不影响商品内容。
    return demo.ResearchResult(
        requirement="计算设备且不超过 6500 元",
        products=[
            demo.Product(
                name="数据分析笔记本", price_yuan=5999, specs="32GB 内存 · 1TB SSD",
                details="便携机型，适合移动办公与数据分析。",
                source_url=f"{site_url}/detail.html?id=laptop",
            ),
            demo.Product(
                name="开发者迷你主机", price_yuan=4299, specs="24GB 内存 · 512GB SSD",
                details="桌面机型，适合固定工位；不含显示器。",
                source_url=f"{site_url}/detail.html?id=mini",
            ),
        ],
        recommendation="固定工位且预算优先时选择开发者迷你主机。",
    )


def check_validation() -> None:
    # 这里的 URL 只参与字符串比对，不启动服务器，也不发出网络请求。
    site_url = "http://127.0.0.1:8765"
    result = expected_result(site_url)
    visited = [product.source_url for product in result.products]
    demo.validate_demo_result(result, site_url, visited)
    # 第一层负例：负数价格连基本数据契约都不满足，应由 Pydantic 拒绝。
    try:
        demo.Product(
            name="错误商品", price_yuan=-1, specs="未知", details="未知", source_url="未知"
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("负数价格必须被 Pydantic 拒绝")
    # 第二层负例：漏项、重复及虚构字段，由独立事实规则而不是模型判定。
    # model_copy(update=...) 不重新执行字段校验，便于定向构造错误结果。
    invalid_results = [
        result.model_copy(update={"products": result.products[:1]}),
        result.model_copy(update={"products": [result.products[0], result.products[0]]}),
    ]
    for field, wrong in (
        ("price_yuan", 1), ("specs", "虚构规格"), ("details", "虚构说明"),
        ("source_url", "https://untrusted.example"),
    ):
        invalid_results.append(result.model_copy(update={"products": [
            result.products[0].model_copy(update={field: wrong}), result.products[1]
        ]}))
    # 最后一组保持答案正确但缺少访问轨迹，验证“写了来源”不等于“访问了来源”。
    for invalid, urls in [(item, visited) for item in invalid_results] + [(result, visited[:1])]:
        try:
            demo.validate_demo_result(invalid, site_url, urls)
        except ValueError:
            pass
        else:
            raise AssertionError("漏项、重复、虚构事实或未访问来源不能通过验收")


def scripted_model(expected: demo.ResearchResult) -> ScriptedModel:
    # 固定 JS 从真实详情页读取四个字段；不使用预设答案代替 DOM 提取。
    read_detail = """(() => Object.fromEntries(
            ['name', 'price', 'specs', 'details'].map(key => [
                key, document.querySelector('[data-testid="product-' + key + '"]').textContent
            ])
        ))()"""
    # 每件商品先导航再提取，最后返回结构化 done；这些动作无需调用模型 API。
    actions = []
    for product in expected.products:
        actions.extend([
            {"navigate": {"url": product.source_url, "new_tab": False}},
            {"evaluate": {"code": read_detail}},
        ])
    actions.append({"done": {"data": expected.model_dump(), "success": True}})
    return ScriptedModel(actions)


async def run_with_site(site: DemoServer, model: ScriptedModel) -> demo.ResearchResult:
    # site 创建时已分配端口；临时替换工厂，让任务和预设来源使用同一个 URL。
    # 服务器仍由 run_demo 的 with 负责启动和清理，不绕过正常入口。
    original_server = demo.DemoServer
    demo.DemoServer = lambda: site
    try:
        return await demo.run_demo(headless=True, max_steps=8, llm=model)
    finally:
        # 无论成功或失败都恢复工厂，避免测试替换泄漏到后续运行。
        demo.DemoServer = original_server


async def check_browser() -> None:
    # 临时产物目录隔离真实学习结果，测试结束后自动清理。
    original_project_dir = runtime.PROJECT_DIR
    try:
        with TemporaryDirectory() as temporary:
            runtime.PROJECT_DIR = Path(temporary)
            site = DemoServer()
            expected = expected_result(site.url)
            model = scripted_model(expected)
            result = await run_with_site(site, model)
            assert result == expected
            root = runtime.PROJECT_DIR / ".artifacts" / "05_structured_research"
            success_dir = next(root.iterdir())
            # 重新解析落盘结果，验证保存的文件也符合契约，不只检查内存对象。
            saved_result = demo.ResearchResult.model_validate_json(
                (success_dir / "result.json").read_text(encoding="utf-8")
            )
            assert saved_result == expected
            status = json.loads((success_dir / "status.json").read_text(encoding="utf-8"))
            assert status == {"status": "success"}
            history = json.loads((success_dir / "history.json").read_text(encoding="utf-8"))
            # 从实际动作轨迹提取 evaluate 返回值，确认两个详情页都真的读过。
            extracted = [
                json.loads(action_result["extracted_content"])
                for step in history["history"]
                for action_result in step["result"]
                if action_result.get("extracted_content", "").startswith("{")
            ]
            for product in expected.products:
                assert {"name": product.name, "price": str(product.price_yuan),
                        "specs": product.specs, "details": product.details} in extracted
            # 两次导航 + 两次提取 + 一次完成，共五个固定模型响应。
            assert model.calls == 5

            # 价格 1 是合法正整数但与页面不符；即使自报成功也必须验收失败。
            failed_site = DemoServer()
            invalid = expected_result(failed_site.url)
            invalid.products[0].price_yuan = 1
            failed_model = ScriptedModel([
                {"done": {"data": invalid.model_dump(), "success": True}},
            ])
            try:
                await run_with_site(failed_site, failed_model)
            except ValueError:
                pass
            else:
                raise AssertionError("事实验收失败时 run_demo 必须失败")
            # 失败运行保存状态和轨迹，但不能生成 result.json 或覆盖旧成功结果。
            failed_dir = next(path for path in root.iterdir() if path != success_dir)
            failed_status = json.loads((failed_dir / "status.json").read_text(encoding="utf-8"))
            assert failed_status["status"] == "failed"
            assert "ValueError" in failed_status["error"]
            assert (failed_dir / "history.json").is_file()
            assert not (failed_dir / "result.json").exists()
            assert (success_dir / "result.json").is_file()
            assert len(list(root.iterdir())) == 2
    finally:
        # 恢复共享路径，确保本检查不改变其他示例的产物位置。
        runtime.PROJECT_DIR = original_project_dir


if __name__ == "__main__":
    # 先测无需浏览器的校验规则，再运行真实 Chromium 的离线集成流程。
    check_validation()
    asyncio.run(check_browser())
    print("05 PASS：完整入口、事实验收、独立结果及失败状态")
