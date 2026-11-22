"""Fetch Joe's news sources and write a Markdown digest.

Usage:
  uv run --no-project news/collect.py            daily digest -> news/digests/YYYY-MM-DD.md
  uv run --no-project news/collect.py --fast     quick check of sources marked "fast"; prints only
                                                 posts not yet alerted (empty output = nothing new)
  add --all to ignore seen state.

Two kinds of source (field "type" in sources.json):
  feed     blogs and news: only posts not seen before are shown.
  ranking  daily lists (trending, top of the day): shown whole each day, each item marked as
           new on the list or how many days in a row it has been there.
Feeds with "cadence_days" get a health warning when nothing new has appeared for 3x that long,
which is how a broken scraper or stale feed shows up.
Stdlib only. State lives in news/state.json.
"""
import html
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,zh;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
        # Some sites (linux.do) block urllib's TLS fingerprint but accept curl.
        return subprocess.run(["curl", "-sfL", "-m", "25", "-A", UA, url], capture_output=True, check=True).stdout.decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def rss(src):
    root = ET.fromstring(get(src["url"]).encode())
    items = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        f = {c.tag.split("}")[-1]: c for c in it}
        link = f.get("link")
        href = (link.get("href") or link.text or "").strip() if link is not None else ""
        title = clean(f["title"].text if "title" in f else "")
        desc = clean((f.get("description") if "description" in f else f.get("summary")).text if ("description" in f or "summary" in f) else "")
        when = next((f[k].text for k in ("pubDate", "published", "updated") if k in f and f[k].text), "")
        if desc in ("Comments", title):
            desc = ""
        items.append({"id": href or title, "title": title, "url": href, "note": desc[:160], "when": when})
    if src.get("newest_last"):
        items.reverse()
    return items


def links(src):
    page = get(src["url"])
    seen, items = set(), []
    for path in re.findall(src["pattern"], page):
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        if path in seen or slug in src.get("skip", []):
            continue
        seen.add(path)
        items.append({"id": path, "title": slug.replace("-", " ").capitalize(), "url": src["base"] + path, "note": "", "when": ""})
    return items


def title_of(url):
    try:
        page = get(url)
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"', page) or re.search(r"<title>([^<]+)</title>", page)
        return re.sub(r"\s+[/|]\s+(claude\.dev Blog|VitePress)$", "", clean(m.group(1))) if m else None
    except Exception:
        return None


def github_trending(src):
    page = get(src["url"])
    items = []
    for block in page.split('<article class="Box-row">')[1:]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="/([^"]+)"', block)
        if not m:
            continue
        repo = m.group(1)
        desc = re.search(r'<p class="col-9[^"]*">(.*?)</p>', block, re.S)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', block)
        today = re.search(r'([\d,]+) stars? today', block)
        note = " · ".join(x for x in [lang and lang.group(1).strip(), today and f"+{today.group(1)}⭐ 今日"] if x)
        items.append({"id": repo, "title": repo, "url": "https://github.com/" + repo,
                      "note": (clean(desc.group(1)) + ("  (" + note + ")" if note else "")) if desc else note, "when": ""})
    return items


def hf(src):
    items = []
    for m in json.loads(get(src["url"])):
        mid = m.get("id") or m.get("modelId")
        note = " · ".join(x for x in [m.get("pipeline_tag") or m.get("sdk"), f"❤ {m.get('likes', 0)}"] if x)
        items.append({"id": mid, "title": mid, "url": src["base"] + mid, "note": note, "when": ""})
    return items


def hn_top(src):
    # Stories posted in the last 24h ranked by points, so one run a day sees the whole day.
    since = int(time.time()) - 86400
    url = f"https://hn.algolia.com/api/v1/search?tags=story&numericFilters=created_at_i%3E{since},points%3E{src.get('min_points', 100)}&hitsPerPage=100"
    hits = sorted(json.loads(get(url))["hits"], key=lambda h: -(h.get("points") or 0))
    return [{"id": h["objectID"], "title": h["title"],
             "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
             "note": f"{h['points']} points · [{h['num_comments']} 评论](https://news.ycombinator.com/item?id={h['objectID']})", "when": ""}
            for h in hits]


