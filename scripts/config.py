INDICATORS = {
    "sahm_rule": {
        "name": "Sahm Rule", "name_zh": "薩姆規則", "source": "fred", "series_id": "SAHMREALTIME", "unit": "%",
        "checklist": ["是否接近 0.5 衰退閾值", "是否連續上升", "與 NFP 和 JOLTS 是否一致"],
        "source_url": "https://fred.stlouisfed.org/series/SAHMREALTIME"
    },
    "yield_curve": {
        "name": "10Y-2Y Treasury Spread", "name_zh": "十年減兩年孳息差", "source": "fred", "series_id": "T10Y2Y", "unit": "%",
        "checklist": ["是否倒掛", "是否處於倒掛後正常化階段", "確認是 Bull 還是 Bear Steepening"],
        "source_url": "https://fred.stlouisfed.org/series/T10Y2Y"
    },
    "hy_spread": {
        "name": "High Yield Credit Spread", "name_zh": "高收益信用差", "source": "fred", "series_id": "BAMLH0A0HYM2", "unit": "%",
        "checklist": ["是否突破 3.5%", "是否快速擴大", "與 VIX 及股市方向是否一致"],
        "source_url": "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"
    },
    "vix": {
        "name": "CBOE Volatility Index", "name_zh": "VIX 波動率指數", "source": "market", "ticker": "^VIX", "unit": "",
        "checklist": ["是否在 20 至 30 的不明朗區間", "是否超過 30 或 45", "恐慌後是否開始回落"],
        "source_url": "https://www.cboe.com/tradable_products/vix/"
    },
    "dxy": {
        "name": "US Dollar Index", "name_zh": "美元指數 DXY", "source": "market", "ticker": "DX-Y.NYB", "unit": "",
        "checklist": ["檢查一個月升跌幅", "美元急升是否壓制風險資產", "與美債孳息及股市比較"],
        "source_url": "https://finance.yahoo.com/quote/DX-Y.NYB"
    },
    "copper": {
        "name": "Copper Futures", "name_zh": "銅價", "source": "market", "ticker": "HG=F", "unit": "USD",
        "checklist": ["距三個月低位的反彈幅度", "是否形成底部", "是否與製造業數據確認"],
        "source_url": "https://finance.yahoo.com/quote/HG=F"
    },
    "oil": {
        "name": "WTI Crude Oil", "name_zh": "WTI 原油", "source": "market", "ticker": "CL=F", "unit": "USD",
        "checklist": ["距六個月高位的跌幅", "油價是否仍處於高位", "與通脹和週期判斷是否一致"],
        "source_url": "https://finance.yahoo.com/quote/CL=F"
    },
    "cot_sp500": {
        "name": "S&P 500 COT", "name_zh": "S&P 500 COT 持倉", "source": "manual", "unit": "index",
        "checklist": ["商業持倉者 COT Index", "小型投機者 Sentiment Index", "確認是否出現極端擠擁"],
        "source_url": "https://www.cftc.gov/MarketReports/CommitmentsofTraders"
    }
}
