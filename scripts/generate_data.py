import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import faker
from datetime import date

DB_USER = "root"
DB_PASSWORD = ""
DB_HOST = "localhost"
DB_PORT = "3306"
DB_NAME = "sales_db"


if DB_PASSWORD:
    connection_string = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    connection_string = f"mysql+pymysql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(connection_string)

## Quick connection test
with engine.connect() as conn:
    result = conn.execute(text("SHOW TABLES;"))
    tables = [row[0] for row in result]
    print("Connected to the data base, available tables: ", tables)

## Data for Dim_Date
'''
CREATE TABLE Dim_Date (
    date_id DATE PRIMARY KEY,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month_number INT NOT NULL,
    month_name VARCHAR(20),
    day_of_week VARCHAR(20),
    is_weekend BOOLEAN
);
'''

def generate_dim_date(start_date='2023-01-01', end_date= '2025-12-31'):
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    df_dates = pd.DataFrame({'date_id': dates.date})
    dt_series = pd.to_datetime(df_dates['date_id'])

    df_dates['year'] = dt_series.dt.year
    df_dates['quarter'] = dt_series.dt.quarter
    df_dates['month_number'] = dt_series.dt.month
    df_dates['month_name'] = dt_series.dt.month_name()
    df_dates['day_of_week'] = dt_series.dt.day_name()
    df_dates['is_weekend'] = dt_series.dt.dayofweek >= 5

    return df_dates

## Data for Dim_Customer
'''
client_id INT AUTO_INCREMENT PRIMARY KEY,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL,
    risk_profile VARCHAR(30) NOT NULL,
    onboarding_date DATE NOT NULL,
    churn_risk_score DECIMAL(5,4) DEFAULT NULL
'''

def generate_dim_customer(n_clients=1500):
    np.random.seed(42)
    region_countries = {
    "EMEA": ["Switzerland", "UK", "Germany", "Poland"],
    "Americas": ["USA", "Canada", "Brazil"],
    "APAC": ["Singapore", "Japan", "Australia"]
    }
    df_customers = pd.DataFrame()
    df_customers['segment'] = np.random.choice(['Retail', 'HNW', 'Institutional'], p=[0.6, 0.25, 0.15], size=n_clients)
    df_customers['onboarding_date'] = np.random.choice(pd.date_range('2023-01-01', '2025-09-30').date, size=n_clients)
    df_customers['churn_risk_score'] = None
    df_customers['region'] = np.random.choice(list(region_countries.keys()), p=[0.65, 0.25, 0.10], size=n_clients)
    df_customers['country'] = [np.random.choice(region_countries[r]) for r in df_customers["region"]]
    df_customers['risk_profile'] = np.random.choice(["Conservative", "Balanced", "Aggressive"], p=[0.3, 0.5, 0.2], size=n_clients)

    return df_customers

## Data for Dim_Advisor
'''
CREATE TABLE Dim_Advisors (
    advisor_id INT AUTO_INCREMENT PRIMARY KEY,
    advisor_name VARCHAR(50) NOT NULL,
    advisor_surname VARCHAR(50) NOT NULL,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL,
    annual_target_usd DECIMAL(15,2) NOT NULL
);
'''

def generate_dim_advisor( n_advisors= 40):
    df_advisor = pd.DataFrame()
    fake = faker.Faker()
    fake.seed_instance(42)

    region_countries = {
    "EMEA": ["Switzerland", "UK", "Germany", "Poland"],
    "Americas": ["USA", "Canada", "Brazil"],
    "APAC": ["Singapore", "Japan", "Australia"]
    }

    df_advisor['advisor_name'] = [fake.first_name() for _ in range(n_advisors)]
    df_advisor['advisor_surname'] = [fake.last_name() for _ in range(n_advisors)]
    df_advisor['segment'] = np.random.choice(['Retail', 'HNW', 'Institutional'], p=[0.6, 0.25, 0.15], size=n_advisors)
    df_advisor['region'] = np.random.choice(list(region_countries.keys()), p=[0.65, 0.25, 0.10], size=n_advisors)
    df_advisor['country'] = [np.random.choice(region_countries[r]) for r in df_advisor["region"]]
    targets = []
    for seg in df_advisor['segment']:
        if seg == 'Retail':
            targets.append(np.random.randint(500_000, 1_500_000))
        elif seg == 'HNW':
            targets.append(np.random.randint(2_000_000, 6_000_000))
        else:
            targets.append(np.random.randint(10_000_000, 30_000_000))
            
    df_advisor['annual_target_usd'] = targets
    return df_advisor


## Data for Dim_Funds
'''
CREATE TABLE Dim_Funds (
    fund_id INT AUTO_INCREMENT PRIMARY KEY,
    fund_name VARCHAR(100) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    asset_class VARCHAR(30) NOT NULL,
    management_fee_bps INT NOT NULL,
    fund_risk_level INT NOT NULL
);
'''

