import fs from "node:fs/promises";
import path from "node:path";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/ai_approval_assistant/.codex-ppt-rebuild-demo";
const outputPath = "D:/PythonProject/LearnOne/AI效能分享-审批与日报四种AI实现-现场演示版.pptx";
const renderDir = path.join(workspace, "template-rendered");
const layoutDir = path.join(workspace, "template-layouts");

const C = {
  bg: "#0B1020",
  bg2: "#10182B",
  panel: "#14213A",
  panel2: "#192944",
  text: "#F5F7FB",
  muted: "#A8B6CE",
  dim: "#6F819E",
  cyan: "#56D6FF",
  teal: "#43D5B3",
  amber: "#FFC857",
  red: "#FF6B6B",
  purple: "#A98BFF",
  white: "#FFFFFF",
};

const sources = {
  fixed: "D:/PythonProject/LearnOne/ai_approval_assistant/app/graph/daily_report_workflow.py",
  autonomous: "D:/PythonProject/LearnOne/ai_approval_assistant/app/agents/daily_report_create_agent.py",
  agenticGraph: "D:/PythonProject/LearnOne/ai_approval_assistant/app/graph/daily_report_agentic_workflow_demo.py",
  agenticNodes: "D:/PythonProject/LearnOne/ai_approval_assistant/app/agents/daily_report_agentic_workflow_demo.py",
  dailyTools: "D:/PythonProject/LearnOne/ai_approval_assistant/app/tools/daily_report_tools.py",
  deepAgent: "D:/PythonProject/LearnOne/ai_deep_agents_assistant/app/agents/approval_agent.py",
  deepTools: "D:/PythonProject/LearnOne/ai_deep_agents_assistant/app/tools/approval_tools.py",
  deepChat: "D:/PythonProject/LearnOne/ai_deep_agents_assistant/app/services/chat_service.py",
  deepService: "D:/PythonProject/LearnOne/ai_deep_agents_assistant/app/services/approval_service.py",
  deepReadme: "D:/PythonProject/LearnOne/ai_deep_agents_assistant/README.md",
};

