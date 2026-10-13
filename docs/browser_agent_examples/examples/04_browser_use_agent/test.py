"""04 离线集成检查：固定模型响应驱动真实本地浏览器。"""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run import run_demo

import browser_examples.runtime as runtime
from browser_examples.testing import ScriptedModel

FILTER_CODE = """(async () => {
    const status = document.querySelector('[data-testid="result-status"]');
    const ready = new Promise(resolve => {
        const observer = new MutationObserver(() => {
            if (status.textContent === '找到 2 件商品') {
                observer.disconnect();
                resolve();
            }
        });
        observer.observe(status, {childList: true});
    });
    document.querySelector('[data-testid="category"]').value = '计算设备';
    document.querySelector('[data-testid="max-price"]').value = '6500';
    document.querySelector('[data-testid="apply-filter"]').click();
    await ready;
    return [...document.querySelectorAll('.product:not([hidden])')].map(card => ({
        name: card.dataset.name, price_yuan: Number(card.dataset.price)
    }));
})()"""


async def main() -> None:
    original_project_dir = runtime.PROJECT_DIR
    try:
        with TemporaryDirectory() as temporary:
            runtime.PROJECT_DIR = Path(temporary)
            model = ScriptedModel([
                {"evaluate": {"code": FILTER_CODE}},
                {"done": {
                    "text": "数据分析笔记本：5999 元；开发者迷你主机：4299 元。",
                    "success": True,
                }},
            ])
            result = await run_demo(headless=True, max_steps=4, llm=model)
            root = runtime.PROJECT_DIR / ".artifacts" / "04_browser_use_agent"
            success_dir = next(root.iterdir())
            history = json.loads((success_dir / "history.json").read_text(encoding="utf-8"))
            extracted = [
                json.loads(action_result["extracted_content"])
                for step in history["history"]
                for action_result in step["result"]
                if action_result.get("extracted_content", "").startswith("[")
            ]
            assert [{"name": "数据分析笔记本", "price_yuan": 5999},
                    {"name": "开发者迷你主机", "price_yuan": 4299}] in extracted
            assert model.calls == 2
            assert "5999" in result
            assert json.loads((success_dir / "status.json").read_text(encoding="utf-8")) == {
                "status": "success"
            }
            assert any((success_dir / "conversation").iterdir())

            failed_model = ScriptedModel([
                {"done": {"text": "没有完成筛选。", "success": False}},
            ])
            try:
                await run_demo(headless=True, max_steps=2, llm=failed_model)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Agent 自报失败时 run_demo 必须失败")
            failed_dir = next(path for path in root.iterdir() if path != success_dir)
            failed_status = json.loads((failed_dir / "status.json").read_text(encoding="utf-8"))
            assert failed_status["status"] == "failed"
            assert "RuntimeError" in failed_status["error"]
            assert (failed_dir / "history.json").is_file()
            assert not (failed_dir / "result.json").exists()
            assert json.loads((success_dir / "status.json").read_text(encoding="utf-8")) == {
                "status": "success"
            }
            assert len(list(root.iterdir())) == 2
    finally:
        runtime.PROJECT_DIR = original_project_dir
    print("04 PASS：完整入口、真实筛选、独立产物及失败状态")


if __name__ == "__main__":
    asyncio.run(main())
