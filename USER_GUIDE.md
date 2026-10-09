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
3. Builds the market breadth, sector, COT, ratio-pair and ASX sector data (`data/market_breadth.json`, `data/sectors.json`, `data/cot.json`, `data/pairs.json`, `data/asx_sectors.json`, `data/asx_pairs.json`).
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

An indicator's `chart` entry lists the levels drawn as dashed lines on its chart. They must be the same numbers as the thresholds in `signal()`; a test fails if they drift apart, so change both together. An optional `points` in the same entry makes the chart draw only that many of the latest values (GDPNow draws its last 12 quarters, so that 2020 does not flatten the line); the data file still keeps 30 values for every indicator.

A market indicator's `bar_rule` says which daily price is safe to show. VIX uses the day's close once the US session has ended. Copper, oil and the dollar index trade almost round the clock and their price for the current day keeps changing for hours after the close, so they always show the last completed day: one trading day behind VIX, but final.

A COT indicator's `scored: False` keeps it on the page but out of the overall score. Only the S&P 500 COT is scored.

A COT indicator has no CFTC settings of its own. Its `cot_id` names a market in `config/universe.json`, and it shows that market's one-year row of `data/cot.json`. If the market or its result is missing the indicator shows N/A and the run warns.

### Breadth, sector and COT tabs

These are driven by two files and need no code change for routine edits:

- `config/universe.json`: what is covered. Index ETFs, the 11 sectors with their ETFs, and the 16 COT markets with their CFTC contract codes. Adding a COT market is one new entry here.
- `config/indicators.json`: the indicators, their parameters and thresholds, column labels and the "Expert's view" wording.

A new kind of calculation needs a function in `scripts/pipeline/calc/` plus its entry in `config/indicators.json`.

Both tabs open as a list with charts beside it. What each list row shows is set by an optional `list` entry on an indicator's scope (`order`, `value_key`, `format`); add or remove one to change the row. The button labels are `view_list` and `view_table` in `ui_labels`. The page remembers the view last chosen on each tab in the browser (local storage), so a reload opens the same one; clearing the site's data brings back the list.

### Ratio pairs (under the sectors)

The 板塊 tab ends with a panel of relative strength ratios such as XLY / XLP, in three groups. Each pair is one entry in the `pairs` block of `config/universe.json`:

- `roles.subject` is the numerator and `roles.benchmark` the denominator (any Yahoo Finance ticker, including futures such as `HG=F` and indices such as `^VIX`).
- `group` is one of the keys of `pairs.groups`; `tag` (optional) is a short label beside the name; `levels` (optional) draws fixed lines on that pair's chart.
- `guide` is the reading guide shown under the chart: `compare`, a sentence for each state in `pairs.state_conditions`, `signals` (other situations, each a `condition` and its `meaning`) and an optional `caveat`.

Adding, removing or reordering a pair is an edit to that block only. The two columns come from the `pair_trend` and `pair_change` indicators in `config/indicators.json`. The panel stays hidden until `data/pairs.json` exists, and none of it counts toward the overall score.

### ASX sectors (tab ASX 板塊)

The ASX 板塊 tab shows the 11 S&P/ASX 200 GICS sector indices with the same relative strength (against the S&P/ASX 200), trend regime, distribution day and realized volatility indicators as the US sectors. It has no equal-weight column: there are no ASX equal-weight sector indices. The list is the `asx_sector` block of `config/universe.json`; the indicators show there because they carry a `scopes.asx_sector` entry, and the table's default order is `asx_sector_table` in `config/indicators.json`.

Every ticker used by an ASX block needs an entry in `ticker_meta` (`universe.json`):

- `calendar`: which entry of `calendars` decides when a day's bar is final. `asx` takes a day's bar from 16:30 Sydney time; `us` from 16:30 New York time (the rule every ticker without an entry uses); `fx` never takes the current day's bar.
- `kind`: what the series is - `price_index` (no dividends), `adjusted` (adjusted for dividends), `futures` or `fx`. The page shows the matching `source_kind_*` label from `ui_labels`.
- `code` and `name` (optional): the ASX index code and full name, shown with the ticker.

Under the sectors, the tab lists 22 Australian ratio pairs: the `asx_pairs` block of `universe.json`, built like the `pairs` block. Two additions:

- `"single": true` with a `caption` marks a series that is a ratio already (AUD/JPY): it has `roles.subject` only, and its chart is the rate itself.
- `guide.us_compare` says how the pair differs from the US list (which US pair it replaces, or that it is new). The page shows it under the guide.

Both sides of a pair are of the same kind (two price indices, or two series adjusted for dividends), so dividends do not tilt the ratio.

The note at the top of the tab is `ui_labels.asx_source_note`; the note under the table, `asx_volume_note`, says that an ASX sector index's volume is the share volume of its constituents. The tab button stays hidden until `data/asx_sectors.json` or `data/asx_pairs.json` has rows, and nothing on it counts toward the overall score.

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