await fs.rm(renderDir, { recursive: true, force: true });
await fs.rm(layoutDir, { recursive: true, force: true });
await fs.mkdir(renderDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function newSlide() {
  const slide = presentation.slides.add();
  const originalCompose = slide.compose.bind(slide);
  slide.compose = (node, options) => typeof node === "function" ? node(slide) : originalCompose(node, options);
  return slide;
}

function t(value, x, y, w, h, fontSize = 20, color = C.text, extra = {}) {
  return (slide) => {
    const textbox = slide.shapes.add({
      geometry: "textbox",
      position: { left: x, top: y, width: w, height: h },
      fill: "none",
      line: { style: "solid", fill: "none", width: 0 },
    });
    textbox.text = value;
    textbox.text.style = {
      fontSize,
      typeface: "Aptos",
      color,
      alignment: extra.alignment || "left",
      bold: extra.bold || false,
    };
    textbox.text.verticalAlignment = extra.verticalAlignment || "top";
    textbox.text.insets = { top: 0, right: 0, bottom: 0, left: 0 };
    return textbox;
  };
}

function rect(x, y, w, h, fill, geometry = "rect") {
  return (slide) => slide.shapes.add({
    geometry,
    fill,
    line: { style: "solid", fill, width: 0 },
    position: { left: x, top: y, width: w, height: h },
  });
}

function line(x, y, w, color = C.dim, h = 2) {
  return rect(x, y, w, h, color);
}

function notes(slide, timing, talk, refs) {
  slide.speakerNotes.textFrame.setText([
    `建议时长：${timing}`,
    talk,
    "",
    "[Sources]",
    ...refs.map((r) => `- ${r}`),
    "[/Sources]",
  ].join("\n"));
  slide.speakerNotes.setVisible(true);
}

function base(slide, page, section, accent = C.cyan) {
  slide.compose(rect(0, 0, 1280, 720, C.bg));
  slide.compose(rect(0, 0, 8, 720, accent));
  slide.compose(t("AI 效能分享 / 审批助手实践", 42, 26, 440, 24, 15, C.muted));
  slide.compose(t(section, 42, 650, 700, 24, 15, C.dim));
  slide.compose(t(String(page).padStart(2, "0"), 1176, 646, 62, 30, 17, C.muted, { alignment: "right" }));
}

function title(slide, kicker, headline, sub = "") {
  slide.compose(t(kicker.toUpperCase(), 42, 92, 1100, 24, 16, C.cyan));
  slide.compose(t(headline, 42, 125, 1160, 66, 37, C.text));
  if (sub) slide.compose(t(sub, 42, 202, 1080, 34, 19, C.muted));
}

function panel(slide, x, y, w, h, fill = C.panel) {
  slide.compose(rect(x, y, w, h, fill, "roundRect"));
}

function pill(slide, label, x, y, w, color) {
  slide.compose(rect(x, y, w, 30, color, "roundRect"));
  slide.compose(t(label, x + 12, y + 6, w - 24, 18, 14, C.bg, { alignment: "center" }));
}

function addCover() {
  const slide = newSlide();
  slide.compose(rect(0, 0, 1280, 720, C.bg));
  slide.compose(rect(0, 0, 8, 720, C.cyan));
  slide.compose(rect(820, 0, 460, 720, C.bg2));
  slide.compose(rect(860, 96, 270, 8, C.cyan));
  slide.compose(t("AI 效能分享会", 42, 48, 500, 34, 20, C.muted));
  slide.compose(t("从复杂表单\n到一句话提交", 42, 172, 730, 180, 62, C.text));
  slide.compose(t("审批助手与日报的四种 AI 实现", 42, 398, 690, 40, 25, C.cyan));
  slide.compose(t("Flow  ·  Agent Flow  ·  Agentic Workflow  ·  Deep Agent", 42, 454, 780, 32, 18, C.muted));
  slide.compose(t("现场分享 / 约 20 分钟", 42, 612, 360, 26, 16, C.dim));
  slide.compose(t("01", 1090, 610, 118, 54, 40, C.cyan, { alignment: "right" }));
  return slide;
}

function addAgenda() {
  const slide = newSlide(); base(slide, 2, "分享路线", C.teal); title(slide, "TODAY", "今天不讲框架名词，讲一次完整演示", "从业务痛点出发，看四种实现如何分配执行权。 ");
  const items = [
    ["01", "应用场景", "为什么要把审批入口改成问答"],
    ["02", "实施路径", "从 Flow 到 Agent，再到混合架构"],
    ["03", "三种日报", "同一目标，连续演示三条路径"],
    ["04", "Deep Agent", "审批场景里的 Checkpoint 与人工确认"],
    ["05", "效果与问题", "当前实现了什么，下一步补什么"],
  ];
  items.forEach((it, i) => {
    const y = 280 + i * 60;
    slide.compose(t(it[0], 64, y, 50, 26, 17, C.cyan));
    slide.compose(t(it[1], 140, y, 180, 26, 21, C.text));
    slide.compose(t(it[2], 340, y, 700, 26, 20, C.muted));
    slide.compose(line(140, y + 40, 900, C.panel2, 1));
  });
  return slide;
}

function addScene() {
  const slide = newSlide(); base(slide, 3, "应用场景", C.amber); title(slide, "WHY", "用户不应该先学会表单，才能完成审批", "目标：把复杂审批提交，变成一次自然语言对话。 ");
  panel(slide, 42, 290, 470, 270, C.panel2); panel(slide, 575, 290, 663, 270, C.panel);
  pill(slide, "现在", 72, 318, 82, C.red); pill(slide, "希望", 605, 318, 82, C.teal);
  slide.compose(t("找入口 → 选模板 → 理解字段\n逐项填写 → 找审批人 → 提交", 72, 382, 390, 100, 25, C.text));
  slide.compose(t("直接说：\n“我要请假三天”\n“把今天完成的工作写进日报”", 605, 372, 560, 130, 31, C.text));
  slide.compose(t("AI 负责理解与追问；业务代码负责校验、预览和写入。", 605, 516, 550, 28, 18, C.cyan));
  return slide;
}

function addEvolution() {
  const slide = newSlide(); base(slide, 4, "实施路径", C.purple); title(slide, "EVOLUTION", "每次演进，都在重新分配“谁做决定”", "不是越智能越好，而是让决策权和业务风险匹配。 ");
  const steps = [
    ["01", "Flow", "代码决定顺序", "先把业务跑稳", C.cyan],
    ["02", "Agent Flow", "模型选择工具", "验证自主调用", C.teal],
    ["03", "Agentic Workflow", "Agent + Workflow", "让 AI 进入受控流程", C.amber],
    ["04", "Deep Agent", "目标驱动 + HITL", "探索更长任务", C.purple],
  ];
  slide.compose(line(110, 310, 1055, C.panel2, 5));
  steps.forEach((s, i) => {
    const x = 90 + i * 285;
    slide.compose(rect(x, 296, 28, 28, s[4], "ellipse"));
    slide.compose(t(s[0], x - 5, 242, 42, 24, 15, s[4], { alignment: "center" }));
    slide.compose(t(s[1], x - 8, 358, 220, 36, 26, C.text));
    slide.compose(t(s[2], x - 8, 408, 235, 30, 19, C.muted));
    slide.compose(t(s[3], x - 8, 466, 235, 50, 20, s[4]));
  });
  return slide;
}

function addArch(slide, page, section, accent, kicker, headline, sub, leftLabel, leftText, rightLabel, rightText, centerLabel, centerText) {
  base(slide, page, section, accent); title(slide, kicker, headline, sub);
  panel(slide, 42, 290, 330, 250, C.panel2); panel(slide, 475, 290, 330, 250, C.panel); panel(slide, 908, 290, 330, 250, C.panel2);
  pill(slide, leftLabel, 72, 320, 130, accent); pill(slide, centerLabel, 505, 320, 130, accent); pill(slide, rightLabel, 938, 320, 130, accent);
  slide.compose(t(leftText, 72, 382, 260, 120, 24, C.text)); slide.compose(t(centerText, 505, 382, 260, 120, 24, C.text)); slide.compose(t(rightText, 938, 382, 260, 120, 24, C.text));
  slide.compose(t("→", 392, 390, 55, 50, 40, accent, { alignment: "center" })); slide.compose(t("→", 825, 390, 55, 50, 40, accent, { alignment: "center" }));
  return slide;
}

function addDemo(page, demoNumber, accent, headline, prompt, session, labels, lines) {
  const slide = newSlide(); base(slide, page, "现场演示", accent); title(slide, `DEMO ${String(demoNumber).padStart(2, "0")}`, headline, "先展示输入，再展示过程，最后用一句话收束结论。 ");
  panel(slide, 42, 272, 1196, 110, C.panel2); pill(slide, "输入", 70, 300, 80, accent); slide.compose(t(prompt, 180, 300, 970, 32, 23, C.text)); slide.compose(t(`session_id：${session}`, 180, 344, 450, 22, 16, C.muted));
  const xs = [42, 437, 832]; labels.forEach((label, i) => { panel(slide, xs[i], 430, 340, 150, C.panel); pill(slide, label, xs[i] + 24, 452, 150, accent); slide.compose(t(lines[i], xs[i] + 24, 502, 292, 58, 20, C.text)); });
  return slide;
}

function addCompare() {
  const slide = newSlide(); base(slide, 11, "怎么选", C.cyan); title(slide, "CHOICE", "四种实现不是排行榜，而是四种执行权配置", "判断标准：业务确定性、写入风险、状态要求、成本预算。 ");
  const rows = [
    ["固定 Flow", "顺序最确定", "状态最好排查", "生产强流程", C.cyan],
    ["自主 Agent", "路径可变化", "需要从 messages 反推", "工具实验", C.teal],
    ["Agentic Workflow", "AI 理解 + 代码 Gate", "结构化状态", "受控智能业务", C.amber],
    ["Deep Agent", "目标驱动", "Checkpoint + HITL", "长任务探索", C.purple],
  ];
  rows.forEach((r, i) => { const y = 285 + i * 75; slide.compose(rect(42, y, 9, 48, r[4])); slide.compose(t(r[0], 76, y + 4, 220, 28, 22, C.text)); slide.compose(t(r[1], 310, y + 4, 250, 28, 20, C.muted)); slide.compose(t(r[2], 580, y + 4, 300, 28, 20, C.muted)); slide.compose(t(r[3], 920, y + 4, 260, 28, 20, r[4])); slide.compose(line(76, y + 51, 1104, C.panel2, 1)); });
  return slide;
}

function addResults() {
  const slide = newSlide(); base(slide, 14, "效果与问题", C.teal); title(slide, "RESULT", "当前先证明体验和安全边界，再测量效率收益", "不虚构效率数字；先把可运行、可观察、可确认做出来。 ");
  panel(slide, 42, 286, 560, 270, C.panel2); panel(slide, 660, 286, 578, 270, C.panel);
  pill(slide, "已经实现", 72, 314, 130, C.teal); pill(slide, "仍然遇到", 690, 314, 130, C.amber);
  slide.compose(t("请假审批\n日报内容、草稿、预览、确认\ntrace / state / messages 可观察\n提交前保留人工确认", 72, 374, 470, 130, 25, C.text));
  slide.compose(t("Flow：节点和条件边越来越重\nAgent：顺序、循环、成本难预测\n会话：复用 session 可能串线\nDemo / Mock 边界必须讲清楚", 690, 374, 500, 145, 23, C.text));
  return slide;
}

function addFinal() {
  const slide = newSlide(); base(slide, 15, "收束", C.cyan); title(slide, "TAKEAWAY", "AI 负责理解，代码负责边界", "让 AI 获得合适的决策权，而不是最大的决策权。 ");
  panel(slide, 42, 300, 1196, 170, C.panel2); slide.compose(t("一句话体验", 78, 338, 190, 32, 22, C.cyan)); slide.compose(t("一句自然语言 → 追问缺失信息 → 生成预览 → 人工确认 → 安全提交", 78, 390, 1060, 44, 29, C.text));
  slide.compose(t("谢谢", 42, 596, 180, 35, 24, C.muted));
  return slide;
}

let slide = addCover(); notes(slide, "40 秒", "开场先讲业务目标，不先讲框架名：平台审批入口多、字段复杂，希望用户用一句自然语言完成信息收集、预览和提交。", [sources.fixed, sources.deepAgent]);
slide = addAgenda(); notes(slide, "40 秒", "按通知要求依次覆盖场景、路径、效果、问题，并把四次演示嵌入主线。", [sources.fixed, sources.deepAgent]);
slide = addScene(); notes(slide, "1 分钟", "说明问答式助手解决的是入口和字段理解成本，AI 不直接替代业务规则。", [sources.fixed, sources.dailyTools]);
slide = addEvolution(); notes(slide, "1 分钟", "讲清楚四个阶段是执行权演进：Flow 控顺序，Agent 选工具，混合架构加 Gate，Deep Agent 探索长任务。", [sources.fixed, sources.autonomous, sources.agenticGraph, sources.deepAgent]);
slide = addArch(newSlide(), 5, "实施路径", C.cyan, "FLOW", "固定 Flow：把业务规则直接写进图里", "节点、条件边和顺序由开发者定义。", "输入", "写日报：今天完成审批助手开发", "节点", "日期 / 上下文 / 草稿 / 预览", "结果", "状态清晰，失败可定位"); notes(slide, "1 分钟", "按业务语言讲固定日报子图，强调它适合强规则生产流程。", [sources.fixed]);
slide = addDemo(6, 1, C.cyan, "现场演示 1｜固定 Flow：看路径是否稳定", "写日报：今天完成审批助手开发", "demo-flow-001", ["看 trace", "看预览", "结论"], ["daily_report_agent\n节点顺序固定", "保存草稿 → 预览\n确认后恢复", "流程稳定\n问题可定位"]); notes(slide, "1 分 40 秒", "打开 8010 Swagger，输入日报内容，用同一 session 回复确认提交，展示 trace 和预览。", [sources.fixed, sources.dailyTools]);
slide = addArch(newSlide(), 7, "实施路径", C.teal, "AGENT FLOW", "自主 Agent：模型自己决定调用什么工具", "自由来自工具选择，但提交仍有参数守卫。", "输入", "理解用户目标", "工具", "日期 / 上下文 / 草稿 / 预览", "结果", "路径灵活，成本难预测"); notes(slide, "1 分钟", "说明 create_agent / ReAct 的自主工具选择和 guarded_submit_daily_report。", [sources.autonomous, sources.dailyTools]);
slide = addDemo(8, 2, C.teal, "现场演示 2｜自主 Agent：看模型如何选工具", "自主agent写日报：今天完成审批助手开发2", "demo-agent-001", ["看 messages", "看 tool calls", "结论"], ["模型消息历史\nToolMessage", "日期 → 上下文 → 草稿\n顺序由模型决定", "更灵活\n更难排查"]); notes(slide, "1 分 40 秒", "换新 session，展示 messages 和工具调用，不只看最后一句回答。", [sources.autonomous, sources.dailyTools]);
slide = addArch(newSlide(), 9, "实施路径", C.amber, "AGENTIC WORKFLOW", "Agentic Workflow：Agent 提建议，Workflow 决定能否继续", "把智能理解和业务写入拆开。", "Agent", "理解 / 规划 / 生成", "Workflow", "日期 / 保存 / 预览", "Gate", "未确认不能提交"); notes(slide, "1 分钟", "强调 Agent 负责智能判断，Workflow 负责业务顺序和写入权限；当前规划与生成是规则模拟。", [sources.agenticGraph, sources.agenticNodes]);
slide = addDemo(10, 3, C.amber, "现场演示 3｜Agentic Workflow：看职责分工与 Gate", "agentic workflow写日报：今天完成审批助手开发3", "demo-agentic-001", ["看结构化状态", "看 Gate", "结论"], ["plan / context / compose\n分开保存", "未预览不能提交\n未确认不能提交", "智能理解\n受控写入"]); notes(slide, "1 分 40 秒", "展示 trace 和结构化状态，确认后才进入 demo_submit_gate，并说明 Demo 保存/提交边界。", [sources.agenticGraph, sources.agenticNodes]);
slide = addCompare(); notes(slide, "1 分 30 秒", "按风险和确定性选择，不做框架排行榜。", [sources.fixed, sources.autonomous, sources.agenticGraph, sources.deepAgent]);
slide = addArch(newSlide(), 12, "Deep Agent", C.purple, "DEEP AGENT", "Deep Agent：探索更长的目标任务", "这次切到审批场景，观察 Checkpoint 与 Human-in-the-loop。", "目标", "我要报销差旅费", "工具", "用户 / 模板 / 草稿 / 预览", "恢复", "interrupt → 确认 → 提交"); notes(slide, "1 分钟", "前三种是日报实验，Deep Agent 是独立审批探索，不做同场景性能对比；后端为 Mock。", [sources.deepAgent, sources.deepTools, sources.deepService]);
slide = addDemo(13, 4, C.purple, "现场演示 4｜Deep Agent：看 Checkpoint 与人工确认", "我要报销差旅费，金额 5200 元，因为去上海拜访客户，发票已提供", "demo-deep-001", ["第一轮", "中断", "确认提交"], ["自主调用用户 / 模板\n生成预览", "危险工具前\ninterrupt_on", "同一 session 恢复\n完成 Mock 提交"]); notes(slide, "2 分钟", "启动 8020，第一轮展示 awaiting_confirmation，第二轮同一 session 回复确认提交，展示恢复后的提交结果。", [sources.deepAgent, sources.deepChat, sources.deepService]);
slide = addResults(); notes(slide, "1 分钟", "诚实讲当前结果和问题，下一步测量轮次、成功率、延迟、Token 和失败重试。", [sources.fixed, sources.autonomous, sources.agenticNodes, sources.deepService]);
slide = addFinal(); notes(slide, "40 秒", "回到开场，收束为一句原则：让 AI 获得合适的决策权，而不是最大的决策权。", [sources.fixed, sources.agenticGraph, sources.deepAgent]);

const inspection = await presentation.inspect({ kind: "deck,slide,textbox,shape,notes", maxChars: 400000 });
await fs.writeFile(path.join(workspace, "template-inspect.ndjson"), inspection.ndjson || "", "utf8");
for (let i = 0; i < presentation.slides.items.length; i += 1) {
  const n = String(i + 1).padStart(2, "0");
  const png = await presentation.export({ slide: presentation.slides.items[i], format: "png", scale: 1 });
  await fs.writeFile(path.join(renderDir, `slide-${n}.png`), Buffer.from(await png.arrayBuffer()));
  const layout = await presentation.slides.items[i].export({ format: "layout" });
  await fs.writeFile(path.join(layoutDir, `slide-${n}.layout.json`), await layout.text(), "utf8");
}
const montage = await presentation.export({ format: "webp", montage: { format: "webp", slideWidth: 360, columns: 4, gap: 16, padding: 16, background: "#080D19" }, scale: 1 });
await fs.writeFile(path.join(workspace, "template-montage.webp"), Buffer.from(await montage.arrayBuffer()));
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPath);
console.log(JSON.stringify({ outputPath, slideCount: presentation.slides.items.length }, null, 2));

