CREATE OR REPLACE VIEW vw_sales_performance AS 
SELECT 
    t.transaction_id,
    t.transaction_date,
    d.year,
    d.quarter,
    d.month_number,
    d.month_name,
    d.is_weekend,
    t.transaction_type,
    t.amount_usd AS gross_amount_usd,
    CASE 
        WHEN t.transaction_type = "Subscription" THEN t.amount_usd
        ELSE -t.amount_usd
    END AS signed_amount_usd,
    t.fee_generated_usd,
    c.client_id,
    c.segment AS client_segment,
    c.region AS client_region,
    c.country AS client_country,
    c.risk_profile AS client_risk_profile,
    a.advisor_id,
    CONCAT(a.advisor_name, ' ', a.advisor_surname) AS advisor_full_name,
    a.segment AS advisor_segment,
    a.region AS advisor_region,
    f.fund_id,
    f.fund_name,
    f.ticker,
    f.asset_class,
    f.management_fee_bps,
    f.fund_risk_level
FROM Fact_Transactions t 
JOIN Dim_Date d ON d.date_id = t.transaction_date
JOIN Dim_Advisors a ON t.advisor_id = a.advisor_id
JOIN Dim_Clients c ON c.client_id = t.client_id
JOIN Dim_Funds f ON f.fund_id = t.fund_id;


CREATE OR REPLACE VIEW vw_advisor_quota_attainment AS 
SELECT
    d.year,
    a.advisor_id,
    CONCAT(a.advisor_name, ' ', a.advisor_surname) AS advisor_full_name,
    a.region,
    a.segment,
    a.annual_target_usd,
    COALESCE(SUM(CASE WHEN t.transaction_type = "Subscription" THEN t.amount_usd ELSE 0 END), 0) AS gross_sales_usd,
    COALESCE(SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END), 0) AS net_flows_usd,
    COALESCE(SUM(t.fee_generated_usd), 0) AS total_fees_usd,
    ROUND(
        (COALESCE(SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE 0 END), 0) / a.annual_target_usd) * 100, 
        2
    ) AS target_attainment_pct,
    CASE 
        WHEN (COALESCE(SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE 0 END), 0) / a.annual_target_usd) >= 1.0 THEN 'Top Performer (>=100%)'
        WHEN (COALESCE(SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE 0 END), 0) / a.annual_target_usd) >= 0.7 THEN 'On Track (70-99%)'
        ELSE 'Underperformer (<70%)'
    END AS performance_tier
FROM Dim_Advisors a
CROSS JOIN (SELECT DISTINCT year FROM Dim_Date) d
LEFT JOIN Fact_Transactions t 
    ON a.advisor_id = t.advisor_id 
    AND YEAR(t.transaction_date) = d.year
GROUP BY 
    d.year, a.advisor_id, advisor_full_name, a.region, a.segment, a.annual_target_usd;



CREATE OR REPLACE VIEW vw_client_churn_signals AS
WITH ClientMetrics AS (
    SELECT 
        c.client_id,
        c.segment,
        c.region,
        c.country,
        c.risk_profile,
        c.onboarding_date,
        -- Całkowity historyczny bilans wpłat minus wypłat (szacowane AUM)
        GREATEST(
            COALESCE(SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END), 0),
            0
        ) AS total_historical_aum,
        -- Aktywność w II połowie 2025 roku
        COALESCE(SUM(CASE WHEN t.transaction_date >= '2025-07-01' AND t.transaction_type = 'Subscription' THEN t.amount_usd ELSE 0 END), 0) AS h2_2025_inflows,
        COALESCE(SUM(CASE WHEN t.transaction_date >= '2025-07-01' AND t.transaction_type = 'Redemption' THEN t.amount_usd ELSE 0 END), 0) AS h2_2025_outflows,
        COALESCE(SUM(CASE WHEN t.transaction_date >= '2025-07-01' THEN 
            CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END 
        ELSE 0 END), 0) AS h2_2025_net_flows
    FROM Dim_Clients c
    LEFT JOIN Fact_Transactions t ON c.client_id = t.client_id
    GROUP BY 
        c.client_id, c.segment, c.region, c.country, c.risk_profile, c.onboarding_date
)
SELECT 
    client_id,
    segment,
    region,
    country,
    risk_profile,
    onboarding_date,
    total_historical_aum,
    h2_2025_inflows,
    h2_2025_outflows,
    h2_2025_net_flows,
    CASE 
        WHEN h2_2025_net_flows < 0 AND h2_2025_outflows > (total_historical_aum * 0.5) THEN 'High Risk'
        WHEN h2_2025_net_flows < 0 THEN 'Watchlist'
        ELSE 'Healthy'
    END AS retention_status
FROM ClientMetrics;