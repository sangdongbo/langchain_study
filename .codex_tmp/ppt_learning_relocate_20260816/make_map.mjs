import fs from "node:fs/promises";

const sourceMap = "D:/PythonProject/LearnOne/.codex_tmp/ppt_learning_roadmap_20260816/template-frame-map.json";
const outputMap = "D:/PythonProject/LearnOne/.codex_tmp/ppt_learning_relocate_20260816/template-frame-map.json";
const map = JSON.parse(await fs.readFile(sourceMap, "utf8"));

for (const entry of map.outputSlides) entry.editTargets = [];
const restoredSlide22 = map.outputSlides.find((entry) => entry.outputSlide === 22);
restoredSlide22.narrativeRole = "delivery roadmap";
restoredSlide22.editTargets = [
  { sourceElementId: "sh/6987itcr", action: "rewrite" },
  { sourceElementId: "sh/p43q1sva", action: "rewrite" },
  { sourceElementId: "sh/436507qx", action: "rewrite" },
  { sourceElementId: "sh/2honyx8r", action: "rewrite" },
  { sourceElementId: "sh/gf65w7ql", action: "rewrite" },
  { sourceElementId: "sh/1cj61w7q", action: "rewrite" },
  { sourceElementId: "sh/krihkz2d", action: "rewrite" },
  { sourceElementId: "sh/yp0zipk7", action: "rewrite" },
  { sourceElementId: "sh/wnihgf2h", action: "rewrite" },
  { sourceElementId: "sh/bm9gnu1w", action: "rewrite" },
  { sourceElementId: "sh/907ylkjq", action: "rewrite" },
  { sourceElementId: "sh/qtwz2547", action: "rewrite" },
  { sourceElementId: "sh/cvy14fmx", action: "rewrite" },
  { sourceElementId: "sh/exgj6p43", action: "rewrite" },
];

const closing = map.outputSlides.find((entry) => entry.outputSlide === 33);
closing.outputSlide = 34;
closing.narrativeRole = "closing thesis";
closing.editTargets = [{ sourceElementId: "sh/nml47a5w", action: "rewrite" }];
map.outputSlides.push({
  outputSlide: 33,
  sourceSlide: 22,
  narrativeRole: "future learning and exploration",
  reuseMode: "duplicate-slide",
  editTargets: [{ sourceElementId: "sh/k7qpgjul", action: "rewrite" }],
});
map.outputSlides.sort((left, right) => left.outputSlide - right.outputSlide);

await fs.writeFile(outputMap, `${JSON.stringify(map, null, 2)}\n`, "utf8");
console.log(outputMap);

