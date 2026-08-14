import { FileBlob, PresentationFile } from "@oai/artifact-tool";

const source = "D:/PythonProject/LearnOne/.codex_tmp/ppt_rag_logic_20260814/source-deck.pptx";
const presentation = await PresentationFile.importPptx(await FileBlob.load(source));
const sourceSlide = presentation.slides.items[32];
const duplicate = sourceSlide.duplicate();

function titles() {
  return presentation.slides.items.map((slide, index) => ({
    index,
    id: slide.id,
    title: slide.title,
  }));
}

console.log(JSON.stringify({ stage: "after-duplicate", count: presentation.slides.items.length, titles: titles().slice(30) }, null, 2));
duplicate.moveTo(34);
console.log(JSON.stringify({ stage: "after-moveTo-34", count: presentation.slides.items.length, titles: titles().slice(30) }, null, 2));

const inspect = await presentation.inspect({
  kind: "slide,textbox,notes",
  search: "怎么搜索出想要的内容|谢谢|ENTERPRISE RAG · SEARCH PATH|欢迎交流",
  maxChars: 30000,
});
console.log(inspect.ndjson || "");
