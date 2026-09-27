import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "bls.json"
API_KEY = os.getenv("BLS_API_KEY", "")
SERIES = {
    "nfp": "CES0000000001",
    "unemployment_rate": "LNS14000000",
    "jolts_openings": "JTS000000000000000JOL",
    "jolts_quits_rate": "JTS000000000000000QUR",
    "jolts_layoffs_rate": "JTS000000000000000LDR",
    "jolts_hires_rate": "JTS000000000000000HIR"
}

def main():
    year = datetime.now(timezone.utc).year
    payload = {"seriesid": list(SERIES.values()), "startyear": str(year - 2), "endyear": str(year)}
    if API_KEY:
        payload["registrationkey"] = API_KEY
    r = requests.post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=payload, timeout=45)
    r.raise_for_status()
    raw = r.json()
    if raw.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(raw.get("message", raw))
    reverse = {v: k for k, v in SERIES.items()}
    result = {"updated_at": datetime.now(timezone.utc).isoformat(), "series": {}}
    for s in raw.get("Results", {}).get("series", []):
        key = reverse.get(s.get("seriesID"), s.get("seriesID"))
        rows = []
        for x in s.get("data", []):
            if not x.get("period", "").startswith("M"):
                continue
            rows.append({"date": f"{x['year']}-{x['period'][1:]}-01", "value": float(x['value'])})
        result["series"][key] = list(reversed(rows))
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
