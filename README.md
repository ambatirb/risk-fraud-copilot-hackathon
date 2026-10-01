# Risk, Fraud & Regulatory Intelligence Copilot

AI-powered Risk, Fraud & Regulatory Intelligence Copilot built natively on Snowflake Cortex -- a hackathon prototype.

## What it does
A Streamlit-in-Snowflake app that lets a compliance/fraud analyst ask natural-language questions. It calls Cortex Analyst to generate SQL against a governed semantic view, summarizes the result with Cortex Complete, cites the matching regulatory rule, and writes every question/answer/citation into an AUDIT_LOG table before showing the answer -- so every response is audit-ready, not just a chat reply.

## Files
- `streamlit_app.py` -- the Streamlit-in-Snowflake app (audit wrapper around Cortex Analyst).
- `environment.yml` -- Snowflake Streamlit app package dependencies.
- `data_freshness_fix.sql` -- one-time maintenance script to shift the synthetic demo data's timestamps forward so relative-date questions (e.g. "last 7 days") keep returning results.

## Deploy
Snowsight -> Projects -> Streamlit App, database `RISK_COPILOT_DEMO`, schema `PUBLIC`, warehouse `COMPUTE_WH`. Requires a Cortex Analyst semantic view named `RISK_FRAUD_COPILOT` and tables `FRAUD_ALERTS`, `TRANSACTIONS`, `REGULATORY_RULES`, `AUDIT_LOG` in that schema.
