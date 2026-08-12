import fs from "node:fs/promises";
import path from "node:path";
import {
  Presentation,
  PresentationFile,
  layers,
  shape,
  table,
  text,
} from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/ai_approval_assistant/.codex-ppt-rebuild-demo";
const outputPath = "D:/PythonProject/LearnOne/AI效能分享-审批与日报四种AI实现-现场演示版.pptx";
const renderDir = path.join(workspace, "rendered");
const layoutDir = path.join(workspace, "layouts");
const templateSource = "C:/Users/EDY/.codex/plugins/cache/openai-primary-runtime/presentations/26.805.11740/skills/presentations/assets/builtin_templates/codex-grid-layout-library/artifact-tool-compose";
const templateDir = path.join(workspace, "codex-grid-layouts");

await fs.mkdir(templateDir, { recursive: true });
for (const filename of [
  "runtime.mjs",
  "content-tokens.json",
  "slide-01.mjs",
  "slide-03.mjs",
  "slide-05.mjs",
  "slide-06.mjs",
  "slide-09.mjs",
  "slide-10.mjs",
  "slide-11.mjs",
  "slide-13.mjs",
  "slide-15.mjs",
  "slide-18.mjs",
  "slide-26.mjs",
]) {
  await fs.copyFile(path.join(templateSource, filename), path.join(templateDir, filename));
}

const [
  { buildSlide01 },
  { buildSlide03 },
  { buildSlide05 },
  { buildSlide06 },
  { buildSlide09 },
  { buildSlide10 },
  { buildSlide11 },
  { buildSlide13 },
  { buildSlide15 },
  { buildSlide18 },
  { buildSlide26 },
] = await Promise.all([
  import(new URL("./codex-grid-layouts/slide-01.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-03.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-05.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-06.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-09.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-10.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-11.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-13.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-15.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-18.mjs", import.meta.url)),
  import(new URL("./codex-grid-layouts/slide-26.mjs", import.meta.url)),
]);

await fs.rm(renderDir, { recursive: true, force: true });
await fs.rm(layoutDir, { recursive: true, force: true });
await fs.mkdir(renderDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });
presentation.theme.colorScheme = {
  name: "AI Efficiency",
  themeColors: {
    accent1: "#3D8DFF",
    accent2: "#0F766E",
    accent3: "#F59E0B",
    accent4: "#DC2626",
    accent5: "#7C3AED",
    accent6: "#16A34A",
    bg1: "#FFFFFF",
    bg2: "#F7F7F7",
    tx1: "#111111",
    tx2: "#5F6368",
    dk1: "#000000",
    dk2: "#1F2937",
    lt1: "#FFFFFF",
    lt2: "#EDEDED",
    hlink: "#3D8DFF",
    folHlink: "#7C3AED",
  },
};

const sources = {
  workflow: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\graph\\workflow.py",
  fixed: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\graph\\daily_report_workflow.py",
  autonomous: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\agents\\daily_report_create_agent.py",
  agenticGraph: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\graph\\daily_report_agentic_workflow_demo.py",
  agenticNodes: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\agents\\daily_report_agentic_workflow_demo.py",
  dailyTools: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\app\\tools\\daily_report_tools.py",
  demo: "D:\\PythonProject\\LearnOne\\ai_approval_assistant\\演示.md",
  deepAgent: "D:\\PythonProject\\LearnOne\\ai_deep_agents_assistant\\app\\agents\\approval_agent.py",
  deepTools: "D:\\PythonProject\\LearnOne\\ai_deep_agents_assistant\\app\\tools\\approval_tools.py",
  deepChat: "D:\\PythonProject\\LearnOne\\ai_deep_agents_assistant\\app\\services\\chat_service.py",
  deepService: "D:\\PythonProject\\LearnOne\\ai_deep_agents_assistant\\app\\services\\approval_service.py",
  deepReadme: "D:\\PythonProject\\LearnOne\\ai_deep_agents_assistant\\README.md",
};

