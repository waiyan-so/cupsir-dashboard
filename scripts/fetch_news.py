"""
Pull macro/market news headlines from NewsAPI.org (https://newsapi.org).

Requires env var NEWS_API_KEY (already configured as a GitHub Actions
secret per the user). Writes data/news.json.

NOTE: NewsAPI's free/dev tier only serves articles from the last ~30 days
and can rate-limit; this script fails soft (keeps the previous news.json)
rather than breaking the whole pipeline if the call errors out.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

QUERY = (
    '"Federal Reserve" OR FOMC OR "interest rate" OR inflation OR '
    '"Treasury" OR "yield curve" OR "jobs report" OR recession'
)
DOMAINS = "cnbc.com,bloomberg.com,reuters.com,wsj.com,ft.com,marketwatch.com"


def fetch_news(page_size: int = 8) -> list:
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY is missing")
    r = requests.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": QUERY,
            "domains": DOMAINS,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "apiKey": NEWS_API_KEY,
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"NewsAPI error: {payload.get('message')}")

    items = []
    for a in payload.get("articles", []):
        items.append({
            "title": a.get("title", ""),
            "source": (a.get("source") or {}).get("name", ""),
            "url": a.get("url", ""),
            "published_at": a.get("publishedAt", ""),
            "summary": (a.get("description") or "")[:220],
        })
    return items


def main():
    try:
        items = fetch_news()
        if not items:
            raise RuntimeError("NewsAPI returned zero articles")
    except Exception as e:
        # Fail soft: keep whatever news.json already has so the site never
        # shows an empty panel just because one run hit a rate limit.
        print(f"[fetch_news] failed, keeping existing news.json: {e}")
        return
    (DATA / "news.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(items)} news items to data/news.json at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
