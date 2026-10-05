# CupSir Dashboard: User Guide

## 1. What you need

- A GitHub account and this repository.
- A free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
- A NewsAPI key for the news panel: https://newsapi.org

## 2. One-time setup

1. **Secrets.** In the repository open **Settings -> Secrets and variables -> Actions** and add two repository secrets, named exactly `FRED_API_KEY` and `NEWS_API_KEY`. Never put a key in a file or a commit.
2. **Pages.** Open **Settings -> Pages** and set **Source** to **GitHub Actions**.
3. **First run.** Open **Actions -> Update CupSir dashboard data -> Run workflow**. When it finishes, **Deploy CupSir dashboard** starts by itself and publishes the page.

The page address is shown in the deploy run and in the Pages settings. It normally looks like `https://YOUR-GITHUB-USER.github.io/cupsir-dashboard/`.

## 3. How the data refresh works

`update-data.yml` is scheduled for 20:00 UTC, Monday to Friday. GitHub often starts scheduled jobs late, sometimes by several hours. You can also start it by hand from the Actions tab.

Each run:

1. Builds the 14-day economic calendar (`data/events.json`).
2. Fetches news (`data/news.json`).
3. Builds the market breadth, sector and COT data (`data/market_breadth.json`, `data/sectors.json`, `data/cot.json`).
4. Builds the 13 indicators and the overall signal (`data/dashboard.json`), then the summary (`data/summary.json`). The five COT indicators are read from `data/cot.json`, so they always match the COT tab.
5. Commits `data/` and pushes. The deploy workflow then publishes the page.

Two runs on the same branch never overlap; a second one waits for the first.

### Checking a run

A green tick is not enough. Three parts of a run keep the previous data and carry on when something fails, so the run still shows as successful:

| Part | What happens on failure |
|---|---|
| News | The previous `news.json` is kept |
| The 13 indicators | A source that fails shows as unavailable. If every source fails, the previous `dashboard.json` is kept |
| Breadth, sector and COT step | Marked `continue-on-error`; the previous files are kept, and the five left-hand COT indicators keep showing the last report |

So open the run page and look at:

- **Annotations** at the bottom of the run summary. Problems are reported there as warnings.
- **The data dates** on the page itself, and `最後更新` in the header.

## 4. Yearly upkeep: the economic calendar

The calendar uses published release dates, held per year in `scripts/fetch_events.py`:

| Table | Holds | Source |
|---|---|---|
| `FOMC_DATES` | FOMC decision days | federalreserve.gov, FOMC calendars |
| `NFP_DAYS` | Employment Situation release days | bls.gov release schedule |
| `MONTHLY_RELEASES[...]["days"]` | CPI, PPI, core PCE, retail sales, durable goods, housing starts, new and existing home sales, trade balance, ISM manufacturing and services | OMB schedule of principal economic indicators, Census, ISM, NAR (links are in the file) |

When the agencies publish next year's schedules, usually in the last quarter, add that year to each table.

A year with no table is never guessed. Its events are left out of the calendar and the run reports one warning naming the missing tables. If the calendar looks thin around the turn of the year, this is why.

FOMC minutes (meeting day plus 21 days) and the QRA estimate (first Wednesday of February, May, August and November) are computed and need no upkeep.

## 5. Customising

### The 13 left-hand indicators

Edit `scripts/config.py`: names, FRED series, Yahoo tickers, checklist wording. Signal thresholds are in `signal()` and `cot_signal()` in `scripts/build_dashboard.py`.

An indicator's `chart` entry lists the levels drawn as dashed lines on its chart. They must be the same numbers as the thresholds in `signal()`; a test fails if they drift apart, so change both together.

A market indicator's `bar_rule` says which daily price is safe to show. VIX uses the day's close once the US session has ended. Copper, oil and the dollar index trade almost round the clock and their price for the current day keeps changing for hours after the close, so they always show the last completed day: one trading day behind VIX, but final.

A COT indicator's `scored: False` keeps it on the page but out of the overall score. Only the S&P 500 COT is scored.

A COT indicator has no CFTC settings of its own. Its `cot_id` names a market in `config/universe.json`, and it shows that market's one-year row of `data/cot.json`. If the market or its result is missing the indicator shows N/A and the run warns.

### Breadth, sector and COT tabs

These are driven by two files and need no code change for routine edits:

- `config/universe.json`: what is covered. Index ETFs, the 11 sectors with their ETFs, and the 16 COT markets with their CFTC contract codes. Adding a COT market is one new entry here.
- `config/indicators.json`: the indicators, their parameters and thresholds, column labels and the "Expert's view" wording.

A new kind of calculation needs a function in `scripts/pipeline/calc/` plus its entry in `config/indicators.json`.

Both tabs open as a list with charts beside it. What each list row shows is set by an optional `list` entry on an indicator's scope (`order`, `value_key`, `format`); add or remove one to change the row. The button labels are `view_list` and `view_table` in `ui_labels`.

`python scripts/run_pipeline.py --dry-run` checks the configuration and runs everything without writing files.

## 6. Running locally

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run offline on fixture files. To preview the page, build it the way the deploy workflow does:

```bash
mkdir -p _site/data && cp -R web/. _site/ && cp -R data/. _site/data/
python -m http.server --directory _site 8000
```

Then open http://localhost:8000. The page loads its data from `data/...` next to `index.html`, so opening `web/index.html` directly shows nothing.

To rebuild the data locally, set the two keys as environment variables and run the scripts in the order shown in section 3.

## 7. Troubleshooting

**The four macro indicators show UNAVAILABLE.** Check that the `FRED_API_KEY` secret exists, is spelled exactly so, and that the key is active.

**Market indicators show UNAVAILABLE.** Yahoo Finance sometimes fails or renames a symbol. Re-run the workflow; if it persists, check the ticker in `scripts/config.py`.

**A COT indicator shows N/A or PENDING.** Read the run's annotations. Either `data/cot.json` is missing, or it has no one-year result for that market (section 5).

**A tab says the data could not be loaded.** Its JSON file is missing or the breadth step failed. Read the annotations and re-run the workflow.

**The page did not change after a run.** Check that **Deploy CupSir dashboard** ran after it and succeeded. It can be started by hand.

**The scheduled run did not happen.** Scheduled workflows run only on the default branch and GitHub can delay or skip them under load. Start one by hand.

**The news panel is empty or old.** Check `NEWS_API_KEY`. NewsAPI's free tier is rate-limited and only serves recent articles.

## 8. Safety note

This dashboard is for education and market research. It gives no financial advice, trading instructions or execution signals. Economic releases get revised and market data can be late.
