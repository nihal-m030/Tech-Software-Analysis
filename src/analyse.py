"""
Turn the raw financials into the ratios analysts use for software companies,
then save a summary table and charts.

Run fetch_data.py first.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw charts to files without opening a window
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INPUT_CSV = ROOT / "data" / "financials.csv"
SUMMARY_CSV = ROOT / "data" / "summary.csv"
CHART_DIR = ROOT / "charts"
YEARS_TO_PLOT = 6


def add_ratios(df):
    """Add growth, margin and Rule of 40 columns (all in percent)."""
    df = df.sort_values(["ticker", "fiscal_year_end"]).copy()
    previous_revenue = df.groupby("ticker")["revenue"].shift(1)
    df["revenue_growth"] = (df["revenue"] / previous_revenue - 1) * 100
    df["gross_margin"] = df["gross_profit"] / df["revenue"] * 100
    df["operating_margin"] = df["operating_income"] / df["revenue"] * 100
    # Free cash flow: cash the business generates after paying for equipment.
    df["free_cash_flow"] = df["operating_cash_flow"] - df["capex"]
    df["fcf_margin"] = df["free_cash_flow"] / df["revenue"] * 100
    # Rule of 40: a healthy software company's growth + profit margin is 40%+.
    df["rule_of_40"] = df["revenue_growth"] + df["fcf_margin"]
    return df


def latest_year(df):
    """Each company's most recent fiscal year."""
    return df.sort_values("fiscal_year_end").groupby("ticker").tail(1).set_index("ticker")


def plot_revenue_growth(df):
    recent = df[df["fiscal_year"] > df["fiscal_year"].max() - YEARS_TO_PLOT]
    fig, ax = plt.subplots(figsize=(10, 6))
    for ticker, group in recent.groupby("ticker"):
        ax.plot(group["fiscal_year"], group["revenue_growth"], marker="o", label=ticker)
    ax.set_title("Annual revenue growth")
    ax.set_xlabel("Fiscal year")
    ax.set_ylabel("Growth vs previous year (%)")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.legend(ncol=4)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "revenue_growth.png", dpi=150)
    plt.close(fig)


def plot_margins(latest):
    data = latest.sort_values("operating_margin")
    fig, ax = plt.subplots(figsize=(10, 6))
    positions = range(len(data))
    ax.barh([p + 0.2 for p in positions], data["gross_margin"], height=0.4, label="Gross margin")
    ax.barh([p - 0.2 for p in positions], data["operating_margin"], height=0.4, label="Operating margin")
    ax.set_yticks(list(positions), data.index)
    # Some companies don't report gross profit in the SEC data.
    for position, value in zip(positions, data["gross_margin"]):
        if pd.isna(value):
            ax.text(1, position + 0.2, "gross margin n/a", va="center", fontsize=8, color="grey")
    ax.set_title("Margins, latest fiscal year")
    ax.set_xlabel("% of revenue")
    ax.axvline(0, color="grey", linewidth=0.8)
    ax.legend(loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "margins.png", dpi=150)
    plt.close(fig)


def plot_rule_of_40(latest):
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.scatter(latest["revenue_growth"], latest["fcf_margin"], s=80)
    for ticker, row in latest.iterrows():
        ax.annotate(ticker, (row["revenue_growth"], row["fcf_margin"]),
                    textcoords="offset points", xytext=(6, 6))
    # Everything above this line passes the Rule of 40.
    x_max = max(latest["revenue_growth"].max(), 40) + 5
    ax.plot([0, x_max], [40, 40 - x_max], linestyle="--", color="grey",
            label="Growth + FCF margin = 40%")
    ax.set_title("Rule of 40, latest fiscal year")
    ax.set_xlabel("Revenue growth (%)")
    ax.set_ylabel("Free cash flow margin (%)")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "rule_of_40.png", dpi=150)
    plt.close(fig)


def plot_capex_intensity(df):
    """Capital spending as a share of revenue: shows who is building data centres."""
    recent = df[df["fiscal_year"] > df["fiscal_year"].max() - YEARS_TO_PLOT]
    fig, ax = plt.subplots(figsize=(10, 6))
    for ticker, group in recent.groupby("ticker"):
        ax.plot(group["fiscal_year"], group["capex"] / group["revenue"] * 100,
                marker="o", label=ticker)
    ax.set_title("Capital spending as % of revenue")
    ax.set_xlabel("Fiscal year")
    ax.set_ylabel("Capex / revenue (%)")
    ax.legend(ncol=4)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "capex_intensity.png", dpi=150)
    plt.close(fig)


def main():
    df = add_ratios(pd.read_csv(INPUT_CSV))
    latest = latest_year(df)

    columns = ["fiscal_year", "revenue", "revenue_growth", "gross_margin",
               "operating_margin", "fcf_margin", "rule_of_40"]
    summary = latest[columns].sort_values("rule_of_40", ascending=False)
    summary.round(1).to_csv(SUMMARY_CSV)

    display = summary.copy()
    display["revenue"] = (display["revenue"] / 1e9).round(1)
    display = display.rename(columns={"revenue": "revenue_$bn"})
    print(display.round(1).to_string())

    CHART_DIR.mkdir(exist_ok=True)
    plot_revenue_growth(df)
    plot_margins(latest)
    plot_rule_of_40(latest)
    plot_capex_intensity(df)
    print(f"\nCharts saved to {CHART_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