function addNotes(slide, timing, talkTrack, sourcePaths) {
  slide.speakerNotes.textFrame.setText([
    `建议时长：${timing}`,
    talkTrack,
    "",
    "[Sources]",
    ...sourcePaths.map((source) => `- ${source}`),
    "[/Sources]",
  ].join("\n"));
  slide.speakerNotes.setVisible(true);
}

function body(title, content) {
  return { titleHere: title, loremIpsumDolorSitAmetConsecteturAdipiscing: content };
}

function gridBody(title, content) {
  return { titleGoesHere: title, loremIpsumDolorSitAmetConsecteturAdipiscing: content };
}

function comparisonBody(topic, intro, detail) {
  return {
    topic,
    loremIpsumDolorSitAmetConsecteturAdipiscing: intro,
    loremIpsumDolorSitAmetConsecteturAdipiscing2: detail,
  };
}

function addComparisonTableSlide() {
  const slide = presentation.slides.add();
  slide.compose(
    layers({ name: "codex-grid-adapted-comparison", width: "fill", height: "fill" }, [
      text(["三种日报实现：同一目标，不同执行权"], {
        name: "comparison-title",
        position: { left: 41.33, top: 36.12 },
        width: 1197.33,
        height: 109.97,
        style: {
          fontSize: "38.67px",
          typeface: "Helvetica Neue",
          color: "#000000",
          alignment: "left",
          verticalAlignment: "top",
          autoFit: "shrinkText",
          insets: { top: 0, right: 0, bottom: 0, left: 0 },
        },
      }),
      text(["公平比较范围：daily_report_agent、daily_report_create_agent、daily_report_agentic_workflow_demo"], {
        name: "comparison-subtitle",
        position: { left: 42.09, top: 112 },
        width: 1197.33,
        height: 82,
        style: {
          fontSize: "21.33px",
          typeface: "Helvetica Neue",
          color: "#5F6368",
          alignment: "left",
          autoFit: "shrinkText",
          insets: { top: 0, right: 0, bottom: 0, left: 0 },
        },
      }),
      table({
        name: "daily-report-comparison-table",
        rows: 5,
        columns: 5,
        values: [
          ["实现", "顺序控制", "状态 / 排查", "成本可控性", "当前定位"],
          ["固定 Flow", "Workflow", "节点状态最清晰", "高", "稳定主流程"],
          ["自主 Agent", "Agent", "从消息与 tool calls 反推", "低", "自主工具实验"],
          ["Agentic Workflow", "Agent 建议 + Workflow 决定", "计划 / 上下文 / 生成 / Gate", "中高", "受控智能流程"],
          ["选择原则", "写入风险越高，代码控制越多", "先保证能定位问题", "限制模型循环", "不是越智能越好"],
        ],
        columnWidths: [180, 245, 300, 170, 302],
        position: { left: 41.33, top: 224 },
        width: 1197.33,
        height: 414,
      }),
      text(["12"], {
        name: "comparison-footer",
        position: { left: 1184.18, top: 659.24 },
        width: 54.48,
        height: 25.33,
        style: {
          fontSize: "13.33px",
          typeface: "Helvetica Neue",
          color: "#000000",
          alignment: "right",
          verticalAlignment: "bottom",
          insets: { top: 0, right: 0, bottom: 0, left: 0 },
        },
      }),
    ]),
    { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 },
  );
  return slide;
}

function basicText(value, position, style = {}) {
  return text([value], {
    position,
    style: {
      fontSize: "22px",
      typeface: "Aptos",
      color: "#111111",
      alignment: "left",
      verticalAlignment: "top",
      autoFit: "shrinkText",
      insets: { top: 0, right: 0, bottom: 0, left: 0 },
      ...style,
    },
  });
}

