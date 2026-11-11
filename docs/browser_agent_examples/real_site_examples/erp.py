"""LanERP 订单页适配：只搜索、读取和打开订单详情，不调用业务 API。"""

# 本文件是站点适配层：对页面结构、动作顺序、金额格式和详情来源作统一检查。
# run.py 与 agent.py 使用同一套小动作；区别在于下一步由 Python 还是模型选择。

import re
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote_plus, urlsplit

from playwright.async_api import Page, async_playwright, expect
from pydantic import BaseModel, ConfigDict, Field

from browser_examples.runtime import PROJECT_DIR
from reporting import RunLog

ORDER_URL = "https://dev2.lanerp.com/web/#/order"
# 真实页保留了其他页签的同名搜索框；认证与订单动作必须共用订单区域的定位规则。
# 原生 DOM 查询使用这个选择器，Playwright 操作时再加 :visible 排除隐藏副本。
ORDER_SEARCH_SELECTOR = '#pane-order input[placeholder="请输入您想搜索的内容"]'
# 以项目路径定位状态文件，避免调用者从不同工作目录启动时读到不同凭据。
AUTH_PATH = PROJECT_DIR / ".artifacts" / "erp_auth.json"
DETAIL_ATTEMPT_LIMIT = 2  # 最多首次点击 + 一次重试；不能一直点击或改选其他订单碰运气。


class DetailOpenError(RuntimeError):
    """携带安全的恢复提示；底层点击调用日志不直接交给模型或写入业务日志。"""

# vxe-table 把固定列拆成不同表格；用 rowid/colid 合并，不能按 tr 数量计订单数。
# 此脚本只读取已渲染的 DOM，不读取 Vue 内部状态、cookies 或网络响应正文。
# JavaScript 先建立 colid → 表头映射，再建立 rowid → 单元格集合，最后输出纯数据。
# 同一 colid 的固定列副本只保留一个值；不同 colid 的同名金额列交给 parse_table 校验。
# 空单元格不写入结果，必填列缺失时由 Python 明确报错，不能默认补零。
READ_TABLE = """pane => {
    const headers = new Map();
    for (const th of pane.querySelectorAll('.vxe-table--header-wrapper th[colid]')) {
        const title = th.innerText.replace(/\\s+/g, '').trim();
        if (title) headers.set(th.getAttribute('colid'), title);
    }
    const rows = new Map();
    for (const tr of pane.querySelectorAll('.vxe-table--body-wrapper tr[rowid]')) {
        const id = tr.getAttribute('rowid');
        if (!rows.has(id)) rows.set(id, new Map());
        for (const td of tr.querySelectorAll('td[colid]')) {
            const text = td.innerText.trim();
            if (text) rows.get(id).set(td.getAttribute('colid'), text);
        }
    }
    return {
        total: pane.querySelector('.el-pagination__total')?.innerText ?? '',
        rows: [...rows.values()].map(cells => [...cells].map(([id, text]) =>
            ({title: headers.get(id) ?? '', text})))
    };
}"""


class Order(BaseModel):
    # 金额保留十进制精度；序列化成 JSON 时表现为字符串，避免浮点误差。
    model_config = ConfigDict(extra="forbid")
    # number 是页面可见订单编号，不是内部数据库 ID；customer 取列表中的关联客户。
    number: str
    customer: str
    # 三项金额都独立读取对应列；不能自行假定“总额 - 已回款 = 待回款”。
    total_yuan: Decimal
    collected_yuan: Decimal
    outstanding_yuan: Decimal
    shipping_status: str


class DetailCheck(BaseModel):
    # 只保存本例需要的详情依据，不把联系人、商品明细等整页信息落盘。
    model_config = ConfigDict(extra="forbid")
    order_number: str
    # 记录实际访问后的 URL 便于追溯，不预先拼接内部订单 ID。
    source_url: str
    total_yuan: Decimal


class OrderReport(BaseModel):
    # extra=forbid 拒绝意料外的字段；类型校验不代替后面的业务事实校验。
    model_config = ConfigDict(extra="forbid")
    keyword: str
    source_url: str
    matched_total: int = Field(ge=0)  # 页面分页组件显示的全部匹配数量。
    rendered_count: int = Field(ge=0)  # 当前页真正渲染、成功解析的行数，未按 limit 截断。
    scope: str = "只统计搜索结果当前页的前 N 条，不代表所有匹配订单"
    orders: list[Order]
    # 仅累加 orders（当前页前 N 条），不把 matched_total 当成已采集数量。
    outstanding_yuan: Decimal
    detail_checks: list[DetailCheck] = Field(default_factory=list)  # 每份报告使用独立列表。


