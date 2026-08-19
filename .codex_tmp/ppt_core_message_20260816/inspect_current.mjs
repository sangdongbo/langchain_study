import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-整体优化版.pptx";
const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_core_message_20260816";
const inspectDir = path.join(workspace, "template-inspect");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

function parseNdjson(ndjson) {
  return (ndjson || "").split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line));
}

await fs.mkdir(inspectDir, { recursive: true });
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const slideIndex = await presentation.inspect({
  kind: "slide",
  include: "id,slide,title,textShapes",
  maxChars: 30000,
});
const slideRecords = parseNdjson(slideIndex.ndjson);
const combined = [];

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slideNumber = index + 1;
  const number = String(slideNumber).padStart(2, "0");
  const slide = presentation.slides.items[index];
  const anchor = slideRecords.find((record) => record.slide === slideNumber)?.id;
  if (!anchor) throw new Error(`Missing slide anchor ${slideNumber}`);

  await writeBlob(
    path.join(inspectDir, `slide-${number}.png`),
    await presentation.export({ slide, format: "png", scale: 1 }),
  );
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(inspectDir, `slide-${number}.layout.json`), await layout.text(), "utf8");

  const snapshot = await presentation.inspect({
    target: { id: anchor, beforeLines: 0, afterLines: 180 },
    kind: "slide,textbox,shape,image,table,chart,notes,layout",
    include: "id,slide,name,title,text,textPreview,textChars,textLines,bbox,bboxUnit,isPlaceholder,placeholders,alt,prompt",
    maxChars: 70000,
  });
  const ndjson = snapshot.ndjson || "";
  await fs.writeFile(path.join(inspectDir, `slide-${number}.inspect.ndjson`), ndjson, "utf8");
  combined.push(ndjson.trim());
}

await writeBlob(
  path.join(inspectDir, "montage.webp"),
  await presentation.export({
    format: "webp",
    montage: { format: "webp", columns: 4, gap: 12, padding: 12 },
    scale: 1,
  }),
);
await fs.writeFile(
  path.join(inspectDir, "template-inspect.ndjson"),
  `${combined.filter(Boolean).join("\n")}\n`,
  "utf8",
);
await fs.writeFile(
  path.join(workspace, "template-manifest.json"),
  JSON.stringify({
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
  }, null, 2),
  "utf8",
);

console.log(JSON.stringify({ inspectDir, slideCount: presentation.slides.items.length }, null, 2));
