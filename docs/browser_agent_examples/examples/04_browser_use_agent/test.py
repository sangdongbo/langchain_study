"""04 离线集成检查：固定模型响应驱动真实本地浏览器。"""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from run import run_demo

import browser_examples.runtime as runtime
from browser_examples.testing import ScriptedModel

# 固定脚本只测试动作接口，不代表真实模型能自主定位控件或制定操作计划。
# JS 先注册 MutationObserver 再点击，并等待筛选完成，避免错过异步状态更新。
# 最后读取未被 hidden 隐藏的卡片，返回真实 DOM 中的名称和价格。
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
    # 暂时重定向产物根目录，让成功/失败场景都不污染已有的学习结果。
    original_project_dir = runtime.PROJECT_DIR
    try:
        with TemporaryDirectory() as temporary:
            runtime.PROJECT_DIR = Path(temporary)
            # 两个固定模型响应：执行真实页面筛选，再报告任务完成。
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
            # 从落盘轨迹验收实际提取内容，不能只断言预先写好的最终答案。
            history = json.loads((success_dir / "history.json").read_text(encoding="utf-8"))
            extracted = [
                json.loads(action_result["extracted_content"])
                for step in history["history"]
                for action_result in step["result"]
                if action_result.get("extracted_content", "").startswith("[")
            ]
            assert [{"name": "数据分析笔记本", "price_yuan": 5999},
                    {"name": "开发者迷你主机", "price_yuan": 4299}] in extracted
            # 确认调用次数、完成状态和对话产物均符合预期。
            assert model.calls == 2
            assert "5999" in result
            assert json.loads((success_dir / "status.json").read_text(encoding="utf-8")) == {
                "status": "success"
            }
            assert any((success_dir / "conversation").iterdir())

            # 第二次运行主动报告失败，验证入口不会把“有回答”误判为成功。
            failed_model = ScriptedModel([
                {"done": {"text": "没有完成筛选。", "success": False}},
            ])
            try:
                await run_demo(headless=True, max_steps=2, llm=failed_model)
            except RuntimeError:
                pass
            else:
                raise AssertionError("Agent 自报失败时 run_demo 必须失败")
            # 失败独立落盘，同时上一轮成功目录和状态必须仍然保留。
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
        # 即使断言失败也恢复全局路径，避免影响同一进程中的其他检查。
        runtime.PROJECT_DIR = original_project_dir
    print("04 PASS：完整入口、真实筛选、独立产物及失败状态")


if __name__ == "__main__":
    asyncio.run(main())
