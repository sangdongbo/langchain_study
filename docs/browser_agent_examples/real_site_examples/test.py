"""离线检查：完整脚本/Agent 入口、细粒度网页动作及安全限制，无真实站/模型/数据库。"""

# 这些是教学用 assert 检查，直接运行本文件即可；不要用 python -O，否则 assert 会被关闭。
# 测试分层：金额/结构校验 → 真实本地 Chromium 的网页动作 → 完整入口与产物验收。
# 所有页面与 UI 请求都由 fixture_router 内存响应，模型由 ScriptedModel 固定响应代替。
# simulate_user_login 只在虚构页面扮演用户，绝不能复制为真实站自动发送验证码的工具。

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from playwright.async_api import Locator, TimeoutError as PlaywrightTimeoutError, async_playwright, expect

import agent as demo
import auth
import browser_examples.runtime as runtime
import run as script
from browser_examples.runtime import create_session
from browser_examples.testing import ScriptedModel
from compare import compare_runs
from erp import DetailOpenError, ORDER_SEARCH_SELECTOR, READ_TABLE, OrderReader, OrderReport, money, parse_table
from reporting import CountedModel

# 用 __file__ 定位 fixture，避免启动目录不同而加载错误测试页面。
FIXTURE = Path(__file__).with_name("fixture.html").read_text(encoding="utf-8")
LOGIN_FIXTURE = Path(__file__).with_name("login_fixture.html").read_text(encoding="utf-8")
# 复用同一订单页，避免认证测试和业务测试各自维护一套表格。
AUTH_FIXTURE = FIXTURE.replace("<body>", '<body><div id="business">').replace(
    "</body>", "</div>" + LOGIN_FIXTURE + "</body>"
)
# 专门复现跨标签页丢失会话：状态只放 sessionStorage，新增标签页不能直接继承。
TAB_AUTH_FIXTURE = AUTH_FIXTURE.replace(
    "localStorage.getItem('fixture-token')", "sessionStorage.getItem('fixture-token')"
).replace("localStorage.setItem('fixture-token'", "sessionStorage.setItem('fixture-token'")
LOCAL_URL = "http://127.0.0.1:8765/web/#/order"
# 该地址只是路由拦截匹配目标，不需要启动 8765 端口服务，也不连接业务后端。


def must_reject(action) -> None:
    # action 是尚未执行的零参数函数；只接受预期的 ValueError，其他异常不能冒充通过。
    try:
        action()
    except ValueError:
        return
    raise AssertionError("错误数据必须被拒绝")


async def must_reject_async(action) -> None:
    # 校验失败必须发生在网页动作之前；不能以“没找到按钮”冒充安全拒绝。
    try:
        await action
    except ValueError:
        return
    raise AssertionError("未授权动作必须被拒绝")


def fixture_router(html: str = FIXTURE):
    # 返回 Playwright route 回调；html 可换为认证页或故意破坏字段的异常测试页。
    async def handle(route):
        # 全部请求在内存响应，未知地址直接终止；不启动后端或接触真实接口。
        url = route.request.url
        if url.startswith("http://127.0.0.1:8765/search?"):
            # 生产代码只检查该 UI 请求成功结束；表格内容仍由虚构页面自己的脚本渲染。
            await route.fulfill(status=200, content_type="application/json", body="{}")
        elif url == "http://127.0.0.1:8765/web/":
            await route.fulfill(content_type="text/html; charset=utf-8", body=html)
        else:
            # 未知地址不放行，防止 fixture 或模型动作意外访问真实网络。
            await route.abort()
    return handle


