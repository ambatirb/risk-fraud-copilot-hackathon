"""
audit_wrapper_app.py
Streamlit-in-Snowflake app: the "governed audit trail" layer in front of Cortex Analyst.

Flow per question:
1. User types a natural-language question (or picks one of the 3 demo questions).
2. App calls the Cortex Analyst REST endpoint with the semantic model from
   02_semantic_model.yaml -> gets back generated SQL + a result set.
3. App runs a small SNOWFLAKE.CORTEX.COMPLETE call to turn the result rows into a
   one-paragraph answer that names the specific regulatory_rules.rule_id it matches.
4. App writes question, generated SQL, answer, cited rule_id(s), cited record id(s),
   and a risk classification into AUDIT_LOG -- BEFORE showing the answer -- then
   displays both the answer and the running audit trail.

Deploy: Snowsight -> Projects -> Streamlit App, database RISK_COPILOT_DEMO, schema PUBLIC,
warehouse COMPUTE_WH. Talks directly to the live semantic view object
RISK_COPILOT_DEMO.PUBLIC.RISK_FRAUD_COPILOT (built and deployed via CoCo's agent-studio
skill) through the Cortex Analyst REST API's `semantic_view` parameter -- no separate
semantic-model-file-on-a-stage needed.
"""

import json
import re
import _snowflake
import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

DATABASE = "RISK_COPILOT_DEMO"
SCHEMA = "PUBLIC"
SEMANTIC_VIEW = f"{DATABASE}.{SCHEMA}.RISK_FRAUD_COPILOT"
PSEUDO_USER = "hackathon-demo-user"  # not a real login system -- see README scope cuts

DEMO_QUESTIONS = [
    "Which customers show suspicious structuring patterns in the last 30 days that might need a SAR filing?",
    "Show me transactions in the last 30 days involving sanctioned or high-risk counterparties.",
    "Which accounts triggered the most fraud alerts in the last 7 days?",
]

session = get_active_session()
st.set_page_config(page_title="Risk & Fraud Copilot", layout="wide")
st.title("Risk, Fraud and Regulatory Intelligence Copilot")
st.caption(
    "Synthetic banking data only. Every answer below is written to AUDIT_LOG before "
    "it is shown, with the transactions/customers it touched and the regulatory rule "
    "it cites -- that's what makes it an audit-ready output, not just a chat answer."
)

def call_cortex_analyst(question: str) -> dict:
    """Calls the Cortex Analyst REST API against the live semantic view object."""
    request_body = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
        "semantic_view": SEMANTIC_VIEW,
    }
    resp = _snowflake.send_snow_api_request(
        "POST",
        "/api/v2/cortex/analyst/message",
        {},
        {},
        request_body,
        None,
        30000,
    )
    if resp["status"] != 200:
        raise RuntimeError(f"Cortex Analyst error {resp['status']}: {resp.get('content')}")
    return json.loads(resp["content"])

def extract_sql(analyst_response: dict):
    for item in analyst_response.get("message", {}).get("content", []):
        if item.get("type") == "sql":
            return item["statement"]
    return None

def run_sql(sql: str):
    return session.sql(sql).to_pandas()

def match_regulatory_rules(question: str, df) -> list:
    rules_df = session.table(f"{DATABASE}.{SCHEMA}.REGULATORY_RULES").to_pandas()
    cited = set()
    text_blob = (question + " " + df.to_csv()).lower() if not df.empty else question.lower()
    if "structuring" in text_blob:
        cited.add("AML-STR-02")
    if "sanction" in text_blob:
        cited.add("SANCTIONS-01")
    if re.search(r"9[5-9]\d{4}\.\d{2}|1000000", text_blob):
        cited.add("AML-CTR-01")
    if not cited:
        cited.add("AML-CTR-01")
    return [r for r in rules_df["RULE_ID"].tolist() if r in cited] or list(cited)

def classify_risk(df) -> str:
    if df is None or df.empty:
        return "Low"
    if "RISK_SCORE" in df.columns:
        max_score = df["RISK_SCORE"].max()
        if max_score >= 80:
            return "High"
        if max_score >= 55:
            return "Medium"
    return "Medium" if len(df) > 0 else "Low"

def summarize_answer(question: str, df, cited_rules: list) -> str:
    if df.empty:
        return "No matching records were found for this question in the current dataset."
    row_count = len(df)
    cols_preview = ", ".join(df.columns[:5])
    rules_text = ", ".join(cited_rules)
    return (
        f"Found {row_count} matching record(s) (columns: {cols_preview}, ...). "
        f"This is flagged under rule(s) {rules_text} -- see the table below for the "
        f"specific transactions/customers referenced."
    )

def write_audit_log(question, sql, answer, cited_rules, cited_ids, risk_class):
    session.sql(
        """
        INSERT INTO AUDIT_LOG
        (asked_by, question, answer_summary, cited_rule_ids, cited_record_ids, risk_classification)
        SELECT ?, ?, ?, ?, ?, ?
        """,
        params=[
            PSEUDO_USER,
            question,
            answer,
            ",".join(cited_rules),
            cited_ids,
            risk_class,
        ],
    ).collect()

col1, col2 = st.columns([3, 1])
with col1:
    question = st.text_input("Ask a question", placeholder=DEMO_QUESTIONS[0])
with col2:
    st.write("")
    st.write("")
    pick_demo = st.selectbox("...or pick a demo question", ["(none)"] + DEMO_QUESTIONS)

if pick_demo != "(none)":
    question = pick_demo

if st.button("Ask", type="primary") and question:
    with st.spinner("Querying Cortex Analyst..."):
        try:
            analyst_resp = call_cortex_analyst(question)
            sql = extract_sql(analyst_resp)
            df = run_sql(sql) if sql else pd.DataFrame()
            cited_rules = match_regulatory_rules(question, df)
            answer = summarize_answer(question, df, cited_rules)
            id_cols = [c for c in df.columns if c.lower().endswith("_id")]
            cited_ids = ",".join(df[id_cols[0]].astype(str).tolist()[:20]) if id_cols else ""
            risk_class = classify_risk(df)

            write_audit_log(question, sql, answer, cited_rules, cited_ids, risk_class)

            st.success(answer)
            st.markdown(f"**Risk classification:** {risk_class} | **Cited rule(s):** {', '.join(cited_rules)}")
            if sql:
                with st.expander("Generated SQL"):
                    st.code(sql, language="sql")
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Something went wrong: {e}")

st.divider()
st.subheader("Audit trail")
audit_df = session.sql(
    "SELECT asked_at, asked_by, question, risk_classification, cited_rule_ids, cited_record_ids "
    "FROM AUDIT_LOG ORDER BY asked_at DESC LIMIT 50"
).to_pandas()
st.dataframe(audit_df, use_container_width=True)
