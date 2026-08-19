import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_erp_ai_issues_20260818";
const pptxPath = "D:/PythonProject/LearnOne/ERP与AI融合实践-问题补充版.pptx";
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
const slideIndex = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 50000 });
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
    target: { id: anchor, beforeLines: 0, afterLines: 220 },
    kind: "slide,textbox,shape,image,table,chart,notes",
    include: "id,slide,title,text,bbox,textLines,textChars,isPlaceholder,placeholders",
    maxChars: 90000,
  });
  allRecords.push(...parseNdjson(snapshot.ndjson).filter((record) => record.slide === slideNumber));
}

const outOfBounds = allRecords.filter((record) => {
  if (!Array.isArray(record.bbox) || record.bbox.length !== 4) return false;
  const [left, top, width, height] = record.bbox;
  return left < 0 || top < 0 || left + width > 1280 || top + height > 720;
});
const emptyPlaceholders = allRecords.filter((record) => record.isPlaceholder && !(record.text || "").trim());
const textForSlide = (slideNumber) => allRecords.filter((record) => record.slide === slideNumber && record.kind === "textbox").map((record) => record.text || "").join("\n");
const slide17Text = textForSlide(17);
const slide27Text = textForSlide(27);
const contentErrors = [];
for (const phrase of ["本次未处理：可信性与运行治理仍需补齐", "记忆只保留会话状态", "字段与客户信息禁止编造", "Trace 记录节点与路由", "Runtime 提供超时、重试、降级"]) {
  if (!slide17Text.includes(phrase)) contentErrors.push(`slide17 missing: ${phrase}`);
}
for (const phrase of ["daily_report_create_agent：自主规划的日报实验版", "通过后端工具确认日期", "ERP 写入边界", "受保护的提交 Tool", "不替代标准日报流程"]) {
  if (!slide27Text.includes(phrase)) contentErrors.push(`slide27 missing: ${phrase}`);
}
if (slide17Text.includes("解决的方案")) contentErrors.push("slide17 blank title remains");
if (slide27Text.includes("标准日报子图：草稿、预览与提交恢复")) contentErrors.push("slide27 blank title remains");
const notes = allRecords.filter((record) => record.kind === "notes" && typeof record.text === "string");
const notesWithoutSources = notes.filter((record) => !record.text.includes("[Sources]")).map((record) => record.slide);

const report = {
  slideCount: presentation.slides.items.length,
  outOfBounds: outOfBounds.length,
  emptyPlaceholders: emptyPlaceholders.length,
  layoutWarnings,
  contentErrors,
  notesWithoutSources,
  keyTitles: Object.fromEntries(slideRecords.filter((record) => [16, 17, 18, 26, 27, 28].includes(record.slide)).map((record) => [record.slide, record.title])),
};
await fs.writeFile(path.join(workspace, "qa-report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.slideCount === 34 && report.outOfBounds === 0 && report.emptyPlaceholders === 0 && report.contentErrors.length === 0 && report.notesWithoutSources.length === 0 ? 0 : 1;
