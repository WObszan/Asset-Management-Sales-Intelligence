CREATE TABLE Dim_Clients (
    client_id INT AUTO_INCREMENT PRIMARY KEY,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL,
    risk_profile VARCHAR(30) NOT NULL,
    onboarding_date DATE NOT NULL,
    churn_risk_score DECIMAL(5,4) DEFAULT NULL
);

CREATE TABLE Dim_Funds (
    fund_id INT AUTO_INCREMENT PRIMARY KEY,
    fund_name VARCHAR(100) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    asset_class VARCHAR(30) NOT NULL,
    management_fee_bps INT NOT NULL,
    fund_risk_level INT NOT NULL
);

CREATE TABLE Dim_Advisors (
    advisor_id INT AUTO_INCREMENT PRIMARY KEY,
    advisor_name VARCHAR(50) NOT NULL,
    advisor_surname VARCHAR(50) NOT NULL,
    segment VARCHAR(30) NOT NULL,
    region VARCHAR(30) NOT NULL,
    country VARCHAR(30) NOT NULL,
    annual_target_usd DECIMAL(15,2) NOT NULL
);

CREATE TABLE Dim_Date (
    date_id DATE PRIMARY KEY,
    year INT NOT NULL,
    quarter INT NOT NULL,
    month_number INT NOT NULL,
    month_name VARCHAR(20),
    day_of_week VARCHAR(20),
    is_weekend BOOLEAN
);

CREATE TABLE Fact_Transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    client_id INT NOT NULL,
    advisor_id INT NOT NULL,
    fund_id INT NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    amount_usd DECIMAL(15,2) NOT NULL,
    fee_generated_usd DECIMAL(15,2) NOT NULL,

    FOREIGN KEY (client_id) REFERENCES Dim_Clients(client_id),
    FOREIGN KEY (advisor_id) REFERENCES Dim_Advisors(advisor_id),
    FOREIGN KEY (fund_id) REFERENCES Dim_Funds(fund_id),
    FOREIGN KEY (transaction_date) REFERENCES Dim_Date(date_id)
);