async def check_reader(page) -> None:
    # 直接测试 OrderReader，不需要模型；每个负例必须在小动作自己的边界检查处拒绝。
    reader = OrderReader(page, "DD-DEMO", 2, LOCAL_URL)
    await reader.open_list()
    # 全页三个同名框、订单区域两个，但业务定位只能得到唯一可见的那个，不能靠 .first() 蒙对。
    assert await page.get_by_placeholder("请输入您想搜索的内容", exact=True).count() == 3
    assert await page.locator(ORDER_SEARCH_SELECTOR).count() == 2
    assert await reader.search_box().count() == 1
    observation = await reader.observe()
    target = observation["controls"][0]["target_id"]
    assert observation["next_action"] == "input_text"
    assert observation["controls"][0]["actions"] == ["input_text"]
    assert observation["controls"][0]["placeholder"] == "请输入您想搜索的内容"
    await must_reject_async(reader.read_orders())
    await must_reject_async(reader.press_enter(target))
    await must_reject_async(reader.input_text(target, "未经授权的其他关键词"))
    await must_reject_async(reader.safe_click("o1:new_order"))
    await must_reject_async(reader.safe_click(target))
    # 上面既验证未登记目标，也验证“搜索框目标不能当订单链接点击”的类型约束。
    await reader.input_text(target, "DD-DEMO")
    assert reader.progress()["next_action"] == "observe_page"
    # 输入必须落到当前订单搜索框，不能污染其他页签或隐藏副本。
    assert await page.locator("#order-keyword").input_value() == "DD-DEMO"
    assert await page.locator("#inactive-other-search").input_value() == "inactive-other"
    assert await page.locator("#inactive-order-search").input_value() == "inactive-order"
    await must_reject_async(reader.press_enter(target))  # 输入后旧目标已失效。
    observation = await reader.observe()
    assert observation["next_action"] == "press_enter"
    assert observation["controls"][0]["actions"] == ["press_enter"]
    await reader.press_enter(observation["controls"][0]["target_id"])
    assert reader.progress()["next_action"] == "read_orders"
    report = await reader.read_orders()
    # 虚构数据特意包含小数和千位分隔，Decimal 精确合计应为 1100.20。
    assert [item.number for item in report.orders] == ["DD-DEMO-001", "DD-DEMO-002"]
    assert report.orders[0].outstanding_yuan == Decimal("100.10")
    assert report.orders[1].outstanding_yuan == Decimal("1000.10")
    assert report.outstanding_yuan == Decimal("1100.20")
    assert report.matched_total == report.rendered_count == 2

    # 两个表的行序故意不同；重名列冲突、缺失列、重复订单都必须拒绝。
    raw = await page.locator("#pane-order").evaluate(READ_TABLE)
    conflict = deepcopy(raw)
    # 每个损坏场景复制独立数据，避免修改一个负例后污染其他测试的输入。
    duplicate = [cell for cell in conflict["rows"][0] if cell["title"] == "订单总金额(元)"]
    duplicate[-1]["text"] = "999.99"
    must_reject(lambda: parse_table(conflict, "DD-DEMO", 2, LOCAL_URL))
    missing = deepcopy(raw)
    missing["rows"][0] = [cell for cell in missing["rows"][0] if cell["title"] != "待回款金额(元)"]
    must_reject(lambda: parse_table(missing, "DD-DEMO", 2, LOCAL_URL))
    repeated = deepcopy(raw)
    repeated["total"] = "共 3 条"
    repeated["rows"].append(repeated["rows"][0])
    must_reject(lambda: parse_table(repeated, "DD-DEMO", 3, LOCAL_URL))

    # 模型不能通过改工具名恢复任意点击、脚本执行、导航或文件写入。
    schema = demo.build_tools(reader).registry.create_action_model()
    # 从真实工具注册表生成 schema，确保不是只在提示词里宣称禁用了通用动作。
    for action in ({"click": {"index": 1}}, {"evaluate": {"code": "alert(1)"}},
                   {"navigate": {"url": LOCAL_URL}}, {"write_file": {"file_name": "x", "content": "x"}},
                   {"query_orders": {}}):
        must_reject(lambda: schema.model_validate(action))
    await must_reject_async(reader.read_detail())
    observation = await reader.observe()
    old_target = observation["controls"][1]["target_id"]
    await reader.observe()
    await must_reject_async(reader.safe_click(old_target))  # 重新观察也会作废目标。
    detail = await reader.verify("DD-DEMO-002")
    # 最大待回款放在第二行，验证不能用“总是点击第一条”蒙混过关。
    assert detail.total_yuan == Decimal("1000.10") and "/order_detail?" in detail.source_url
    # 目标必须是绑定订单点击事件的容器，而不是可能被遮挡/不接收指针的子 span。
    assert await reader.order_link("DD-DEMO-002").evaluate("element => element.matches('.order_num')")
    assert await page.locator("#write-attempts").inner_text() == "0"
    assert any(item["status"] == "failed" for item in reader.log.actions)

    # 合法结构不代表事实正确；覆盖漏项、错金额、虚构访问及核对错订单。
    good = expected_summary()
    demo.validate_summary(good, reader)
    for updates in ({"outstanding_yuan": Decimal("0")}, {"checked_order_numbers": []},
                    {"order_numbers": good.order_numbers[:1]}):
        must_reject(lambda: demo.validate_summary(good.model_copy(update=updates), reader))
    report.detail_checks[0].order_number = "DD-DEMO-001"
    # 故意把“工具证据”和“模型摘要”一起改成非最大订单，最大待回款验收仍应失败。
    wrong_check = good.model_copy(update={"checked_order_numbers": ["DD-DEMO-001"]})
    must_reject(lambda: demo.validate_summary(wrong_check, reader))

    empty = await OrderReader(page, "DD-NO-MATCH", 2, LOCAL_URL).query()
    assert empty.orders == [] and empty.outstanding_yuan == 0
    limited = await OrderReader(page, "DD-DEMO", 1, LOCAL_URL).query()
    assert limited.matched_total == 2 and len(limited.orders) == 1
    assert limited.outstanding_yuan == Decimal("100.10")


