"""Rule-based churn signals, their evaluation against the ground truth, and the Power BI export.

Rules (rolling windows relative to the last month in the data; same logic as
vw_client_churn_signals in sql/views.sql):

    Lost       current AUM < 10% of the client's peak month-end AUM in the last 12 months
    High Risk  net outflows in the last 6 months >= 40% of AUM 6 months ago,
               OR >= 3 months with net redemptions and no subscriptions in the last 6 months
    Watchlist  net outflows in the last 6 months >= 15% of AUM 6 months ago
    Healthy    everything else

Usage:
    python scripts/churn_rules.py   # prints precision/recall, writes data/processed/*.csv
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
TRUTH = ROOT / "data" / "ground_truth" / "churn_labels.csv"


def churn_signals(tx: pd.DataFrame, pos: pd.DataFrame, clients: pd.DataFrame) -> pd.DataFrame:
    pos = pos.assign(month_end=pd.to_datetime(pos["month_end"]))
    tx = tx.assign(transaction_date=pd.to_datetime(tx["transaction_date"]))
    as_of = pos["month_end"].max()
    m6 = as_of - pd.offsets.MonthEnd(6)
    m12 = as_of - pd.offsets.MonthEnd(12)

    client_month = pos.groupby(["client_id", "month_end"])["aum_usd"].sum().unstack(fill_value=0.0)
    aum_now = client_month.get(as_of, 0.0)
    aum_6m = client_month.get(m6, 0.0)
    peak_12m = client_month.loc[:, (client_month.columns > m12) & (client_month.columns <= as_of)].max(axis=1)

    last6 = tx[tx["transaction_date"] > m6]
    signed = np.where(last6["transaction_type"] == "Subscription", last6["amount_usd"], -last6["amount_usd"])
    last6 = last6.assign(signed=signed, ym=last6["transaction_date"].dt.to_period("M"))
    net_6m = last6.groupby("client_id")["signed"].sum()
    outflows_6m = last6[last6["transaction_type"] == "Redemption"].groupby("client_id")["amount_usd"].sum()
    subs_6m = last6[last6["transaction_type"] == "Subscription"].groupby("client_id").size()
    monthly = last6.groupby(["client_id", "ym"])["signed"].sum()
    red_months = (monthly < 0).groupby(level=0).sum()

    df = clients[["client_id"]].copy().set_index("client_id")
    df["aum_now_usd"] = aum_now.reindex(df.index, fill_value=0.0)
    df["aum_6m_ago_usd"] = aum_6m.reindex(df.index, fill_value=0.0)
    df["peak_aum_12m_usd"] = peak_12m.reindex(df.index, fill_value=0.0)
    df["net_flows_6m_usd"] = net_6m.reindex(df.index, fill_value=0.0)
    df["outflows_6m_usd"] = outflows_6m.reindex(df.index, fill_value=0.0)
    df["subscriptions_6m"] = subs_6m.reindex(df.index, fill_value=0).astype(int)
    df["net_redemption_months_6m"] = red_months.reindex(df.index, fill_value=0).astype(int)

    base = df["aum_6m_ago_usd"].where(df["aum_6m_ago_usd"] > 0, np.nan)
    outflow_ratio = (-df["net_flows_6m_usd"] / base).fillna(0.0)
    lost = (df["peak_aum_12m_usd"] > 0) & (df["aum_now_usd"] < 0.10 * df["peak_aum_12m_usd"])
    steady_bleed = (df["net_redemption_months_6m"] >= 3) & (df["subscriptions_6m"] == 0)
    high = (outflow_ratio >= 0.40) | steady_bleed
    watch = outflow_ratio >= 0.15

    df["retention_status"] = np.select([lost, high, watch], ["Lost", "High Risk", "Watchlist"], "Healthy")
    df["status_reason"] = np.select(
        [lost, outflow_ratio >= 0.40, steady_bleed, watch],
        [
            "AUM down >90% from 12-month peak",
            "Net outflows >= 40% of AUM in last 6 months",
            "3+ months of net redemptions, no new money",
            "Net outflows 15-40% of AUM in last 6 months",
        ],
        "No warning signals",
    )
    df["outflow_ratio_6m"] = outflow_ratio.round(4)
    df["as_of_date"] = as_of.date()
    return df.reset_index()


def evaluate(signals: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    d = signals.merge(labels, on="client_id")
    rows = []
    for name, flagged in {
        "Lost + High Risk": d["retention_status"].isin(["Lost", "High Risk"]),
        "Lost + High Risk + Watchlist": d["retention_status"] != "Healthy",
    }.items():
        tp = int((flagged & d["is_churner"]).sum())
        fp = int((flagged & ~d["is_churner"]).sum())
        fn = int((~flagged & d["is_churner"]).sum())
        rows.append({"rule": name, "flagged": int(flagged.sum()), "true_positives": tp, "false_positives": fp,
                     "missed_churners": fn, "precision": round(tp / max(tp + fp, 1), 3),
                     "recall": round(tp / max(tp + fn, 1), 3)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    tables = {p.stem: pd.read_csv(p) for p in RAW_DIR.glob("*.csv")}
    signals = churn_signals(tables["Fact_Transactions"], tables["Fact_Positions_Monthly"], tables["Dim_Clients"])

    labels = pd.read_csv(TRUTH)
    print(pd.crosstab(signals.merge(labels, on="client_id")["retention_status"],
                      labels["is_churner"].rename("true churner")))
    print(evaluate(signals, labels).to_string(index=False))

    # Power BI export: raw tables + clients enriched with the churn signals (no ground truth!)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.csv"):
        old.unlink()
    for name, df in tables.items():
        if name == "Dim_Clients":
            df = df.merge(signals, on="client_id", how="left")
        df.to_csv(OUT_DIR / f"{name}.csv", index=False)
    print(f"Wrote {len(tables)} tables to {OUT_DIR}")
