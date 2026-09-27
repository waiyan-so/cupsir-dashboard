INDICATOR_GROUPS = [
    {"id": "macro_labour", "name": "宏觀與就業 Macro & Labour"},
    {"id": "liquidity_credit", "name": "流動性與信用 Liquidity & Credit"},
    {"id": "market_temperature", "name": "市場溫度 Market Temperature"},
    {"id": "events", "name": "經濟日曆 Economic Calendar"},
    {"id": "positioning", "name": "機構持倉 Positioning / COT"}
]

INDICATORS = {
    "nfp": {
        "name": "Nonfarm Payroll Employment", "name_zh": "非農就業 NFP", "category": "macro_labour", "source": "bls", "series_id": "CES0000000001", "unit": "thousand jobs",
        "checklist": ["比較最新月度變化與前兩個月修正", "比較實際值與市場預期（需另行接入共識資料）", "觀察公布後 SPY、TLT、DXY 的即時反應"],
        "source_url": "https://www.bls.gov/news.release/empsit.toc.htm"
    },
    "jolts": {
        "name": "JOLTS Job Openings", "name_zh": "JOLTS 職位空缺", "category": "macro_labour", "source": "bls", "series_id": "JTS000000000000000JOL", "unit": "thousand openings",
        "checklist": ["查看職位空缺趨勢", "比較職位空缺與失業人數的 V/U Ratio", "同時觀察 Quits、Layoffs 與 Hires"],
        "source_url": "https://www.bls.gov/jlt/"
    },
    "sahm_rule": {
        "name": "Sahm Rule Recession Indicator", "name_zh": "薩姆規則 Sahm Rule", "category": "macro_labour", "source": "fred", "series_id": "SAHMREALTIME", "unit": "%",
        "checklist": ["是否接近或突破 0.5 衰退閾值", "是否連續上升", "與 NFP、失業率、JOLTS 是否一致"],
        "source_url": "https://fred.stlouisfed.org/series/SAHMREALTIME"
    },
    "gdpnow": {
        "name": "Atlanta Fed GDPNow", "name_zh": "GDP / GDPNow", "category": "macro_labour", "source": "manual", "unit": "% annualised",
        "checklist": ["稍後接入 Atlanta Fed GDPNow 來源", "比較官方 GDP 初值、二次修正與終值", "確認是否進入連續負增長"],
        "source_url": "https://www.atlantafed.org/cqer/research/gdpnow"
    },
    "richmond_sos": {
        "name": "Richmond Fed Manufacturing / SOS", "name_zh": "里奇蒙聯儲製造業 + SOS", "category": "macro_labour", "source": "manual", "unit": "index",
        "checklist": ["製造業指數是否低於 0", "SOS 是否接近 0.042 閾值", "與失業申請和 Sahm Rule 交叉確認"],
        "source_url": "https://www.richmondfed.org/research/regional_economy/surveys_of_business_conditions/manufacturing"
    },
    "yield_curve": {
        "name": "10Y-2Y Treasury Spread", "name_zh": "孳息曲線 T10Y2Y", "category": "liquidity_credit", "source": "fred", "series_id": "T10Y2Y", "unit": "%",
        "checklist": ["是否深度倒掛（低於 -0.5）", "是否處於倒掛後恢復的 Bear Steepening 期", "比較長端與短端孳息的變動原因"],
        "source_url": "https://fred.stlouisfed.org/series/T10Y2Y"
    },
    "hy_spread": {
        "name": "High Yield Credit Spread", "name_zh": "高收益信用差 HY Spread", "category": "liquidity_credit", "source": "fred", "series_id": "BAMLH0A0HYM2", "unit": "%",
        "checklist": ["是否突破 3.5% 或 5%", "是否快速擴大", "與 VIX、股市和長債是否互相確認"],
        "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
    },
    "on_rrp": {
        "name": "Overnight Reverse Repo", "name_zh": "MMF / ON RRP", "category": "liquidity_credit", "source": "fred", "series_id": "RRPONTSYD", "unit": "USD bn",
        "checklist": ["是否高於 500B、200B、50B 流動性區間", "觀察 ON RRP 的下跌速度", "配合 Treasury Bills 發行和 QRA 解讀"],
        "source_url": "https://fred.stlouisfed.org/series/RRPONTSYD"
    },
    "qra": {
        "name": "Quarterly Refunding Announcement", "name_zh": "季度再融資公告 QRA", "category": "liquidity_credit", "source": "manual", "unit": "",
        "checklist": ["比較 Bills 與 Coupons 的發行比例", "比較本季與上季的發債結構", "關注週一總額與週三細節"],
        "source_url": "https://home.treasury.gov/policy-issues/financing-the-government/quarterly-refunding"
    },
    "copper": {
        "name": "Copper Futures", "name_zh": "銅價 Copper", "category": "market_temperature", "source": "market", "ticker": "HG=F", "unit": "USD/lb",
        "checklist": ["距三個月低位反彈是否超過 10%", "是否形成底部後反彈", "是否與製造業及全球增長訊號一致"],
        "source_url": "https://finance.yahoo.com/quote/HG=F"
    },
    "oil": {
        "name": "WTI Crude Oil", "name_zh": "油價 WTI", "category": "market_temperature", "source": "market", "ticker": "CL=F", "unit": "USD/bbl",
        "checklist": ["距六個月高位的跌幅", "是否仍在高位", "是否與通脹、週期與風險資產走勢一致"],
        "source_url": "https://finance.yahoo.com/quote/CL=F"
    },
    "dxy": {
        "name": "US Dollar Index", "name_zh": "美元指數 DXY", "category": "market_temperature", "source": "market", "ticker": "DX-Y.NYB", "unit": "index",
        "checklist": ["比較一個月升跌幅", "美元急升是否形成風險資產逆風", "與美債孳息、信用差和股市比較"],
        "source_url": "https://finance.yahoo.com/quote/DX-Y.NYB"
    },
    "vix": {
        "name": "CBOE Volatility Index", "name_zh": "VIX 波動率", "category": "market_temperature", "source": "market", "ticker": "^VIX", "unit": "index",
        "checklist": ["是否在 20 至 30 的危險區間", "是否超過 30 或 45", "高位恐慌後是否開始回落"],
        "source_url": "https://www.cboe.com/tradable_products/vix/"
    },
    "economic_calendar": {
        "name": "Economic Calendar", "name_zh": "經濟日曆", "category": "events", "source": "calendar", "unit": "",
        "checklist": ["查看未來兩周三星事件", "識別 FOMC、QRA、NFP 是否同周", "重要發布後觀察市場即時反應"],
        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    },
    "cot": {
        "name": "Commitments of Traders", "name_zh": "COT 持倉報告", "category": "positioning", "source": "manual", "unit": "index",
        "checklist": ["計算 Commercials 的 52 周 COT Index", "計算 Small Speculators Sentiment Index", "留意極端多空與擁擠交易"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders"
    }
}
