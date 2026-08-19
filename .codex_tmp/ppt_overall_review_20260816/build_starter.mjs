import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_overall_review_20260816";
const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx";
const map = JSON.parse(await fs.readFile(path.join(workspace, "template-frame-map.json"), "utf8"));
const starter = path.join(workspace, "template-starter.pptx");
const previewDir = path.join(workspace, "template-starter-preview");
const layoutDir = path.join(workspace, "template-starter-layout");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const originalSlides = [...presentation.slides.items];
const copiedSlides = map.outputSlides.map((entry) => originalSlides[entry.sourceSlide - 1].duplicate());

for (let index = 0; index < copiedSlides.length; index += 1) {
  copiedSlides[index].moveTo(index);
}
for (const slide of originalSlides) slide.delete();

if (presentation.slides.items.length !== map.outputSlides.length) {
  throw new Error(`Starter slide count mismatch: ${presentation.slides.items.length}`);
}

await fs.rm(previewDir, { recursive: true, force: true });
await fs.rm(layoutDir, { recursive: true, force: true });
await fs.mkdir(previewDir, { recursive: true });
await fs.mkdir(layoutDir, { recursive: true });

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const number = String(index + 1).padStart(2, "0");
  const slide = presentation.slides.items[index];
  await writeBlob(path.join(previewDir, `slide-${number}.png`), await presentation.export({ slide, format: "png", scale: 1 }));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(layoutDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
}

const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(starter);
console.log(JSON.stringify({ starter, slideCount: presentation.slides.items.length }, null, 2));
