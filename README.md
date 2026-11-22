# daily-news

Joe 每日要闻：采集脚本 `news/collect.py`，来源 `news/sources.json`，日报 `news/digests/`。

网站：<https://awelynx.github.io/daily-news/>（RSS：`/daily-news/rss.xml`）

## 目录

| 路径 | 内容 |
| --- | --- |
| `news/collect.py` | 采集脚本，只用标准库 |
| `news/sources.json` | 来源列表 |
| `news/digests/YYYY-MM-DD.md` | Markdown 日报 |
| `news/data/YYYY-MM-DD.json` | 同一份日报的 JSON，网站从这里读 |
| `news/data/fast/YYYY-MM-DD.json` | 当天快速检查（`--fast`）发现的新文章，网站上显示为「刚刚发布」 |
| `news/data/highlights/YYYY-MM-DD.json` | 当天的「今日汇报」和重点条目，首页默认只显示这一部分（格式见下） |
| `news/profile.md` | 主人的关注方向和挑选规则，写汇报和挑重点时参考 |
| `news/highlight.py` | 重点的兜底生成：有 `ANTHROPIC_API_KEY` 时调用 Claude，否则按规则挑 |
| `news/state.json` | 已见过的文章、榜单连续天数 |
| `site/` | Astro 静态站 |
| `.github/workflows/` | `daily.yml` 每日日报，`fast.yml` 快速检查，`pages.yml` 构建并部署网站 |

## 自动运行

- `daily.yml`：每天纽约时间 08:00 生成日报，提交回 `main`，然后部署网站。GitHub 的 cron 只认 UTC，所以在 12:00 和 13:00 UTC 各触发一次，由脚本判断只让纽约时间 08:00 之后、当天还没有日报的那一次真正运行。可以在 Actions 页面手动运行（workflow_dispatch），手动运行不受这个限制。
- `fast.yml`：纽约时间约 9:00–23:00 每 2 小时检查一次官方博客（`sources.json` 里 `"fast": true` 的来源）。有新文章才提交和重新部署。
- 重点（`news/data/highlights/`）：主路径是 Joe 每天约 08:20（纽约时间）在本机读当天数据，写好文件（`"by": "joe"`）推到 `main`，推送会触发 `pages.yml` 重新部署。`daily.yml` 在 `collect.py` 之后运行 `news/highlight.py` 先放一个兜底版本：配置了仓库 secret `ANTHROPIC_API_KEY` 就用 Claude（`claude-sonnet-5-5`）生成，否则按规则挑（`"by": "rules"`，没有汇报正文）。它不会覆盖 `"by": "joe"` 的文件，提交前也会检查 Joe 是否已经推了当天的文件。
- 两个工作流共用一个 `concurrency` 组，不会同时提交。提交者是 `github-actions[bot]`。
- 网站由 GitHub Actions 部署（仓库 Settings → Pages → Source 为 GitHub Actions）。

## 本地运行

```sh
TZ=America/New_York uv run --no-project news/collect.py          # 日报
TZ=America/New_York uv run --no-project news/collect.py --fast   # 快速检查
TZ=America/New_York uv run --script news/highlight.py            # 兜底重点（不覆盖 Joe 的文件）

cd site && npm install && npm run dev                              # 本地预览网站
```

同一天再次运行会合并到当天的日报：之前收录的新文章保留，榜单换成最新的；某个榜单这次抓取失败时保留之前的结果，并在「来源状态」里注明。

## 重点文件格式（`news/data/highlights/YYYY-MM-DD.json`）

