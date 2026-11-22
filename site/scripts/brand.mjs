// Draws the seal logo (朱红方印「闻」) and every file made from it into public/:
// logo.svg, logo-dark.svg, favicon.svg, favicon-32.png, favicon.ico, apple-touch-icon.png, og.png.
// Text is converted to outlines, so nothing depends on installed fonts. Fonts come from Google
// Fonts, subset to the characters used (an old user agent gets TrueType, which opentype.js reads).
// Run by hand when the mark changes (`npm run brand`); the outputs are committed.
//   --compare <file.png>  also draws the three candidate directions side by side.
import { writeFileSync } from "node:fs";
import { Resvg } from "@resvg/resvg-js";
import opentype from "opentype.js";

const OUT = new URL("../public/", import.meta.url);
const C = { seal: "#c8341f", sealDark: "#e0563f", paper: "#f6f3ec", ink: "#1a1a18", ink2: "#55534d", rule: "#d9d4c7", night: "#121212", nightInk: "#ebe7de" };

async function font(family, weight, text) {
  const css = await (await fetch(`https://fonts.googleapis.com/css2?family=${family.replace(/ /g, "+")}:wght@${weight}&text=${encodeURIComponent(text)}`, { headers: { "User-Agent": "Mozilla/4.0" } })).text();
  const src = css.match(/url\(([^)]+)\)/)?.[1];
  if (!src) throw new Error(`no font for ${family} ${weight}: ${css.slice(0, 200)}`);
  return opentype.parse(await (await fetch(src)).arrayBuffer());
}

// Path commands to SVG path data. (opentype.js's own toPathData emits NaN for some values.)
const n2 = (v) => +v.toFixed(2);
const pathData = (p) =>
  p.commands.map((c) =>
    c.type === "Z" ? "Z"
    : c.type === "Q" ? `Q${n2(c.x1)} ${n2(c.y1)} ${n2(c.x)} ${n2(c.y)}`
    : c.type === "C" ? `C${n2(c.x1)} ${n2(c.y1)} ${n2(c.x2)} ${n2(c.y2)} ${n2(c.x)} ${n2(c.y)}`
    : `${c.type}${n2(c.x)} ${n2(c.y)}`).join("");

// Lays out `text` from (x, baseline) and returns { d, width }. `fonts` is a fallback chain;
// `track` is extra space per character in em.
function run(text, fonts, size, x, y, track = 0) {
  let d = "", at = x;
  for (const ch of text) {
    const f = fonts.find((f) => f.charToGlyph(ch).index !== 0) ?? fonts[0];
    const g = f.charToGlyph(ch);
    d += pathData(g.getPath(at, y, size));
    at += (g.advanceWidth / f.unitsPerEm) * size + track * size;
  }
  return { d, width: at - x - track * size };
}

// One glyph scaled so its ink box fills `box` and centred on (cx, cy).
function centred(f, ch, box, cx, cy) {
  const bb = f.charToGlyph(ch).getPath(0, 0, 1000).getBoundingBox();
  const s = box / Math.max(bb.x2 - bb.x1, bb.y2 - bb.y1);
  const b = f.charToGlyph(ch).getPath(0, 0, 1000 * s).getBoundingBox();
  return pathData(f.charToGlyph(ch).getPath(cx - (b.x1 + b.x2) / 2, cy - (b.y1 + b.y2) / 2, 1000 * s));
}

// The seal: a square of side `n` at (x, y), corners 1/12 of the side, the glyph at `fill` of it.
// The glyph is stroked in its own colour for slightly heavier strokes than the 900 weight.
const seal = (f, x, y, n, { fill = 0.7, color = C.seal, cls = "", glyph = "闻" } = {}) =>
  `<rect${cls && ` class="${cls}"`} x="${x}" y="${y}" width="${n}" height="${n}" rx="${(n / 12).toFixed(2)}" fill="${color}"/>` +
  `<path d="${centred(f, glyph, n * fill, x + n / 2, y + n / 2)}" fill="#fff" stroke="#fff" stroke-width="${(n * 0.012).toFixed(2)}" stroke-linejoin="round"/>`;

const svg = (w, h, body, extra = "") =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"${extra}>${body}</svg>\n`;
const png = (s, width) => new Resvg(s, { fitTo: { mode: "width", value: width } }).render().asPng();

const ico = (pngs) => {
  // ICO with PNG entries (Vista+); each entry: size, 32 bpp, byte length, offset.
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(pngs.length, 4);
  let off = head.length;
  pngs.forEach(([n, buf], i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(n % 256, e);
    head.writeUInt8(n % 256, e + 1);
    head.writeUInt16LE(1, e + 4);
    head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(buf.length, e + 8);
    head.writeUInt32LE(off, e + 12);
    off += buf.length;
  });
  return Buffer.concat([head, ...pngs.map(([, b]) => b)]);
};

const SUB = "AI 公司博客 · 技术博客 · 各大榜单 · 每天 8:00";
const heavy = await font("Noto Serif SC", 900, "闻要");
const serif = await font("Noto Serif SC", 700, "Joe每日要闻");
const mono = await font("JetBrains Mono", 500, "JOE·DAILYWIRE AI8:0" + "NO.");
const sansCJK = await font("Noto Sans SC", 500, SUB);

