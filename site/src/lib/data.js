// Reads the collector's output (../news) at build time.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

// NEWS_DIR points the build at another copy of the data (used for testing layouts).
const NEWS = resolve(process.cwd(), process.env.NEWS_DIR || "../news");
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const datedFiles = (dir) =>
  existsSync(dir) ? readdirSync(dir).filter((f) => /^\d{4}-\d{2}-\d{2}\.json$/.test(f)).sort().reverse() : [];

export const sources = readJson(join(NEWS, "sources.json"));
export const sourceById = Object.fromEntries(sources.map((s) => [s.id, s]));

// Newest first.
export const digests = datedFiles(join(NEWS, "data")).map((f) => readJson(join(NEWS, "data", f)));
export const latest = digests[0];

// Intraday --fast hits, newest first.
export const fastHits = datedFiles(join(NEWS, "data", "fast"))
  .flatMap((f) => readJson(join(NEWS, "data", "fast", f)))
  .sort((a, b) => Date.parse(b.time) - Date.parse(a.time));

// Hits newer than the latest digest are what the home page calls 刚刚发布.
export const freshHits = latest ? fastHits.filter((h) => Date.parse(h.time) > Date.parse(latest.generated)) : fastHits;

export const sections = (d) => [...d.feeds, ...d.rankings];
export const count = (secs) => secs.reduce((n, s) => n + s.items.length, 0);

export const url = (p = "") => import.meta.env.BASE_URL.replace(/\/$/, "") + "/" + p.replace(/^\//, "");

const TZ = "America/New_York";
export const fmtTime = (iso) =>
  new Intl.DateTimeFormat("zh-CN", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso));
export const fmtDay = (iso) =>
  new Intl.DateTimeFormat("zh-CN", { timeZone: TZ, month: "numeric", day: "numeric" }).format(new Date(iso));
export const weekday = (day) =>
  new Intl.DateTimeFormat("zh-CN", { timeZone: "UTC", weekday: "short" }).format(new Date(day + "T12:00:00Z"));

// Where to send a reader for a source as a whole.
export const homepage = (s) =>
  ({ hn_top: "https://news.ycombinator.com/", hf: s.base, rss: s.url && new URL(s.url).origin + "/" })[s.kind] ?? s.url;

export const short = (id) => sourceById[id]?.short ?? sourceById[id]?.name ?? id;

// Ranking helpers. Every field is optional: data from before 2026-11-22 has only title/url/note.
export const isNew = (i) => i.mark === "new";
// Yesterday's list exists, so "new" really is new. Without the field, guess from the marks.
export const hasHistory = (sec) => sec.history ?? !sec.items.every(isNew);
export const newCount = (secs) => secs.filter(hasHistory).reduce((n, s) => n + s.items.filter(isNew).length, 0);

const num = (n) => n.toLocaleString("en-US");
// The number shown right-aligned on a ranking row, with what it means.
export const value = (i) =>
  i.score != null ? { text: num(i.score), label: `${i.score} 分` }
  : i.stars != null ? { text: "今日 ★ +" + num(i.stars), label: `今日 +${i.stars} star` }
  : i.likes != null ? { text: "❤ " + num(i.likes), label: `累计 ${i.likes} 个赞` }
  : i.votes != null ? { text: num(i.votes), label: `${i.votes} 票` }
  : null;

// "org/name" titles (GitHub, Hugging Face) read better name-first.
export const splitTitle = (sec, i) => {
  const kind = sourceById[sec.source]?.kind;
  const m = (kind === "github_trending" || kind === "hf") && i.title.match(/^([^/]+)\/(.+)$/);
  return m ? { org: m[1], name: m[2] } : { name: i.title };
};

// Meta line under a ranking title, a short tag after the title (`inline`), and a one-line
// summary where the source has a useful one.
export const rankMeta = (sec, i) => {
  const kind = sourceById[sec.source]?.kind;
  if (kind === "hn_top") return i.score != null ? { discuss: i.discuss } : { text: i.note, discuss: i.discuss };
  if (kind === "github_trending") return i.stars != null || i.desc != null ? { inline: i.lang, summary: i.desc } : { summary: i.note };
  if (kind === "hf") return i.likes != null ? { inline: i.tag } : { text: i.note };
  return { summary: i.note };
};

// Sources whose summaries carry more per line (Chinese prose) get two lines instead of one.
export const noteLines = (id) => (id === "kexue" ? 2 : 1);
