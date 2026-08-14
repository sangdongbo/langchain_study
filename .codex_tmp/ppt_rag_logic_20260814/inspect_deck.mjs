import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_rag_logic_20260814";
const source = path.join(workspace, "source-deck.pptx");
const outDir = path.join(workspace, "direct-inspect");

async function writeBlob(filePath, blob) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, new Uint8Array(await blob.arrayBuffer()));
}

const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
await fs.mkdir(outDir, { recursive: true });

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const slide = presentation.slides.items[index];
  const number = String(index + 1).padStart(2, "0");
  await writeBlob(
    path.join(outDir, `slide-${number}.png`),
    await presentation.export({ slide, format: "png", scale: 1 }),
  );
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(outDir, `slide-${number}.layout.json`), await layout.text(), "utf8");
}

await writeBlob(
  path.join(outDir, "montage.webp"),
  await presentation.export({ format: "webp", montage: true, scale: 1 }),
);

const inspect = await presentation.inspect({
  kind: "slide,textbox,shape,image,table,chart,notes,layout",
  include: "id,slide,name,title,text,textPreview,textChars,textLines,bbox,bboxUnit,isPlaceholder,placeholders,preview",
  maxChars: 500000,
});
await fs.writeFile(path.join(outDir, "inspect.ndjson"), inspect.ndjson || "", "utf8");

const structure = {
  slideCount: presentation.slides.items.length,
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
await fs.writeFile(path.join(outDir, "structure.json"), JSON.stringify(structure, null, 2), "utf8");
console.log(JSON.stringify({ slideCount: structure.slideCount, outDir }, null, 2));