def generate_dim_funds():

    ### funds genereted by AI
    funds_data = [
        {"fund_name": "Global Equity Alpha Fund", "ticker": "GEAF", "asset_class": "Equity", "management_fee_bps": 125, "fund_risk_level": 6},
        {"fund_name": "US Tech & Innovation Equity", "ticker": "UTIE", "asset_class": "Equity", "management_fee_bps": 140, "fund_risk_level": 7},
        {"fund_name": "European Sustainable Leaders", "ticker": "EUSL", "asset_class": "Equity", "management_fee_bps": 115, "fund_risk_level": 5},
        {"fund_name": "Global Sovereign Bond Fund", "ticker": "GSBF", "asset_class": "Fixed Income", "management_fee_bps": 45, "fund_risk_level": 2},
        {"fund_name": "US Investment Grade Credit", "ticker": "USIG", "asset_class": "Fixed Income", "management_fee_bps": 55, "fund_risk_level": 3},
        {"fund_name": "Euro High Yield Bond", "ticker": "EHYB", "asset_class": "Fixed Income", "management_fee_bps": 75, "fund_risk_level": 4},
        {"fund_name": "Balanced Global Multi-Asset", "ticker": "BGMA", "asset_class": "Multi-Asset", "management_fee_bps": 95, "fund_risk_level": 4},
        {"fund_name": "Conservative Income Strategy", "ticker": "CINS", "asset_class": "Multi-Asset", "management_fee_bps": 80, "fund_risk_level": 3},
        {"fund_name": "Global Real Estate & Infrastructure", "ticker": "GREI", "asset_class": "Alternatives", "management_fee_bps": 175, "fund_risk_level": 6},
        {"fund_name": "Private Credit Opportunities", "ticker": "PCOP", "asset_class": "Alternatives", "management_fee_bps": 190, "fund_risk_level": 7},
    ]
    return pd.DataFrame(funds_data)


## Data for transactions
'''
CREATE TABLE Fact_Transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    advisor_id INT NOT NULL,
    fund_id INT NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    amount_usd DECIMAL(15,2) NOT NULL,
    fee_generated_usd DECIMAL(15,2) NOT NULL,
'''

def generate_fact_transactions(engine, n_transactions=25000):
    clients = pd.read_sql("SELECT client_id, segment, region, risk_profile, onboarding_date FROM Dim_Clients", engine)
    advisors = pd.read_sql("SELECT advisor_id, segment, region FROM Dim_Advisors", engine)
    funds = pd.read_sql("SELECT fund_id, asset_class, management_fee_bps, fund_risk_level FROM Dim_Funds", engine)
    
    n_churn = int(len(clients) * 0.15)
    churn_clients = set(np.random.choice(clients['client_id'], size=n_churn, replace=False))
    sampled_clients = clients.sample(n=n_transactions, replace=True, random_state=42).reset_index(drop=True)
    advisors_by_region = advisors.groupby('region')['advisor_id'].apply(list).to_dict()

    df_transactions = pd.DataFrame()
    df_transactions['client_id'] = sampled_clients['client_id']
    df_transactions['advisor_id'] = [np.random.choice(advisors_by_region[reg]) for reg in sampled_clients['region']]
    df_transactions['fund_id'] = np.random.choice(funds['fund_id'], size=n_transactions)

    end_date = date(2025, 12, 31)
    t_dates = []
    for onb_date in sampled_clients['onboarding_date']:
        if isinstance(onb_date, pd.Timestamp):
            onb_date = onb_date.date()
        max_days = (end_date - onb_date).days
        random_days = np.random.randint(0, max(1, max_days + 1))
        t_dates.append(pd.to_datetime(onb_date) + pd.Timedelta(days=random_days))
        
    df_transactions['transaction_date'] = pd.to_datetime(t_dates).date

    churn_cutoff = date(2025, 7, 1)
    t_types = []
    for cid, t_date in zip(df_transactions['client_id'], df_transactions['transaction_date']):
        if cid in churn_clients and t_date >= churn_cutoff:
            t_types.append(np.random.choice(['Subscription', 'Redemption'], p=[0.15, 0.85]))
        else:
            t_types.append(np.random.choice(['Subscription', 'Redemption'], p=[0.75, 0.25]))
            
    df_transactions['transaction_type'] = t_types

    amounts = []
    for seg in sampled_clients['segment']:
        if seg == 'Retail':
            amounts.append(round(np.random.uniform(1_000, 25_000), 2))
        elif seg == 'HNW':
            amounts.append(round(np.random.uniform(50_000, 450_000), 2))
        else:
            amounts.append(round(np.random.uniform(500_000, 4_000_000), 2))
            
    df_transactions['amount_usd'] = amounts

    fee_map = funds.set_index('fund_id')['management_fee_bps'].to_dict()
    df_transactions['fee_generated_usd'] = [
        round(amt * (fee_map[fid] / 10000), 2)
        for amt, fid in zip(df_transactions['amount_usd'], df_transactions['fund_id'])
    ]
    return df_transactions


if __name__ == "__main__":
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM Fact_Transactions;"))
        conn.execute(text("DELETE FROM Dim_Clients;"))
        conn.execute(text("DELETE FROM Dim_Advisors;"))
        conn.execute(text("DELETE FROM Dim_Funds;"))
        conn.execute(text("DELETE FROM Dim_Date;"))
        
        conn.execute(text("ALTER TABLE Fact_Transactions AUTO_INCREMENT = 1;"))
        conn.execute(text("ALTER TABLE Dim_Clients AUTO_INCREMENT = 1;"))
        conn.execute(text("ALTER TABLE Dim_Advisors AUTO_INCREMENT = 1;"))
        conn.execute(text("ALTER TABLE Dim_Funds AUTO_INCREMENT = 1;"))

    generate_dim_date().to_sql("Dim_Date", con=engine, if_exists="append", index=False)
    generate_dim_customer().to_sql("Dim_Clients", con=engine, if_exists="append", index=False)
    generate_dim_advisor().to_sql("Dim_Advisors", con=engine, if_exists="append", index=False)
    generate_dim_funds().to_sql("Dim_Funds", con=engine, if_exists="append", index=False)

    df_transactions = generate_fact_transactions(engine, n_transactions=25000)
    df_transactions.to_sql("Fact_Transactions", con=engine, if_exists="append", index=False)

    print("All tables are filled")

