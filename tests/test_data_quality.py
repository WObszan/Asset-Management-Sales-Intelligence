"""Data quality checks on the generated star schema (data/processed)."""
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def t():
    return {p.stem: pd.read_csv(p) for p in DATA.glob("*.csv")}


def test_no_negative_positions(t):
    assert (t["Fact_Positions_Monthly"]["aum_usd"] >= 0).all()


def test_redemption_never_exceeds_holding(t):
    tx = t["Fact_Transactions"].sort_values(["transaction_date", "transaction_id"])
    signed = tx["amount_usd"].where(tx["transaction_type"] == "Subscription", -tx["amount_usd"])
    # flows only (no returns) can dip slightly below zero after market losses, but a position must never
    # start with a redemption
    first = tx.groupby(["client_id", "fund_id"])["transaction_type"].first()
    assert (first == "Subscription").all()
    assert signed.notna().all()


def test_one_advisor_per_client_matching_segment_and_region(t):
    tx = t["Fact_Transactions"].merge(t["Dim_Clients"][["client_id", "advisor_id", "segment", "region"]],
                                      on="client_id", suffixes=("", "_client"))
    assert (tx["advisor_id"] == tx["advisor_id_client"]).all()
    pairs = t["Dim_Clients"].merge(t["Dim_Advisors"], on="advisor_id", suffixes=("", "_adv"))
    assert (pairs["segment"] == pairs["segment_adv"]).all()
    assert (pairs["region"] == pairs["region_adv"]).all()


def test_no_weekend_transactions(t):
    days = pd.to_datetime(t["Fact_Transactions"]["transaction_date"]).dt.day_of_week
    assert (days < 5).all()


def test_foreign_keys(t):
    tx = t["Fact_Transactions"]
    assert tx["client_id"].isin(t["Dim_Clients"]["client_id"]).all()
    assert tx["fund_id"].isin(t["Dim_Funds"]["fund_id"]).all()
    assert tx["transaction_date"].isin(t["Dim_Date"]["date_id"]).all()


def test_quota_attainment_is_realistic(t):
    tx = t["Fact_Transactions"].assign(year=lambda d: pd.to_datetime(d["transaction_date"]).dt.year)
    gross = tx[tx["transaction_type"] == "Subscription"].groupby(["advisor_id", "year"])["amount_usd"].sum()
    tg = t["Dim_Advisor_Targets"].set_index(["advisor_id", "year"])["target_usd"]
    att = gross.reindex(tg.index, fill_value=0) / tg
    assert 0.8 <= att.median() <= 1.0
    assert 0.15 <= (att >= 1).mean() <= 0.45
    assert (att > 2).mean() < 0.02


def test_ground_truth_kept_out_of_powerbi_data(t):
    assert "is_churner" not in t["Dim_Clients"].columns
    labels = pd.read_csv(ROOT / "data" / "ground_truth" / "churn_labels.csv")
    assert 0.13 <= labels["is_churner"].mean() <= 0.17
