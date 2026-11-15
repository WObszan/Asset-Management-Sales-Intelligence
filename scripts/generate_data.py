"""Synthetic data generator for the Asset Management Sales Intelligence project.

Builds a star schema of fund sales for an asset manager (2023-2025):

    Dim_Date, Dim_Clients, Dim_Advisors, Dim_Funds, Dim_Advisor_Targets,
    Fact_Transactions, Fact_Fund_Returns, Fact_Positions_Monthly

Design rules (all data is synthetic):
- every client has ONE relationship manager from the same region and segment,
- transactions happen on business days only,
- a redemption never exceeds what the client holds in that fund,
- positions grow with monthly fund returns; management fees = AUM x bps / 12,
- ~15% of clients churn (fast or slow "silent" churn); ~10% of other clients make
  one large one-off redemption (noise), and the true labels are saved separately
  in data/ground_truth so the churn rules can be evaluated.

Usage:
    python scripts/generate_data.py               # write CSVs to data/raw
    python scripts/generate_data.py --load-mysql  # also load the tables into MySQL
"""
from __future__ import annotations

import argparse
from pathlib import Path

import faker
import numpy as np
import pandas as pd

SEED = 42
START, END = pd.Timestamp("2023-01-02"), pd.Timestamp("2025-12-31")
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
TRUTH_DIR = ROOT / "data" / "ground_truth"

REGIONS = {  # region -> (share of clients, countries)
    "EMEA": (0.65, ["Switzerland", "UK", "Germany", "Poland"]),
    "Americas": (0.25, ["USA", "Canada", "Brazil"]),
    "APAC": (0.10, ["Singapore", "Japan", "Australia"]),
}
SEGMENTS = {  # segment -> (share of clients, ticket size range USD, expected transactions per month)
    "Retail": (0.60, (1_000, 25_000), 0.55),
    "HNW": (0.25, (50_000, 450_000), 0.75),
    "Institutional": (0.15, (500_000, 4_000_000), 0.45),
}
# Which asset classes each risk profile prefers when subscribing
PROFILE_WEIGHTS = {
    "Conservative": {"Equity": 0.10, "Fixed Income": 0.55, "Multi-Asset": 0.30, "Alternatives": 0.05},
    "Balanced": {"Equity": 0.35, "Fixed Income": 0.30, "Multi-Asset": 0.25, "Alternatives": 0.10},
    "Aggressive": {"Equity": 0.60, "Fixed Income": 0.10, "Multi-Asset": 0.10, "Alternatives": 0.20},
}
# Annual expected return / volatility per asset class, and loading on a common market factor
RETURN_PARAMS = {
    "Equity": (0.08, 0.16, 0.9),
    "Fixed Income": (0.03, 0.05, 0.3),
    "Multi-Asset": (0.05, 0.09, 0.7),
    "Alternatives": (0.06, 0.10, 0.5),
}
CHURN_SHARE, NOISE_SHARE = 0.15, 0.10


# ---------------------------------------------------------------- dimensions
def generate_dim_date() -> pd.DataFrame:
    """Continuous calendar (all days) so Power BI time intelligence works."""
    d = pd.date_range("2023-01-01", "2025-12-31", freq="D")
    return pd.DataFrame({
        "date_id": d.date,
        "year": d.year,
        "quarter": d.quarter,
        "month_number": d.month,
        "month_name": d.month_name(),
        "year_month": d.strftime("%Y-%m"),
        "month_end": (d + pd.offsets.MonthEnd(0)).date,
        "day_of_week": d.day_name(),
        "is_weekend": d.day_of_week >= 5,
    })


def generate_dim_funds() -> pd.DataFrame:
    funds = [
        ("Global Equity Alpha Fund", "GEAF", "Equity", 125, 6),
        ("US Tech & Innovation Equity", "UTIE", "Equity", 140, 7),
        ("European Sustainable Leaders", "EUSL", "Equity", 115, 5),
        ("Global Sovereign Bond Fund", "GSBF", "Fixed Income", 45, 2),
        ("US Investment Grade Credit", "USIG", "Fixed Income", 55, 3),
        ("Euro High Yield Bond", "EHYB", "Fixed Income", 75, 4),
        ("Balanced Global Multi-Asset", "BGMA", "Multi-Asset", 95, 4),
        ("Conservative Income Strategy", "CINS", "Multi-Asset", 80, 3),
        ("Global Real Estate & Infrastructure", "GREI", "Alternatives", 175, 6),
        ("Private Credit Opportunities", "PCOP", "Alternatives", 190, 7),
    ]
    df = pd.DataFrame(funds, columns=["fund_name", "ticker", "asset_class", "management_fee_bps", "fund_risk_level"])
    df.insert(0, "fund_id", range(1, len(df) + 1))
    return df