```json
{
  "date": "2026-11-22",
  "generated": "2026-11-22T08:20:00-05:00",
  "by": "joe",
  "summary": "今天最大的事是 **Anthropic 正式上市**：[S-1 招股书](https://www.anthropic.com/news/s1-sec)……\n\n第二段……",
  "items": [
    {
      "title_zh": "Thinking Machines 发布 Inkling-2-Mini",
      "title": "thinkingmachines/Inkling-2-Mini",
      "url": "https://huggingface.co/thinkingmachines/Inkling-2-Mini",
      "why": "HF 热门模型第 1，HN 有人在 5.4GB 内存里跑起来，本地可跑的多模态小模型。",
      "tag": "开源",
      "sources": [
        {"source": "hf-models", "name": "Hugging Face 热门模型", "url": "https://huggingface.co/thinkingmachines/Inkling-2-Mini",
         "title": "thinkingmachines/Inkling-2-Mini", "rank": 1, "score": 3326, "score_kind": "likes"},
        {"source": "hn", "name": "Hacker News 24 小时最高分", "url": "https://github.com/ShinMegamiBoson/lookatmyquant",
         "title": "Inkling-2-Mini in 5.4 GB Memory", "rank": 4, "score": 441, "score_kind": "score"}
      ]
    }
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `date` | 和文件名相同的日期 |
| `generated` | 生成时间，ISO 8601 带时区；首页显示为「由 Joe 生成 · HH:MM」 |
| `by` | `"joe"`（本机手写或本机生成）、`"claude-api"`、`"rules"`。`"joe"` 的文件不会被自动流程覆盖 |
| `summary` | 今日汇报，Markdown 字符串：3–5 段、约 300–500 字中文，讲今天最重要的事、趋势、和主人方向的关联。段落之间空一行；支持 `[文字](url)`、`**粗体**`、`*斜体*`、`` `代码` ``、以 `- ` 开头的列表。不要写标题。可以为空字符串，这时首页只显示条目 |
| `items` | 5–7 条，按重要程度排序，显示在汇报下方的「提到的条目」 |
| `items[].title_zh` | 中文标题（英文原题给出中文译名或概括） |
| `items[].title` | 主出处的原标题 |
| `items[].url` | 主出处链接，等于 `sources[0].url` |
| `items[].why` | 一句中文：为什么值得看 |
| `items[].tag` | `官方`、`开源`、`论文`、`社区`、`产品` 之一 |
| `items[].sources` | 这件事出现过的所有地方，最主要的在前；同一件事跨来源合并成一条 |
| `sources[].source` / `name` | 来源 id 和名称，取自当天 `news/data/YYYY-MM-DD.json` 的分组 |
| `sources[].url` / `title` | 该条在当天数据里的 `url` 和 `title` |
| `sources[].rank` | 可选，榜单排名（在该榜单 `items` 里的位置，从 1 开始） |
| `sources[].score` / `score_kind` | 可选，数值和含义：`score`（HN 分）、`stars`（GitHub 今日 star）、`likes`（Hugging Face 赞） |

约束：

- **所有 url（`items[].url`、`sources[].url`、`summary` 里的链接）都必须来自当天的 `news/data/YYYY-MM-DD.json`**，不要编造或改写链接。
- 文件是 UTF-8 JSON。写完用 `TZ=America/New_York uv run --script news/highlight.py YYYY-MM-DD --check` 检查字段和链接，再用 `cd site && npm run build` 看页面。
- 推送前先 `git pull --rebase`：08:00 的 Actions 可能已经提交了当天的兜底版本，直接覆盖它即可。

## linux.do 被拦时的处理

linux.do 在 Cloudflare 后面，有时会对 GitHub Actions 的 IP 返回 403。这时日报照常生成，「来源状态」里会写明 LINUX DO 抓取失败，工作流不会失败。

要补上这一项，在自己的 Mac 上运行：

```sh
git pull
TZ=America/New_York uv run --no-project news/collect.py --only linuxdo
git add news && git commit -m "linux.do from Mac" && git push
```

`--only` 只抓指定来源，当天日报的其余内容保持不变。推送后在 Actions 页面手动运行 `pages` 工作流，网站就会更新。如果 linux.do 长期被拦，可以在 Mac 上用 launchd 或 cron 每天 8:10 跑上面几行。
