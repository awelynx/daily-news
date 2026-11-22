# /// script
# requires-python = ">=3.10"
# dependencies = ["anthropic>=2.12,<3"]
# ///
"""Fallback writer of the day's highlights (今日汇报 + 今日重点) from news/data/DATE.json.

The main path is Joe (an agent on the owner's Mac) writing the file by hand each morning; see the
README for the format. This script fills in when that hasn't happened yet.

Usage:
  uv run --script news/highlight.py [DATE] [--rules] [--force] [--dry-run]
  uv run --script news/highlight.py [DATE] --check    validate an existing file (e.g. Joe's)

Writes news/data/highlights/DATE.json:
  {"date", "generated", "by": "claude-api" | "joe" | "rules", "summary": Markdown ("" if none),
   "items": [{"title_zh", "title", "url", "why", "tag",
              "sources": [{"source", "name", "url", "title", "rank"?, "score"?, "score_kind"?}]}]}
The same story across sources is one item, with every place it appeared listed in `sources`.

With ANTHROPIC_API_KEY set it asks Claude, steered by news/profile.md; Claude refers to the
day's items by number, so every item URL comes from that day's data, and summary links to any
other URL are reduced to plain text. Without a key, or if the call fails, simple rules pick the
items and the summary stays empty (--rules forces that). A file written by hand (by "joe") is
never overwritten, and a Claude pick is not replaced by a rules pick; --force overrides both.
--dry-run prints the result instead of writing it.
Dates are local time, like collect.py: set TZ=America/New_York outside New York.
"""
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "highlights"
MODEL = "claude-sonnet-5-5"  # latest Sonnet: plenty for ranking ~110 links, at Sonnet cost
TAGS = ["官方", "开源", "论文", "社区", "产品"]
MAX_ITEMS = 7


def candidates(day):
    """Every item of the day as a flat list, each with its source section and rank."""
    out = []
    for sec in day["feeds"] + day["rankings"]:
        for rank, item in enumerate(sec["items"], 1):
            out.append({"sec": sec, "item": item, "rank": rank if sec["type"] == "ranking" else None})
    return out


def source_entry(c):
    sec, item = c["sec"], c["item"]
    e = {"source": sec["source"], "name": sec["name"], "url": item["url"], "title": item["title"]}
    if c["rank"]:
        e["rank"] = c["rank"]
    for kind in ("score", "stars", "likes"):
        if item.get(kind) is not None:
            e["score"], e["score_kind"] = item[kind], kind
            break
    return e


def build_item(cands, refs, title_zh, why, tag):
    refs = list(dict.fromkeys(r for r in refs if 0 <= r < len(cands)))
    if not refs:
        return None
    first = cands[refs[0]]["item"]
    return {"title_zh": title_zh or first["title"], "title": first["title"], "url": first["url"],
            "why": why, "tag": tag if tag in TAGS else "社区", "sources": [source_entry(cands[r]) for r in refs]}


# ---- Claude ----

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "refs": {"type": "array", "items": {"type": "integer"}},
                    "title_zh": {"type": "string"},
                    "why": {"type": "string"},
                    "tag": {"type": "string", "enum": TAGS},
                },
                "required": ["refs", "title_zh", "why", "tag"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["summary", "items"],
    "additionalProperties": False,
}


def describe(n, c):
    sec, item = c["sec"], c["item"]
    bits = [f"[{n}] {sec['name']}" + (f" 第{c['rank']}" if c["rank"] else ""), item["title"]]
    for kind, label in (("score", "分"), ("stars", "今日 star"), ("likes", "赞")):
        if item.get(kind) is not None:
            bits.append(f"{item[kind]} {label}")
    if item.get("mark") == "streak":
        bits.append(f"连续第 {item['streak']} 天在榜")
    note = item.get("desc") or item.get("note") or ""
    if note:
        bits.append(note[:200])
    return " | ".join(bits)