function addInputComparisonSlide() {
  const slide = presentation.slides.add();
  slide.compose(layers({ name: "input-comparison", width: "fill", height: "fill" }, [
    basicText("公平对比：同一个日报目标，只改变执行方式", { left: 42, top: 34, width: 1196, height: 55 }, { fontSize: "38px" }),
    basicText("现场只做一件事：输入一句话，然后观察谁决定下一步。", { left: 42, top: 104, width: 1196, height: 35 }, { fontSize: "22px", color: "#5F6368" }),
    ...[
      { x: 42, title: "固定 Flow", prompt: "写日报：\n今天完成审批助手开发", session: "demo-flow-001", color: "#DCEBFF" },
      { x: 444, title: "自主 Agent", prompt: "自主agent写日报：\n今天完成审批助手开发2", session: "demo-agent-001", color: "#DDF5EF" },
      { x: 846, title: "Agentic Workflow", prompt: "agentic workflow写日报：\n今天完成审批助手开发3", session: "demo-agentic-001", color: "#FFF1D6" },
    ].flatMap((item) => [
      shape({ geometry: "roundRect", fill: item.color, position: { left: item.x, top: 180, width: 360, height: 430 } }),
      basicText(item.title, { left: item.x + 24, top: 204, width: 312, height: 40 }, { fontSize: "28px" }),
      basicText("提问", { left: item.x + 24, top: 272, width: 312, height: 30 }, { fontSize: "20px", color: "#5F6368" }),
      basicText(item.prompt, { left: item.x + 24, top: 310, width: 312, height: 122 }, { fontSize: "23px" }),
      basicText("独立 session", { left: item.x + 24, top: 478, width: 312, height: 30 }, { fontSize: "20px", color: "#5F6368" }),
      basicText(item.session, { left: item.x + 24, top: 516, width: 312, height: 36 }, { fontSize: "21px" }),
    ]),
    basicText("下一页开始演示：先看输入，再看 trace / messages / Gate。", { left: 42, top: 650, width: 800, height: 25 }, { fontSize: "17px", color: "#5F6368" }),
    basicText("5", { left: 1184, top: 659, width: 54, height: 25 }, { fontSize: "13px", alignment: "right" }),
  ]), { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 });
  return slide;
}

function addDemoSlide({ page, title, prompt, session, leftTitle, leftLines, rightTitle, rightLines }) {
  const slide = presentation.slides.add();
  slide.compose(layers({ name: `demo-slide-${page}`, width: "fill", height: "fill" }, [
    basicText(title, { left: 42, top: 34, width: 1196, height: 55 }, { fontSize: "38px" }),
    basicText("输入", { left: 42, top: 112, width: 100, height: 28 }, { fontSize: "20px", color: "#5F6368" }),
    basicText(prompt, { left: 42, top: 145, width: 730, height: 42 }, { fontSize: "26px" }),
    basicText(`Swagger：${page === 14 ? "8020" : "8010"} / POST /api/ai-approval/chat`, { left: 42, top: 194, width: 740, height: 28 }, { fontSize: "18px", color: "#5F6368" }),
    basicText(`session_id：${session}`, { left: 42, top: 226, width: 740, height: 28 }, { fontSize: "18px", color: "#5F6368" }),
    shape({ geometry: "roundRect", fill: "#EAF2FF", position: { left: 42, top: 306, width: 560, height: 84 } }),
    basicText(leftTitle, { left: 70, top: 328, width: 500, height: 38 }, { fontSize: "28px" }),
    basicText(leftLines.join("\n"), { left: 70, top: 420, width: 540, height: 150 }, { fontSize: "21px" }),
    shape({ geometry: "roundRect", fill: "#EAF7F3", position: { left: 660, top: 306, width: 578, height: 84 } }),
    basicText(rightTitle, { left: 688, top: 328, width: 520, height: 38 }, { fontSize: "28px" }),
    basicText(rightLines.join("\n"), { left: 688, top: 420, width: 540, height: 150 }, { fontSize: "21px" }),
    basicText(String(page), { left: 1184, top: 659, width: 54, height: 25 }, { fontSize: "13px", alignment: "right" }),
  ]), { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 });
  return slide;
}

