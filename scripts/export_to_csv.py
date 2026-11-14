import os
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("mysql+pymysql://root@localhost:3306/sales_db")
os.makedirs("data/processed", exist_ok=True)

tables_to_export = [
    "Dim_Date",
    "vw_sales_performance",
    "vw_advisor_quota_attainment",
    "vw_client_churn_signals"
]

for table in tables_to_export:
    df = pd.read_sql(f"SELECT * FROM {table}", engine)
    output_path = f"data/processed/{table}.csv"
    df.to_csv(output_path, index=False)
    print(f"Exported {table}: {len(df)} raws -> {output_path}")