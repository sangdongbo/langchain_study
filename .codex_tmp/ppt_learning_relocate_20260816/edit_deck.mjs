import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_learning_relocate_20260816";
const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-学习探索版.pptx";
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-学习探索后置版.pptx";
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
  const index = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 40000 });
  const anchor = parseNdjson(index.ndjson).find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Slide anchor not found: ${slideNumber}`);
  const result = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 200 },
    kind: "slide,textbox,notes",
    include: "id,slide,text,bbox,title",
    maxChars: 70000,
  });
  return parseNdjson(result.ndjson).filter((record) => record.slide === slideNumber);
}

function findTextbox(records, text) {
  const matches = records.filter((record) => record.kind === "textbox" && record.text === text);
  if (matches.length !== 1) throw new Error(`Expected one textbox ${JSON.stringify(text)}, found ${matches.length}`);
  return matches[0];
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const learningSlide = presentation.slides.items[21].duplicate();
learningSlide.moveTo(32);

const slide22Records = await inspectSlide(presentation, 22);
const restoreReplacements = [
  ["后续学习与探索：从工作流走向企业级 AI 底座", "下一步：从两个场景沉淀 ERP 智能化底座"],
  ["强化 AI 工程化", "完善审批与日报闭环"],
  ["Structured Output 与 Schema", "动态字段适配"],
  ["Tool Calling 与幂等", "确认与错误恢复"],
  ["LangSmith 评测体系", "链路观测"],
  ["深入 LangGraph 编排", "沉淀通用能力"],
  ["State 与 Checkpoint", "统一业务 Schema"],
  ["Subgraph 与节点复用", "统一 ERP Tool"],
  ["Human-in-the-loop", "公司级配置适配"],
  ["探索企业级 RAG", "扩展更多 ERP 场景"],
  ["混合检索与 Rerank", "订单与库存"],
  ["权限过滤与知识治理", "客户跟进"],
  ["GraphRAG / LightRAG 评测", "经营分析与任务执行"],
  ["学习目标：补齐 ERP 智能化所需的稳定性、评测、治理与规模化能力", "以 LangGraph 作为主框架：让 AI 理解任务，让 ERP 流程稳定、可控、可追踪"],
];
for (const [oldText, newText] of restoreReplacements) {
  presentation.resolve(findTextbox(slide22Records, oldText).id).text = newText;
}
const slide22 = presentation.slides.items[21];
slide22.speakerNotes.textFrame.setText(
  "【只记一句】下一步是把两个试点沉淀成可复用底座。\n\n" +
  "【可直接照读】近期完善审批与日报的动态字段、错误恢复和链路观测；中期沉淀统一业务 Schema、ERP Tool和公司级配置适配；长期扩展订单、库存、客户跟进和经营分析。最终目标是让 AI 理解任务，让 ERP 流程稳定、可控、可追踪。\n\n" +
  "【时间建议】约 45 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/README.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/architecture.md\n" +
  "[/Sources]"
);
slide22.speakerNotes.setVisible(true);

const slide33Records = await inspectSlide(presentation, 33);
presentation.resolve(findTextbox(slide33Records, "22").id).text = "33";
const slide34Records = await inspectSlide(presentation, 34);
presentation.resolve(findTextbox(slide34Records, "33").id).text = "34";

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
  await presentation.export({ format: "webp", montage: { format: "webp", columns: 4, gap: 12, padding: 12 }, scale: 1 }),
);
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);
console.log(JSON.stringify({ output, slideCount: presentation.slides.items.length, renderDir, layoutDir }, null, 2));

