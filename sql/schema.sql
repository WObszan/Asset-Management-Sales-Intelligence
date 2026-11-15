-- Star schema for the Asset Management Sales Intelligence project (MySQL 8).
CREATE DATABASE IF NOT EXISTS sales_db;
USE sales_db;

DROP TABLE IF EXISTS Fact_Positions_Monthly;
DROP TABLE IF EXISTS Fact_Transactions;
DROP TABLE IF EXISTS Fact_Fund_Returns;
DROP TABLE IF EXISTS Dim_Advisor_Targets;
DROP TABLE IF EXISTS Dim_Clients;
DROP TABLE IF EXISTS Dim_Advisors;
DROP TABLE IF EXISTS Dim_Funds;
DROP TABLE IF EXISTS Dim_Date;

CREATE TABLE Dim_Date (
    date_id DATE PRIMARY KEY,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month_number INT NOT NULL,
    month_name VARCHAR(20) NOT NULL,
    year_month CHAR(7) NOT NULL,
    month_end DATE NOT NULL,
    day_of_week VARCHAR(20) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

CREATE TABLE Dim_Funds (
    fund_id INT PRIMARY KEY,
    fund_name VARCHAR(100) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    asset_class VARCHAR(30) NOT NULL,
    management_fee_bps INT NOT NULL,
    fund_risk_level INT NOT NULL
);

CREATE TABLE Dim_Advisors (
    advisor_id INT PRIMARY KEY,
    advisor_name VARCHAR(50) NOT NULL,
    advisor_surname VARCHAR(50) NOT NULL,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL
);

-- One relationship manager per client (same region and segment)
CREATE TABLE Dim_Clients (
    client_id INT PRIMARY KEY,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    risk_profile VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL,
    onboarding_date DATE NOT NULL,
    advisor_id INT NOT NULL,
    FOREIGN KEY (advisor_id) REFERENCES Dim_Advisors(advisor_id)
);

-- Yearly gross-sales targets per advisor
CREATE TABLE Dim_Advisor_Targets (
    advisor_id INT NOT NULL,
    year INT NOT NULL,
    target_usd DECIMAL(15,2) NOT NULL,
    PRIMARY KEY (advisor_id, year),
    FOREIGN KEY (advisor_id) REFERENCES Dim_Advisors(advisor_id)
);

CREATE TABLE Fact_Fund_Returns (
    fund_id INT NOT NULL,
    month_end DATE NOT NULL,
    monthly_return DECIMAL(10,6) NOT NULL,
    PRIMARY KEY (fund_id, month_end),
    FOREIGN KEY (fund_id) REFERENCES Dim_Funds(fund_id)
);

CREATE TABLE Fact_Transactions (
    transaction_id INT PRIMARY KEY,
    client_id INT NOT NULL,
    advisor_id INT NOT NULL,
    fund_id INT NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_type VARCHAR(20) NOT NULL,   -- 'Subscription' or 'Redemption'
    amount_usd DECIMAL(15,2) NOT NULL,
    FOREIGN KEY (client_id) REFERENCES Dim_Clients(client_id),
    FOREIGN KEY (advisor_id) REFERENCES Dim_Advisors(advisor_id),
    FOREIGN KEY (fund_id) REFERENCES Dim_Funds(fund_id),
    FOREIGN KEY (transaction_date) REFERENCES Dim_Date(date_id),
    INDEX idx_tx_client (client_id),
    INDEX idx_tx_advisor_date (advisor_id, transaction_date),
    INDEX idx_tx_date (transaction_date)
);

-- Month-end balance per client and fund (after flows and fund return); fee = avg balance x bps / 12
CREATE TABLE Fact_Positions_Monthly (
    client_id INT NOT NULL,
    fund_id INT NOT NULL,
    advisor_id INT NOT NULL,
    month_end DATE NOT NULL,
    aum_usd DECIMAL(15,2) NOT NULL,
    fee_usd DECIMAL(15,2) NOT NULL,
    PRIMARY KEY (client_id, fund_id, month_end),
    FOREIGN KEY (client_id) REFERENCES Dim_Clients(client_id),
    FOREIGN KEY (fund_id) REFERENCES Dim_Funds(fund_id),
    FOREIGN KEY (advisor_id) REFERENCES Dim_Advisors(advisor_id),
    INDEX idx_pos_month (month_end)
);