// Wordmark: seal, 每日要闻, and JOE · DAILY WIRE under it. 168 x 40.
function wordmark(inkColor, subColor) {
  const name = run("每日要闻", [serif], 21, 50, 21);
  const tag = run("JOE · DAILY WIRE", [mono], 8, 50.5, 34.5, 0.08);
  const w = Math.ceil(Math.max(name.width, tag.width) + 52);
  return svg(w, 40, seal(heavy, 0, 0, 40) + `<path d="${name.d}" fill="${inkColor}"/><path d="${tag.d}" fill="${subColor}"/>`);
}
writeFileSync(new URL("logo.svg", OUT), wordmark(C.ink, C.ink2));
writeFileSync(new URL("logo-dark.svg", OUT), wordmark(C.nightInk, "#9c978c"));

// Favicon: the seal alone, a touch brighter on dark browser chrome. Glyph larger so it reads at 16px.
const favBody = (cls) => seal(heavy, 0, 0, 64, { fill: 0.76, cls });
writeFileSync(new URL("favicon.svg", OUT),
  svg(64, 64, `<style>@media (prefers-color-scheme: dark){.s{fill:${C.sealDark}}}</style>` + favBody("s")));
const favStatic = svg(64, 64, favBody());
writeFileSync(new URL("favicon-32.png", OUT), png(favStatic, 32));
writeFileSync(new URL("favicon.ico", OUT), ico([16, 32, 48].map((n) => [n, png(favStatic, n)])));

// Apple touch icon: full-bleed vermilion (iOS rounds the corners), glyph inside a 12% margin.
const touch = svg(180, 180, `<rect width="180" height="180" fill="${C.seal}"/>` +
  `<path d="${centred(heavy, "闻", 180 * 0.76, 90, 90)}" fill="#fff" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>`);
writeFileSync(new URL("apple-touch-icon.png", OUT), png(touch, 180));

// Open Graph card, 1200 x 630: paper, the seal large on the left, name and line on the right.
{
  const title = run("Joe 每日要闻", [serif], 92, 452, 318);
  const sub = run(SUB, [mono, sansCJK], 24, 455, 392);
  const wire = run("JOE · DAILY WIRE", [mono], 20, 455, 210, 0.08);
  const body = `<rect width="1200" height="630" fill="${C.paper}"/>` +
    `<rect x="96" y="60" width="1008" height="1" fill="${C.rule}"/><rect x="96" y="569" width="1008" height="1" fill="${C.rule}"/>` +
    seal(heavy, 96, 165, 300) +
    `<path d="${wire.d}" fill="${C.seal}"/><path d="${title.d}" fill="${C.ink}"/>` +
    `<rect x="455" y="350" width="${Math.round(title.width)}" height="1.5" fill="${C.ink}"/>` +
    `<path d="${sub.d}" fill="${C.ink2}"/>`;
  writeFileSync(new URL("og.png", OUT), png(svg(1200, 630, body), 1200));
}

// Three directions side by side, at 128 / 32 / 16 px and as a wordmark, light and dark.
const i = process.argv.indexOf("--compare");
if (i > 0) {
  const label = await font("JetBrains Mono", 500, "ABCDEFGHIJKLMNOPQRSTUVWXYZ·0123456789 /▮-()");
  const lab = await font("Noto Sans SC", 500, "方印闻圆要电讯符号默认推荐「」（）色块+");
  const dirs = [
    ["A  方印「闻」（默认）", (x, y, n) => seal(heavy, x, y, n)],
    ["B  圆印「要」", (x, y, n) => `<circle cx="${x + n / 2}" cy="${y + n / 2}" r="${n / 2}" fill="${C.seal}"/><path d="${centred(heavy, "要", n * 0.62, x + n / 2, y + n / 2)}" fill="#fff"/>`],
    ["C  电讯符号（色块 + 闻）", (x, y, n, ink = C.ink) => `<rect x="${x}" y="${y + n * 0.1}" width="${n * 0.3}" height="${n * 0.8}" fill="${C.seal}"/><path d="${centred(heavy, "闻", n * 0.8, x + n * 0.75, y + n / 2)}" fill="${ink}"/>`],
  ];
  let body = `<rect width="1200" height="760" fill="${C.paper}"/><rect y="380" width="1200" height="380" fill="${C.night}"/>`;
  [[0, C.ink, C.ink2], [380, C.nightInk, "#9c978c"]].forEach(([oy, ink, sub]) => {
    dirs.forEach(([name, draw], k) => {
      const x = 40 + k * 390;
      const l = run(name, [label, lab], 15, x, oy + 40);
      body += `<path d="${l.d}" fill="${sub}"/>`;
      body += draw(x, oy + 64, 128, ink) + draw(x + 152, oy + 64, 32, ink) + draw(x + 200, oy + 64, 16, ink);
      const wm = run("每日要闻", [serif], 26, x + 60, oy + 270);
      const tg = run("JOE · DAILY WIRE", [mono], 10, x + 61, oy + 288, 0.08);
      body += draw(x, oy + 240, 48, ink) + `<path d="${wm.d}" fill="${ink}"/><path d="${tg.d}" fill="${sub}"/>`;
    });
  });
  writeFileSync(process.argv[i + 1], png(svg(1200, 760, body), 1200));
}
console.log("brand files written to public/");
