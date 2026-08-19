import fs from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

const workspace = "D:/PythonProject/LearnOne/.codex_tmp/ppt_erp_ai_issues_20260818";
const renderDir = path.join(workspace, "final-render");
const output = path.join(workspace, "final-contact-sheet.png");
const columns = 5;
const thumbWidth = 400;
const thumbHeight = 225;
const labelHeight = 34;
const gap = 12;
const padding = 12;
const files = (await fs.readdir(renderDir))
  .filter((name) => /^slide-\d+\.png$/i.test(name))
  .sort();
const rows = Math.ceil(files.length / columns);
const canvasWidth = padding * 2 + columns * thumbWidth + (columns - 1) * gap;
const canvasHeight = padding * 2 + rows * (thumbHeight + labelHeight) + (rows - 1) * gap;
const composites = [];

for (let index = 0; index < files.length; index += 1) {
  const column = index % columns;
  const row = Math.floor(index / columns);
  const left = padding + column * (thumbWidth + gap);
  const top = padding + row * (thumbHeight + labelHeight + gap);
  const input = await sharp(path.join(renderDir, files[index]))
    .resize(thumbWidth, thumbHeight, { fit: "contain", background: "#ffffff" })
    .png()
    .toBuffer();
  const label = Buffer.from(
    `<svg width="${thumbWidth}" height="${labelHeight}" xmlns="http://www.w3.org/2000/svg">` +
    `<rect width="100%" height="100%" fill="#f4f2ee"/>` +
    `<text x="${thumbWidth / 2}" y="24" text-anchor="middle" font-family="Arial, sans-serif" font-size="20" fill="#111111">${files[index]}</text>` +
    `</svg>`,
  );
  composites.push({ input, left, top });
  composites.push({ input: label, left, top: top + thumbHeight });
}

await sharp({
  create: { width: canvasWidth, height: canvasHeight, channels: 4, background: "#e7e7e7" },
}).composite(composites).png().toFile(output);
console.log(output);
