"""
Download annual financial data for a list of software companies from SEC EDGAR
and save it as a tidy CSV (one row per company per fiscal year).

Data source: the free SEC "companyfacts" API, which contains every number
companies report in their official filings (10-K annual reports).
"""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# Companies to analyse: large US-listed software firms that file 10-K reports.
TICKERS = ["MSFT", "ORCL", "ADBE", "CRM", "NOW", "INTU", "WDAY", "SNOW"]

# Companies sometimes report the same figure under different names ("tags"),
# and some changed tag over the years. Tags are tried in order; earlier tags win.
METRIC_TAGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
    ],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment"],
}

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUTPUT_CSV = ROOT / "data" / "financials.csv"


def get_session():
    """The SEC asks every script to identify itself with a name and email."""
    user_agent = os.environ.get("SEC_USER_AGENT")
    if not user_agent:
        sys.exit(
            "Please set SEC_USER_AGENT first, for example:\n"
            '  PowerShell:  $env:SEC_USER_AGENT = "Your Name your.email@example.com"\n'
            '  bash:        export SEC_USER_AGENT="Your Name your.email@example.com"'
        )
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    return session


def get_json(session, url, cache_file):
    """Download a JSON file, or reuse a saved copy so we don't re-download."""
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    response = session.get(url, timeout=30)
    response.raise_for_status()
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(response.text)
    time.sleep(0.2)  # stay well under the SEC limit of 10 requests per second
    return response.json()


def ticker_to_cik(session):
    """Map tickers (e.g. MSFT) to the SEC's company ID number (CIK)."""
    data = get_json(
        session,
        "https://www.sec.gov/files/company_tickers.json",
        RAW_DIR / "company_tickers.json",
    )
    return {row["ticker"]: (row["cik_str"], row["title"]) for row in data.values()}


def annual_values(facts, tags):
    """
    Return {fiscal year end date: value} for full-year figures from 10-K reports.

    Each 10-K repeats figures for earlier years too, so the same year appears
    several times. We keep the most recently filed number, which includes any
    corrections the company made later.
    """
    us_gaap = facts["facts"].get("us-gaap", {})
    result = {}
    for tag in tags:
        if tag not in us_gaap:
            continue
        best = {}  # end date -> (filed date, value)
        for entry in us_gaap[tag]["units"].get("USD", []):
            if entry.get("form") not in ("10-K", "10-K/A") or "start" not in entry:
                continue
            days = (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days
            if not 350 <= days <= 380:  # skip quarterly figures
                continue
            end = entry["end"]
            if end not in best or entry["filed"] > best[end][0]:
                best[end] = (entry["filed"], entry["val"])
        for end, (_, value) in best.items():
            result.setdefault(end, value)  # earlier tags take priority
    return result


def main():
    session = get_session()
    ciks = ticker_to_cik(session)

    rows = []
    for ticker in TICKERS:
        cik, name = ciks[ticker]
        print(f"Fetching {ticker} ({name})...")
        facts = get_json(
            session,
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            RAW_DIR / f"{ticker}.json",
        )
        metrics = {metric: annual_values(facts, tags) for metric, tags in METRIC_TAGS.items()}
        for end in sorted(metrics["revenue"]):
            row = {"ticker": ticker, "company": name, "fiscal_year_end": end}
            for metric, values in metrics.items():
                row[metric] = values.get(end)
            rows.append(row)

    df = pd.DataFrame(rows)
    df["fiscal_year"] = pd.to_datetime(df["fiscal_year_end"]).dt.year
    # Some companies don't report gross profit directly, so work it out.
    missing = df["gross_profit"].isna()
    df.loc[missing, "gross_profit"] = df["revenue"] - df["cost_of_revenue"]

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(df)} rows to {OUTPUT_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
