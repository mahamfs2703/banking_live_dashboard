import streamlit as st
import altair as alt

st.set_page_config(page_title="Banking Live Dashboard", layout="wide")

st.markdown(
    """
<style>
.block-container { padding-top: 2rem; }

[data-testid="stMetric"] {
    background: #12304A;
    border: 1px solid rgba(20, 184, 166, 0.35);
    border-left: 4px solid #14B8A6;
    border-radius: 14px;
    padding: 16px 18px;
}
[data-testid="stMetricLabel"] { opacity: 0.8; }

div[class*="st-key-card_"] {
    background: #12304A;
    border: 1px solid rgba(20, 184, 166, 0.25);
    border-radius: 14px;
    padding: 14px 16px;
}

.pill {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
}
</style>
""",
    unsafe_allow_html=True,
)

conn = st.connection("snowflake")
TTL = 60


def run(sql):
    return conn.query(sql, ttl=TTL)


def num(v, decimals=0):
    if v is None or v != v:
        return "–"
    return f"{float(v):,.{decimals}f}"


def pct(v):
    return "–" if v is None or v != v else f"{float(v) * 100:.1f}%"


def delta_pct(cur, prev, prev_date):
    if cur is None or prev is None or cur != cur or prev != prev or prev == 0:
        return None
    return f"{(cur - prev) / prev * 100:+.1f}% vs {prev_date:%d %b}"


def delta_pp(cur, prev, prev_date):
    if cur is None or prev is None or cur != cur or prev != prev:
        return None
    return f"{(cur - prev) * 100:+.1f} pp vs {prev_date:%d %b}"


FRESH_SQL = """
select convert_timezone('Asia/Kolkata', max(fivetran_synced_at))::timestamp_ntz as synced_ist,
       datediff('minute', max(fivetran_synced_at), current_timestamp()) as mins_ago
from DB_BANKING.MARTS.FCT_TRANSACTIONS
"""

KPI_SQL = """
with daily as (
    select convert_timezone('Asia/Kolkata', transaction_ts)::date as d,
           count(*) as txn_count,
           coalesce(sum(case when is_completed then amount end), 0)::float as completed_amount,
           div0(count_if(is_completed), count(*))::float as success_rate,
           avg(case when is_completed then amount end)::float as avg_ticket
    from DB_BANKING.MARTS.FCT_TRANSACTIONS
    where not is_deleted
    group by 1
),
x as (
    select d as kpi_date, txn_count, completed_amount, success_rate, avg_ticket,
           lag(d) over (order by d) as prev_date,
           lag(txn_count) over (order by d) as p_txn,
           lag(completed_amount) over (order by d) as p_amount,
           lag(success_rate) over (order by d) as p_success,
           lag(avg_ticket) over (order by d) as p_ticket
    from daily
)
select x.*, convert_timezone('Asia/Kolkata', current_timestamp())::date as today_ist
from x
qualify kpi_date = max(kpi_date) over ()
"""

RECENT_SQL = """
select convert_timezone('Asia/Kolkata', f.transaction_ts)::timestamp_ntz as time_ist,
       f.transaction_id, f.transaction_type,
       coalesce(m.merchant_name, '–') as merchant,
       f.amount, f.status
from DB_BANKING.MARTS.FCT_TRANSACTIONS f
left join DB_BANKING.MARTS.DIM_MERCHANT m on m.merchant_key = f.merchant_key
where not f.is_deleted
order by f.transaction_ts desc
limit 20
"""

TOP_SQL = """
select merchant_name, completed_amount, completed_txn_count, merchant_rank
from DB_BANKING.MARTS.AGG_TOP_MERCHANTS
order by merchant_rank, merchant_name
limit 5
"""

STATUS_COLORS = {
    "COMPLETED": "#2FB36D",
    "PENDING": "#E5A93B",
    "FAILED": "#E05252",
    "REVERSED": "#8B84D6",
}

TREND_SQL = """
with bounds as (
  select max(minute_ts) as end_ts from DB_BANKING.MARTS.AGG_TXN_VOLUME_PER_MINUTE
),
minutes as (
  select dateadd('minute', -(row_number() over (order by seq4()) - 1), end_ts) as minute_ts
  from bounds, table(generator(rowcount => 60))
)
select convert_timezone('Asia/Kolkata', m.minute_ts)::timestamp_ntz as minute_ist,
       coalesce(a.txn_count, 0) as txn_count,
       coalesce(a.total_amount, 0) as total_amount
from minutes m
left join DB_BANKING.MARTS.AGG_TXN_VOLUME_PER_MINUTE a on a.minute_ts = m.minute_ts
order by minute_ist
"""