function addConclusionSlide() {
  const slide = presentation.slides.add();
  slide.compose(layers({ name: "conclusion", width: "fill", height: "fill" }, [
    basicText("结论", { left: 42, top: 42, width: 300, height: 40 }, { fontSize: "30px" }),
    basicText("AI 负责理解，代码负责边界", { left: 42, top: 220, width: 1100, height: 90 }, { fontSize: "56px" }),
    basicText("固定 Flow：先把业务跑稳\nAgentic Workflow：让 AI 安全进入流程\nDeep Agent：探索更复杂、更长的目标任务", { left: 42, top: 400, width: 860, height: 150 }, { fontSize: "25px" }),
    basicText("18", { left: 1184, top: 659, width: 54, height: 25 }, { fontSize: "13px", alignment: "right" }),
  ]), { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 });
  return slide;
}

let slide = buildSlide01(presentation, {
  title: "AI 应用分享会",
  title2: "从复杂表单到一句话提交",
  title3: "审批助手与日报：固定 Flow、自主 Agent、Agentic Workflow、Deep Agent 的实践与演示",
});
addNotes(slide, "40 秒", "开场不要先讲框架名。先说业务目标：平台审批和日报入口多、字段复杂，我希望用户用一句自然语言完成信息收集、预览和提交。今天用真实代码展示四种实现的执行权差异。", [sources.workflow, sources.deepAgent]);

slide = buildSlide03(presentation, {
  title: "20 分钟分享路线",
  footer1: "2",
});
const agendaTable = slide.tables.items[0];
const agenda = [
  ["01", "应用场景：为什么要做问答式审批助手"],
  ["02", "实施路径：从 Flow 到 Agent，再到混合架构"],
  ["03", "同一日报目标：三种实现逐一演示"],
  ["04", "Deep Agent：审批场景的独立探索"],
  ["05", "预期效果：当前已经实现什么"],
  ["06", "遇到的问题：哪些边界还不能交给 AI"],
];
for (let row = 0; row < agenda.length; row += 1) {
  agendaTable.cells.set(row, 0, agenda[row][0]);
  agendaTable.cells.set(row, 1, agenda[row][1]);
}
addNotes(slide, "40 秒", "这六项正好覆盖通知要求的应用场景、实施路径、预期效果、遇到的问题，同时把现场演示放在主线中间，不是最后临时补一个 Demo。", [sources.demo]);

slide = buildSlide05(presentation, {
  title: "应用场景：用户不应该先学会表单，才能完成审批",
  body1: body("现在的操作", "找到入口\n选择模板\n理解字段\n逐项填写\n确认审批人\n提交"),
  body2: body("希望的体验", "直接说：\n“我要请假三天”\n“把今天完成的工作写进日报”\n\n系统负责追问缺失信息、生成预览，用户只负责最终确认。"),
  footer1: "3",
});
addNotes(slide, "1 分钟", "强调这不是为了炫技，而是减少用户记忆入口和理解复杂表单的成本。AI 的价值是理解自然语言，业务系统仍然要负责字段、校验和提交边界。", [sources.workflow, sources.fixed]);

slide = buildSlide15(presentation, {
  title: "实施路径：每次演进都在重新分配“谁做决定”",
  body1: {
    titleHere: "演进不是不断换框架",
    loremIpsumDolorSitAmetConsecteturAdipiscing: "同一个目标反复实现，才能看清哪些逻辑应该交给模型，哪些规则必须留在代码里。",
    quamUtMassaLuctusCursusNullamPharetra: "核心变量：执行顺序、工具权限、状态可观测性、人工确认。",
  },
  label1: "固定 Flow",
  body2: "节点、条件边和顺序由开发者定义。",
  label2: "自主 Agent",
  body3: "模型自己选择工具和下一步。",
  label3: "Agentic Workflow",
  body4: "Agent 负责理解生成，Workflow 负责业务 Gate。",
  label4: "Deep Agent",
  body5: "目标驱动、Checkpoint、HITL，探索复杂任务。",
  footer1: "4",
});
addNotes(slide, "1 分钟", "四个阶段不是简单的强弱排名。固定 Flow 解决能不能稳定跑，自主 Agent 验证能不能自己做，Agentic Workflow 解决怎么安全进入业务，Deep Agent 探索更长任务和线程恢复。", [sources.fixed, sources.autonomous, sources.agenticGraph, sources.deepAgent]);