async def expect_detail_error(action) -> str:
    # 只接受安全的业务异常；浏览器原始异常、断言失败都不能冒充预期失败。
    try:
        await action
    except DetailOpenError as error:
        assert "fixture-secret" not in str(error) and error.__suppress_context__
        return str(error)
    raise AssertionError("详情未打开时必须明确报告失败")


async def check_detail_recovery(context) -> None:
    """只在内存 fixture 上注入点击故障，覆盖状态恢复，不接触真实 ERP。"""
    async def prepared_reader():
        page = await context.new_page()
        reader = OrderReader(page, "DD-DEMO", 2, LOCAL_URL)
        await reader.query()
        observation = await reader.observe()
        target = next(item["target_id"] for item in observation["controls"] if item["text"] == "DD-DEMO-002")
        return reader, target

    # 首次点击超时且仍在列表：允许重新观察，但仅发放同一订单的新目标。
    reader, target = await prepared_reader()
    with patch.object(Locator, "click", side_effect=PlaywrightTimeoutError("fixture-secret")):
        await expect_detail_error(reader.safe_click(target))
    assert reader.stage == "read" and reader.selected_order is None and reader.report.detail_checks == []
    assert reader.progress()["next_action"] == "observe_page"
    observation = await reader.observe()
    assert [item["text"] for item in observation["controls"]] == ["DD-DEMO-002"]
    await must_reject_async(reader.safe_click(target))  # 失败前的旧 target_id 仍然无效。
    await reader.safe_click(observation["controls"][0]["target_id"])
    assert reader.stage == "detail" and reader.progress()["next_action"] == "read_detail"
    assert reader.report.detail_checks == []  # 打开成功绝不能自动补一条“金额核对”。
    await reader.read_detail()
    assert reader.progress()["detail_verified"] and reader.progress()["next_action"] == "done"
    actions = [item for item in reader.log.actions if item["action"] == "safe_click"]
    diagnostic = actions[0]["parameters"]["diagnostics"]
    assert actions[0]["status"] == "failed" and diagnostic[0]["target_count"] == 1
    assert diagnostic[-1]["error_type"] == "TimeoutError" and diagnostic[-1]["route"] == "/order"
    assert "fixture-secret" not in json.dumps(actions)

    # 连续两次失败后停止，不因重新观察而重置重试预算或无限发放目标。
    reader, target = await prepared_reader()
    with patch.object(Locator, "click", side_effect=PlaywrightTimeoutError("fixture-secret")):
        await expect_detail_error(reader.safe_click(target))
        observation = await reader.observe()
        await expect_detail_error(reader.safe_click(observation["controls"][0]["target_id"]))
    observation = await reader.observe()
    assert reader.stage == "blocked" and reader.detail_attempts == 2
    assert observation["controls"] == [] and observation["next_action"] == "done"
    assert observation["last_click_error"] and not observation["detail_verified"]
    await must_reject_async(reader.read_detail())

    # 模拟真实点击已打开详情，底层随后才报超时；必须按实际标题/路由恢复，不能再点击。
    reader, target = await prepared_reader()
    original_click = Locator.click

    async def opened_then_timeout(locator, **kwargs):
        await original_click(locator, **kwargs)
        raise PlaywrightTimeoutError("fixture-secret")

    with patch.object(Locator, "click", new=opened_then_timeout):
        await reader.safe_click(target)
    assert reader.stage == "detail" and reader.selected_order == "DD-DEMO-002"
    assert reader.report.detail_checks == [] and reader.last_click_diagnostics[-1]["target_detail_open"]
    observation = await reader.observe()
    assert observation["controls"] == [] and observation["next_action"] == "read_detail"
    await reader.read_detail()

    # 错订单、未知路由、关闭页面都必须停止，不能把“有页面”当成目标已打开。
    for mode in ("wrong_detail", "unknown_route", "closed"):
        reader, target = await prepared_reader()

        async def invalid_destination(locator, **kwargs):
            if mode == "wrong_detail":
                await original_click(locator, **kwargs)
                await reader.page.locator("h2").evaluate("element => element.textContent = 'DD-DEMO-001'")
            elif mode == "unknown_route":
                await reader.page.evaluate("location.hash = '/unexpected?token=fixture-secret'")
            else:
                await reader.page.close()
            raise PlaywrightTimeoutError("fixture-secret")

        with patch.object(Locator, "click", new=invalid_destination):
            await expect_detail_error(reader.safe_click(target))
        assert reader.stage == "blocked" and reader.selected_order is None and reader.report.detail_checks == []
        observation = await reader.observe()
        assert observation["controls"] == [] and observation["last_click_error"]
        assert "fixture-secret" not in json.dumps(reader.log.actions)
        await must_reject_async(reader.read_detail())


