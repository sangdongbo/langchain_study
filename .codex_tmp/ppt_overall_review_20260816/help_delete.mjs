import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const presentation = await PresentationFile.importPptx(
  await FileBlob.load("D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx"),
);
const result = presentation.help("*", {
  search: "delete slide remove slide slides.delete slides.remove moveTo duplicate",
  include: ["index", "examples", "notes"],
  maxChars: 20000,
});
console.log(result.ndjson || "");