slide = addInputComparisonSlide();
addNotes(slide, "50 秒", "三个实验必须使用不同 session_id；同一种流程的‘确认提交’必须继续使用原 session_id。否则活跃会话状态会让路由继续进入上一种 Agent，现场就会出现走错节点或还在等待上一步输入。", [sources.workflow, sources.demo]);

slide = buildSlide10(presentation, {
  title: "固定 Flow：把业务规则直接写进图里",
  body1: "开发者控制\n执行顺序",
  body2: {
    loremIpsumDolorSitAmetConsecteturAdipiscing: "daily_report_agent 内部是一个独立日报子图：日期、上下文、内容、草稿、预览、提交和取消都有明确节点。",
    loremIpsumDolorSitAmetConsecteturAdipiscing2: "它的优势不是‘更智能’，而是路径确定、状态清晰、异常可定位。",
  },
  label1: "固定节点与条件边",
  label2: "保存草稿后才能预览",
  label3: "明确确认后才能提交",
  label4: "支持修改日期 / 内容 / 取消",
  label5: "适合强规则生产流程",
  footer1: "6",
});
addNotes(slide, "1 分钟", "按业务语言讲节点：系统先识别动作，再加载日报上下文，缺内容就追问，有内容就保存草稿、生成预览，最后等待确认。不要逐个念代码节点名。", [sources.fixed]);

slide = addDemoSlide({ page: 7, title: "现场演示 1｜固定 Flow：看路径是否稳定", prompt: "写日报：今天完成审批助手开发", session: "demo-flow-001", leftTitle: "看 trace", leftLines: ["路由进入 daily_report_agent", "节点顺序可直接定位", "失败时知道卡在哪一步"], rightTitle: "看预览与确认", rightLines: ["先保存草稿，再生成预览", "回复“确认提交”才继续", "同一 session 完成恢复"] });
addNotes(slide, "1 分 40 秒", "操作：打开 http://127.0.0.1:8010/docs，调用 POST /api/ai-approval/chat。输入页面文字，展示 daily_report_agent、status、daily_report_preview 和 trace；再用同一 session 回复‘确认提交’。失败兜底：不现场排查 ERP，只展示输入、预期 trace、预览和 Gate。", [sources.fixed, sources.dailyTools, sources.demo]);

slide = buildSlide05(presentation, {
  title: "自主 Agent：模型自己决定下一步和调用什么工具",
  body1: body("得到的自由", "create_agent / ReAct\n理解用户目标\n选择日报工具\n观察工具结果\n决定继续调用还是回答"),
  body2: body("仍保留的边界", "必须先确认日期\n必须加载上下文\n保存草稿后展示预览\n提交工具要求 confirmed=true\n外部接口失败不能假装成功"),
  footer1: "8",
});
addNotes(slide, "1 分钟", "自主 Agent 不是完全放开。代码把日报工具注册给模型，但替换了提交工具：guarded_submit_daily_report 要求 confirmed=true。这里的安全主要靠 Prompt + 工具参数守卫，不是固定执行图。", [sources.autonomous, sources.dailyTools]);

slide = addDemoSlide({ page: 9, title: "现场演示 2｜自主 Agent：看模型如何选择工具", prompt: "自主agent写日报：今天完成审批助手开发2", session: "demo-agent-001", leftTitle: "看 messages", leftLines: ["daily_report_agent_messages", "模型回答与 ToolMessage", "业务阶段需要从历史反推"], rightTitle: "看工具调用", rightLines: ["日期 → 上下文 → 草稿 → 预览", "顺序可能随模型变化", "Token 与延迟更难预测"] });
addNotes(slide, "1 分 40 秒", "操作与固定 Flow 相同，但换新 session。重点不要只看最后一句回答，要展示 daily_report_agent_messages 或 Studio 中的 tool calls。强调：最终结果可能一样，排查方式和成本模型已经不同。模型/API 不可用时，直接说明这是需要真实模型的实验版。", [sources.autonomous, sources.demo]);