def pick_with_claude(day, cands, profile):
    import anthropic

    listing = "\n".join(describe(n, c) for n, c in enumerate(cands))
    prompt = f"""下面是 {day['date']} 的每日要闻候选（编号、来源和排名、标题、数值、摘要）。请按主人的关注方向挑出今天的重点。

<profile>
{profile}
</profile>

<candidates>
{listing}
</candidates>

要求：
- 选 5–7 条，宁缺毋滥；按重要程度排序。
- 同一件事出现在多个来源（例如同一个模型同时在 HF 热门和 HN 上）合并成一条，refs 列出所有相关编号，最主要的放第一个。
- refs 只能用上面列出的编号。
- title_zh：简洁的中文标题（英文原题给出中文译名或概括）。
- why：一句中文，说明为什么值得主人看，可以引用排名或数值；不要编造候选里没有的事实。
- tag：官方 / 开源 / 论文 / 社区 / 产品 之一。
- summary：一段中文汇报，Markdown，3–5 段、约 300–500 字：今天最重要的事、趋势、和主人关注方向的关联。段内可以用 [文字](url) 链接，url 只能用候选里出现过的。不要标题。"""

    client = anthropic.Anthropic()
    # Refusals fall back server-side to another model ("default" routing) instead of stopping.
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason={response.stop_reason}")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    items = [build_item(cands, h["refs"], h["title_zh"].strip(), h["why"].strip(), h["tag"]) for h in data["items"]]
    items = [i for i in items if i][:MAX_ITEMS]
    if len(items) < 3:
        raise RuntimeError(f"only {len(items)} usable items")
    known = {c["item"]["url"] for c in cands}
    summary = re.sub(r"\[([^\]]+)\]\((\S+?)\)", lambda m: m.group(0) if m.group(2) in known else m.group(1), data["summary"].strip())
    print(f"claude: {response.usage.input_tokens} in / {response.usage.output_tokens} out tokens", file=sys.stderr)
    return summary, items


# ---- Rules (no key) ----

def profile_keywords(profile):
    """Interest terms from the profile's bullet list; the line marked 最高优先 weighs more."""
    words = {}
    for line in profile.splitlines():
        if not line.startswith("- ") or "：" not in line and "、" not in line:
            continue
        if line.startswith("- 每天") or line.startswith("- 官方") or line.startswith("- 每条"):
            continue
        weight = 3 if "最高优先" in line else 1
        for w in re.split(r"[/、：:，,（）()]|\s+与\s+|与", line[2:]):
            w = w.strip()
            w = w.replace("这类", "").strip()
            if len(w) >= 2 and "优先" not in w:
                words[w.lower()] = max(words.get(w.lower(), 0), weight)
    # Short English forms of the multi-word terms, so "agent" matches "agent 框架" and the like.
    for w, weight in list(words.items()):
        for token in re.findall(r"[a-z][a-z0-9.+-]{2,}", w):
            words.setdefault(token, weight)
    return words


DOWNRANK = re.compile(r"/business/|customer|webinar|demo|onboarding|walkthrough|case stud|案例|教程", re.I)
OFFICIAL = {"openai", "anthropic", "claude-blog", "claude-dev"}


def rule_score(c, keywords):
    sec, item = c["sec"], c["item"]
    text = f"{sec['name']} {item['title']} {item.get('desc') or item.get('note') or ''}".lower()
    s = 0.0
    if sec["source"] in OFFICIAL:
        s += 3
    if c["rank"] == 1:
        s += 2
    if sec["source"] == "hn" and (item.get("score") or 0) >= 500:
        s += 3
    if sec["source"] == "kexue":
        s += 1
    s += min(4, sum(w for k, w in keywords.items() if k in text))
    if DOWNRANK.search(item["url"] + " " + item["title"]):
        s -= 3
    return s


def eligible(c):
    sec, item = c["sec"], c["item"]
    return (sec["source"] in OFFICIAL or sec["source"] == "kexue" or c["rank"] == 1
            or (sec["source"] == "hn" and (item.get("score") or 0) >= 500))


def story_key(c):
    """A distinctive name (repo or model) other sources may mention, e.g. Inkling-2-Mini."""
    if c["sec"]["source"] in ("github-trending", "hf-models", "hf-spaces"):
        name = c["item"]["title"].split("/")[-1]
        name = re.sub(r"-(gguf|awq|gptq|mlx|fp8|int4)$", "", name, flags=re.I)
        return name.lower() if len(name) >= 5 else None
    return None


def rule_why(c):
    sec, item = c["sec"], c["item"]
    facts = []
    if c["rank"]:
        facts.append(f"{sec['short'] if 'short' in sec else sec['name']} 第 {c['rank']}")
    if item.get("score") is not None:
        facts.append(f"{item['score']} 分")
    if item.get("stars") is not None:
        facts.append(f"今日 +{item['stars']}★")
    if item.get("likes") is not None:
        facts.append(f"❤{item['likes']}")
    # HN and Hugging Face notes only repeat the numbers above.
    numeric = item.get("score") is not None or item.get("likes") is not None
    note = (item.get("desc") or ("" if numeric else item.get("note")) or "").strip()
    if note:
        note = note[:60] + ("…" if len(note) > 60 else "")
    return "；".join(x for x in ["、".join(facts), note] if x) or sec["name"] + " 新文章"