def money(text: str) -> Decimal:
    """严格解析页面金额，空白、--、NaN 不能偷偷当成零。"""
    text = text.strip()
    # 支持负数、规范千位分隔和最多两位小数；拒绝空值、科学计数法与不规范分组。
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", text):
        raise ValueError(f"页面金额格式无法确认：{text!r}")
    # 必须从字符串构造 Decimal，不能先转 float；quantize 统一输出两位小数。
    return Decimal(text.replace(",", "")).quantize(Decimal("0.01"))


def parse_table(raw: dict, keyword: str, limit: int, source_url: str) -> OrderReport:
    """动态匹配表头；同名金额列必须相等，否则停止，避免静默选错字段。"""
    # raw 来自 READ_TABLE，包含分页文本 total 与按行合并的 rows，不是接口响应。
    # keyword/limit/source_url 作为本轮采集上下文写进报告，不在这里重新访问页面。
    total_match = re.fullmatch(r"共\s*([\d,]+)\s*条", raw["total"].strip())
    if total_match is None:
        raise ValueError("没有找到搜索结果总数，请检查登录、权限或页面结构。")
    orders = []
    for row in raw["rows"]:
        # 同名表头可能对应不同 colid，所以保留值列表，而不是简单覆盖前一个值。
        cells: dict[str, list[str]] = {}
        for cell in row:
            cells.setdefault(cell["title"], []).append(cell["text"])

        def value(title: str, is_money: bool = False):
            # 重名列只在全部可读值一致时合并；缺失字段也属于采集失败。
            values = cells.get(title, [])
            parsed = [money(item) if is_money else item for item in values]
            if not parsed or len(set(parsed)) != 1:
                raise ValueError(f"字段缺失或同名列不一致：{title}")
            return parsed[0]

        number_match = re.fullmatch(r"\s*(DD-[A-Za-z0-9-]+)\s*", value("订单编号"))
        # 编号格式属于当前站点适配约定；格式变化时停止，不猜测其他文字就是订单链接。
        if number_match is None:
            raise ValueError("订单编号格式变化，不能可靠定位详情。")
        orders.append(Order(
            number=number_match[1], customer=value("关联客户"),
            total_yuan=value("订单总金额(元)", True),
            collected_yuan=value("累计回款金额(元)", True),
            outstanding_yuan=value("待回款金额(元)", True),
            shipping_status=value("发货状态"),
        ))
    total = int(total_match[1].replace(",", ""))
    # 允许“总匹配数 > 本页行数”，但不接受总数为零却有行，或有匹配数却一行都未加载。
    if (total == 0) != (len(orders) == 0) or total < len(orders):
        raise ValueError("总数与已渲染行不一致，可能仍在加载，停止生成报告。")
    if len({order.number for order in orders}) != len(orders):
        raise ValueError("发现重复订单编号，不能重复计入金额。")
    selected = orders[:limit]
    # 先验证本页全部可读行再截取，避免跳过本页中异常/重复的数据而产出看似成功的报告。
    return OrderReport(
        keyword=keyword, source_url=source_url, matched_total=total,
        rendered_count=len(orders), orders=selected,
        outstanding_yuan=sum((order.outstanding_yuan for order in selected), Decimal("0.00")),
    )


