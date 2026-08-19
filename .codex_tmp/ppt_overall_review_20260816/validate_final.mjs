import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const pptxPath = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-整体优化版.pptx";
const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_overall_review_20260816";
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

const slideIndex = await presentation.inspect({ kind: "slide", include: "id,slide,title", maxChars: 20000 });
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
    target: { id: anchor, beforeLines: 0, afterLines: 160 },
    kind: "slide,textbox,shape,image,table,chart,notes",
    include: "id,slide,title,text,bbox,textLines,textChars,isPlaceholder,placeholders",
    maxChars: 60000,
  });
  allRecords.push(...parseNdjson(snapshot.ndjson).filter((record) => record.slide === slideNumber));
}

const outOfBounds = allRecords.filter((record) => {
  if (!Array.isArray(record.bbox) || record.bbox.length !== 4) return false;
  const [left, top, width, height] = record.bbox;
  return left < 0 || top < 0 || left + width > 1280 || top + height > 720;
});

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

const visibleText = allRecords.filter((record) => record.kind === "textbox").map((record) => record.text || "").join("\n");
const stalePhrases = ["现场演示", "LIVE DEMO", "建议截图", "AGENT WORKFLOW 4/4"].filter((phrase) => visibleText.includes(phrase));
const titleBySlide = Object.fromEntries(slideRecords.map((record) => [record.slide, record.title]));
const notes = allRecords.filter((record) => record.kind === "notes" && typeof record.text === "string");
const notesWithoutSources = notes.filter((record) => !record.text.includes("[Sources]")).map((record) => record.slide);

const report = {
  slideCount: presentation.slides.items.length,
  outOfBounds: outOfBounds.length,
  pageMarkerErrors,
  stalePhrases,
  layoutWarnings,
  notesWithoutSources,
  keyTitles: {
    slide16: titleBySlide[16],
    slide17: titleBySlide[17],
    slide18: titleBySlide[18],
    slide29: titleBySlide[29],
    slide30: titleBySlide[30],
    slide31: titleBySlide[31],
    slide32: titleBySlide[32],
    slide33: titleBySlide[33],
  },
};

await fs.writeFile(path.join(workspace, "qa-report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify(report, null, 2));

const failed =
  report.slideCount !== 33 ||
  report.outOfBounds !== 0 ||
  report.pageMarkerErrors.length !== 0 ||
  report.stalePhrases.length !== 0 ||
  report.notesWithoutSources.length !== 0;
process.exitCode = failed ? 1 : 0;