FAILED_SQL = """
with bounds as (
    select date_trunc('hour', convert_timezone('Asia/Kolkata', max(transaction_ts))::timestamp_ntz) as end_hr
    from DB_BANKING.MARTS.FCT_TRANSACTIONS
    where not is_deleted
),
hours as (
    select dateadd('hour', -(row_number() over (order by seq4()) - 1), end_hr) as hour_ist
    from bounds, table(generator(rowcount => 24))
),
agg as (
    select date_trunc('hour', convert_timezone('Asia/Kolkata', transaction_ts)::timestamp_ntz) as hour_ist,
           count(*) as txn_count,
           count_if(is_failed) as failed_count
    from DB_BANKING.MARTS.FCT_TRANSACTIONS
    where not is_deleted
    group by 1
)
select h.hour_ist, a.txn_count, a.failed_count,
       iff(a.txn_count > 0, a.failed_count / a.txn_count * 100, null)::float as failed_pct
from hours h
left join agg a on a.hour_ist = h.hour_ist
order by h.hour_ist
"""

# ---------- header ----------
left, right = st.columns([6, 1])
left.title("🏦 Banking Live Dashboard")
if right.button("🔄 Refresh"):
    st.cache_data.clear()

f = run(FRESH_SQL).iloc[0]
if f["SYNCED_IST"] is None or f["SYNCED_IST"] != f["SYNCED_IST"]:
    st.markdown(
        '<span class="pill" style="background:#8B84D622;color:#8B84D6;'
        'border:1px solid #8B84D6">No data synced yet</span>',
        unsafe_allow_html=True,
    )
else:
    mins = int(f["MINS_AGO"])
    c = "#2FB36D" if mins <= 420 else ("#E5A93B" if mins <= 780 else "#E05252")
    st.markdown(
        f'<span class="pill" style="background:{c}22;color:{c};border:1px solid {c}">'
        f'🔄 Last synced: {f["SYNCED_IST"]:%d %b %Y, %H:%M} IST</span>',
        unsafe_allow_html=True,
    )

# ---------- KPI cards ----------
kdf = run(KPI_SQL)
if kdf.empty:
    st.info("No transaction data yet.")
    st.stop()
k = kdf.iloc[0]

kd = k["KPI_DATE"]
pd_ = k["PREV_DATE"]
has_prev = pd_ is not None and pd_ == pd_
is_today = kd == k["TODAY_IST"]
when = "today" if is_today else f"on {kd:%d %b}"

if not is_today:
    st.caption(f"Showing data for {kd:%d %b %Y} (no transactions yet today, IST)")

c1, c2, c3, c4 = st.columns(4)
c1.metric(f"💳 Transactions {when}", num(k["TXN_COUNT"]),
          delta_pct(k["TXN_COUNT"], k["P_TXN"], pd_) if has_prev else None)
c2.metric(f"💰 Completed value {when}", "₹ " + num(k["COMPLETED_AMOUNT"], 2),
          delta_pct(k["COMPLETED_AMOUNT"], k["P_AMOUNT"], pd_) if has_prev else None)
c3.metric("✅ Success rate", pct(k["SUCCESS_RATE"]),
          delta_pp(k["SUCCESS_RATE"], k["P_SUCCESS"], pd_) if has_prev else None)
c4.metric("🎟️ Avg ticket size", "₹ " + num(k["AVG_TICKET"], 2),
          delta_pct(k["AVG_TICKET"], k["P_TICKET"], pd_) if has_prev else None)

st.write("")

# ---------- row 1: trend + failed rate ----------
col_a, col_b = st.columns(2)

