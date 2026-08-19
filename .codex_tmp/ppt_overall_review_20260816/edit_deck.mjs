import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_overall_review_20260816";
const starter = path.join(workspace, "template-starter.pptx");
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-整体优化版.pptx";
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
  const slideIndex = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 20000 });
  const anchor = parseNdjson(slideIndex.ndjson).find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Slide anchor not found: ${slideNumber}`);
  const result = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 120 },
    kind: "slide,textbox,notes",
    include: "id,slide,text,bbox,title",
    maxChars: 40000,
  });
  return parseNdjson(result.ndjson).filter((record) => record.slide === slideNumber);
}

function findTextbox(records, text) {
  const matches = records.filter((record) => record.kind === "textbox" && record.text === text);
  if (matches.length !== 1) throw new Error(`Expected one textbox ${JSON.stringify(text)}, found ${matches.length}`);
  return matches[0];
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(starter));

for (let slideNumber = 2; slideNumber <= presentation.slides.items.length; slideNumber += 1) {
  const records = await inspectSlide(presentation, slideNumber);
  const pageMarker = records.find((record) =>
    record.kind === "textbox" &&
    Array.isArray(record.bbox) &&
    record.bbox[0] === 1170 &&
    record.bbox[1] === 674 &&
    record.bbox[2] === 42 &&
    record.bbox[3] === 20
  );
  if (pageMarker) presentation.resolve(pageMarker.id).text = String(slideNumber).padStart(2, "0");
}

const slide16Records = await inspectSlide(presentation, 16);
const slide16 = presentation.slides.items[15];
slide16.speakerNotes.textFrame.setText(
  "【只记一句】预期效果不是让 AI 多回答一句，而是让两个业务动作形成可确认、可恢复、可衡量的闭环。\n\n" +
  "【可直接照读】当前已实现聊天请假、动态字段收集、审批预览和确认提交，以及聊天写日报、草稿、预览和 interrupt/resume 恢复。下一页用两个场景验证这条业务闭环。后续可以用模板识别准确率、平均对话轮次、必填字段完成率、预览到提交成功率、恢复成功率和 ERP Tool P95 延迟衡量规模化效果。\n\n" +
  "【时间建议】约 50 秒\n\n" +
  "[Sources]\n- D:/PythonProject/LearnOne/ai_approval_assistant/README.md\n[/Sources]"
);
slide16.speakerNotes.setVisible(true);

const slide17Records = await inspectSlide(presentation, 17);
const slide17Replacements = [
  ["现场演示：用两条对话证明业务闭环", "两个高频场景，验证 AI 能否完成业务闭环"],
  ["LIVE DEMO · 2–3 MIN", "ERP × AI · BUSINESS LOOP"],
  ["演示一：聊天请假", "场景一：聊天请假"],
  ["演示二：聊天发日报", "场景二：聊天发日报"],
  ["演示原则：先展示输入与结果，再解释背后的 Agent、Workflow 和 ERP Tool", "验证标准：自然语言输入、信息补全、人工确认与 ERP 结果反馈"],
];
for (const [oldText, newText] of slide17Replacements) {
  presentation.resolve(findTextbox(slide17Records, oldText).id).text = newText;
}
const inputLabels = slide17Records.filter((record) => record.kind === "textbox" && record.text === "现场输入");
if (inputLabels.length !== 2) throw new Error(`Expected two input labels, found ${inputLabels.length}`);
for (const record of inputLabels) presentation.resolve(record.id).text = "用户输入";
const resultLabels = slide17Records.filter((record) => record.kind === "textbox" && record.text === "展示结果");
if (resultLabels.length !== 2) throw new Error(`Expected two result labels, found ${resultLabels.length}`);
for (const record of resultLabels) presentation.resolve(record.id).text = "闭环结果";

const slide17 = presentation.slides.items[16];
slide17.speakerNotes.textFrame.setText(
  "【只记一句】两个场景都不是单轮问答，而是从自然语言理解走到了 ERP 可确认的业务结果。\n\n" +
  "【可直接照读】聊天请假会根据真实配置补充请假类型和时间，字段完整后生成审批预览，只有明确确认后才提交；聊天发日报会加载业务上下文、生成草稿和预览，再等待用户确认。大家重点看四点：自然语言入口、动态补充信息、提交前人工确认，以及 ERP 结果反馈。\n\n" +
  "【现场演示提示】可以在本页讲完后切到实际系统，演示控制在约 2 分钟；如果现场环境异常，直接使用后面的 LangGraph Studio 附录说明同一条输入、预览、确认和提交路径。\n\n" +
  "【时间建议】PPT 讲解约 30 秒，现场演示约 2 分钟\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/演示.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/README.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/app/api/chat.py\n" +
  "[/Sources]"
);
slide17.speakerNotes.setVisible(true);

const slide19Records = await inspectSlide(presentation, 19);
presentation.resolve(findTextbox(slide19Records, "建议截图：审批完整 Trace + 日报 interrupt/resume + Agentic Workflow 计划与闸门").id).text =
  "排查目标：快速定位问题发生在模型、路由、状态还是 ERP 接口";

const slide32Records = await inspectSlide(presentation, 32);
presentation.resolve(findTextbox(slide32Records, "ENTERPRISE RAG · AGENT WORKFLOW 4/4").id).text =
  "ENTERPRISE RAG · ERP WORKFLOW";

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

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
console.log(JSON.stringify({ output, slideCount: presentation.slides.items.length, renderDir, layoutDir }, null, 2));
