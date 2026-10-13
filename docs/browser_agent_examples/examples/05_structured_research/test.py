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
    site_url = "http://127.0.0.1:8765"
    result = expected_result(site_url)
    visited = [product.source_url for product in result.products]
    demo.validate_demo_result(result, site_url, visited)
    try:
        demo.Product(
            name="错误商品", price_yuan=-1, specs="未知", details="未知", source_url="未知"
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("负数价格必须被 Pydantic 拒绝")
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
    for invalid, urls in [(item, visited) for item in invalid_results] + [(result, visited[:1])]:
        try:
            demo.validate_demo_result(invalid, site_url, urls)
        except ValueError:
            pass
        else:
            raise AssertionError("漏项、重复、虚构事实或未访问来源不能通过验收")


def scripted_model(expected: demo.ResearchResult) -> ScriptedModel:
    read_detail = """(() => Object.fromEntries(
            ['name', 'price', 'specs', 'details'].map(key => [
                key, document.querySelector('[data-testid="product-' + key + '"]').textContent
            ])
        ))()"""
    actions = []
    for product in expected.products:
        actions.extend([
            {"navigate": {"url": product.source_url, "new_tab": False}},
            {"evaluate": {"code": read_detail}},
        ])
    actions.append({"done": {"data": expected.model_dump(), "success": True}})
    return ScriptedModel(actions)


async def run_with_site(site: DemoServer, model: ScriptedModel) -> demo.ResearchResult:
    original_server = demo.DemoServer
    demo.DemoServer = lambda: site
    try:
        return await demo.run_demo(headless=True, max_steps=8, llm=model)
    finally:
        demo.DemoServer = original_server


async def check_browser() -> None:
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
            saved_result = demo.ResearchResult.model_validate_json(
                (success_dir / "result.json").read_text(encoding="utf-8")
            )
            assert saved_result == expected
            status = json.loads((success_dir / "status.json").read_text(encoding="utf-8"))
            assert status == {"status": "success"}
            history = json.loads((success_dir / "history.json").read_text(encoding="utf-8"))
            extracted = [
                json.loads(action_result["extracted_content"])
                for step in history["history"]
                for action_result in step["result"]
                if action_result.get("extracted_content", "").startswith("{")
            ]
            for product in expected.products:
                assert {"name": product.name, "price": str(product.price_yuan),
                        "specs": product.specs, "details": product.details} in extracted
            assert model.calls == 5

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
            failed_dir = next(path for path in root.iterdir() if path != success_dir)
            failed_status = json.loads((failed_dir / "status.json").read_text(encoding="utf-8"))
            assert failed_status["status"] == "failed"
            assert "ValueError" in failed_status["error"]
            assert (failed_dir / "history.json").is_file()
            assert not (failed_dir / "result.json").exists()
            assert (success_dir / "result.json").is_file()
            assert len(list(root.iterdir())) == 2
    finally:
        runtime.PROJECT_DIR = original_project_dir


if __name__ == "__main__":
    check_validation()
    asyncio.run(check_browser())
    print("05 PASS：完整入口、事实验收、独立结果及失败状态")