def generate_dim_advisors(rng: np.random.Generator, fake: faker.Faker, n_target: int = 40) -> pd.DataFrame:
    """At least two advisors for every (region, segment) pair, the rest proportional to client mix."""
    rows = []
    for region, (r_share, countries) in REGIONS.items():
        for segment, (s_share, _, _) in SEGMENTS.items():
            n = max(2, round(n_target * r_share * s_share))
            for _ in range(n):
                rows.append({
                    "advisor_name": fake.first_name(),
                    "advisor_surname": fake.last_name(),
                    "segment": segment,
                    "region": region,
                    "country": rng.choice(countries),
                })
    df = pd.DataFrame(rows)
    df.insert(0, "advisor_id", range(1, len(df) + 1))
    return df


def generate_dim_clients(rng: np.random.Generator, advisors: pd.DataFrame, n_clients: int = 1500) -> pd.DataFrame:
    regions = list(REGIONS)
    segments = list(SEGMENTS)
    df = pd.DataFrame({
        "client_id": range(1, n_clients + 1),
        "segment": rng.choice(segments, p=[SEGMENTS[s][0] for s in segments], size=n_clients),
        "region": rng.choice(regions, p=[REGIONS[r][0] for r in regions], size=n_clients),
        "risk_profile": rng.choice(["Conservative", "Balanced", "Aggressive"], p=[0.3, 0.5, 0.2], size=n_clients),
    })
    df["country"] = [rng.choice(REGIONS[r][1]) for r in df["region"]]
    # 35% of clients are already on the book at the start, the rest join over time (last joiners mid-2025)
    bdays = pd.bdate_range(START, "2025-06-30")
    existing = rng.random(n_clients) < 0.35
    df["onboarding_date"] = np.where(existing, START, rng.choice(bdays, size=n_clients))
    df["onboarding_date"] = pd.to_datetime(df["onboarding_date"]).dt.date
    # One relationship manager per client, same region and segment
    pools = advisors.groupby(["region", "segment"])["advisor_id"].apply(list).to_dict()
    df["advisor_id"] = [rng.choice(pools[(r, s)]) for r, s in zip(df["region"], df["segment"])]
    return df


# ---------------------------------------------------------------- fund returns
def generate_fund_returns(rng: np.random.Generator, funds: pd.DataFrame, months: pd.DatetimeIndex) -> pd.DataFrame:
    market = rng.standard_normal(len(months))
    rows = []
    for f in funds.itertuples():
        mu, vol, beta = RETURN_PARAMS[f.asset_class]
        z = beta * market + np.sqrt(1 - beta**2) * rng.standard_normal(len(months))
        r = mu / 12 + vol / np.sqrt(12) * z
        rows += [{"fund_id": f.fund_id, "month_end": m.date(), "monthly_return": round(x, 6)} for m, x in zip(months, r)]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- client simulation
def _ticket(rng, segment):
    lo, hi = SEGMENTS[segment][1]
    # log-uniform: many small tickets, few large ones
    return round(float(np.exp(rng.uniform(np.log(lo), np.log(hi)))), 2)


def _pick_fund(rng, funds, profile):
    w = PROFILE_WEIGHTS[profile]
    p = funds["asset_class"].map(w).to_numpy()
    p = p / p.sum()
    return int(rng.choice(funds["fund_id"], p=p))


