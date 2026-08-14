import fs from "node:fs/promises";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const pptxPath = "D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx";
const inspectPath = `${pptxPath}.inspect.ndjson`;

const presentation = await PresentationFile.importPptx(await FileBlob.load(pptxPath));
const lines = (await fs.readFile(inspectPath, "utf8")).split(/\r?\n/).filter(Boolean);
const records = lines.map((line) => JSON.parse(line));
const outOfBounds = records.filter((record) => {
  if (!Array.isArray(record.bbox) || record.bbox.length !== 4) return false;
  const [left, top, width, height] = record.bbox;
  return left < 0 || top < 0 || left + width > 1280 || top + height > 720;
});

const hasWorkflow = records.some(
  (record) => record.slide === 35 && record.text === "一次请求，如何从聊天走到 ERP",
);
const hasThanks = records.some(
  (record) => record.slide === 36 && record.text === "谢谢",
);
const hasWorkflowPageNumber = records.some(
  (record) => record.slide === 35 && record.text === "35",
);
const hasThanksPageNumber = records.some(
  (record) => record.slide === 36 && record.text === "36",
);
const staleExample = records.some(
  (record) => record.slide === 32 && record.text === "例：帮我明天下午请半天事假",
);

const slide35 = await presentation.export({ slide: presentation.slides.items[34], format: "png", scale: 1 });
const slide36 = await presentation.export({ slide: presentation.slides.items[35], format: "png", scale: 1 });

const result = {
  slideCount: presentation.slides.items.length,
  outOfBounds: outOfBounds.length,
  hasWorkflow,
  hasThanks,
  hasWorkflowPageNumber,
  hasThanksPageNumber,
  staleExample,
  slide35Rendered: typeof slide35.arrayBuffer === "function",
  slide36Rendered: typeof slide36.arrayBuffer === "function",
};

console.log(JSON.stringify(result, null, 2));

const failed =
  result.slideCount !== 36 ||
  result.outOfBounds !== 0 ||
  !result.hasWorkflow ||
  !result.hasThanks ||
  !result.hasWorkflowPageNumber ||
  !result.hasThanksPageNumber ||
  result.staleExample ||
  !result.slide35Rendered ||
  !result.slide36Rendered;

process.exitCode = failed ? 1 : 0;
