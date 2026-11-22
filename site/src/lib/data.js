// Reads the collector's output (../news) at build time.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const NEWS = resolve(process.cwd(), "../news");
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
