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
| `news/state.json` | 已见过的文章、榜单连续天数 |
| `site/` | Astro 静态站 |
| `.github/workflows/` | `daily.yml` 每日日报，`fast.yml` 快速检查，`pages.yml` 构建并部署网站 |

## 自动运行

- `daily.yml`：每天纽约时间 08:00 生成日报，提交回 `main`，然后部署网站。GitHub 的 cron 只认 UTC，所以在 12:00 和 13:00 UTC 各触发一次，由脚本判断只让纽约时间 08:00 之后、当天还没有日报的那一次真正运行。可以在 Actions 页面手动运行（workflow_dispatch），手动运行不受这个限制。
- `fast.yml`：纽约时间约 9:00–23:00 每 2 小时检查一次官方博客（`sources.json` 里 `"fast": true` 的来源）。有新文章才提交和重新部署。
- 两个工作流共用一个 `concurrency` 组，不会同时提交。提交者是 `github-actions[bot]`。
- 网站由 GitHub Actions 部署（仓库 Settings → Pages → Source 为 GitHub Actions）。

## 本地运行

```sh
TZ=America/New_York uv run --no-project news/collect.py          # 日报
TZ=America/New_York uv run --no-project news/collect.py --fast   # 快速检查

cd site && npm install && npm run dev                              # 本地预览网站
```

同一天再次运行会合并到当天的日报：之前收录的新文章保留，榜单换成最新的；某个榜单这次抓取失败时保留之前的结果，并在「来源状态」里注明。

## linux.do 被拦时的处理

linux.do 在 Cloudflare 后面，有时会对 GitHub Actions 的 IP 返回 403。这时日报照常生成，「来源状态」里会写明 LINUX DO 抓取失败，工作流不会失败。

要补上这一项，在自己的 Mac 上运行：

```sh
git pull
TZ=America/New_York uv run --no-project news/collect.py --only linuxdo
git add news && git commit -m "linux.do from Mac" && git push
```

`--only` 只抓指定来源，当天日报的其余内容保持不变。推送后在 Actions 页面手动运行 `pages` 工作流，网站就会更新。如果 linux.do 长期被拦，可以在 Mac 上用 launchd 或 cron 每天 8:10 跑上面几行。