slide = buildSlide18(presentation, {
  title: "Agentic Workflow：Agent 提建议，Workflow 决定能不能继续",
  body1: body("Agent 规划", "理解用户输入\n提取日期表达\n提取工作内容\n给出 next_action"),
  body2: body("Workflow 执行", "确认日期\n加载 ERP 上下文\n保存草稿\n进入预览 Gate"),
  body3: body("Agent 生成 + Gate", "组织日报正文\n保留完整 payload\n等待人工确认\n提交 Gate 最终裁决"),
  label1: "理解",
  label2: "受控执行",
  label3: "安全写入",
  footer1: "10",
});
addNotes(slide, "1 分钟", "最重要的一句话：Agent 负责智能判断和表达空间，Workflow 负责业务顺序和写入权限。当前 Demo 中规划和正文生成采用规则模拟，加载上下文调用现有工具，保存与最终提交用 Demo 状态验证架构。", [sources.agenticGraph, sources.agenticNodes]);

slide = addDemoSlide({ page: 11, title: "现场演示 3｜Agentic Workflow：看职责分工与 Gate", prompt: "agentic workflow写日报：今天完成审批助手开发3", session: "demo-agentic-001", leftTitle: "看结构化状态", leftLines: ["plan / context / compose 分开保存", "events 显示 Agent 与 Workflow 交替", "trace 精确定位阶段"], rightTitle: "看 Gate 拦截", rightLines: ["未预览不能提交", "未明确确认不能提交", "确认后进入 demo_submit_gate"] });
addNotes(slide, "1 分 40 秒", "展示 trace：demo_agent_plan → demo_confirm_date → demo_load_context → demo_agent_compose → demo_save_draft → demo_preview_gate。然后说明回复‘确认提交’才会进入 demo_submit_gate。必须主动说明保存/提交是 Demo 状态，避免包装成真实 ERP 落地。", [sources.agenticGraph, sources.agenticNodes, sources.demo]);

slide = addComparisonTableSlide();
addNotes(slide, "1 分 30 秒", "不要逐格念表。只讲选择标准：业务越确定、写入风险越高，执行顺序越应该由 Workflow 控制；任务越开放、工具风险越低，越可以增加 Agent 决策权。Agentic Workflow 是日报场景当前最值得继续完善的方向。", [sources.fixed, sources.autonomous, sources.agenticGraph]);

slide = buildSlide05(presentation, {
  title: "Deep Agent：这次换成审批场景，探索更长的目标任务",
  body1: body("Deep Agents 负责", "根据目标自主调用工具\n查询用户与审批模板\n收集字段并追问缺失项\n生成审批预览\n按 session 保存线程状态"),
  body2: body("业务系统仍负责", "模板与必填字段\n校验与审批节点计算\nMock 提交与幂等\nsubmit_approval_request 前 interrupt_on\n人工批准后才能恢复"),
  footer1: "13",
});
addNotes(slide, "1 分钟", "这里不要和前三种做完全同场景性能对比，因为 Deep Agent 项目实现的是审批，不是日报。它的价值是展示真实 Deep Agents、checkpoint 和 interrupt_on；业务服务仍是确定性的 mock backend。", [sources.deepAgent, sources.deepTools, sources.deepService]);

slide = addDemoSlide({ page: 14, title: "现场演示 4｜Deep Agent：看 Checkpoint 与 Human-in-the-loop", prompt: "我要报销差旅费，金额 5200 元，因为去上海拜访客户，发票已提供", session: "demo-deep-001", leftTitle: "第一轮", leftLines: ["调用用户 / 模板 / 草稿工具", "生成预览与高金额警告", "危险工具前触发 interrupt"], rightTitle: "确认提交", rightLines: ["同一 session 回复“确认提交”", "Command(resume) 批准中断", "恢复线程并完成 Mock 提交"] });
addNotes(slide, "2 分钟", "先启动 ai_deep_agents_assistant：.\\start_windows.ps1 -Port 8020，打开 http://127.0.0.1:8020/docs。第一轮展示 trace 工具名、awaiting_confirmation 和 interrupt；第二轮用同一 session 回复‘确认提交’，展示恢复后 submitted。网络或模型不稳定时，用截图/录屏兜底。", [sources.deepReadme, sources.deepChat, sources.deepAgent]);

