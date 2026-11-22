import rss from "@astrojs/rss";
import { count, digests, fmtTime } from "../lib/data.js";

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const list = (items, ordered) =>
  `<${ordered ? "ol" : "ul"}>` +
  items.map((i) => `<li><a href="${esc(i.url)}">${esc(i.title)}</a>${i.mark === "new" ? " 🆕" : ""}${i.note ? ` — ${esc(i.note)}` : ""}</li>`).join("") +
  `</${ordered ? "ol" : "ul"}>`;

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
    customData: "<language>zh-CN</language>",
    items: digests.slice(0, 30).map((d) => ({
      title: `Joe 每日要闻 ${d.date}`,
      link: new URL(`d/${d.date}/`, base).href,
      pubDate: new Date(d.generated),
      description: `${fmtTime(d.generated)} 生成 · 新文章 ${count(d.feeds)} 篇 · 榜单 ${count(d.rankings)} 条` + (d.feeds.length ? "：" + d.feeds.flatMap((s) => s.items).slice(0, 5).map((i) => i.title).join("；") : ""),
      content: content(d),
    })),
  });
}
