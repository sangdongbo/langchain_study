import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_rag_logic_20260814";
const source = path.join(workspace, "source-deck.pptx");
const output = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx";
const renderDir = path.join(workspace, "final-render");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function parseInspect(ndjson) {
  return (ndjson || "")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function indexTextboxes(records, slideNumber) {
  const byText = new Map();
  for (const record of records) {
    if (record.slide === slideNumber && record.kind === "textbox" && typeof record.text === "string") {
      if (!byText.has(record.text)) byText.set(record.text, []);
      byText.get(record.text).push(record.id);
    }
  }
  return byText;
}

function replaceExact(presentation, textIndex, oldText, newText) {
  const ids = textIndex.get(oldText) || [];
  if (ids.length !== 1) {
    throw new Error(`Expected exactly one textbox for ${JSON.stringify(oldText)}, found ${ids.length}`);
  }
  presentation.resolve(ids[0]).text = newText;
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));

presentation.resolve("sh/sr29cbuh").text = "三个边界，避免“所有能力都塞进一个 Prompt”";
presentation.resolve("sh/rqt836dw").text = "RAG 管知识 · ERP Tool 管实时事实 · LangGraph 管流程、状态和写入";

const workflowSlide = presentation.slides.items[32].duplicate();
workflowSlide.moveTo(34);

const afterDuplicate = await presentation.inspect({
  kind: "slide,textbox,notes",
  maxChars: 250000,
});
const records = parseInspect(afterDuplicate.ndjson);
const workflowText = indexTextboxes(records, 35);

const replacements = [
  ["怎么搜索出想要的内容？一条企业级检索链路", "一次请求，如何从聊天走到 ERP"],
  ["ENTERPRISE RAG · SEARCH PATH 2/4", "ENTERPRISE RAG · AGENT WORKFLOW 4/4"],
  ["33", "35"],
  ["用户问题", "用户提问"],
  ["自然语言\n带上下文", "自然语言\n表达业务目标"],
  ["问题拆解", "LLM 理解"],
  ["业务类型 · 公司\n部门 · 时间 · 关键词", "识别意图\n抽取业务字段"],
  ["权限过滤", "路由选择"],
  ["tenant / company\ndepartment / ACL", "制度问答\n实时查询 · 业务动作"],
  ["混合召回", "能力调用"],
  ["Dense 语义\n+ BM25 精确词", "RAG 检索\n或 ERP Tool"],
  ["融合与精排", "LangGraph 控制"],
  ["RRF / Weighted\n+ Reranker", "追问 · 校验\n预览 · 确认"],
  ["证据回答", "返回结果"],
  ["来源 · 章节\n版本 · 原文", "证据回答\n或写入 ERP"],
  ["为什么要两路检索？", "三个关键边界"],
  ["Dense 向量", "LLM Agent"],
  ["擅长同义表达和语义问题，例如“出差回来怎么报销”", "负责理解与规划，不直接修改 ERP"],
  ["BM25 关键词", "RAG + Milvus"],
  ["擅长制度号、订单号、产品编码和字段名等精确匹配", "只在权限范围内检索制度和文档"],
  ["找不到怎么办", "ERP Tool + LangGraph"],
  ["返回“当前权限范围内没有找到”，向用户追问范围，不编造答案", "ERP 提供实时事实，LangGraph 控制业务写入"],
];

for (const [oldText, newText] of replacements) {
  replaceExact(presentation, workflowText, oldText, newText);
}

workflowSlide.speakerNotes.textFrame.setText(
  "【只记一句】用户只说业务目标，Agent 负责理解和选路，RAG 或 ERP Tool 负责执行，LangGraph 负责追问、确认和写入控制。\n\n" +
  "【可直接照读】用户从前端输入自然语言后，LLM 先识别这是制度问答、实时查询还是业务动作；制度问题进入 RAG，实时数据和动态模板通过 ERP Tool 获取；如果要执行审批，LangGraph 会继续补充字段、校验、生成预览，并在用户确认后才写入 ERP。整个过程可以返回执行计划、工具调用、检索证据和 ERP 结果，方便现场演示和问题排查。\n\n" +
  "【时间建议】约 45 秒\n\n" +
  "[Sources]\n" +
  "- D:/PythonProject/LearnOne/ai_erp_rag_assistant/app/graph/workflow.py\n" +
  "- D:/PythonProject/LearnOne/ai_erp_rag_assistant/app/services/milvus_service.py\n" +
  "- D:/PythonProject/LearnOne/ai_erp_rag_assistant/app/services/erp_client.py\n" +
  "[/Sources]"
);
workflowSlide.speakerNotes.setVisible(true);

presentation.resolve("sh/gb6lcn6x").text = "36";

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(output);

await fs.rm(renderDir, { recursive: true, force: true });
await fs.mkdir(renderDir, { recursive: true });
for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slide = presentation.slides.items[index];
  const number = String(index + 1).padStart(2, "0");
  await writeBlob(
    path.join(renderDir, `slide-${number}.png`),
    await presentation.export({ slide, format: "png", scale: 1 }),
  );
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(renderDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
}

await writeBlob(
  path.join(renderDir, "montage.webp"),
  await presentation.export({ format: "webp", montage: true, scale: 1 }),
);

const finalInspect = await presentation.inspect({
  kind: "slide,textbox,shape,notes,layout",
  include: "id,slide,name,title,text,textPreview,textChars,textLines,bbox,bboxUnit,isPlaceholder,preview",
  maxChars: 500000,
});
await fs.writeFile(path.join(renderDir, "inspect.ndjson"), finalInspect.ndjson || "", "utf8");

console.log(JSON.stringify({ output, slideCount: presentation.slides.items.length, renderDir }, null, 2));
