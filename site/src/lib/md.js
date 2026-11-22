// Just enough Markdown for the daily summary (今日汇报): paragraphs, "- " lists, [links](url),
// **bold**, *italic*, `code`. Everything is escaped first, so the source cannot inject HTML.
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

const inline = (s) =>
  esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");

export function renderMarkdown(src = "") {
  return src
    .trim()
    .split(/\n\s*\n/)
    .map((block) => {
      const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
      if (lines.length && lines.every((l) => /^[-*] /.test(l)))
        return "<ul>" + lines.map((l) => `<li>${inline(l.slice(2))}</li>`).join("") + "</ul>";
      const heading = lines[0]?.match(/^#{1,4}\s+(.*)$/);
      if (heading && lines.length === 1) return `<p><strong>${inline(heading[1])}</strong></p>`;
      return `<p>${lines.map(inline).join("<br>")}</p>`;
    })
    .join("");
}