def simulate(rng, clients, funds, returns, months):
    """Month-by-month simulation of every client's transactions and fund positions."""
    ret = returns.pivot(index="month_end", columns="fund_id", values="monthly_return")
    bps = funds.set_index("fund_id")["management_fee_bps"]

    # ---- churn labels (ground truth)
    n = len(clients)
    churners = rng.choice(clients["client_id"], size=int(n * CHURN_SHARE), replace=False)
    churn_months = pd.date_range("2025-01-31", "2025-10-31", freq="ME")
    labels = pd.DataFrame({"client_id": clients["client_id"], "is_churner": clients["client_id"].isin(churners)})
    labels["churn_start"] = pd.NaT
    labels.loc[labels.is_churner, "churn_start"] = rng.choice(churn_months, size=labels.is_churner.sum())
    labels["churn_pattern"] = None
    labels.loc[labels.is_churner, "churn_pattern"] = rng.choice(["fast", "slow"], size=labels.is_churner.sum())
    non_churners = labels.loc[~labels.is_churner, "client_id"].to_numpy()
    noisy = set(rng.choice(non_churners, size=int(n * NOISE_SHARE), replace=False))
    noise_month = {c: rng.choice(pd.date_range("2025-01-31", "2025-12-31", freq="ME")) for c in noisy}
    lab = labels.set_index("client_id")

    tx_rows, pos_rows = [], []
    for c in clients.itertuples():
        positions: dict[int, float] = {}
        rate = SEGMENTS[c.segment][2]
        churn_start = lab.at[c.client_id, "churn_start"]
        pattern = lab.at[c.client_id, "churn_pattern"]
        onboard = pd.Timestamp(c.onboarding_date)
        slow_len = int(rng.integers(4, 7))

        for m in months:
            if m < onboard + pd.offsets.MonthEnd(0):
                continue
            m_start = max(m.replace(day=1), onboard)
            bdays = pd.bdate_range(m_start, m)
            if len(bdays) == 0:
                continue
            start_bal = dict(positions)
            events = []  # (date, type, fund, amount)

            first_month = (m == onboard + pd.offsets.MonthEnd(0)) and not positions
            churning = pd.notna(churn_start) and m >= churn_start
            months_in = ((m.year - churn_start.year) * 12 + m.month - churn_start.month) if churning else -1

            if first_month:
                # initial investment in 1-3 funds; clients already on the book in 2023 bring a
                # larger legacy portfolio, so the firm starts with a mature AUM base
                legacy = 12 if onboard == START else 2
                for _ in range(int(rng.integers(1, 4))):
                    events.append((bdays[0], "Subscription", _pick_fund(rng, funds, c.risk_profile),
                                   _ticket(rng, c.segment) * legacy))
            elif churning and pattern == "fast":
                if months_in <= 1:  # sell everything over ~2 months
                    for f in [f for f, b in positions.items() if b > 1]:
                        share = 1.0 if months_in == 1 else float(rng.uniform(0.6, 0.9))
                        events.append((rng.choice(bdays), "Redemption", f, round(positions[f] * share, 2)))
            elif churning and pattern == "slow":
                if months_in < slow_len:  # silent churn: partial monthly redemptions, no new money
                    held = [f for f, b in positions.items() if b > 1]
                    for f in rng.choice(held, size=min(len(held), int(rng.integers(1, 3))), replace=False) if held else []:
                        events.append((rng.choice(bdays), "Redemption", int(f),
                                       round(positions[int(f)] * float(rng.uniform(0.2, 0.4)), 2)))
            else:
                # normal activity
                for _ in range(rng.poisson(rate)):
                    held = [f for f, b in positions.items() if b > 1]
                    if held and rng.random() < 0.28:
                        f = int(rng.choice(held))
                        events.append((rng.choice(bdays), "Redemption", f, round(positions[f] * float(rng.uniform(0.05, 0.4)), 2)))
                    else:
                        events.append((rng.choice(bdays), "Subscription", _pick_fund(rng, funds, c.risk_profile),
                                       _ticket(rng, c.segment)))
                if c.client_id in noisy and m == noise_month[c.client_id] and positions:
                    f = max(positions, key=positions.get)  # one large one-off redemption from the biggest position
                    events.append((bdays[-1], "Redemption", f, round(positions[f] * float(rng.uniform(0.5, 0.8)), 2)))

            # apply events in date order, never redeem more than held
            for d, t, f, amt in sorted(events, key=lambda e: e[0]):
                if t == "Redemption":
                    held_now = np.floor(positions.get(f, 0.0) * 100) / 100  # never round above the holding
                    amt = min(amt, held_now)
                    if amt <= 0:
                        continue
                    positions[f] = max(positions[f] - amt, 0.0)
                else:
                    positions[f] = positions.get(f, 0.0) + amt
                tx_rows.append((c.client_id, c.advisor_id, f, pd.Timestamp(d).date(), t, round(amt, 2)))

            # month end: market return and management fee
            for f in set(positions) | set(start_bal):
                bal = positions.get(f, 0.0) * (1 + ret.at[m.date(), f])
                positions[f] = bal
                b0 = start_bal.get(f, 0.0)
                if bal > 0.5 or b0 > 0.5:
                    fee = (b0 + bal) / 2 * bps[f] / 10_000 / 12
                    pos_rows.append((c.client_id, f, c.advisor_id, m.date(), round(bal, 2), round(fee, 2)))
            positions = {f: b for f, b in positions.items() if b > 0.5}

    tx = pd.DataFrame(tx_rows, columns=["client_id", "advisor_id", "fund_id", "transaction_date",
                                        "transaction_type", "amount_usd"])
    tx = tx.sort_values(["transaction_date", "client_id"]).reset_index(drop=True)
    tx.insert(0, "transaction_id", range(1, len(tx) + 1))
    pos = pd.DataFrame(pos_rows, columns=["client_id", "fund_id", "advisor_id", "month_end", "aum_usd", "fee_usd"])
    labels["churn_start"] = pd.to_datetime(labels["churn_start"]).dt.date
    labels["is_noise_redeemer"] = labels["client_id"].isin(noisy)
    return tx, pos, labels


