// Just enough Markdown for the daily summary (今日汇报): paragraphs, "- " lists, [links](url),
// **bold**, *italic*, `code`. Everything is escaped first, so the source cannot inject HTML.
// `notes` (url -> number) adds a footnote mark after each link that points at a 今日重点 item;
// a run of links to the same item ("S-1、定价和交割公告") gets one mark, after the last.
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const FN = "\u0000";

const inline = (s, notes) =>
  esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, (_, text, href) => {
      const n = notes?.get(href.replace(/&amp;/g, "&"));
      return `<a href="${href}" target="_blank" rel="noopener">${text}</a>` + (n ? `${FN}${n}${FN}` : "");
    })
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");

// Drop a mark when the same mark follows within a few characters; render the rest.
const marks = (html) =>
  html
    .replace(new RegExp(`${FN}(\\d+)${FN}(?=((?:(?!${FN})[\\s\\S]){0,120}?)${FN}\\1${FN})`, "g"), (m, n, between) =>
      between.replace(/<[^>]+>/g, "").length <= 8 ? "" : m)
    // The link's last character, its mark and a following Chinese punctuation mark stay on one
    // line (nowrap spans, plus a word joiner: Chrome ignores nowrap at the link's edge), while
    // the rest of the link text still wraps.
    .replace(new RegExp(`(<a [^>]*>(?:(?!</a>)[\\s\\S])*</a>)${FN}(\\d+)${FN}([，。、；：]?)`, "g"),
      (_, a, n, punct) =>
        `<span class="fn-tail">${a.replace(/(&[#\w]+;|[^<>])<\/a>$/, '<span class="nb">$1\u2060</span></a>')}` +
        `<sup class="fn"><a href="#pick-${n}" data-pick="${n}" aria-label="今日重点第 ${n} 条">${n}</a></sup>${punct}</span>`)
    .replace(new RegExp(`${FN}(\\d+)${FN}`, "g"), '<sup class="fn"><a href="#pick-$1" data-pick="$1" aria-label="今日重点第 $1 条">$1</a></sup>');

export function renderMarkdown(src = "", notes) {
  return src
    .trim()
    .split(/\n\s*\n/)
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (lines.length && lines.every((l) => /^[-*] /.test(l)))
        return "<ul>" + lines.map((l) => `<li>${marks(inline(l.slice(2), notes))}</li>`).join("") + "</ul>";
      const heading = lines[0]?.match(/^#{1,4}\s+(.*)$/);
      if (heading && lines.length === 1) return `<p><strong>${marks(inline(heading[1], notes))}</strong></p>`;
      return `<p>${marks(lines.map((l) => inline(l, notes)).join("<br>"))}</p>`;
    })
    .join("");
}