KINDS = {"rss": rss, "links": links, "github_trending": github_trending, "hf": hf, "hn_top": hn_top}


def fetch(src):
    try:
        return src, KINDS[src["kind"]](src)[: src.get("limit", 10)], None
    except Exception as e:  # one bad source must not sink the digest
        return src, [], f"{type(e).__name__}: {e}"


def line(i, mark=""):
    s = f"- [{i['title']}]({i['url']}){mark}"
    return s + (f" — {i['note']}" if i["note"] else "")


def load_state():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for k, v in list(state.items()):
        if isinstance(v, list):  # pre-2026-11-22 format: a plain list of seen ids
            state[k] = {"seen": v}
    return state


def main():
    show_all, fast = "--all" in sys.argv, "--fast" in sys.argv
    today = date.today().isoformat()
    sources = [s for s in json.loads((HERE / "sources.json").read_text()) if not fast or s.get("fast")]
    state = load_state()
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(fetch, sources))

    if fast:
        out = []
        for src, items, err in results:
            st = state.setdefault(src["id"], {})
            known = set(st.get("seen", [])) | set(st.get("alerted", []))
            if err or not known:  # no baseline yet: stay quiet, the daily run sets it
                continue
            new = [i for i in items if show_all or i["id"] not in known]
            st["alerted"] = list(dict.fromkeys([i["id"] for i in new] + st.get("alerted", [])))[:200]
            for i in new:
                if src["kind"] == "links":
                    i["title"] = title_of(i["url"]) or i["title"]
                out.append(line(i, f" ·（{src['name']}）"))
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
        print("\n".join(out))
        return

    feeds, rankings, failures, health, total = [], [], [], [], 0
    for src, items, err in results:
        st = state.setdefault(src["id"], {})
        if err:
            failures.append(f"- {src['name']}: {err}")
            continue
        seen = set(st.get("seen", []))
        if src.get("type") == "ranking":
            # streak[id] = [last day on list, days in a row]
            prev, streak = (date.today() - timedelta(days=1)).isoformat(), st.get("streak", {})
            block = [f"### {src['name']}", ""]
            for i in items:
                last, n = streak.get(i["id"], ["", 0])
                n = n if last == today else (n + 1 if last == prev else 1)
                streak[i["id"]] = [today, n]
                block.append(line(i, " 🆕" if n == 1 else f" ·（第 {n} 天）"))
                total += 1
            st["streak"] = {k: v for k, v in streak.items() if v[0] >= prev}
            rankings += block + [""]
            continue
        new = items if show_all else [i for i in items if i["id"] not in seen]
        st["seen"] = list(dict.fromkeys([i["id"] for i in items] + list(seen)))[:500]
        st.pop("alerted", None)  # the daily digest supersedes intraday alerts
        if new and seen:
            st["last_new"] = today
        st.setdefault("last_new", today)
        cadence = src.get("cadence_days")
        if cadence and not new:
            quiet = (date.today() - date.fromisoformat(st["last_new"])).days
            if quiet > 3 * cadence:
                health.append(f"- {src['name']}：已 {quiet} 天没有新内容（平时约每 {cadence} 天一篇），可能是源坏了")
        if not new:
            continue
        feeds += [f"### {src['name']}", ""]
        for i in new:
            if src["kind"] == "links":
                i["title"] = title_of(i["url"]) or i["title"]
            feeds.append(line(i))
            total += 1
        feeds.append("")

    out = [f"# Joe 每日要闻 {today}", ""]
    out += ["## 新文章", ""] + (feeds or ["（今天各博客都没有新文章）", ""])
    out += ["## 今日榜单", ""] + rankings
    if failures or health:
        out += ["## 来源状态", ""] + failures + health + [""]

    digests = HERE / "digests"
    digests.mkdir(exist_ok=True)
    path = digests / f"{today}.md"
    path.write_text("\n".join(out))
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(path)
    print(f"{total} items, {len(failures)} failed sources, {len(health)} health warnings")


if __name__ == "__main__":
    main()
