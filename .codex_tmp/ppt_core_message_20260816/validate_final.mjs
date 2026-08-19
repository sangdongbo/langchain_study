import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_core_message_20260816";
const pptxPath = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-主线强化版.pptx";
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
const pageMarkerErrors = [];
for (let slideNumber = 2; slideNumber <= presentation.slides.items.length; slideNumber += 1) {
  const expected = String(slideNumber).padStart(2, "0");
  const marker = allRecords.find((record) =>
    record.slide === slideNumber &&
    record.kind === "textbox" &&
    Array.isArray(record.bbox) &&
    record.bbox[0] === 1170 && record.bbox[1] === 674 && record.bbox[2] === 42 && record.bbox[3] === 20
  );
  if (!marker || marker.text !== expected) pageMarkerErrors.push({ slideNumber, expected, actual: marker?.text ?? null });
}

const visibleBySlide = Object.fromEntries(
  Array.from({ length: presentation.slides.items.length }, (_, index) => [
    index + 1,
    allRecords.filter((record) => record.slide === index + 1 && record.kind === "textbox").map((record) => record.text || "").join("\n"),
  ]),
);
const requiredPhrases = [
  { slide: 1, phrase: "AI没有替代ERP，而是为ERP增加自然语言业务入口" },
  { slide: 21, phrase: "核心结论：AI 增加自然语言入口，ERP 保证可信执行" },
  { slide: 21, phrase: "用户从“找功能、填表单”转向“说目标、确认结果”" },
  { slide: 33, phrase: "AI没有替代ERP" },
  { slide: 33, phrase: "而是为ERP增加自然语言业务入口" },
];
const missingPhrases = requiredPhrases.filter(({ slide, phrase }) => !visibleBySlide[slide].includes(phrase));
const stalePhrases = [
  { slide: 1, phrase: "让用户直接表达业务目标，让 AI 在 ERP 规则内协助完成操作" },
  { slide: 21, phrase: "八句话总结：AI 负责理解，ERP 负责可信执行" },
  { slide: 33, phrase: "AI 让 ERP 更易用" },
  { slide: 33, phrase: "ERP 让 AI 更可靠" },
].filter(({ slide, phrase }) => visibleBySlide[slide].includes(phrase));
const notes = allRecords.filter((record) => record.kind === "notes" && typeof record.text === "string");
const notesWithoutSources = notes.filter((record) => !record.text.includes("[Sources]")).map((record) => record.slide);

const report = {
  slideCount: presentation.slides.items.length,
  outOfBounds: outOfBounds.length,
  emptyPlaceholders: emptyPlaceholders.length,
  pageMarkerErrors,
  layoutWarnings,
  missingPhrases,
  stalePhrases,
  notesWithoutSources,
  keyTitles: Object.fromEntries(slideRecords.filter((record) => [1, 21, 33].includes(record.slide)).map((record) => [record.slide, record.title])),
};

await fs.writeFile(path.join(workspace, "qa-report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));

const failed =
  report.slideCount !== 33 ||
  report.outOfBounds !== 0 ||
  report.emptyPlaceholders !== 0 ||
  report.pageMarkerErrors.length !== 0 ||
  report.missingPhrases.length !== 0 ||
  report.stalePhrases.length !== 0 ||
  report.notesWithoutSources.length !== 0;
process.exitCode = failed ? 1 : 0;
