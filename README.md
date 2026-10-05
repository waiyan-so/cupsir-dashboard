# CupSir Macro Dashboard

A static market-research dashboard. GitHub Actions refreshes the data every weekday and GitHub Pages serves the page. Nothing runs on your own computer.

The page is in Traditional Chinese.

## What the page shows

| Area | Content | Data file |
|---|---|---|
| Economic calendar | Events in the next 14 days: NFP, FOMC, FOMC minutes, QRA and eleven monthly releases | `data/events.json` |
| News | Macro and market headlines from NewsAPI | `data/news.json` |
| Tab 整體市場 | Status cards for market breadth (trend regime, distribution days, equal-weight ratio, follow-through day, for SPY and QQQ), then 13 indicators in three groups: macro (4), market temperature (4), COT positioning (5). The 13 feed the overall signal and score in the header | `data/market_breadth.json`, `data/dashboard.json` |
| Tab 板塊 | 11 sectors by 5 indicators: relative strength, trend regime, distribution days, equal-weight ratio, realized volatility | `data/sectors.json` |
| Tab COT 持倉 | 16 futures markets by 3 lookbacks (6 months, 1 year, 3 years): COT Index and Sentiment Index from the CFTC Legacy report | `data/cot.json` |
| Research summary | Rule-based text built from the 13 indicators | `data/summary.json` |

The breadth, sector and COT tabs do not feed the overall score.

## How it works

```text
.github/workflows/update-data.yml   weekdays 20:00 UTC (often runs later), or by hand
  scripts/fetch_events.py      -> data/events.json
  scripts/fetch_news.py        -> data/news.json          (keeps the old file on failure)
  scripts/run_pipeline.py      -> data/market_breadth.json, data/sectors.json, data/cot.json
  scripts/build_dashboard.py   -> data/dashboard.json     (FRED, Yahoo Finance, and data/cot.json for the five COT indicators; keeps the old file if every source fails)
  scripts/generate_summary.py  -> data/summary.json
  commit data/ and push

.github/workflows/deploy-pages.yml  on push to main, after a data refresh, or by hand
  copies web/ and data/ into one site and publishes it
```

## Repository layout

| Path | What is in it |
|---|---|
| `web/` | The page: `index.html`, `app.js` (calendar, news, 13 indicators, summary), `breadth.js` (status cards, sector and COT tabs), `styles.css` |
| `scripts/config.py` | The 13 left-hand indicators: names, sources, checklists |
| `scripts/build_dashboard.py`, `fetch_events.py`, `fetch_news.py`, `generate_summary.py` | The original data scripts |
| `config/indicators.json`, `config/universe.json` | Registry for the breadth, sector and COT tabs: indicators, parameters, wording, tickers and CFTC contract codes |
| `scripts/run_pipeline.py`, `scripts/pipeline/` | The newer pipeline in layers: `collect/` (download), `calc/` (pure calculations), `sectors/` (cross-sector work), and `run_pipeline.py`, the only code that writes its output |
| `data/` | Generated JSON, committed by the workflow |
| `tests/` | `pytest` suite; runs offline |

## Secrets

Set under **Settings -> Secrets and variables -> Actions**:

| Secret | Used for |
|---|---|
| `FRED_API_KEY` | The four macro indicators |
| `NEWS_API_KEY` | The news panel (NewsAPI.org) |

Yahoo Finance and the CFTC need no key.

## Run it yourself

```bash
pip install -r requirements-dev.txt
pytest                                   # offline, about half a minute

# preview the page the way the deploy workflow builds it
mkdir -p _site/data && cp -R web/. _site/ && cp -R data/. _site/data/
python -m http.server --directory _site 8000
```

See **USER_GUIDE.md** for setup, daily checks, customisation and yearly upkeep.

## Important

This is a research and education tool, not trading software or financial advice. Data can be late, revised or unavailable. Verify before relying on it.
