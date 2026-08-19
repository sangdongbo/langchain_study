import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_erp_ai_issues_20260818";
const source = "D:/PythonProject/LearnOne/ERP与AI融合实践.pptx";
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-问题补充版.pptx";
const renderDir = path.join(workspace, "final-render");
const layoutDir = path.join(workspace, "final-layout");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function parseNdjson(ndjson) {
  return (ndjson || "").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

async function inspectSlide(presentation, slideNumber) {
  const slideIndex = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 50000 });
  const anchor = parseNdjson(slideIndex.ndjson).find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Slide anchor not found: ${slideNumber}`);
  const result = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 220 },
    kind: "slide,textbox,notes",
    include: "id,slide,text,bbox,title",
    maxChars: 80000,
  });
  return parseNdjson(result.ndjson).filter((record) => record.slide === slideNumber);
}

function findTextbox(records, text) {
  const matches = records.filter((record) => record.kind === "textbox" && record.text === text);
  if (matches.length !== 1) throw new Error(`Expected one textbox ${JSON.stringify(text)}, found ${matches.length}`);
  return matches[0];
}

function applyReplacements(presentation, records, replacements) {
  for (const [oldText, newText] of replacements) {
    presentation.resolve(findTextbox(records, oldText).id).text = newText;
  }
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));

const blank17 = presentation.slides.items[16];
const futureOptimization = presentation.slides.items[18].duplicate();
futureOptimization.moveTo(16);
blank17.delete();

const slide17Records = await inspectSlide(presentation, 17);
applyReplacements(presentation, slide17Records, [
  ["优化方向：稳定流程标准化，开放判断 Agent 化", "本次未处理：可信性与运行治理仍需补齐"],
  ["20", "17"],
  ["适合保留在流程中的内容", "可信性边界"],
  ["字段是否完整", "记忆只保留会话状态"],
  ["业务校验是否通过", "业务事实实时查询 ERP"],
  ["是否已经生成预览", "权限以当前用户为准"],
  ["用户是否明确确认", "字段与客户信息禁止编造"],
  ["写入是否幂等、可审计", "关键写入必须预览确认"],
  ["适合交给 Agent 的内容", "可观测与运行时治理"],
  ["理解用户真实目标", "Trace 记录节点与路由"],
  ["从自然语言提取信息", "日志记录 Tool 参数与结果"],
  ["决定需要查询哪些上下文", "指标监控延迟与成功率"],
  ["组织日报和业务摘要", "评测覆盖幻觉与权限越界"],
  ["面对开放任务制定下一步", "Runtime 提供超时、重试、降级"],
  ["配套改进", "后续优化"],
  ["规则配置化", "记忆分层"],
  ["节点单一职责", "证据引用与校验"],
  ["统一 ERP 工具", "LangSmith 全链路观测"],
  ["LangSmith 全链路观测", "Agent Runtime 治理"],
]);
const slide17 = presentation.slides.items[16];
slide17.speakerNotes.textFrame.setText(
  "【只记一句】这四项是本次没有完成生产级处理、后续必须补齐的可信性与运行治理能力。\n\n" +
  "【可直接照读】第一是记忆边界，ERP业务事实不能依赖模型记忆，必须以实时ERP数据和当前用户权限为准；第二是幻觉防护，审批字段、客户信息和日报事实必须来自用户输入或ERP上下文，关键写入前还要预览确认；第三是可观测性，需要通过Trace、日志和指标知道模型如何判断、走了哪些节点、调用了什么Tool；第四是Agent Runtime治理，需要补齐超时、重试、降级和异常恢复。这些能力本次只完成了部分验证，还没有形成完整的生产级方案。\n\n" +
  "【时间建议】约 70 秒\n\n" +
  "[Sources]\n" +
  "- User-provided reference screenshot: C:/Users/EDY/AppData/Local/Temp/codex-clipboard-aa65bb8f-8161-400a-b762-b18ec105a92c.png\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/architecture.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/studio_debug.md\n" +
  "[/Sources]"
);
slide17.speakerNotes.setVisible(true);

const blank27 = presentation.slides.items[26];
const createAgentExplanation = presentation.slides.items[11].duplicate();
createAgentExplanation.moveTo(26);
blank27.delete();

const slide27Records = await inspectSlide(presentation, 27);
applyReplacements(presentation, slide27Records, [
  ["自主日报助手：让 Agent 决定下一步做什么", "daily_report_create_agent：自主规划的日报实验版"],
  ["13", "27"],
  ["输入不再要求固定格式", "开放输入，自主选择工具"],
  ["把今天的客户跟进整理成日报", "把今天的客户跟进整理成日报"],
  ["Agent 自主判断", "Agent 自主判断"],
  ["先确认日期", "通过后端工具确认日期"],
  ["需要加载哪些 ERP 数据", "加载字段、配置、草稿与同步数据"],
  ["是否继续追问内容", "保存草稿并生成预览"],
  ["何时生成预览", "反馈后继续补充"],
  ["能力提升", "ERP 写入边界"],
  ["适应更自然、更开放的用户表达", "不允许模型推断或编造日期"],
  ["减少固定流程中的人工分支设计", "接口失败必须明确返回"],
  ["可按上下文自主调用日报工具", "自定义字段与附件必须保留"],
  ["仍需保留的边界", "提交闸门"],
  ["不允许编造内容 · 不允许跳过预览 · 不允许自动提交", "仅在用户明确确认后调用受保护的提交 Tool"],
  ["适合作为能力探索：灵活性更高，但执行顺序与异常恢复更依赖约束", "当前定位：独立实验入口，验证 Agent 自主工具选择，不替代标准日报流程"],
]);
const slide27FinalBullet = presentation.resolve(findTextbox(slide27Records, "何时生成预览").id);
slide27FinalBullet.position = { ...slide27FinalBullet.position, top: 514 };
const slide27 = presentation.slides.items[26];
slide27.speakerNotes.textFrame.setText(
  "【只记一句】daily_report_create_agent 是自主规划的独立实验版，Agent可以选择工具，但ERP写入边界仍然固定。\n\n" +
  "【可直接照读】它接收更开放的日报请求，由Agent自主决定下一步：先调用后端工具确认权威日期，再加载字段、配置、草稿和同步数据，保存草稿并生成预览。它和标准daily_report_agent的区别是，标准版由LangGraph固定流程保证稳定执行，自主版由Agent根据上下文选择工具。为了避免误写，代码移除了普通提交工具，改为guarded_submit_daily_report，只有用户明确确认后才允许提交；接口失败也必须明确返回，不能假装保存成功。当前它是独立实验入口，用于验证开放任务中的自主工具选择，不替代标准日报主流程。\n\n" +
  "【时间建议】约 75 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/app/agents/daily_report_create_agent.py\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/app/tools/daily_report_tools.py\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/app/agents/daily_report_chat_agent.py\n" +
  "[/Sources]"
);
slide27.speakerNotes.setVisible(true);

await fs.rm(renderDir, { recursive: true, force: true });
await fs.rm(layoutDir, { recursive: true, force: true });
await fs.mkdir(renderDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });
for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const number = String(index + 1).padStart(2, "0");
  const slide = presentation.slides.items[index];
  await writeBlob(path.join(renderDir, `slide-${number}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(layoutDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
}
await writeBlob(path.join(workspace, "final-montage.webp"), await presentation.export({
  format: "webp",
  montage: { format: "webp", columns: 4, gap: 12, padding: 12 },
  scale: 1,
}));
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
console.log(JSON.stringify({ output, slideCount: presentation.slides.items.length, renderDir, layoutDir }, null, 2));