def rule_tag(c):
    s = c["sec"]["source"]
    return "官方" if s in OFFICIAL else "论文" if s == "kexue" else "开源" if s in ("github-trending", "hf-models", "hf-spaces") else "产品" if s == "producthunt" else "社区"


def pick_with_rules(day, cands, profile):
    keywords = profile_keywords(profile)
    # A story that other sources also carry (a model on HF and HN) counts for more.
    echoes = {id(c): sum(1 for o in cands if o is not c and story_key(c) and story_key(c) in o["item"]["title"].lower())
              for c in cands}
    scored = sorted((c for c in cands if eligible(c)), key=lambda c: -(rule_score(c, keywords) + min(2, echoes[id(c)])))
    # Spread the picks: one per source, and official blogs at most three of the seven.
    used, items, sources, official = set(), [], set(), 0
    for c in scored:
        src = c["sec"]["source"]
        if id(c) in used or src in sources or (src in OFFICIAL and official >= 3):
            continue
        sources.add(src)
        official += src in OFFICIAL
        group = [c]
        key = story_key(c)
        # Fold in the same story from other sources (also items that aren't eligible on their own).
        for other in cands:
            if other is c or id(other) in used:
                continue
            k2 = story_key(other)
            if key and (key in other["item"]["title"].lower() or (k2 and k2 == key)):
                group.append(other)
            elif k2 and k2 in c["item"]["title"].lower():
                group.append(other)
        used.update(id(g) for g in group)
        refs = [cands.index(g) for g in group]
        items.append(build_item(cands, refs, c["item"]["title"], rule_why(c), rule_tag(c)))
        if len(items) == MAX_ITEMS:
            break
    return items


def check(path, day):
    """Problems in a highlights file: missing fields, or URLs that aren't in the day's data."""
    hl = json.loads(path.read_text())
    known = {i["url"] for sec in day["feeds"] + day["rankings"] for i in sec["items"]}
    problems = [f"missing {k}" for k in ("date", "generated", "by", "items") if k not in hl]
    if not 3 <= len(hl.get("items", [])) <= MAX_ITEMS:
        problems.append(f"{len(hl.get('items', []))} items (expected 5–7)")
    urls = re.findall(r"\]\((\S+?)\)", hl.get("summary", ""))
    for n, item in enumerate(hl.get("items", []), 1):
        problems += [f"item {n}: missing {k}" for k in ("title_zh", "url", "why", "tag", "sources") if not item.get(k)]
        if item.get("tag") not in TAGS:
            problems.append(f"item {n}: tag {item.get('tag')!r} not one of {TAGS}")
        urls += [item.get("url", "")] + [s.get("url", "") for s in item.get("sources", [])]
    problems += [f"url not in {day['date']} data: {u}" for u in dict.fromkeys(urls) if u not in known]
    return problems


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day_str = args[0] if args else date.today().isoformat()
    src = HERE / "data" / f"{day_str}.json"
    if not src.exists():
        print(f"no digest data for {day_str}", file=sys.stderr)
        return
    out = OUT / f"{day_str}.json"
    if "--check" in sys.argv:
        problems = check(out, json.loads(src.read_text())) if out.exists() else [f"{out} does not exist"]
        print("\n".join(problems) or f"{out}: ok")
        sys.exit(1 if problems else 0)
    old = json.loads(out.read_text()) if out.exists() else {}
    force = "--force" in sys.argv or "--dry-run" in sys.argv  # a dry run writes nothing
    if old.get("by") == "joe" and not force:
        print(f"{out} was written by hand; leaving it")
        return

    day = json.loads(src.read_text())
    short = {s["id"]: s.get("short", s["name"]) for s in json.loads((HERE / "sources.json").read_text())}
    for sec in day["feeds"] + day["rankings"]:
        sec["short"] = short.get(sec["source"], sec["name"])
    cands = candidates(day)
    profile = (HERE / "profile.md").read_text()

    by, summary, items = "rules", "", None
    if os.environ.get("ANTHROPIC_API_KEY") and "--rules" not in sys.argv:
        try:
            (summary, items), by = pick_with_claude(day, cands, profile), "claude-api"
        except Exception as e:  # the digest must not depend on the API: fall back to rules
            print(f"claude pick failed, using rules: {type(e).__name__}: {e}", file=sys.stderr)
    if items is None:
        if old.get("by") == "claude-api" and not force:
            print(f"{out} has a Claude pick; not replacing it with rules")
            return
        items = pick_with_rules(day, cands, profile)

    result = {"date": day_str, "generated": datetime.now().astimezone().isoformat(timespec="seconds"), "by": by,
              "summary": summary, "items": items}
    text = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    if "--dry-run" in sys.argv:
        print(text)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"{out}: {len(items)} items by {by}")


if __name__ == "__main__":
    main()
