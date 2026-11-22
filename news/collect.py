"""Fetch Joe's news sources and write a Markdown digest.

Usage:
  uv run --no-project news/collect.py            daily digest -> news/digests/YYYY-MM-DD.md
  uv run --no-project news/collect.py --fast     quick check of sources marked "fast"; prints only
                                                 posts not yet alerted (empty output = nothing new)
  add --all to ignore seen state; --only id1,id2 to fetch just those sources (the rest of
  today's digest is kept as it was, e.g. to fill in linux.do from a machine it does not block).

Besides the Markdown digest, each run writes news/data/YYYY-MM-DD.json (the same digest as data,
for the website), and --fast appends its hits to news/data/fast/YYYY-MM-DD.json. Running again on
the same day merges into that day's digest: earlier new posts stay, rankings are replaced, and a
ranking whose fetch fails keeps the earlier snapshot. Dates are local time, so set
TZ=America/New_York on machines that are not in New York.

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
DATA = HERE / "data"
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
        r = subprocess.run(["curl", "-sfL", "-m", "25", "-A", UA, url], capture_output=True)
        if r.returncode:
            # Usually Cloudflare refusing the IP (GitHub runners); see README for the fallback.
            raise RuntimeError(f"HTTP 403, curl 也失败（exit {r.returncode}），可能是 IP 被拦") from None
        return r.stdout.decode("utf-8", "replace")


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
             "note": f"{h['points']} points", "when": "",
             "discuss": {"label": f"{h['num_comments']} 评论", "url": f"https://news.ycombinator.com/item?id={h['objectID']}"}}
            for h in hits]


KINDS = {"rss": rss, "links": links, "github_trending": github_trending, "hf": hf, "hn_top": hn_top}


def fetch(src):
    try:
        return src, KINDS[src["kind"]](src)[: src.get("limit", 10)], None
    except Exception as e:  # one bad source must not sink the digest
        return src, [], f"{type(e).__name__}: {e}"


def line(i, mark=""):
    s = f"- [{i['title']}]({i['url']}){mark}"
    note = " · ".join(x for x in [i["note"], i.get("discuss") and "[{label}]({url})".format(**i["discuss"])] if x)
    return s + (f" — {note}" if note else "")


def mark_text(i):
    return {"": "", "new": " 🆕"}.get(i.get("mark", ""), f" ·（第 {i.get('streak')} 天）")


def item_data(i, **extra):
    d = {k: i[k] for k in ("id", "title", "url", "note")}
    if i.get("discuss"):
        d["discuss"] = i["discuss"]
    return d | extra


def render(data):
    out = [f"# Joe 每日要闻 {data['date']}", ""]
    feeds = []
    for sec in data["feeds"]:
        feeds += [f"### {sec['name']}", ""] + [line(i) for i in sec["items"]] + [""]
    out += ["## 新文章", ""] + (feeds or ["（今天各博客都没有新文章）", ""])
    out += ["## 今日榜单", ""]
    for sec in data["rankings"]:
        out += [f"### {sec['name']}", ""] + [line(i, mark_text(i)) for i in sec["items"]] + [""]
    if data["status"]:
        out += ["## 来源状态", ""] + [f"- {s['name']}：{s['message']}" for s in data["status"]] + [""]
    return "\n".join(out)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n")


def load_state():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for k, v in list(state.items()):
        if isinstance(v, list):  # pre-2026-11-22 format: a plain list of seen ids
            state[k] = {"seen": v}
    return state


def main():
    show_all, fast = "--all" in sys.argv, "--fast" in sys.argv
    today = date.today().isoformat()
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    sources = [s for s in json.loads((HERE / "sources.json").read_text())
               if (not fast or s.get("fast")) and (not only or s["id"] in only)]
    state = load_state()
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(fetch, sources))

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if fast:
        out, hits = [], []
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
                hits.append(item_data(i, source=src["id"], name=src["name"], time=now))
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
        if hits:
            path = DATA / "fast" / f"{today}.json"
            write_json(path, (json.loads(path.read_text()) if path.exists() else []) + hits)
        print("\n".join(out))
        return

    # Merge into today's digest if one exists: a rerun must not drop posts shown earlier today.
    json_path = DATA / f"{today}.json"
    old = json.loads(json_path.read_text()) if json_path.exists() else {}
    old_feeds = {sec["source"]: sec for sec in old.get("feeds", [])}
    old_rankings = {sec["source"]: sec for sec in old.get("rankings", [])}
    fetched = {src["id"] for src, _, _ in results}
    feeds, rankings, status = {}, {}, []
    for src, items, err in results:
        st = state.setdefault(src["id"], {})
        ranking = src.get("type") == "ranking"
        sec = {"source": src["id"], "name": src["name"], "type": "ranking" if ranking else "feed", "items": []}
        if err:
            status.append({"source": src["id"], "name": src["name"], "kind": "error", "message": err})
            if ranking and src["id"] in old_rankings:
                rankings[src["id"]] = old_rankings[src["id"]] | {"stale": True}
                status[-1]["message"] += f"（榜单保留了今天 {old_rankings[src['id']].get('fetched', '')[11:16]} 抓到的结果）"
            continue
        seen = set(st.get("seen", []))
        if ranking:
            # streak[id] = [last day on list, days in a row]
            prev, streak = (date.today() - timedelta(days=1)).isoformat(), st.get("streak", {})
            for i in items:
                last, n = streak.get(i["id"], ["", 0])
                n = n if last == today else (n + 1 if last == prev else 1)
                streak[i["id"]] = [today, n]
                sec["items"].append(item_data(i, mark="new" if n == 1 else "streak", streak=n))
            st["streak"] = {k: v for k, v in streak.items() if v[0] >= prev}
            rankings[src["id"]] = sec | {"fetched": now}
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
                status.append({"source": src["id"], "name": src["name"], "kind": "health",
                               "message": f"已 {quiet} 天没有新内容（平时约每 {cadence} 天一篇），可能是源坏了"})
        for i in new:
            if src["kind"] == "links":
                i["title"] = title_of(i["url"]) or i["title"]
            sec["items"].append(item_data(i))
        earlier = [i for i in old_feeds.get(src["id"], {}).get("items", []) if i["id"] not in {n["id"] for n in sec["items"]}]
        sec["items"] += earlier
        if sec["items"]:
            feeds[src["id"]] = sec

    # Sources not fetched this run (--only) keep what today's digest already had.
    for sid, sec in old_feeds.items():
        feeds.setdefault(sid, sec)
    for sid, sec in old_rankings.items():
        rankings.setdefault(sid, sec)
    status += [s for s in old.get("status", []) if s["source"] not in fetched]
    order = {s["id"]: n for n, s in enumerate(json.loads((HERE / "sources.json").read_text()))}
    by_order = lambda secs: sorted(secs, key=lambda sec: order.get(sec["source"], 99))
    data = {"date": today, "generated": now, "feeds": by_order(feeds.values()), "rankings": by_order(rankings.values()),
            "status": sorted(status, key=lambda s: order.get(s["source"], 99))}
    total = sum(len(sec["items"]) for sec in data["feeds"] + data["rankings"])
    failures = sum(s["kind"] == "error" for s in data["status"])

    digests = HERE / "digests"
    digests.mkdir(exist_ok=True)
    path = digests / f"{today}.md"
    path.write_text(render(data))
    write_json(json_path, data)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    print(path)
    print(f"{total} items, {failures} failed sources, {len(data['status']) - failures} health warnings")


if __name__ == "__main__":
    main()
