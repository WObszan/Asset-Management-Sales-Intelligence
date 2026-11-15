"""Alternative export path: read the star schema and the churn view from MySQL into CSVs for Power BI.

The default path (no database needed) is:
    python scripts/generate_data.py && python scripts/churn_rules.py
Use this script instead when the data was loaded with `generate_data.py --load-mysql`.
"""
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "processed_mysql"
url = (f"mysql+pymysql://{os.getenv('DB_USER', 'root')}:{os.getenv('DB_PASSWORD', '')}"
       f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '3306')}/{os.getenv('DB_NAME', 'sales_db')}")
engine = create_engine(url)
OUT_DIR.mkdir(parents=True, exist_ok=True)

tables = ["Dim_Date", "Dim_Funds", "Dim_Advisors", "Dim_Advisor_Targets",
          "Fact_Fund_Returns", "Fact_Transactions", "Fact_Positions_Monthly"]
for table in tables:
    df = pd.read_sql(f"SELECT * FROM {table}", engine)
    df.to_csv(OUT_DIR / f"{table}.csv", index=False)
    print(f"Exported {table}: {len(df)} rows")

# Clients enriched with the churn signals from the SQL view
clients = pd.read_sql(
    """SELECT c.*, v.aum_now_usd, v.aum_6m_ago_usd, v.peak_aum_12m_usd, v.net_flows_6m_usd,
              v.outflows_6m_usd, v.outflow_ratio_6m, v.retention_status
       FROM Dim_Clients c JOIN vw_client_churn_signals v ON v.client_id = c.client_id""",
    engine,
)
clients.to_csv(OUT_DIR / "Dim_Clients.csv", index=False)
print(f"Exported Dim_Clients (with churn signals): {len(clients)} rows")