slide = buildSlide13(presentation, {
  title: "四种实现不是排行榜，而是四种执行权配置",
  body1: gridBody("固定 Flow", "规则明确、写入风险高。\n适合生产强流程。"),
  body2: gridBody("自主 Agent", "目标开放、允许路径变化。\n适合工具调用实验。"),
  body3: gridBody("Agentic Workflow", "既需要自然语言理解，也必须控制写入顺序。\n适合受控智能业务。"),
  body4: gridBody("Deep Agent", "复杂目标、长线程、工具较多。\n当前适合学习探索与辅助任务。"),
  footer1: "15",
});
addNotes(slide, "1 分钟", "这一页回答‘最终怎么选’。不是框架越新越好，而是看业务确定性、写入风险、状态要求和成本预算。审批与 ERP 写入的生产主控仍建议保留 Workflow。", [sources.workflow, sources.deepReadme]);

slide = buildSlide13(presentation, {
  title: "预期效果：当前先证明体验和安全边界，而不是虚构效率数字",
  body1: gridBody("问答入口", "用户用自然语言表达审批或日报目标。"),
  body2: gridBody("已实现能力", "请假审批；日报内容、草稿、预览与确认。"),
  body3: gridBody("可观察过程", "响应中返回 Agent 身份、状态、trace、preview。"),
  body4: gridBody("可验证边界", "提交前人工确认；错误接口不假装成功。"),
  footer1: "16",
});
addNotes(slide, "1 分钟", "不要说‘效率提升 80%’这类没有测量的数据。当前成果是功能验证与架构验证。下一步才测平均完成轮次、工具调用成功率、响应时间、Token 成本和失败重试率。", [sources.workflow, sources.fixed, sources.autonomous]);

slide = buildSlide13(presentation, {
  title: "遇到的问题：真正困难的是状态、边界和演示稳定性",
  body1: gridBody("Flow 节点膨胀", "规则越多，条件边和修改分支越重。"),
  body2: gridBody("Agent 不确定性", "工具顺序、循环次数、Token 与延迟难预测。"),
  body3: gridBody("会话状态串线", "复用 session 可能继续进入上一种 Agent；演示必须隔离。"),
  body4: gridBody("Demo 与生产边界", "Agentic 保存/提交为 Demo；Deep Agent 后端为 Mock，必须如实说明。"),
  footer1: "17",
});
addNotes(slide, "1 分 10 秒", "结合真实踩坑讲：Flow 可靠但越来越重；Agent 灵活但排查困难；多种 Agent 共存时，活跃会话状态优先于关键词；演示型实现必须主动说明真实接口、规则模拟和 Mock 的边界。", [sources.fixed, sources.autonomous, sources.agenticNodes, sources.deepService]);

slide = addConclusionSlide();
addNotes(slide, "40 秒", "回到开场：用户只想一句话完成任务，但后台不能因此失去业务规则。最终原则是让 AI 获得合适的决策权，而不是最大决策权。", [sources.workflow, sources.deepReadme]);

const inspection = await presentation.inspect({
  kind: "deck,slide,textbox,shape,table,notes",
  maxChars: 400000,
});
await fs.writeFile(path.join(workspace, "deck-inspect.ndjson"), inspection.ndjson || "", "utf8");

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const currentSlide = presentation.slides.items[index];
  const number = String(index + 1).padStart(2, "0");
  const png = await presentation.export({ slide: currentSlide, format: "png", scale: 1 });
  await fs.writeFile(path.join(renderDir, `slide-${number}.png`), Buffer.from(await png.arrayBuffer()));
  const layout = await currentSlide.export({ format: "layout" });
  await fs.writeFile(path.join(layoutDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
}

const montage = await presentation.export({
  format: "webp",
  montage: { format: "webp", slideWidth: 360, columns: 4, gap: 16, padding: 16, background: "#EDEDED" },
  scale: 1,
});
await fs.writeFile(path.join(workspace, "deck-montage.webp"), Buffer.from(await montage.arrayBuffer()));

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(outputPath);

console.log(JSON.stringify({ outputPath, slideCount: presentation.slides.items.length, workspace }, null, 2));
