-- Analytical views (MySQL 8). Business logic lives here; Power BI only adds DAX measures.
USE sales_db;

-- 1) Every transaction with all dimensions and signed flows (+ subscription, - redemption)
CREATE OR REPLACE VIEW vw_sales_performance AS
SELECT
    t.transaction_id,
    t.transaction_date,
    d.year,
    d.quarter,
    d.month_number,
    d.month_name,
    t.transaction_type,
    t.amount_usd AS gross_amount_usd,
    CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END AS signed_amount_usd,
    c.client_id,
    c.segment AS client_segment,
    c.region AS client_region,
    c.country AS client_country,
    c.risk_profile AS client_risk_profile,
    a.advisor_id,
    CONCAT(a.advisor_name, ' ', a.advisor_surname) AS advisor_full_name,
    f.fund_id,
    f.fund_name,
    f.ticker,
    f.asset_class,
    f.management_fee_bps,
    f.fund_risk_level
FROM Fact_Transactions t
JOIN Dim_Date d     ON d.date_id = t.transaction_date
JOIN Dim_Advisors a ON a.advisor_id = t.advisor_id
JOIN Dim_Clients c  ON c.client_id = t.client_id
JOIN Dim_Funds f    ON f.fund_id = t.fund_id;


-- 2) Yearly quota attainment per advisor. Quota is measured on GROSS SALES (subscriptions).
--    Starting from targets keeps advisors with no sales in a year (attainment 0%).
CREATE OR REPLACE VIEW vw_advisor_quota_attainment AS
WITH sales AS (
    SELECT
        t.advisor_id,
        YEAR(t.transaction_date) AS year,
        SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE 0 END) AS gross_sales_usd,
        SUM(CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END) AS net_flows_usd
    FROM Fact_Transactions t
    GROUP BY t.advisor_id, YEAR(t.transaction_date)
),
fees AS (
    SELECT advisor_id, YEAR(month_end) AS year, SUM(fee_usd) AS fee_revenue_usd
    FROM Fact_Positions_Monthly
    GROUP BY advisor_id, YEAR(month_end)
)
SELECT
    tg.year,
    a.advisor_id,
    CONCAT(a.advisor_name, ' ', a.advisor_surname) AS advisor_full_name,
    a.region,
    a.segment,
    tg.target_usd,
    COALESCE(s.gross_sales_usd, 0) AS gross_sales_usd,
    COALESCE(s.net_flows_usd, 0) AS net_flows_usd,
    COALESCE(f.fee_revenue_usd, 0) AS fee_revenue_usd,
    ROUND(COALESCE(s.gross_sales_usd, 0) / tg.target_usd * 100, 2) AS target_attainment_pct,
    CASE
        WHEN COALESCE(s.gross_sales_usd, 0) / tg.target_usd >= 1.0 THEN 'Top Performer (>=100%)'
        WHEN COALESCE(s.gross_sales_usd, 0) / tg.target_usd >= 0.7 THEN 'On Track (70-99%)'
        ELSE 'Underperformer (<70%)'
    END AS performance_tier
FROM Dim_Advisor_Targets tg
JOIN Dim_Advisors a ON a.advisor_id = tg.advisor_id
LEFT JOIN sales s   ON s.advisor_id = tg.advisor_id AND s.year = tg.year
LEFT JOIN fees f    ON f.advisor_id = tg.advisor_id AND f.year = tg.year;


-- 3) Churn signals with rolling windows relative to the last month in the data
--    (same rules as scripts/churn_rules.py):
--    Lost      : AUM now < 10% of the 12-month peak
--    High Risk : net outflows (6m) >= 40% of AUM 6 months ago, or 3+ months of net redemptions and no subscriptions
--    Watchlist : net outflows (6m) >= 15% of AUM 6 months ago
CREATE OR REPLACE VIEW vw_client_churn_signals AS
WITH as_of AS (
    SELECT MAX(month_end) AS d FROM Fact_Positions_Monthly
),
client_aum AS (
    SELECT client_id, month_end, SUM(aum_usd) AS aum
    FROM Fact_Positions_Monthly
    GROUP BY client_id, month_end
),
aum_points AS (
    SELECT
        c.client_id,
        SUM(CASE WHEN ca.month_end = a.d THEN ca.aum ELSE 0 END) AS aum_now_usd,
        SUM(CASE WHEN ca.month_end = LAST_DAY(a.d - INTERVAL 6 MONTH) THEN ca.aum ELSE 0 END) AS aum_6m_ago_usd,
        MAX(CASE WHEN ca.month_end > LAST_DAY(a.d - INTERVAL 12 MONTH) THEN ca.aum ELSE 0 END) AS peak_aum_12m_usd
    FROM Dim_Clients c
    CROSS JOIN as_of a
    LEFT JOIN client_aum ca ON ca.client_id = c.client_id
    GROUP BY c.client_id
),
recent_tx AS (
    SELECT
        t.client_id,
        LAST_DAY(t.transaction_date) AS month_end,
        t.transaction_type,
        t.amount_usd,
        CASE WHEN t.transaction_type = 'Subscription' THEN t.amount_usd ELSE -t.amount_usd END AS signed_usd
    FROM Fact_Transactions t
    CROSS JOIN as_of a
    WHERE t.transaction_date > LAST_DAY(a.d - INTERVAL 6 MONTH)
),
flows AS (
    SELECT
        client_id,
        SUM(signed_usd) AS net_flows_6m_usd,
        SUM(CASE WHEN transaction_type = 'Redemption' THEN amount_usd ELSE 0 END) AS outflows_6m_usd,
        SUM(CASE WHEN transaction_type = 'Subscription' THEN 1 ELSE 0 END) AS subscriptions_6m
    FROM recent_tx
    GROUP BY client_id
),
redemption_months AS (
    SELECT client_id, SUM(CASE WHEN month_net < 0 THEN 1 ELSE 0 END) AS net_redemption_months_6m
    FROM (SELECT client_id, month_end, SUM(signed_usd) AS month_net FROM recent_tx GROUP BY client_id, month_end) m
    GROUP BY client_id
),
metrics AS (
    SELECT
        c.client_id,
        c.segment,
        c.region,
        c.country,
        c.advisor_id,
        ap.aum_now_usd,
        ap.aum_6m_ago_usd,
        ap.peak_aum_12m_usd,
        COALESCE(f.net_flows_6m_usd, 0) AS net_flows_6m_usd,
        COALESCE(f.outflows_6m_usd, 0) AS outflows_6m_usd,
        COALESCE(f.subscriptions_6m, 0) AS subscriptions_6m,
        COALESCE(r.net_redemption_months_6m, 0) AS net_redemption_months_6m,
        CASE WHEN ap.aum_6m_ago_usd > 0 THEN -COALESCE(f.net_flows_6m_usd, 0) / ap.aum_6m_ago_usd ELSE 0 END
            AS outflow_ratio_6m
    FROM Dim_Clients c
    JOIN aum_points ap            ON ap.client_id = c.client_id
    LEFT JOIN flows f             ON f.client_id = c.client_id
    LEFT JOIN redemption_months r ON r.client_id = c.client_id
)
SELECT
    m.*,
    CASE
        WHEN peak_aum_12m_usd > 0 AND aum_now_usd < 0.10 * peak_aum_12m_usd THEN 'Lost'
        WHEN outflow_ratio_6m >= 0.40 OR (net_redemption_months_6m >= 3 AND subscriptions_6m = 0) THEN 'High Risk'
        WHEN outflow_ratio_6m >= 0.15 THEN 'Watchlist'
        ELSE 'Healthy'
    END AS retention_status
FROM metrics m;
