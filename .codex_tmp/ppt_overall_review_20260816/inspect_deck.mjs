import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx";
const outDir = "D:/PythonProject/LearnOne/.codex_tmp/ppt_overall_review_20260816/template-inspect";

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function parseNdjson(ndjson) {
  return (ndjson || "").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

await fs.mkdir(outDir, { recursive: true });
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));

const slideIndex = await presentation.inspect({
  kind: "slide",
  include: "id,slide,title,textShapes",
  maxChars: 20000,
});
const slideRecords = parseNdjson(slideIndex.ndjson);
const combined = [];

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slide = presentation.slides.items[index];
  const slideNumber = String(index + 1).padStart(2, "0");
  const anchor = slideRecords.find((record) => record.slide === index + 1)?.id;

  await writeBlob(
    path.join(outDir, `slide-${slideNumber}.png`),
    await presentation.export({ slide, format: "png", scale: 1 }),
  );
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(outDir, `slide-${slideNumber}.layout.json`), await layout.text(), "utf8");

  if (anchor) {
    const snapshot = await presentation.inspect({
      target: { id: anchor, beforeLines: 0, afterLines: 250 },
      kind: "slide,textbox,shape,image,table,chart,notes,layout",
      include: "id,slide,name,title,text,textPreview,textChars,textLines,bbox,bboxUnit,isPlaceholder,placeholders,preview,alt,prompt",
      maxChars: 80000,
    });
    const ndjson = snapshot.ndjson || "";
    await fs.writeFile(path.join(outDir, `slide-${slideNumber}.inspect.ndjson`), ndjson, "utf8");
    combined.push(ndjson.trim());
  }
}

await writeBlob(
  path.join(outDir, "montage.webp"),
  await presentation.export({ format: "webp", montage: { format: "webp", columns: 4, gap: 12, padding: 12 }, scale: 1 }),
);

await fs.writeFile(path.join(outDir, "template-inspect.ndjson"), combined.filter(Boolean).join("\n") + "\n", "utf8");
const manifest = {
  source,
  slideCount: presentation.slides.items.length,
  slideSize: presentation.slideSize,
  masters: presentation.masters.items.map((master) => ({
    id: master.id,
    name: master.name,
    placeholders: master.placeholders?.summary?.() ?? [],
  })),
  layouts: presentation.layouts.items.map((layout) => ({
    id: layout.id,
    name: layout.name,
    parentLayoutId: layout.parentLayoutId,
    placeholders: layout.placeholders?.summary?.() ?? [],
  })),
};
await fs.writeFile(path.join(outDir, "template-manifest.json"), JSON.stringify(manifest, null, 2), "utf8");
console.log(JSON.stringify({ outDir, slideCount: manifest.slideCount }, null, 2));
