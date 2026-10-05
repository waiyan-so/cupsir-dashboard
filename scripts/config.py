"""
Indicator registry for the CupSir dashboard.

Each indicator dict:
  category     - "macro" | "market" | "cot"   (drives the left-panel grouping)
  source       - "fred" | "market" | "cot"
  series_id    - FRED series id (source == "fred")
  ticker       - Yahoo Finance ticker (source == "market")
  cot_id       - id of the market in config/universe.json's "cot" scope (source == "cot").
                 The indicator shows that market's row of data/cot.json, so it can never
                 differ from the COT tab. Contract codes live only in universe.json.
  embed        - {"type": "fred"|"tradingview", "target": <series_id or TradingView symbol>}
                 drives the live chart iframe/widget in the detail panel
  date_as      - "quarter" when the source dates each value by the first day of the
                 quarter it is for; the detail panel then shows the quarter, not that day
  summary_label - short market name used when the research summary lists the COT
                 markets (source == "cot")
"""

INDICATORS = {
    # ---- 一、宏觀環境 (macro) ----
    "sahm_rule": {
        "category": "macro", "name": "Sahm Rule", "name_zh": "薩姆規則",
        "source": "fred", "series_id": "SAHMREALTIME", "unit": "%",
        "checklist": ["是否接近 0.5 衰退閾值", "是否連續上升", "與 NFP 和 JOLTS 是否一致"],
        "source_url": "https://fred.stlouisfed.org/series/SAHMREALTIME",
        "embed": {"type": "fred", "target": "SAHMREALTIME"},
    },
    "yield_curve": {
        "category": "macro", "name": "10Y-2Y Treasury Spread", "name_zh": "十年減兩年孳息差",
        "source": "fred", "series_id": "T10Y2Y", "unit": "%",
        "checklist": ["是否倒掛", "是否處於倒掛後正常化階段", "確認是 Bull 還是 Bear Steepening"],
        "source_url": "https://fred.stlouisfed.org/series/T10Y2Y",
        "embed": {"type": "fred", "target": "T10Y2Y"},
    },
    "hy_spread": {
        "category": "macro", "name": "High Yield Credit Spread", "name_zh": "高收益信用差",
        "source": "fred", "series_id": "BAMLH0A0HYM2", "unit": "%",
        "checklist": ["是否突破 3.5%", "是否快速擴大", "與 VIX 及股市方向是否一致"],
        "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2",
        "embed": {"type": "fred", "target": "BAMLH0A0HYM2"},
    },
    "gdpnow": {
        "category": "macro", "name": "Atlanta Fed GDPNow", "name_zh": "GDPNow 實時預估",
        # GDPNow is mirrored on FRED under series id GDPNOW - no separate Excel scraper needed.
        # FRED dates each GDPNow value by the first day of the quarter being estimated,
        # so the raw date looks months old while the estimate itself is current.
        "source": "fred", "series_id": "GDPNOW", "unit": "%", "date_as": "quarter",
        "checklist": ["是否連續兩季為負（技術性衰退）", "與官方 GDP 方向是否一致", "增長率所處區間（強/中性/疲弱/收縮）"],
        "source_url": "https://www.atlantafed.org/cqer/research/gdpnow",
        "embed": {"type": "fred", "target": "GDPNOW"},
    },

    # ---- 二、市場溫度 (market) ----
    "vix": {
        "category": "market", "name": "CBOE Volatility Index", "name_zh": "VIX 波動率指數",
        "source": "market", "ticker": "^VIX", "unit": "",
        "checklist": ["是否在 20 至 30 的不明朗區間", "是否超過 30 或 45", "恐慌後是否開始回落"],
        "source_url": "https://www.cboe.com/tradable_products/vix/",
        "embed": {"type": "tradingview", "target": "TVC:VIX"},
    },
    "dxy": {
        "category": "market", "name": "US Dollar Index", "name_zh": "美元指數 DXY",
        "source": "market", "ticker": "DX-Y.NYB", "unit": "",
        "checklist": ["檢查一個月升跌幅", "美元急升是否壓制風險資產", "與美債孳息及股市比較"],
        "source_url": "https://finance.yahoo.com/quote/DX-Y.NYB",
        "embed": {"type": "tradingview", "target": "TVC:DXY"},
    },
    "copper": {
        "category": "market", "name": "Copper Futures", "name_zh": "銅價",
        "source": "market", "ticker": "HG=F", "unit": "USD",
        "checklist": ["距三個月低位的反彈幅度", "是否形成底部", "是否與製造業數據確認"],
        "source_url": "https://finance.yahoo.com/quote/HG=F",
        "embed": {"type": "tradingview", "target": "COMEX:HG1!"},
    },
    "oil": {
        "category": "market", "name": "WTI Crude Oil", "name_zh": "WTI 原油",
        "source": "market", "ticker": "CL=F", "unit": "USD",
        "checklist": ["距六個月高位的跌幅", "油價是否仍處於高位", "與通脹和週期判斷是否一致"],
        "source_url": "https://finance.yahoo.com/quote/CL=F",
        "embed": {"type": "tradingview", "target": "NYMEX:CL1!"},
    },

    # ---- 三、COT 聰明錢持倉 (cot) ----
    "cot_sp500": {
        "category": "cot", "name": "S&P 500 COT", "name_zh": "S&P 500 COT 持倉", "summary_label": "S&P 500",
        "source": "cot", "cot_id": "sp500", "unit": "index",
        "checklist": ["商業持倉者 COT Index 是否 ≥80 或 ≤20", "小型投機者 Sentiment Index 是否反向極端", "確認是否出現極端擠擁"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
        "embed": {"type": "tradingview", "target": "SP:SPX"},
    },
    "cot_10y": {
        "category": "cot", "name": "10Y Treasury COT", "name_zh": "10年期國債 COT", "summary_label": "10年債",
        "source": "cot", "cot_id": "ust10y", "unit": "index",
        "checklist": ["商業持倉者 COT Index 是否 ≥80 或 ≤20", "小型投機者 Sentiment Index 是否反向極端", "是否與孳息曲線走勢背馳"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
        "embed": {"type": "tradingview", "target": "CBOT:ZN1!"},
    },
    "cot_gold": {
        "category": "cot", "name": "Gold COT", "name_zh": "黃金 COT", "summary_label": "黃金",
        "source": "cot", "cot_id": "gold", "unit": "index",
        "checklist": ["商業持倉者 COT Index 是否 ≥80 或 ≤20", "小型投機者 Sentiment Index 是否反向極端", "是否與避險需求走勢一致"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
        "embed": {"type": "tradingview", "target": "COMEX:GC1!"},
    },
    "cot_oil": {
        "category": "cot", "name": "Oil COT", "name_zh": "原油 COT", "summary_label": "原油",
        # crude_oil is the NYMEX WTI contract (CL), the one the framework names and the
        # one the oil price indicator above tracks - not ICE Futures Europe's look-alike.
        "source": "cot", "cot_id": "crude_oil", "unit": "index",
        "checklist": ["商業持倉者 COT Index 是否 ≥80 或 ≤20", "小型投機者 Sentiment Index 是否反向極端", "是否與油價週期判斷一致"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
        "embed": {"type": "tradingview", "target": "NYMEX:CL1!"},
    },
    "cot_dxy": {
        "category": "cot", "name": "DXY COT", "name_zh": "美元指數 COT", "summary_label": "美元",
        "source": "cot", "cot_id": "usd_index", "unit": "index",
        "checklist": ["商業持倉者 COT Index 是否 ≥80 或 ≤20", "小型投機者 Sentiment Index 是否反向極端", "是否與風險資產走勢背馳"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders",
        "embed": {"type": "tradingview", "target": "TVC:DXY"},
    },
}

CATEGORY_LABELS = {
    "macro": "一、宏觀環境",
    "market": "二、市場溫度",
    "cot": "三、COT 聰明錢持倉",
}
CATEGORY_ORDER = ["macro", "market", "cot"]

# Where the left-hand COT indicators come from: the file the COT tab is drawn from
# (written by scripts/run_pipeline.py from the CFTC Legacy report) and which of its
# lookbacks they show. One source, so the list and the tab always agree.
COT_FILE = "cot.json"
COT_LOOKBACK = "cot_index_1y"

# The sentence under each indicator's value in the detail panel
# (dashboard.json "interpretation"). {signal} is the indicator's signal label;
# {error} is the reason a fetch failed, as reported by the source.
INTERPRETATION_TEXT = "CupSir 框架分類：{signal}。"
FETCH_FAILED_TEXT = "資料讀取失敗：{error}"

# How a "date_as": "quarter" indicator's data date is written (dashboard.json "data_date").
QUARTER_DATE_TEXT = "{year} 年第{quarter}季"
QUARTER_NAMES = ["一", "二", "三", "四"]
