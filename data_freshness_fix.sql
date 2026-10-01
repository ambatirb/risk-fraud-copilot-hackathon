-- data_freshness_fix.sql
-- One-time fix for the hackathon demo: the synthetic FRAUD_ALERTS and TRANSACTIONS
-- timestamps were maxing out in the past, which made "last 7 days" demo questions
-- return 0 rows. This shifts all timestamps forward so the data's max date lines up
-- with "now". Re-run this before any demo/presentation if the data has gone stale
-- again (consider a Snowflake Task to automate this on a schedule).

USE DATABASE RISK_COPILOT_DEMO;
USE SCHEMA PUBLIC;

-- 1. Compute how many seconds to shift forward so MAX(timestamp) = CURRENT_TIMESTAMP().
SET offset_sec = (
    SELECT DATEDIFF(
        second,
        GREATEST(
            (SELECT MAX(CREATED_AT) FROM FRAUD_ALERTS),
            (SELECT MAX(TS) FROM TRANSACTIONS)
        ),
        CURRENT_TIMESTAMP()
    )
);

-- 2. Apply the shift to both tables.
UPDATE FRAUD_ALERTS SET CREATED_AT = DATEADD(second, $offset_sec, CREATED_AT);
UPDATE TRANSACTIONS SET TS = DATEADD(second, $offset_sec, TS);

-- 3. Verify the new date ranges now extend up to roughly the current date.
SELECT MIN(CREATED_AT), MAX(CREATED_AT) FROM FRAUD_ALERTS;
SELECT MIN(TS), MAX(TS) FROM TRANSACTIONS;
