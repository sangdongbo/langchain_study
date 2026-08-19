import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_core_message_20260816";
const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-整体优化版.pptx";
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-主线强化版.pptx";
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
  const index = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 30000 });
  const anchor = parseNdjson(index.ndjson).find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Slide anchor not found: ${slideNumber}`);
  const result = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 160 },
    kind: "slide,textbox,notes",
    include: "id,slide,text,bbox,title",
    maxChars: 50000,
  });
  return parseNdjson(result.ndjson).filter((record) => record.slide === slideNumber);
}

function findTextbox(records, text) {
  const matches = records.filter((record) => record.kind === "textbox" && record.text === text);
  if (matches.length !== 1) throw new Error(`Expected one textbox ${JSON.stringify(text)}, found ${matches.length}`);
  return matches[0];
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));

const slide1Records = await inspectSlide(presentation, 1);
presentation.resolve(findTextbox(slide1Records, "让用户直接表达业务目标，让 AI 在 ERP 规则内协助完成操作").id).text =
  "AI没有替代ERP，而是为ERP增加自然语言业务入口";
const slide1 = presentation.slides.items[0];
slide1.speakerNotes.textFrame.setText(
  "【只记一句】AI没有替代ERP，而是为ERP增加自然语言业务入口。\n\n" +
  "【可直接照读】今天整场分享只围绕一句话：AI没有替代ERP，而是为ERP增加自然语言业务入口。传统ERP要求用户先找到菜单、理解字段、填写表单；引入AI以后，用户只需要表达业务目标，AI负责理解、追问和整理，ERP仍然负责权限、规则、字段和最终写入。接下来我用聊天发起审批和聊天填写日报两个场景说明这条路径。\n\n" +
  "【时间建议】约 50 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/architecture.md\n" +
  "- Visual style references supplied by the user: C:/Users/EDY/Pictures/1.jpg–16.jpg\n" +
  "[/Sources]"
);
slide1.speakerNotes.setVisible(true);

const slide21Records = await inspectSlide(presentation, 21);
presentation.resolve(findTextbox(slide21Records, "八句话总结：AI 负责理解，ERP 负责可信执行").id).text =
  "核心结论：AI 增加自然语言入口，ERP 保证可信执行";
presentation.resolve(findTextbox(slide21Records, "AI不是替代ERP，而是给ERP增加自然语言入口。").id).text =
  "AI没有替代ERP，而是为ERP增加自然语言业务入口。";
presentation.resolve(findTextbox(slide21Records, "一条主线：AI 降低用户操作门槛，ERP 保证业务执行可信").id).text =
  "用户从“找功能、填表单”转向“说目标、确认结果”";
const slide21 = presentation.slides.items[20];
slide21.speakerNotes.textFrame.setText(
  "【只记一句】AI没有替代ERP，而是为ERP增加自然语言业务入口。\n\n" +
  "【可直接照读】最后把这次实践收敛成一个核心结论：AI没有替代ERP，而是为ERP增加自然语言业务入口。用户不再需要先理解系统菜单，而是直接说出请假、写日报这样的业务目标；AI负责理解意图、补充信息和组织交互，ERP继续负责权限、规则、字段以及最终写入。所以变化的是用户与ERP交互的方式，不变的是ERP对业务执行的控制。技术上，LangChain提供基础组件，LangGraph负责可控流程，Deep Agents用于探索自主规划。\n\n" +
  "【领导追问时可补充】可以概括为：AI负责理解与交互，ERP负责规则与执行；用户从找功能、填表单，转向说目标、确认结果。\n\n" +
  "【时间建议】约 60 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/README.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/architecture.md\n" +
  "[/Sources]"
);
slide21.speakerNotes.setVisible(true);

const slide33Records = await inspectSlide(presentation, 33);
presentation.resolve(findTextbox(slide33Records, "AI 让 ERP 更易用").id).text = "AI没有替代ERP";
presentation.resolve(findTextbox(slide33Records, "ERP 让 AI 更可靠").id).text =
  "而是为ERP增加自然语言业务入口";
const slide33 = presentation.slides.items[32];
slide33.speakerNotes.textFrame.setText(
  "【只记一句】AI没有替代ERP，而是为ERP增加自然语言业务入口。\n\n" +
  "【可直接照读】最后再重复一次今天最重要的结论：AI没有替代ERP，而是为ERP增加自然语言业务入口。用户从找功能、填表单，转向说目标、确认结果；AI负责理解和交互，ERP继续负责规则和可信执行。后续无论扩展到采购、订单、库存还是知识问答，都应该坚持这一职责边界。谢谢大家，欢迎交流。\n\n" +
  "【时间建议】约 30 秒\n\n" +
  "[Sources]\n" +
  "- Closing slide; no external claims.\n" +
  "[/Sources]"
);
slide33.speakerNotes.setVisible(true);

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

await writeBlob(
  path.join(workspace, "final-montage.webp"),
  await presentation.export({
    format: "webp",
    montage: { format: "webp", columns: 4, gap: 12, padding: 12 },
    scale: 1,
  }),
);

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
console.log(JSON.stringify({ output, slideCount: presentation.slides.items.length, renderDir, layoutDir }, null, 2));