with col_a:
    with st.container(key="card_trend"):
        st.subheader("📈 Transactions per minute")
        st.caption("Last 60 min of data, IST")
        t = run(TREND_SQL)
        if t.empty:
            st.info("No transaction data yet.")
        else:
            area = (
                alt.Chart(t)
                .mark_area(
                    line={"color": "#14B8A6", "strokeWidth": 2},
                    color=alt.Gradient(
                        gradient="linear",
                        stops=[
                            alt.GradientStop(color="rgba(20,184,166,0.55)", offset=0),
                            alt.GradientStop(color="rgba(20,184,166,0.02)", offset=1),
                        ],
                        x1=1, x2=1, y1=1, y2=0,
                    ),
                )
                .encode(
                    x=alt.X("MINUTE_IST:T", title=None,
                            axis=alt.Axis(format="%H:%M", grid=False, labelAngle=0)),
                    y=alt.Y("TXN_COUNT:Q", title=None,
                            axis=alt.Axis(gridColor="#1D4466")),
                    tooltip=[
                        alt.Tooltip("MINUTE_IST:T", title="Minute (IST)", format="%d %b %H:%M"),
                        alt.Tooltip("TXN_COUNT:Q", title="Transactions"),
                        alt.Tooltip("TOTAL_AMOUNT:Q", title="Amount (₹)", format=",.2f"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(area)

with col_b:
    with st.container(key="card_failed"):
        st.subheader("⚠️ Failed rate by hour")
        st.caption("Last 24 h of data, IST. Empty hours had no transactions.")
        fr = run(FAILED_SQL)
        if fr["TXN_COUNT"].isna().all():
            st.info("No transaction data yet.")
        else:
            bars = (
                alt.Chart(fr)
                .mark_bar(color="#E05252", size=18,
                          cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("HOUR_IST:T", title=None,
                            axis=alt.Axis(format="%H:%M", grid=False, labelAngle=0)),
                    y=alt.Y("FAILED_PCT:Q", title=None,
                            scale=alt.Scale(domainMin=0),
                            axis=alt.Axis(gridColor="#1D4466",
                                          labelExpr="datum.value + '%'")),
                    tooltip=[
                        alt.Tooltip("HOUR_IST:T", title="Hour (IST)", format="%d %b %H:00"),
                        alt.Tooltip("TXN_COUNT:Q", title="Transactions"),
                        alt.Tooltip("FAILED_COUNT:Q", title="Failed"),
                        alt.Tooltip("FAILED_PCT:Q", title="Failed %", format=".1f"),
                    ],
                )
                .properties(height=300)
            )
            st.altair_chart(bars)

# ---------- row 2: top merchants + recent transactions ----------
col_c, col_d = st.columns([4, 6])

with col_c:
    with st.container(key="card_merchants"):
        st.subheader("🏆 Top 5 merchants")
        st.caption("By completed value (₹)")
        m = run(TOP_SQL)
        if m.empty:
            st.info("No completed transactions yet.")
        else:
            top = (
                alt.Chart(m)
                .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                .encode(
                    x=alt.X("MERCHANT_NAME:N", sort="-y", title=None,
                            axis=alt.Axis(labelAngle=-30, labelLimit=110, grid=False)),
                    y=alt.Y("COMPLETED_AMOUNT:Q", title=None,
                            axis=alt.Axis(gridColor="#1D4466")),
                    color=alt.Color("MERCHANT_RANK:Q", legend=None,
                                    scale=alt.Scale(range=["#14B8A6", "#0B5F59"])),
                    tooltip=[
                        alt.Tooltip("MERCHANT_NAME:N", title="Merchant"),
                        alt.Tooltip("COMPLETED_AMOUNT:Q", title="Completed (₹)", format=",.2f"),
                        alt.Tooltip("COMPLETED_TXN_COUNT:Q", title="Transactions"),
                    ],
                )
                .properties(height=360)
            )
            st.altair_chart(top)

with col_d:
    with st.container(key="card_table"):
        st.subheader("🧾 Recent transactions")
        st.caption("Latest 20, IST")
        r = run(RECENT_SQL)
        if r.empty:
            st.info("No transactions yet.")
        else:
            styled = r.style.map(
                lambda s: f"color: {STATUS_COLORS.get(s, '#E8EEF4')}; font-weight: 600",
                subset=["STATUS"],
            )
            st.dataframe(
                styled,
                hide_index=True,
                height=420,
                column_config={
                    "TIME_IST": st.column_config.DatetimeColumn("Time", format="DD MMM, HH:mm:ss"),
                    "TRANSACTION_ID": "ID",
                    "TRANSACTION_TYPE": "Type",
                    "MERCHANT": "Merchant",
                    "AMOUNT": st.column_config.NumberColumn("Amount (₹)", format="%.2f"),
                    "STATUS": "Status",
                },
            )