def expected_summary(empty: bool = False) -> demo.AgentSummary:
    # 统一维护非空/空结果的预期结构；这里只使用虚构编号，不引用真实业务账号或订单。
    return demo.AgentSummary(
        order_numbers=[] if empty else ["DD-DEMO-001", "DD-DEMO-002"],
        outstanding_yuan="0.00" if empty else "1100.20",
        checked_order_numbers=[] if empty else ["DD-DEMO-002"],
        observation="只描述本轮当前页前两条的虚构订单，不推断逾期或信用风险。",
    )


def scripted_model(empty: bool = False) -> ScriptedModel:
    # 固定响应只是验证接口；实际工具仍在真实 Chromium 里逐步操作和读取 DOM。
    keyword = "DD-NO-MATCH" if empty else "DD-DEMO"
    actions = [
        # 每次观察递增 revision；填写后旧目标作废，因此必须再次 observe 才能按 Enter。
        {"observe_page": {}},
        {"input_text": {"target_id": "o1:search", "text": keyword}},
        {"observe_page": {}},
        {"press_enter": {"target_id": "o2:search"}},
        {"read_orders": {}},
    ]
    if not empty:
        # 空结果没有候选详情链接；非空分支模拟模型选择第二条订单并实际读取核对。
        actions.extend([
            {"observe_page": {}},
            {"safe_click": {"target_id": "o3:order:2"}},
            {"read_detail": {}},
        ])
    actions.append({"done": {"data": expected_summary(empty).model_dump(mode="json"), "success": True}})
    return ScriptedModel(actions)


async def simulate_user_login(page, code: str = "246810") -> None:
    """仅测试使用：扮演用户在虚构网页点击和填写，不属于生产认证逻辑。"""
    account_box = page.get_by_placeholder("请输入手机号/邮箱", exact=True)
    await expect(account_box).to_be_visible()
    await expect(page.get_by_placeholder("验证码", exact=True)).to_have_value("")
    # 明确检查生产等待逻辑没有提前填写验证码，再由本测试驱动输入虚构数据。
    await account_box.fill("learner@example.invalid")
    await page.get_by_role("button", name="获取验证码", exact=True).click()
    await page.get_by_placeholder("验证码", exact=True).fill(code)
    await page.get_by_role("button", name="登录", exact=True).click()


@asynccontextmanager
async def offline_browser(headless, auth_path, html=FIXTURE, manual_code=None):
    # auth_path 由 run_offline 替换为临时目录，只允许导入虚构登录状态。
    async with async_playwright() as playwright:
        session = await create_session(headless=True)
        # 即使调用方模拟有窗口模式，测试也始终用无窗口 Chromium，便于自动执行。
        user_task = None
        try:
            await session.start()
            browser = await playwright.chromium.connect_over_cdp(session.cdp_url)
            context = browser.contexts[0]
            await context.route("**/*", fixture_router(html))
            # 必须先安装路由再恢复状态/打开页面，任何页面加载都不能意外进入真实站点。
            await auth.restore_auth(context, auth_path)
            page = context.pages[0] if context.pages else await context.new_page()
            if manual_code is not None:
                # 与生产 ensure_login 同时运行，模拟用户在程序等待期间主动操作网页。
                user_task = asyncio.create_task(simulate_user_login(page, manual_code))
            yield session, page
            # 登录接续必须保留原标签页，不能再静默新开标签页进行订单检查。
            assert context.pages == [page] and not page.is_closed()
            for business_page in context.pages:
                if await business_page.locator("#write-attempts").count():
                    assert await business_page.locator("#write-attempts").inner_text() == "0"
        finally:
            try:
                if user_task is not None:
                    # 业务失败或提前结束时回收模拟用户任务，避免后台继续操作已关闭页面。
                    if not user_task.done():
                        user_task.cancel()
                    try:
                        await user_task
                    except asyncio.CancelledError:
                        pass
            finally:
                await session.kill()


async def run_offline(module, keyword: str = "DD-DEMO", llm=None, html=FIXTURE,
                      manual_code=None) -> Path:
    # 只替换站点入口和浏览器工厂；生产 run_demo 的验收、落盘、失败处理全部保留。
    # patch 必须打在使用名字的模块上；partial 仅绑定本地 URL/fixture，不重写业务步骤。
    # AUTH_PATH 同时替换到临时目录，保证不会读取仓库 .artifacts 中的真实登录状态。
    with patch.object(module, "order_browser", partial(offline_browser, html=html, manual_code=manual_code)), \
         patch.object(module, "AUTH_PATH", runtime.PROJECT_DIR / "fixture_auth.json"), \
         patch.object(module, "ensure_login", partial(auth.ensure_login, url=LOCAL_URL)), \
         patch.object(module, "OrderReader", partial(OrderReader, url=LOCAL_URL)):
        if module is demo:
            # 工厂始终启动无窗口测试浏览器；这里只模拟调用方选择了人工登录模式。
            return await demo.run_demo(keyword, 2, manual_code is None, 12, False, llm=llm)
        return await script.run_demo(keyword, 2, manual_code is None, False)


