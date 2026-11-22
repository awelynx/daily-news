import rss from "@astrojs/rss";
import { count, digests, fmtTime, highlights, short } from "../lib/data.js";

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const list = (items, ordered) =>
  `<${ordered ? "ol" : "ul"}>` +
  items.map((i) => `<li><a href="${esc(i.url)}">${esc(i.title)}</a>${i.mark === "new" ? " 🆕" : ""}${i.note ? ` — ${esc(i.note)}` : ""}</li>`).join("") +
  `</${ordered ? "ol" : "ul"}>`;

// One entry per day: its 今日重点 with links to every source, then a link to the full digest.
function picks(d, hl, link) {
  const items = hl.items.map((h) =>
    `<li><p><b>[${esc(h.tag)}] <a href="${esc(h.url)}">${esc(h.title_zh)}</a></b>` +
    (h.title && h.title !== h.title_zh ? `<br><small>${esc(h.title)}</small>` : "") +
    `</p><p>${esc(h.why)}</p><p><small>出处：` +
    h.sources.map((s) => `<a href="${esc(s.url)}">${esc(short(s.source))}${s.rank ? ` 第${s.rank}` : ""}</a>`).join(" · ") +
    `</small></p></li>`).join("");
  return `<ol>${items}</ol><p><a href="${esc(link)}">查看全部 ${count(d.feeds) + count(d.rankings)} 条 →</a></p>`;
}

// Days without a 今日重点 list (before it existed) carry the whole digest.
function content(d) {
  let h = "<h2>新文章</h2>";
  h += d.feeds.length ? d.feeds.map((s) => `<h3>${esc(s.name)}</h3>${list(s.items)}`).join("") : "<p>今天各博客都没有新文章。</p>";
  h += "<h2>今日榜单</h2>" + d.rankings.map((s) => `<h3>${esc(s.name)}</h3>${list(s.items, true)}`).join("");
  if (d.status.length) h += "<h2>来源状态</h2><ul>" + d.status.map((s) => `<li>${esc(s.name)}：${esc(s.message)}</li>`).join("") + "</ul>";
  return h;
}

export function GET(context) {
  const base = new URL(import.meta.env.BASE_URL, context.site);
  return rss({
    title: "Joe 每日要闻",
    description: "AI 公司博客、技术博客与各大榜单的每日汇总",
    site: base.href,
    customData:
      "<language>zh-CN</language>" +
      `<image><url>${new URL("og.png", base).href}</url><title>Joe 每日要闻</title><link>${base.href}</link></image>`,
    items: digests.slice(0, 30).map((d) => {
      const link = new URL(`d/${d.date}/`, base).href;
      const hl = highlights[d.date];
      return {
        title: `Joe 每日要闻 ${d.date}`,
        link,
        pubDate: new Date(d.generated),
        description: hl
          ? `今日重点 ${hl.items.length} 条：` + hl.items.map((h) => h.title_zh).join("；")
          : `${fmtTime(d.generated)} 生成 · 新文章 ${count(d.feeds)} 篇 · 榜单 ${count(d.rankings)} 条` + (d.feeds.length ? "：" + d.feeds.flatMap((s) => s.items).slice(0, 5).map((i) => i.title).join("；") : ""),
        content: hl ? picks(d, hl, link) : content(d),
      };
    }),
  });
}
