import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_learning_roadmap_20260816";
const pptxPath = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-学习探索版.pptx";
const renderDir = path.join(workspace, "qa-reimport-render");
const layoutDir = path.join(workspace, "qa-reimport-layout");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function parseNdjson(ndjson) {
  return (ndjson || "").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(pptxPath));
await fs.rm(renderDir, { recursive: true, force: true });
await fs.rm(layoutDir, { recursive: true, force: true });
await fs.mkdir(renderDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });

const slideIndex = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 30000 });
const slideRecords = parseNdjson(slideIndex.ndjson);
const allRecords = [];
let layoutWarnings = 0;

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slideNumber = index + 1;
  const number = String(slideNumber).padStart(2, "0");
  const slide = presentation.slides.items[index];
  const anchor = slideRecords.find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Missing slide anchor ${slideNumber}`);
  await writeBlob(path.join(renderDir, `slide-${number}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
  const layout = await slide.export({ format: "layout" });
  const layoutText = await layout.text();
  await fs.writeFile(path.join(layoutDir, `slide-${number}.layout.json`), layoutText, "utf8");
  if (/overflow|overlap|warning/i.test(layoutText)) layoutWarnings += 1;
  const snapshot = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 180 },
    kind: "slide,textbox,shape,image,table,chart,notes",
    include: "id,slide,title,text,bbox,textLines,textChars,isPlaceholder,placeholders",
    maxChars: 70000,
  });
  allRecords.push(...parseNdjson(snapshot.ndjson).filter((record) => record.slide === slideNumber));
}

const outOfBounds = allRecords.filter((record) => {
  if (!Array.isArray(record.bbox) || record.bbox.length !== 4) return false;
  const [left, top, width, height] = record.bbox;
  return left < 0 || top < 0 || left + width > 1280 || top + height > 720;
});
const emptyPlaceholders = allRecords.filter((record) => record.isPlaceholder && !(record.text || "").trim());
const slide22Text = allRecords.filter((record) => record.slide === 22 && record.kind === "textbox").map((record) => record.text || "").join("\n");
const requiredPhrases = [
  "后续学习与探索：从工作流走向企业级 AI 底座",
  "强化 AI 工程化",
  "深入 LangGraph 编排",
  "探索企业级 RAG",
  "学习目标：补齐 ERP 智能化所需的稳定性、评测、治理与规模化能力",
];
const missingPhrases = requiredPhrases.filter((phrase) => !slide22Text.includes(phrase));
const stalePhrases = ["完善审批与日报闭环", "沉淀通用能力", "扩展更多 ERP 场景"].filter((phrase) => slide22Text.includes(phrase));
const notes = allRecords.filter((record) => record.kind === "notes" && typeof record.text === "string");
const notesWithoutSources = notes.filter((record) => !record.text.includes("[Sources]")).map((record) => record.slide);

const report = {
  slideCount: presentation.slides.items.length,
  outOfBounds: outOfBounds.length,
  emptyPlaceholders: emptyPlaceholders.length,
  layoutWarnings,
  missingPhrases,
  stalePhrases,
  notesWithoutSources,
  slide22Title: slideRecords.find((record) => record.slide === 22)?.title,
};
await fs.writeFile(path.join(workspace, "qa-report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.slideCount === 33 && report.outOfBounds === 0 && report.emptyPlaceholders === 0 && report.missingPhrases.length === 0 && report.stalePhrases.length === 0 && report.notesWithoutSources.length === 0 ? 0 : 1;