async def check_entries() -> None:
    # 分别调用生产固定脚本和 Agent 完整入口，再用真实 compare_runs 验证同任务一致性。
    script_dir = await run_offline(script)
    model = scripted_model()
    agent_dir = await run_offline(demo, llm=model)
    comparison = compare_runs(script_dir, agent_dir)
    assert comparison["same_snapshot"] and comparison["same_checked_orders"]
    assert comparison["script"]["model_calls"] == 0
    assert comparison["agent"]["model_calls"] == model.calls == 9
    # 九次是此固定响应序列的调用数，不代表真实模型总能九步完成，也不能据此估算费用。
    actions = json.loads((agent_dir / "actions.json").read_text(encoding="utf-8"))
    assert [item["action"] for item in actions] == [
        "open_list", "observe_page", "input_text", "observe_page", "press_enter",
        "read_orders", "observe_page", "safe_click", "read_detail",
    ]
    result = demo.AgentSummary.model_validate_json((agent_dir / "result.json").read_text(encoding="utf-8"))
    assert result == expected_summary()
    assert comparison["agent"]["failed_actions"] == 0
    assert comparison["agent"]["elapsed_seconds"] > 0

    # 快照不同应明确报告，不能把两次业务数据变化说成模型计算错误。
    changed = OrderReport.model_validate_json((script_dir / "result.json").read_text(encoding="utf-8"))
    changed.orders[0].customer = "另一份虚构快照"
    (script_dir / "result.json").write_text(changed.model_dump_json(), encoding="utf-8")
    assert compare_runs(script_dir, agent_dir)["same_snapshot"] is False

    # done 在框架宣布成功前先验收；无查询证据的 success=true 被拒绝，再以失败结束。
    failed_model = ScriptedModel([
        {"done": {"data": expected_summary().model_dump(mode="json"), "success": True}},
        {"done": {"data": expected_summary().model_dump(mode="json"), "success": False}},
    ])
    try:
        await run_offline(demo, llm=failed_model)
    except RuntimeError:
        pass
    else:
        raise AssertionError("模型空口声明成功不能通过验收")
    root = runtime.PROJECT_DIR / ".artifacts" / "erp_order_agent"
    failed_dir = next(path for path in root.iterdir() if path != agent_dir)
    metrics = json.loads((failed_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "failed" and metrics["model_calls"] == 2
    failed_history = json.loads((failed_dir / "history.json").read_text(encoding="utf-8"))["history"]
    assert failed_history[0]["result"][0]["is_done"] is False
    assert "业务验收拒绝" in failed_history[0]["result"][0]["error"]
    assert (failed_dir / "history.json").is_file() and not (failed_dir / "result.json").exists()
    assert (agent_dir / "result.json").is_file()
    must_reject(lambda: compare_runs(script_dir, failed_dir))

    # 空结果也经过完整 Agent 入口，不打开详情，成功结果仍可落盘。
    empty_dir = await run_offline(demo, "DD-NO-MATCH", scripted_model(empty=True))
    empty = demo.AgentSummary.model_validate_json((empty_dir / "result.json").read_text(encoding="utf-8"))
    assert empty == expected_summary(empty=True)
    must_reject(lambda: compare_runs(script_dir, empty_dir))  # 不同关键词不能直接比较。

    # 有真实列表但没核对详情时，提前 done 必须被拒绝；模型仍可继续补齐详情后成功。
    actions = list(scripted_model().actions)
    premature = expected_summary().model_copy(update={"checked_order_numbers": []})
    actions.insert(5, {"done": {"data": premature.model_dump(mode="json"), "success": True}})
    recovery_model = ScriptedModel(actions)
    recovered_dir = await run_offline(demo, llm=recovery_model)
    assert recovery_model.calls == 10
    recovered_history = json.loads((recovered_dir / "history.json").read_text(encoding="utf-8"))["history"]
    assert recovered_history[5]["result"][0]["is_done"] is False
    assert "未核对" in recovered_history[5]["result"][0]["error"]
    assert json.loads((recovered_dir / "status.json").read_text(encoding="utf-8"))["status"] == "success"

    # 完整 Agent 也实际经历一次详情点击失败：工具反馈→重新观察→原订单重试→核对→验收。
    actions = list(scripted_model().actions)
    actions[7:7] = [{"observe_page": {}}, {"safe_click": {"target_id": "o4:order:2"}}]
    retry_model = ScriptedModel(actions)
    original_click = Locator.click
    failed_once = False

    async def fail_first_click(locator, **kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise PlaywrightTimeoutError("fixture-secret")
        return await original_click(locator, **kwargs)

    with patch.object(Locator, "click", new=fail_first_click):
        retried_dir = await run_offline(demo, llm=retry_model)
    retry_metrics = json.loads((retried_dir / "metrics.json").read_text(encoding="utf-8"))
    retry_actions = json.loads((retried_dir / "actions.json").read_text(encoding="utf-8"))
    clicks = [item for item in retry_actions if item["action"] == "safe_click"]
    assert retry_model.calls == 11 and retry_metrics["status"] == "success" and retry_metrics["failed_actions"] == 1
    assert [item["status"] for item in clicks] == ["failed", "success"]
    assert clicks[0]["parameters"]["diagnostics"][-1]["route"] == "/order"
    assert "fixture-secret" not in json.dumps(retry_actions)


async def check_auth(playwright, directory: Path) -> None:
    """只在虚构网页模拟人工登录，不读取仓库真实的 erp_auth.json。"""
    state_path = directory / "auth.json"
    browser = await playwright.chromium.launch(headless=True)
    try:
        async def new_page():
            # 每次使用新 context，避免上一个场景的有效 token 掩盖本场景的未登录状态。
            context = await browser.new_context()
            await context.route("**/*", fixture_router(AUTH_FIXTURE))
            return await context.new_page()

        # 没有用户操作时必须等待：不点击获取验证码，不读取/填写验证码。
        page = await new_page()
        answers = AsyncMock(return_value="no")
        # 只替换保存确认，绝不把验证码注入终端；验证码由 simulate_user_login 在虚构页输入。
        with patch.object(auth, "terminal_input", answers):
            task = asyncio.create_task(auth.ensure_login(page, state_path, url=LOCAL_URL))
            # ensure_login 正在后台等用户操作；下面先断言没有短信点击、没有询问保存。
            await expect(page.get_by_placeholder("请输入手机号/邮箱", exact=True)).to_be_visible()
            assert await page.evaluate("localStorage.getItem('fixture-sms-count')") is None
            assert not task.done() and answers.await_count == 0
            await simulate_user_login(page)
            business_page = await task
        assert business_page is page and not page.is_closed() and not state_path.exists()
        assert page.context.pages == [page]
        assert await business_page.get_by_placeholder("请输入您想搜索的内容", exact=True).count() == 3
        assert await business_page.locator(f"{ORDER_SEARCH_SELECTOR}:visible").count() == 1
        assert await business_page.locator('#login').count() == 0
        assert await business_page.evaluate("localStorage.getItem('fixture-sms-count')") == "1"
        assert answers.await_count == 1 and "保存" in answers.call_args.args[0]

        # 回归：sessionStorage 会话也能在原标签页继续，不能靠复制 token 或新开页修补。
        tab_context = await browser.new_context()
        await tab_context.route("**/*", fixture_router(TAB_AUTH_FIXTURE))
        tab_page = await tab_context.new_page()
        with patch.object(auth, "terminal_input", AsyncMock(return_value="no")):
            task = asyncio.create_task(auth.ensure_login(tab_page, state_path, url=LOCAL_URL))
            await simulate_user_login(tab_page)
            assert await task is tab_page
        assert tab_context.pages == [tab_page]
        assert await tab_page.evaluate("sessionStorage.getItem('fixture-token')") == "fixture-live"
        assert await tab_page.locator('#login').count() == 0
        # open_list 不能在认证完成后重复刷新同一 URL，页面内存标记必须保留。
        await tab_page.evaluate("window.fixtureDocumentMarker = 'same-document'")
        await OrderReader(tab_page, "DD-DEMO", 2, LOCAL_URL).query()
        assert await tab_page.evaluate("window.fixtureDocumentMarker") == "same-document"
        await tab_context.close()

        # 保存后新上下文直接复用：不询问账号、不请求短信、不改写原文件。
        await auth.save_auth(business_page.context, state_path)
        original = state_path.read_bytes()
        # 用原始字节检查有效会话复用没有悄悄改写凭据文件。
        page = await new_page()
        await auth.restore_auth(page.context, state_path)
        with patch.object(auth, "terminal_input", side_effect=AssertionError("有效会话不应询问登录")):
            assert await auth.ensure_login(page, state_path, url=LOCAL_URL, headless=True) is page
        assert state_path.read_bytes() == original
        assert await page.evaluate("localStorage.getItem('fixture-sms-count')") == "1"

        # 过期状态重新登录；刷新页面不能把刚获得的 token 回滚为旧 token。
        expired = json.loads(original)
        token = next(item for item in expired["origins"][0]["localStorage"] if item["name"] == "fixture-token")
        token["value"] = "fixture-expired"
        # 这是临时 fixture 文件，不是真实登录态；恢复过期值后必须允许人工换成新 token。
        state_path.write_text(json.dumps(expired), encoding="utf-8")
        page = await new_page()
        await auth.restore_auth(page.context, state_path)
        with patch.object(auth, "terminal_input", AsyncMock(return_value="yes")):
            task = asyncio.create_task(auth.ensure_login(page, state_path, "learner@example.invalid", url=LOCAL_URL))
            await expect(page.get_by_placeholder("请输入手机号/邮箱", exact=True)).to_have_value("learner@example.invalid")
            assert await page.evaluate("localStorage.getItem('fixture-sms-count')") == "1"
            await simulate_user_login(page)
            business_page = await task
        await business_page.reload()
        assert await business_page.evaluate("localStorage.getItem('fixture-token')") == "fixture-live"
        assert await business_page.locator(f"{ORDER_SEARCH_SELECTOR}:visible").is_visible()
        assert b"fixture-expired" not in state_path.read_bytes()

        # 输错仍等待人工修正，不自行重发；修正完成后才能继续。
        original = state_path.read_bytes()
        page = await new_page()
        with patch.object(auth, "terminal_input", AsyncMock(return_value="no")):
            task = asyncio.create_task(auth.ensure_login(page, state_path, url=LOCAL_URL))
            await simulate_user_login(page, "135790")
            await expect(page.locator("#login-error")).to_have_text("虚构验证码错误")
            assert not task.done()
            await page.get_by_placeholder("验证码", exact=True).fill("246810")
            await page.get_by_role("button", name="登录", exact=True).click()
            await task
        assert state_path.read_bytes() == original

        # 无操作超时、错误验证码超时和无窗口缺少会话均不能继续或保存。
        for mode, sent in (("idle", 0), ("wrong", 1), ("headless", 0)):
            # 缩短测试等待避免每个负例耗时五分钟，不改变生产 MANUAL_LOGIN_TIMEOUT_MS。
            page = await new_page()
            with patch.object(auth, "terminal_input", side_effect=AssertionError("未登录不能询问保存")), \
                 patch.object(auth, "MANUAL_LOGIN_TIMEOUT_MS", 1500):
                task = asyncio.create_task(auth.ensure_login(page, state_path, url=LOCAL_URL, headless=mode == "headless"))
                if mode == "wrong":
                    await simulate_user_login(page, "135790")
                try:
                    await task
                except auth.LoginError as exc:
                    assert "learner@example.invalid" not in str(exc) and "135790" not in str(exc)
                    if mode == "headless":
                        assert "--headless" in str(exc)
                else:
                    raise AssertionError("登录失败不能继续业务")
            assert state_path.read_bytes() == original
            assert int(await page.evaluate("localStorage.getItem('fixture-sms-count') || '0'")) == sent
            await page.context.close()

        # fill 的底层异常可能携带输入值，只能向外抛安全错误。
        page = await new_page()
        with patch("playwright.async_api.Locator.fill", side_effect=RuntimeError("虚构秘密-calllog")):
            # 模拟底层异常携带秘密，确认最外层 LoginError 隐藏原始调用日志。
            try:
                await auth.ensure_login(page, state_path, "learner@example.invalid", url=LOCAL_URL)
            except auth.LoginError as exc:
                assert "虚构秘密" not in str(exc) and exc.__suppress_context__
            else:
                raise AssertionError("原始填表异常不能继续业务")
        assert state_path.read_bytes() == original

        # 损坏文件不删除、不覆盖；原子保存失败也必须保留旧文件。
        state_path.write_text("invalid fixture state", encoding="utf-8")
        page = await new_page()
        await auth.restore_auth(page.context, state_path)
        assert state_path.read_text(encoding="utf-8") == "invalid fixture state"
        with patch.object(auth.os, "replace", side_effect=OSError("虚构磁盘错误")):
            # 故障发生在临时文件已写完、正式替换之前，验证旧文件仍在且临时文件被清理。
            try:
                await auth.save_auth(page.context, state_path)
            except OSError:
                pass
            else:
                raise AssertionError("模拟磁盘错误应保留失败")
        assert list(directory.iterdir()) == [state_path]
        assert state_path.read_text(encoding="utf-8") == "invalid fixture state"
    finally:
        await browser.close()


async def check_auth_entries() -> None:
    # 完整 Agent 入口从首次登录开始；模型只在原页卸载认证输入框后启动。
    model = scripted_model()
    with patch.object(auth, "terminal_input", AsyncMock(return_value="yes")):
        success = await run_offline(demo, llm=model, html=AUTH_FIXTURE, manual_code="246810")
    assert model.calls == 9
    for path in success.rglob("*"):
        # 检查 Agent 文本产物，而非只检查业务摘要，避免登录输入残留在历史/对话中。
        if path.is_file() and path.suffix in {".json", ".txt"}:
            text = path.read_text(encoding="utf-8")
            assert "learner@example.invalid" not in text and "246810" not in text

    # 在 browser-use 管理的 CDP 上下文也实际恢复一次，验证两个入口共享状态。
    with patch.object(auth, "terminal_input", side_effect=AssertionError("复用状态不应再次请求验证码")):
        await run_offline(script, html=AUTH_FIXTURE)
    state_path = runtime.PROJECT_DIR / "fixture_auth.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    for origin in state["origins"]:
        for item in origin["localStorage"]:
            if item["name"] == "fixture-token":
                item["value"] = "fixture-expired"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    # 再把临时状态改成过期，下一轮必须停在人工登录，不能沿用上轮成功状态。

    # 错误验证码不能走到 build_llm（main 中将其替换为断言失败）。
    root = runtime.PROJECT_DIR / ".artifacts" / "erp_order_agent"
    previous = set(root.iterdir())
    with patch.object(auth, "terminal_input", side_effect=AssertionError("未登录不能询问保存")), \
         patch.object(auth, "MANUAL_LOGIN_TIMEOUT_MS", 1500):
        try:
            await run_offline(demo, html=AUTH_FIXTURE, manual_code="135790")
        except auth.LoginError:
            pass
        else:
            raise AssertionError("未登录不能创建模型")
    failed, = set(root.iterdir()) - previous
    # 必须新增一份明确 failed 的目录，且没有模型轨迹和成功结果，不能拿旧成功文件顶替。
    assert not (failed / "history.json").exists() and not (failed / "result.json").exists()
    metrics = json.loads((failed / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["status"] == "failed" and metrics["model_calls"] == 0
    assert metrics["action_attempts"] == 0
    status = (failed / "status.json").read_text(encoding="utf-8")
    assert "learner@example.invalid" not in status and "135790" not in status


async def main() -> None:
    # 按层级顺序执行，前面的解析/认证失败会直接中止，避免后续错误掩盖真正原因。
    class FailingModel:
        async def ainvoke(self, messages, output_format=None, **kwargs):
            # 不连接服务，用异常确认失败调用也计入指标。
            raise ValueError("虚构模型错误")

    counted = CountedModel(FailingModel())
    await must_reject_async(counted.ainvoke([]))
    assert counted.calls == 1
    assert money("1,000.10") + money("100.10") == Decimal("1100.20")
    for invalid in ("--", "", "NaN", "Infinity", "1,00.00", "1.234"):
        must_reject(lambda: money(invalid))
    # 登录已在网页完成，终端只收集保存确认；EOF 仍需明确报错。
    with patch("builtins.input", side_effect=EOFError):
        try:
            await auth.terminal_input("是否保存虚构状态：")
        except auth.LoginError:
            pass
        else:
            raise AssertionError("保存确认缺少交互终端应停止")
    async with async_playwright() as playwright:
        with TemporaryDirectory() as directory:
            await check_auth(playwright, Path(directory))
        print("PASS：等待网页人工登录、零自动短信、错误验证码修正/超时、会话复用/过期与旧状态保护")
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            await context.route("**/*", fixture_router())
            await check_reader(await context.new_page())
            await check_detail_recovery(context)
            # 详情金额与列表不符时，不产生已核对证据。
            bad_page = await context.new_page()
            bad_html = FIXTURE.replace("'订单总金额(元)：' + item.total", "'订单总金额(元)：9.99'")
            await bad_page.route("**/*", fixture_router(bad_html))
            reader = OrderReader(bad_page, "DD-DEMO", 2, LOCAL_URL)
            await reader.query()
            await must_reject_async(reader.verify("DD-DEMO-002"))
            assert reader.report.detail_checks == []
        finally:
            await browser.close()
    print("PASS：细粒度动作、详情失败恢复/有限重试/诊断、错误详情拒绝、固定列和金额校验")
    with TemporaryDirectory() as directory, \
         patch.object(runtime, "PROJECT_DIR", Path(directory)), \
         patch.object(demo, "build_llm", side_effect=AssertionError("离线检查禁止创建真实模型")):
        # 产物全部进临时目录；若漏注入模型，这个断言立刻失败，不能访问真实模型服务。
        await check_entries()
        await check_auth_entries()
    print("PASS：完整固定脚本/Agent 入口、动作与指标、结果对比、空结果及失败留证")


if __name__ == "__main__":
    # 导入辅助断言/fixture 时不自动启动 Chromium；只有直接运行测试文件才执行 main。
    asyncio.run(main())