class OrderReader:
    """共享小动作：脚本固定排序，Agent 自己选择；两者经过同一安全检查。"""

    def __init__(self, page: Page, keyword: str, limit: int, url: str = ORDER_URL,
                 log: RunLog | None = None):
        # page 必须是完成登录确认后的业务页；keyword 和 limit 固定本轮允许的查询范围。
        if not keyword.strip() or not 1 <= limit <= 15:
            raise ValueError("关键词不能为空，limit 必须在 1–15 之间。")
        self.page, self.keyword, self.limit, self.url = page, keyword, limit, url
        self.report: OrderReport | None = None
        # 调用者传入同一个 RunLog，才能把小动作汇总到本轮入口的 metrics/actions 中。
        self.log = log if log is not None else RunLog()
        self.stage = "new"
        # 成功主线：new → list → filled → searching → searched → read → opening_detail → detail。
        # 详情打开异常后按页面实况恢复为 read/detail，无法确认或重试耗尽时进入 blocked。
        self.selected_order: str | None = None
        self.attempted_order: str | None = None  # 第一次实际点击后锁定候选，重试也只能是同一张。
        self.detail_attempts = 0
        self.last_click_error: str | None = None
        self.last_click_diagnostics: list[dict] = []
        self.revision = 0
        # targets: target_id → (控件类型, 业务值)，业务值只可能是空串或本轮订单编号。
        # revision 每次观察递增；输入/提交/点击清空 targets，强制重新获取有效目标。
        self.targets: dict[str, tuple[str, str]] = {}

    def search_box(self):
        # 只操作订单区域内可见的精确 placeholder；不使用 first/nth 掩盖多个可见控件的歧义。
        return self.page.locator(f"{ORDER_SEARCH_SELECTOR}:visible")

    def order_link(self, number: str):
        # 点击真正绑定订单事件的 .order_num 容器；真实站子 span 滚动后可能被单元格遮挡。
        # 用整段编号匹配保留原来的精确限制，不使用 force 或脚本点击绕过遮挡检查。
        return self.page.locator("#pane-order .fixed-left--wrapper .order_num").filter(
            has_text=re.compile(rf"^\s*{re.escape(number)}\s*$")
        )

    def require_list(self) -> None:
        # 防止人工切页后，把旧观察用于其他业务页面。
        if self.page.url != self.url:
            raise ValueError("当前已不在本轮订单列表页，停止操作。")

    def target(self, target_id: str, kind: str) -> str:
        # 目标由最近一次观察产生；不接受模型传入 URL、CSS、任意 DOM 索引。
        if target_id not in self.targets or self.targets[target_id][0] != kind:
            raise ValueError("目标不存在、已过期或动作不匹配，请重新 observe_page。")
        return self.targets[target_id][1]  # 返回已登记的业务值，而不是相信模型自带的编号。

    async def open_list(self) -> None:
        # 仅允许本轮首次打开固定入口；导航权限不作为通用工具暴露给模型。
        async with self.log.action("open_list"):
            if self.stage != "new":
                raise ValueError("本轮只允许打开一次固定列表入口。")
            # ensure_login 已在原标签页打开列表时，不再 goto 相同 URL，避免整页刷新丢失 SPA 状态。
            if self.page.url != self.url:
                await self.page.goto(self.url, wait_until="domcontentloaded")
            await expect(self.search_box()).to_be_visible(timeout=30_000)
            self.stage = "list"

    async def observe(self) -> dict:
        # 返回小型控件清单，不替模型执行下一步；只观察也会作废之前发出的目标编号。
        async with self.log.action("observe_page"):
            self.revision += 1
            self.targets.clear()
            controls = []
            if self.stage in {"list", "filled", "searched", "read"}:
                self.require_list()
            if self.stage in {"list", "filled"}:
                # 搜索前仅提供搜索框；此时订单还不是本轮搜索结果，不能发放详情目标。
                search = self.search_box()
                await expect(search).to_be_visible()
                token = f"o{self.revision}:search"
                self.targets[token] = ("search", "")
                controls.append({"target_id": token, "kind": "textbox",
                                 "placeholder": await search.get_attribute("placeholder"),
                                 "value": await search.input_value(),
                                 "actions": ["input_text" if self.stage == "list" else "press_enter"]})
            elif self.stage == "read" and self.report is not None:
                # 只有采集成功后才为 report.orders 发放候选链接，不扩展到未采集的其他订单。
                for index, order in enumerate(self.report.orders, 1):
                    if self.attempted_order is not None and order.number != self.attempted_order:
                        continue  # 失败后的新观察也不能把重试扩展成打开另一张订单。
                    link = self.order_link(order.number)
                    await expect(link).to_be_visible()
                    token = f"o{self.revision}:order:{index}"
                    self.targets[token] = ("order", order.number)
                    controls.append({"target_id": token, "kind": "order_link",
                                     "text": await link.inner_text(), "actions": ["safe_click"]})
            # 仅列出已审阅的控件；browser-use 自身仍能看到整页 DOM，这不是脱敏。
            # 没有可点击控件不等于白屏：detail/blocked 阶段仍返回明确状态与下一步提示。
            return {**self.progress(), "controls": controls}

    def progress(self) -> dict:
        """各工具复用的小型反馈，不额外观察页面，也不自动替模型执行下一步。"""
        if self.stage == "list":
            action = "input_text" if self.targets else "observe_page"
        elif self.stage == "filled":
            action = "press_enter" if self.targets else "observe_page"
        elif self.stage == "searched":
            action = "read_orders"
        elif self.stage == "read":
            action = "done" if self.report is not None and not self.report.orders else (
                "safe_click" if self.targets else "observe_page")
        elif self.stage == "detail":
            action = "done" if self.report is not None and self.report.detail_checks else "read_detail"
        else:
            action = "done"  # 未知/失败阶段只能以 success=false 结束，不能当作业务已完成。
        instructions = {
            "observe_page": "观察一次取得新 target_id，随后执行推荐动作，不要连续重复观察。",
            "input_text": "使用本次返回的搜索框 target_id 填写已授权关键词，不需要再次观察。",
            "press_enter": "使用本次返回的新 target_id 按 Enter，不需要再次观察。",
            "read_orders": "本轮搜索已完成，直接读取列表，不要重新搜索。",
            "safe_click": "从本次候选选择待回款最多的一张；重试时只能点击此前选中的同一张。",
            "read_detail": "目标详情已确认打开，直接读取金额；尚未核对，不能报告成功。",
            "done": "提交摘要；有订单时必须已有详情金额核对证据，未完成则 success=false。",
        }
        return {"stage": self.stage, "next_action": action, "instruction": instructions[action],
                "detail_verified": bool(self.report and self.report.detail_checks),
                "detail_attempts": self.detail_attempts, "last_click_error": self.last_click_error,
                "click_diagnostics": self.last_click_diagnostics}

    async def detail_is_open(self, number: str) -> bool:
        # 路由和精确标题必须同时成立；错误详情、旧页隐藏标题都不能冒充本轮目标。
        prefix = self.url.split("#", 1)[0] + "#/order_detail?"
        if self.page.is_closed() or not self.page.url.startswith(prefix):
            return False
        heading = self.page.get_by_role("heading", name=number, exact=True)
        return await heading.count() == 1 and await heading.is_visible()

    async def click_diagnostics(self, number: str, phase: str) -> dict:
        # 只记录路由类别和计数，不读取输入值、token、整页 DOM 或 URL 查询参数。
        pages = self.page.context.pages
        data = {"phase": phase, "page_closed": self.page.is_closed(), "tab_count": len(pages),
                "page_index": pages.index(self.page) if self.page in pages else -1}
        if data["page_closed"]:
            return data
        same_origin = urlsplit(self.page.url)[:2] == urlsplit(self.url)[:2]
        route = urlsplit(self.page.url).fragment.split("?", 1)[0]
        data.update(same_origin=same_origin,
                    route=route if same_origin and route in {"/order", "/order_detail", "/workBench", "/login"} else "other")
        if not same_origin:
            return data  # 离开允许来源时不继续读取新站点 DOM。
        try:
            link = self.order_link(number)
            data.update(target_count=await link.count(),
                        visible_target_count=await link.filter(visible=True).count(),
                        target_detail_open=await self.detail_is_open(number))
        except Exception as error:
            # 页面可能在诊断时关闭；诊断失败不能掩盖原点击异常，也不输出原始异常文本。
            data["diagnostic_error"] = type(error).__name__
        return data

    async def input_text(self, target_id: str, text: str) -> None:
        # target_id 验证“在哪填”，text 精确匹配验证“填什么”；两项都通过才操作页面。
        async with self.log.action("input_text", target_id=target_id, text=text):
            self.target(target_id, "search")
            self.require_list()
            if self.stage not in {"list", "filled"} or text != self.keyword:
                raise ValueError("只能在搜索前填写本轮已授权关键词。")
            self.targets.clear()
            await self.search_box().fill(text)
            self.stage = "filled"

    async def press_enter(self, target_id: str) -> None:
        # 必须同时检查状态和输入框现值，防止页面被人工改动后提交了其他关键词。
        async with self.log.action("press_enter", target_id=target_id):
            self.target(target_id, "search")
            self.require_list()
            if self.stage != "filled" or await self.search_box().input_value() != self.keyword:
                raise ValueError("请先填写本轮关键词，不允许提交空搜索或其他内容。")
            self.targets.clear()
            self.stage = "searching"

            def is_search_request(request):
                # 识别 UI 产生的本轮请求，不直接请求或解析业务 API。
                # 同时兼容 URL 参数和表单请求体中的 URL 编码关键词，不读取响应业务数据。
                payload = unquote_plus(request.url + " " + (request.post_data or ""))
                return request.resource_type in {"xhr", "fetch"} and self.keyword in payload

            async with self.page.expect_request_finished(is_search_request, timeout=30_000) as pending:
                # 先注册请求监听再按 Enter，避免响应太快而错过事件。
                await self.search_box().press("Enter")
            response = await (await pending.value).response()
            # HTTP 成功只证明请求结束；后面仍需等渲染完成并解析实际 DOM。
            if response is None or not response.ok:
                raise RuntimeError("搜索请求失败，没有有效的成功响应。")
            # shortcut: 站点若加入持续轮询，需要改成明确的表格加载完成信号。
            await self.page.wait_for_load_state("networkidle", timeout=30_000)
            await expect(self.page.locator("#pane-order .el-loading-mask:visible")).to_have_count(0)
            self.stage = "searched"

    async def read_orders(self) -> OrderReport:
        # 同一轮只采集一次并缓存，重复读取返回同一份报告，防止列表/详情使用不同快照。
        async with self.log.action("read_orders"):
            self.require_list()
            if self.stage not in {"searched", "read"}:
                raise ValueError("必须先提交本轮搜索，不能把初始或旧表格当成本轮结果。")
            if self.report is None:
                raw = await self.page.locator("#pane-order").evaluate(READ_TABLE)
                self.report = parse_table(raw, self.keyword, self.limit, self.page.url)
            self.stage = "read"
            return self.report

    async def safe_click(self, target_id: str) -> None:
        # 点击只负责打开详情，不登记“已核对”；证据必须由 read_detail 实际读取后生成。
        diagnostics: list[dict] = []
        async with self.log.action("safe_click", target_id=target_id, diagnostics=diagnostics):
            number = self.target(target_id, "order")
            self.require_list()
            if self.stage != "read" or self.selected_order is not None:
                raise ValueError("必须先读列表，本例只允许打开一张候选订单。")
            if self.detail_attempts >= DETAIL_ATTEMPT_LIMIT or self.attempted_order not in {None, number}:
                raise ValueError("详情点击仅允许对同一候选尝试两次，不能更换订单或无限重试。")
            self.targets.clear()
            self.attempted_order = number
            self.detail_attempts += 1
            self.last_click_error = None
            self.last_click_diagnostics = diagnostics
            diagnostics.append(await self.click_diagnostics(number, "before"))
            self.stage = "opening_detail"
            try:
                await self.order_link(number).click(timeout=30_000)
                # 标题可能来自缓存页；同时等待本站详情路由，不能只看一个同名标题。
                prefix = self.url.split("#", 1)[0] + "#/order_detail?"
                await expect(self.page).to_have_url(re.compile("^" + re.escape(prefix)), timeout=10_000)
                await expect(self.page.get_by_role("heading", name=number, exact=True)).to_be_visible(timeout=10_000)
                if not await self.detail_is_open(number):
                    raise RuntimeError("目标详情尚未确认")
            except Exception as error:
                after = await self.click_diagnostics(number, "after_error")
                after["error_type"] = type(error).__name__
                diagnostics.append(after)
                if after.get("target_detail_open"):
                    # 某些点击会在导航已成功后才报告异常；确认目标后禁止再次点击，转去读金额。
                    self.selected_order, self.stage = number, "detail"
                    self.last_click_error = "点击报告异常，但已确认目标详情打开；请 read_detail，尚未核对金额。"
                    return
                if not self.page.is_closed() and self.page.url == self.url and self.detail_attempts < DETAIL_ATTEMPT_LIMIT:
                    self.stage = "read"
                    self.last_click_error = "详情点击失败，当前仍在订单列表；请重新观察后对同一订单重试一次。"
                else:
                    self.stage = "blocked"
                    self.last_click_error = "详情点击失败，页面位置无法确认、已关闭或重试次数已用完；停止点击，不能报告成功。"
                raise DetailOpenError(self.last_click_error) from None
            diagnostics.append(await self.click_diagnostics(number, "after"))
            self.selected_order, self.stage = number, "detail"

    async def read_detail(self) -> DetailCheck:
        # 先确认所选编号、详情标题和来源路由，再独立读取金额并与列表快照交叉校验。
        async with self.log.action("read_detail"):
            if self.stage != "detail" or self.report is None or self.selected_order is None:
                raise ValueError("请先点击本轮候选订单，不能直接声称读过详情。")
            await expect(self.page.get_by_role("heading", name=self.selected_order, exact=True)).to_be_visible()
            prefix = self.url.split("#", 1)[0] + "#/order_detail?"
            if not self.page.url.startswith(prefix):
                raise ValueError("详情来源不是本轮站点的订单详情。")
            if self.report.detail_checks:
                # 本轮最多核对一张；重复读取复用已核验结果，不重复添加证据记录。
                return self.report.detail_checks[0]
            amount_line = self.page.locator("#pane-detail").get_by_text(
                # 锚定整行字段名与金额，避免误把其他金额、商品价格或含糊文本作为总金额。
                re.compile(r"^订单总金额\(元\)[：:]\s*[\d,.]+$")
            )
            await expect(amount_line).to_have_count(1, timeout=30_000)
            # 唯一且可见才读取，兼容详情页异步加载；不以固定 sleep 猜测何时加载完成。
            await expect(amount_line).to_be_visible()
            amount = money(re.split(r"[：:]", await amount_line.inner_text(), maxsplit=1)[1])
            known = next(item for item in self.report.orders if item.number == self.selected_order)
            if amount != known.total_yuan:
                raise ValueError("列表与详情总金额不一致，可能在运行期间被修改。")
            check = DetailCheck(order_number=known.number, source_url=self.page.url, total_yuan=amount)
            self.report.detail_checks.append(check)
            return check

    async def query(self) -> OrderReport:
        # 只供固定脚本调用；Agent 不暴露这个一次包办查询的方法。
        await self.open_list()
        observation = await self.observe()
        await self.input_text(observation["controls"][0]["target_id"], self.keyword)
        # 填写使旧目标失效，所以即使固定脚本也必须重新观察后才能提交。
        observation = await self.observe()
        await self.press_enter(observation["controls"][0]["target_id"])
        return await self.read_orders()

    async def verify(self, order_number: str) -> DetailCheck:
        # 固定脚本也从真实观察选择目标，并经过与 Agent 完全相同的点击限制。
        observation = await self.observe()
        target = next((item for item in observation["controls"] if item.get("text") == order_number), None)
        if target is None:
            raise ValueError("只能核对本轮候选订单。")
        await self.safe_click(target["target_id"])
        return await self.read_detail()


