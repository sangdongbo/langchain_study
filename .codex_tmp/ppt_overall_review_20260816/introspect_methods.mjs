import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const presentation = await PresentationFile.importPptx(
  await FileBlob.load("D:/PythonProject/LearnOne/ERP与AI融合实践-智能审批与日报-RAG扩展版-流程优化版.pptx"),
);

function methods(value) {
  const names = new Set();
  let current = value;
  while (current && current !== Object.prototype) {
    for (const name of Object.getOwnPropertyNames(current)) names.add(name);
    current = Object.getPrototypeOf(current);
  }
  return [...names].sort();
}

console.log(JSON.stringify({
  slideMethods: methods(presentation.slides.items[0]),
  slideCollectionMethods: methods(presentation.slides),
}, null, 2));
