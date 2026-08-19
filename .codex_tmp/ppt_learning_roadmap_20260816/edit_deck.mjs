import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_learning_roadmap_20260816";
const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-主线强化版.pptx";
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-学习探索版.pptx";
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
    target: { id: anchor, beforeLines: 0, afterLines: 180 },
    kind: "slide,textbox,notes",
    include: "id,slide,text,bbox,title",
    maxChars: 60000,
  });
  return parseNdjson(result.ndjson).filter((record) => record.slide === slideNumber);
}

function findTextbox(records, text) {
  const matches = records.filter((record) => record.kind === "textbox" && record.text === text);
  if (matches.length !== 1) throw new Error(`Expected one textbox ${JSON.stringify(text)}, found ${matches.length}`);
  return matches[0];
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const records = await inspectSlide(presentation, 22);
const replacements = [
  ["下一步：从两个场景沉淀 ERP 智能化底座", "后续学习与探索：从工作流走向企业级 AI 底座"],
  ["完善审批与日报闭环", "强化 AI 工程化"],
  ["动态字段适配", "Structured Output 与 Schema"],
  ["确认与错误恢复", "Tool Calling 与幂等"],
  ["链路观测", "LangSmith 评测体系"],
  ["沉淀通用能力", "深入 LangGraph 编排"],
  ["统一业务 Schema", "State 与 Checkpoint"],
  ["统一 ERP Tool", "Subgraph 与节点复用"],
  ["公司级配置适配", "Human-in-the-loop"],
  ["扩展更多 ERP 场景", "探索企业级 RAG"],
  ["订单与库存", "混合检索与 Rerank"],
  ["客户跟进", "权限过滤与知识治理"],
  ["经营分析与任务执行", "GraphRAG / LightRAG 评测"],
  ["以 LangGraph 作为主框架：让 AI 理解任务，让 ERP 流程稳定、可控、可追踪", "学习目标：补齐 ERP 智能化所需的稳定性、评测、治理与规模化能力"],
];

for (const [oldText, newText] of replacements) {
  presentation.resolve(findTextbox(records, oldText).id).text = newText;
}

const slide22 = presentation.slides.items[21];
slide22.speakerNotes.textFrame.setText(
  "【只记一句】下一阶段不是继续堆框架，而是补齐 ERP 智能化所需的工程化、流程治理和企业知识能力。\n\n" +
  "【可直接照读】后续学习与探索主要分三个方向。近期重点强化 AI 工程化，包括 Structured Output、统一 Schema、Tool Calling 的幂等设计，以及通过 LangSmith 建立评测体系；中期继续深入 LangGraph，重点学习 State、Checkpoint、Subgraph、节点复用和 Human-in-the-loop，把复杂流程拆得更清晰；长期重点探索企业级 RAG，包括混合检索、Rerank、权限过滤、知识治理，并用真实评测判断 GraphRAG 或 LightRAG 是否值得引入。最终目标不是掌握更多名词，而是把这些能力沉淀成可评测、可治理、可规模化的 ERP 智能化底座。\n\n" +
  "【时间建议】约 70 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/README.md\n" +
  "- D:/PythonProject/LearnOne/ai_approval_assistant/docs/architecture.md\n" +
  "- D:/PythonProject/LearnOne/docs/python_langchain_notes.md\n" +
  "- D:/PythonProject/LearnOne/docs/python_rag_notes.md\n" +
  "- D:/PythonProject/LearnOne/docs/python_milvus_notes.md\n" +
  "- D:/PythonProject/LearnOne/docs/python_rag_graphrag_lightrag_notes.md\n" +
  "[/Sources]"
);
slide22.speakerNotes.setVisible(true);

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

