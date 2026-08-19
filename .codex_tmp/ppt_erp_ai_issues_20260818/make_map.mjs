import fs from "node:fs/promises";

const output = "D:/PythonProject/LearnOne/.codex_tmp/ppt_erp_ai_issues_20260818/template-frame-map.json";
const outputSlides = [];
for (let slide = 1; slide <= 34; slide += 1) {
  outputSlides.push({
    outputSlide: slide,
    sourceSlide: slide,
    narrativeRole: "preserve source slide",
    reuseMode: "duplicate-slide",
    editTargets: [],
  });
}

const slide17 = outputSlides[16];
slide17.sourceSlide = 19;
slide17.narrativeRole = "unresolved risks and future optimization";
slide17.editTargets = [
  "sh/9gb6xgbi", "sh/vitozqt8", "sh/xkbq10be", "sh/jmd83atk", "sh/cri1gnql",
  "sh/qpgjex8f", "sh/0vi1k7qx", "sh/et0jix8r", "sh/oj21o7qt", "sh/x07i1cji",
  "sh/vep0z21c", "sh/54ri5wje", "sh/j2p03m1o", "sh/l8nitsja", "sh/07ehknip",
  "sh/belg3yh8", "sh/dg3y58zy", "sh/zilg7yh4", "sh/lk3y98za",
].map((sourceElementId) => ({ sourceElementId, action: "rewrite" }));

const slide27 = outputSlides[26];
slide27.sourceSlide = 12;
slide27.narrativeRole = "daily_report_create_agent explanation";
slide27.editTargets = [
  "sh/1gbm9s3a", "sh/ra943il8", "sh/dcbm583y", "sh/b6d4f2lc", "sh/a543mx4r",
  "sh/xw3q94ne", "sh/bulo7u58", "sh/9sj65kn2", "sh/nq1o3a5w", "sh/hkbm5wzu",
  "sh/fit436ho", "sh/tgrm1wzy", "sh/7u94zmhs", "sh/6t0n6hg7", "sh/dcv6dgz2",
  "sh/alwbitsn",
].map((sourceElementId) => ({ sourceElementId, action: "rewrite" }));

await fs.writeFile(output, `${JSON.stringify({
  outputSlides,
  omittedSourceSlides: [
    { sourceSlide: 17, reason: "blank placeholder replaced by source slide 19 pattern" },
    { sourceSlide: 27, reason: "blank placeholder replaced by source slide 12 pattern" },
  ],
}, null, 2)}\n`, "utf8");
console.log(output);