# ---------------------------------------------------------------- targets
def generate_targets(rng, advisors, tx) -> pd.DataFrame:
    """Yearly gross-sales targets per advisor.

    Target = average gross sales of advisors in the same (region, segment, year) x a random
    ambition factor, scaled so the median attainment is ~90% (realistic stretch targets).
    """
    gross = (tx[tx.transaction_type == "Subscription"]
             .assign(year=pd.to_datetime(tx.transaction_date).dt.year)
             .groupby(["advisor_id", "year"])["amount_usd"].sum())
    grid = pd.MultiIndex.from_product([advisors.advisor_id, [2023, 2024, 2025]], names=["advisor_id", "year"])
    df = gross.reindex(grid, fill_value=0).rename("gross").reset_index().merge(advisors[["advisor_id", "region", "segment"]])
    peer_mean = df.groupby(["region", "segment", "year"])["gross"].transform("mean")
    df["target_usd"] = peer_mean * rng.uniform(0.8, 1.25, len(df))
    scale = np.median(df["gross"] / df["target_usd"]) / 0.90
    df["target_usd"] = (df["target_usd"] * scale).round(-3)
    return df[["advisor_id", "year", "target_usd"]]


# ---------------------------------------------------------------- main
def build_all(seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    fake = faker.Faker()
    fake.seed_instance(seed)
    months = pd.date_range(START, END, freq="ME")

    dim_date = generate_dim_date()
    funds = generate_dim_funds()
    advisors = generate_dim_advisors(rng, fake)
    clients = generate_dim_clients(rng, advisors)
    returns = generate_fund_returns(rng, funds, months)
    tx, positions, labels = simulate(rng, clients, funds, returns, months)
    targets = generate_targets(rng, advisors, tx)
    return {
        "Dim_Date": dim_date, "Dim_Funds": funds, "Dim_Advisors": advisors, "Dim_Clients": clients,
        "Dim_Advisor_Targets": targets, "Fact_Fund_Returns": returns, "Fact_Transactions": tx,
        "Fact_Positions_Monthly": positions, "_churn_labels": labels,
    }


def load_mysql(tables: dict[str, pd.DataFrame]) -> None:
    """Optional: load all tables into MySQL (settings from environment / .env)."""
    import os
    from sqlalchemy import create_engine, text

    url = (f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:{os.getenv('DB_PASSWORD', '')}"
           f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', 'sales_db')}")
    engine = create_engine(url)
    order = ["Dim_Date", "Dim_Funds", "Dim_Advisors", "Dim_Clients", "Dim_Advisor_Targets",
             "Fact_Fund_Returns", "Fact_Transactions", "Fact_Positions_Monthly"]
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for name in reversed(order):
            conn.execute(text(f"DELETE FROM {name}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    for name in order:
        tables[name].to_sql(name, con=engine, if_exists="append", index=False)
    print("Loaded all tables into MySQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--load-mysql", action="store_true")
    args = parser.parse_args()

    tables = build_all()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        if name == "_churn_labels":
            df.to_csv(TRUTH_DIR / "churn_labels.csv", index=False)
        else:
            df.to_csv(RAW_DIR / f"{name}.csv", index=False)
        print(f"{name:<24} {len(df):>7} rows")
    if args.load_mysql:
        load_mysql(tables)
