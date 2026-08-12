import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const input = "D:/PythonProject/LearnOne/AI效能分享-审批与日报四种AI实现-现场演示版.pptx";
const outputDir = "D:/PythonProject/LearnOne/ai_approval_assistant/.codex-ppt-rebuild-demo/final-import-rendered";

await fs.rm(outputDir, { recursive: true, force: true });
await fs.mkdir(outputDir, { recursive: true });

const presentation = await PresentationFile.importPptx(await FileBlob.load(input));
const inspection = await presentation.inspect({ kind: "deck,slide,textbox,shape,table,notes", maxChars: 400000 });
await fs.writeFile(path.join(outputDir, "final-inspect.ndjson"), inspection.ndjson || "", "utf8");

for (let index = 0; index < presentation.slides.items.length; index += 1) {
  const png = await presentation.export({ slide: presentation.slides.items[index], format: "png", scale: 1 });
  await fs.writeFile(path.join(outputDir, `slide-${String(index + 1).padStart(2, "0")}.png`), Buffer.from(await png.arrayBuffer()));
}

console.log(JSON.stringify({ slideCount: presentation.slides.items.length, outputDir }, null, 2));
