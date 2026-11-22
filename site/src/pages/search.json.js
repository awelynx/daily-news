import { digests, fastHits, sourceById } from "../lib/data.js";

// Every item ever shown, one entry per (source, url), keeping the newest date it appeared on.
export function GET() {
  const seen = new Map();
  const add = (source, item, date) => {
    const key = source + " " + item.url;
    if (!seen.has(key)) seen.set(key, { t: item.title, u: item.url, n: item.note || "", s: source, d: date });
  };
  for (const d of digests) for (const sec of [...d.feeds, ...d.rankings]) for (const i of sec.items) add(sec.source, i, d.date);
  for (const h of fastHits) add(h.source, h, h.time.slice(0, 10));
  const names = Object.fromEntries(Object.entries(sourceById).map(([id, s]) => [id, s.short ?? s.name]));
  return new Response(JSON.stringify({ sources: names, items: [...seen.values()] }), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