@asynccontextmanager
async def order_browser(headless: bool, auth_path: Path):
    """真实站单独创建会话，不扩大原 01–05 示例的本地导航权限。"""
    from browser_use import BrowserProfile, BrowserSession

    # 延迟导入避免 auth 使用本站常量时形成循环导入。
    from auth import restore_auth

    # asynccontextmanager 的 yield 把 session/page 借给入口；退出 async with 时统一清理。
    async with async_playwright() as playwright:
        session = BrowserSession(browser_profile=BrowserProfile(
            executable_path=playwright.chromium.executable_path,
            headless=headless, allowed_domains=["dev2.lanerp.com"],
            # 登录态交给 Playwright 一次性恢复，不交给依赖的周期同步器。
            use_cloud=False, captcha_solver=False,
            # 禁止自动解安全挑战；不装扩展；keep_alive 使关闭时机由 finally 明确控制。
            enable_default_extensions=False, keep_alive=True,
        ))
        run_error = None
        try:
            await session.start()
            # Playwright 和 browser-use 连接同一个本机 Chromium，避免两份登录会话。
            browser = await playwright.chromium.connect_over_cdp(session.cdp_url)
            # CDP 是连接同一浏览器的控制通道，不是另启一份 Playwright 登录会话。
            context = browser.contexts[0]
            await restore_auth(context, auth_path)
            # 只恢复状态，不据此认定已登录；是否能访问订单页由 ensure_login 继续验证。
            page = context.pages[0] if context.pages else await context.new_page()
            yield session, page
        except BaseException as exc:
            # 关闭浏览器出错时仍保留原始查询/验收异常。
            run_error = exc
            raise
        finally:
            try:
                await session.kill()
            except Exception as cleanup_error:
                if run_error is None:
                    raise
                run_error.add_note(f"关闭浏览器失败：{cleanup_error}")
