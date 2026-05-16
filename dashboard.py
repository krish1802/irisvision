#!/usr/bin/env python3
"""
SEO Dashboard for irisvision.ai.


Reads the CSVs produced by:
  • crawl_script.py  → technical audit, page keywords, keyword clusters
  • bypass.py        → search-engine click-bot daily totals

Plus a live Google Analytics 4 section (via ga_client.py).


Run:
    streamlit run dashboard.py
"""


from __future__ import annotations


import csv
import os
import re
from datetime import datetime, timedelta, date


import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


from sites_config import SITE
from ga_client import (
    ga_is_configured,
    ga_daily_traffic,
    ga_totals,
    ga_top_pages,
    default_range,
)



# ──────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────


REPORTS_BASE = "seo_reports"
os.makedirs(REPORTS_BASE, exist_ok=True)



# ──────────────────────────────────────────────────────────────────────────
# REPORT LOADERS  (unchanged from your version)
# ──────────────────────────────────────────────────────────────────────────


def _site_dir() -> str:
    return SITE.output_dir(REPORTS_BASE)



def _find_csv(prefix_with_date: str) -> str | None:
    fname = f"{prefix_with_date}.csv"
    for d in (_site_dir(), REPORTS_BASE):
        path = os.path.join(d, fname)
        if os.path.exists(path):
            return path
    return None



def get_report_dates() -> list[str]:
    dates: set[str] = set()
    for d in (_site_dir(), REPORTS_BASE):
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
            if m:
                dates.add(m.group(1))
    return sorted(dates, reverse=True)



def load_csv(prefix: str, date_str: str) -> pd.DataFrame | None:
    path = _find_csv(f"{prefix}_{date_str}")
    return pd.read_csv(path) if path else None



def load_audit(date_str: str) -> pd.DataFrame | None:
    return load_csv(f"{SITE.domain}_technical_audit", date_str)



def load_keywords(date_str: str) -> pd.DataFrame | None:
    return load_csv(f"{SITE.domain}_page_keywords", date_str)



def load_clusters(date_str: str) -> pd.DataFrame | None:
    return load_csv(f"{SITE.domain}_keyword_clusters", date_str)



def _read_clickbot_csv(path: str) -> pd.DataFrame | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            rows = []
            for raw in reader:
                if not raw or raw[0].strip().lower() == "date":
                    continue
                if len(raw) >= 5:
                    rows.append(raw[:5])
                elif len(raw) == 4:
                    rows.append([raw[0], "", raw[1], raw[2], raw[3]])
        if not rows:
            return None
        df = pd.DataFrame(rows, columns=["date", "run_timestamp", "site", "engine", "clicks"])
        df["clicks"] = pd.to_numeric(df["clicks"], errors="coerce").fillna(0).astype(int)
        return df
    except Exception:
        return None



def load_clickbot_today() -> pd.DataFrame | None:
    today = datetime.today().strftime("%Y-%m-%d")
    path = _find_csv(f"traffic_generated_{today}")
    return _read_clickbot_csv(path) if path else None



def load_clickbot_window(days: int = 7) -> pd.DataFrame | None:
    frames: list[pd.DataFrame] = []
    today = datetime.today().date()
    for offset in range(days):
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        path = _find_csv(f"traffic_generated_{d}")
        if not path:
            continue
        frame = _read_clickbot_csv(path)
        if frame is None or frame.empty:
            continue
        if "date" not in frame.columns:
            frame["date"] = d
        frames.append(frame)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)



# ──────────────────────────────────────────────────────────────────────────
# SNAPSHOT HELPERS  (unchanged)
# ──────────────────────────────────────────────────────────────────────────


def compute_audit_snapshot(df: pd.DataFrame | None) -> dict | None:
    if df is None or len(df) == 0:
        return None
    total = len(df)
    broken = len(df[df["status"].astype(str).str.match(r"^[45E]")]) if "status" in df.columns else 0
    with_issues = len(df[df["issues"].astype(str).str.len() > 0]) if "issues" in df.columns else 0
    clean = total - with_issues

    load_col = "load_time_s" if "load_time_s" in df.columns else None
    if load_col:
        s = pd.to_numeric(df[load_col], errors="coerce")
        avg_load = s.mean()
        slow = int((s > 3.0).sum())
    else:
        avg_load = None
        slow = 0

    health = round(100 * clean / total, 1) if total else 0

    return {
        "total_pages": total,
        "clean_pages": clean,
        "pages_with_issues": with_issues,
        "broken_pages": broken,
        "avg_load_time": round(avg_load, 3) if pd.notna(avg_load) else None,
        "slow_pages": slow,
        "health_score": health,
    }



def load_audit_history() -> pd.DataFrame:
    rows = []
    for d in get_report_dates():
        snap = compute_audit_snapshot(load_audit(d))
        if snap:
            snap["date"] = d
            rows.append(snap)
    return pd.DataFrame(rows).sort_values("date") if rows else pd.DataFrame()



# ──────────────────────────────────────────────────────────────────────────
# GA4 CACHED WRAPPERS — keyed on (start, end) so date-range changes refetch
# ──────────────────────────────────────────────────────────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _ga_daily(start: str, end: str) -> pd.DataFrame:
    return ga_daily_traffic(start, end)


@st.cache_data(ttl=600, show_spinner=False)
def _ga_totals(start: str, end: str) -> dict:
    return ga_totals(start, end)


@st.cache_data(ttl=600, show_spinner=False)
def _ga_top_pages(start: str, end: str, limit: int) -> pd.DataFrame:
    return ga_top_pages(start, end, limit=limit)



# ──────────────────────────────────────────────────────────────────────────
# UI
# ──────────────────────────────────────────────────────────────────────────


st.set_page_config(
    page_title=f"{SITE.brand_name} SEO Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap');
    html, body, .stApp { font-family: 'DM Sans', sans-serif; }
    .seo-section-anchor { scroll-margin-top: 80px; padding-top: 1.5rem; }
    .site-pill {
        display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
        background: #eef5f5; color: #01696f; font-size: 0.75rem; font-weight: 500;
        margin-left: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)


# ─── Sidebar ───────────────────────────────────────────────────────────


with st.sidebar:
    st.markdown(f"## 🔍 {SITE.brand_name}")
    st.caption(SITE.site_description)
    st.markdown(f"**Domain:** [`{SITE.domain}`]({SITE.site_url})")
    st.divider()
    st.markdown("### Pipelines")
    st.code("python crawl_script.py", language="bash")
    st.code("python bypass.py", language="bash")
    st.caption(f"Reports root: `{REPORTS_BASE}/{SITE.slug}/`")

    st.divider()
    st.markdown("### Google Analytics")
    ga_ok, ga_reason = ga_is_configured()
    if ga_ok:
        st.success("GA4 connected")
        if st.button("🔄 Clear GA cache"):
            _ga_daily.clear(); _ga_totals.clear(); _ga_top_pages.clear()
            st.toast("GA cache cleared")
    else:
        st.warning("GA4 not configured")
        st.caption(ga_reason)



# ─── Header ────────────────────────────────────────────────────────────


st.markdown(
    f"# 📊 SEO Dashboard <span class='site-pill'>{SITE.brand_name}</span>",
    unsafe_allow_html=True,
)
st.markdown(f"**Site:** [`{SITE.domain}`]({SITE.site_url})")


dates = get_report_dates()
header_cols = st.columns([3, 1])
with header_cols[1]:
    selected_date = (
        st.selectbox("Report date", dates, index=0, key="date")
        if dates else datetime.today().strftime("%Y-%m-%d")
    )
if not dates:
    st.info(f"No reports yet. Run `python crawl_script.py` to populate `{REPORTS_BASE}/{SITE.slug}/`.")


st.caption("Public-web SEO toolkit + live GA4 analytics.")
st.divider()


# Jump links
st.markdown("""
<div style="margin-bottom: 1rem; font-size: 0.95rem;">
<strong>Jump to:</strong>
<a href="#overview">🏠 Overview</a> &nbsp;·&nbsp;
<a href="#analytics">📊 Analytics</a> &nbsp;·&nbsp;
<a href="#growth">📈 Growth</a> &nbsp;·&nbsp;
<a href="#audit">🔍 Audit</a> &nbsp;·&nbsp;
<a href="#content">📝 Content</a> &nbsp;·&nbsp;
<a href="#keywords">🔑 Keywords</a> &nbsp;·&nbsp;
<a href="#clickbot">🤖 Click bot</a>
</div>
""", unsafe_allow_html=True)
st.divider()



# ── 🏠 OVERVIEW ────────────────────────────────────────────────────────


st.markdown('<div id="overview" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 🏠 SEO Performance Overview")
st.markdown(f"**{SITE.domain}** — Report for **{selected_date}**")


audit_df = load_audit(selected_date) if dates else None


if audit_df is not None:
    snap = compute_audit_snapshot(audit_df) or {}
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pages Crawled", snap.get("total_pages", 0))
    c2.metric(
        "Clean Pages",
        snap.get("clean_pages", 0),
        delta=f"{snap.get('health_score', 0)}%",
    )
    c3.metric("Issues Found", snap.get("pages_with_issues", 0))
    c4.metric("Broken Pages", snap.get("broken_pages", 0))
    c5.metric(
        "Avg Load Time",
        f"{snap['avg_load_time']:.2f}s" if snap.get("avg_load_time") is not None else "N/A",
    )

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 📊 Issue Distribution")
        issue_labels: list[str] = []
        for iss_str in audit_df["issues"].fillna(""):
            for iss in str(iss_str).split(" | "):
                if iss.strip():
                    issue_labels.append(iss.strip())
        if issue_labels:
            issue_counts = pd.Series(issue_labels).value_counts().head(10).reset_index()
            issue_counts.columns = ["Issue", "Count"]
            fig = px.pie(issue_counts, names="Issue", values="Count", hole=0.45)
            st.plotly_chart(fig, use_container_width=True, key="overview_pie")
        else:
            st.success("No issues found.")

    with col2:
        st.markdown("### ⏱️ Load Times")
        lt = audit_df["load_time_s"].dropna() if "load_time_s" in audit_df else pd.Series(dtype=float)
        if len(lt) > 0:
            fig = px.histogram(
                lt, nbins=20, labels={"value": "Load Time (s)"},
                color_discrete_sequence=["#01696f"],
            )
            fig.add_vline(x=3.0, line_dash="dash", line_color="#da7101")
            st.plotly_chart(fig, use_container_width=True, key="overview_load")
else:
    st.warning("No audit CSV loaded yet.")


st.divider()



# ── 📊 ANALYTICS (GA4) ────────────────────────────────────────────────


st.markdown('<div id="analytics" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 📊 Analytics (Google Analytics 4)")


ga_ok, ga_reason = ga_is_configured()
if not ga_ok:
    st.warning(f"GA4 not configured — {ga_reason}")
    st.markdown(
        "Set the env vars **`GA_PROPERTY_ID`** and **`GA_CREDENTIALS_JSON`** "
        "(or fill them in `sites_config.SITE`) and install the SDK:\n\n"
        "```bash\npip install google-analytics-data\n```"
    )
else:
    # Date range picker
    default_start_str, default_end_str = default_range(28)
    default_start = datetime.strptime(default_start_str, "%Y-%m-%d").date()
    default_end = datetime.strptime(default_end_str, "%Y-%m-%d").date()

    preset_col, range_col = st.columns([1, 3])
    with preset_col:
        preset = st.selectbox(
            "Preset",
            ["Last 7 days", "Last 28 days", "Last 90 days", "Year to date", "Custom"],
            index=1,
            key="ga_preset",
        )
    today = date.today()
    if preset == "Last 7 days":
        ds, de = today - timedelta(days=6), today
    elif preset == "Last 28 days":
        ds, de = today - timedelta(days=27), today
    elif preset == "Last 90 days":
        ds, de = today - timedelta(days=89), today
    elif preset == "Year to date":
        ds, de = date(today.year, 1, 1), today
    else:
        ds, de = default_start, default_end

    with range_col:
        picked = st.date_input(
            "Date range",
            value=(ds, de),
            max_value=today,
            key="ga_range",
        )
    if isinstance(picked, tuple) and len(picked) == 2:
        ga_start, ga_end = picked
    else:
        ga_start, ga_end = ds, de

    s_str, e_str = ga_start.strftime("%Y-%m-%d"), ga_end.strftime("%Y-%m-%d")

    try:
        with st.spinner(f"Fetching GA4 data {s_str} → {e_str}…"):
            totals = _ga_totals(s_str, e_str)
            daily = _ga_daily(s_str, e_str)
            top_pages = _ga_top_pages(s_str, e_str, 25)
    except Exception as exc:
        st.error(f"GA4 query failed: {type(exc).__name__}: {exc}")
        totals, daily, top_pages = None, None, None

    if totals is not None:
        # Compute previous-period deltas
        span_days = (ga_end - ga_start).days + 1
        prev_end = ga_start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span_days - 1)
        try:
            prev_totals = _ga_totals(prev_start.strftime("%Y-%m-%d"), prev_end.strftime("%Y-%m-%d"))
        except Exception:
            prev_totals = None

        def _delta(curr, prev):
            if not prev:
                return None
            return curr - prev

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Sessions",
            f"{totals['sessions']:,}",
            delta=_delta(totals["sessions"], prev_totals["sessions"]) if prev_totals else None,
        )
        k2.metric(
            "Users",
            f"{totals['totalUsers']:,}",
            delta=_delta(totals["totalUsers"], prev_totals["totalUsers"]) if prev_totals else None,
        )
        k3.metric(
            "Pageviews",
            f"{totals['screenPageViews']:,}",
            delta=_delta(totals["screenPageViews"], prev_totals["screenPageViews"]) if prev_totals else None,
        )
        k4.metric(
            "New Users",
            f"{totals['newUsers']:,}",
            delta=_delta(totals["newUsers"], prev_totals["newUsers"]) if prev_totals else None,
        )
        if prev_totals:
            st.caption(
                f"Compared with previous {span_days} days "
                f"({prev_start:%Y-%m-%d} → {prev_end:%Y-%m-%d})."
            )

        st.markdown("### 📈 Daily traffic")
        if daily is None or daily.empty:
            st.info("No GA4 rows returned for this window.")
        else:
            metric_choice = st.multiselect(
                "Metrics",
                ["sessions", "totalUsers", "screenPageViews", "newUsers"],
                default=["sessions", "totalUsers", "screenPageViews"],
                key="ga_metric_pick",
            )
            if metric_choice:
                long_df = daily.melt(
                    id_vars="date", value_vars=metric_choice,
                    var_name="metric", value_name="value",
                )
                fig = px.line(
                    long_df, x="date", y="value", color="metric",
                    markers=True, title=f"GA4 daily metrics — {s_str} to {e_str}",
                )
                fig.update_layout(xaxis_title="Date", yaxis_title="")
                st.plotly_chart(fig, use_container_width=True, key="ga_daily_chart")
            with st.expander("📅 Daily table"):
                st.dataframe(daily, use_container_width=True, key="ga_daily_tbl")
                st.download_button(
                    "📥 Download daily CSV",
                    daily.to_csv(index=False).encode(),
                    f"ga_daily_{s_str}_to_{e_str}.csv",
                    "text/csv",
                    key="ga_daily_dl",
                )

        st.markdown("### 🏆 Top pages")
        if top_pages is None or top_pages.empty:
            st.info("No top-pages data for this window.")
        else:
            top_pages = top_pages.rename(columns={
                "pagePath": "Path",
                "screenPageViews": "Pageviews",
                "sessions": "Sessions",
                "totalUsers": "Users",
            })
            st.dataframe(top_pages, use_container_width=True, height=400, key="ga_top_tbl")


st.divider()



# ── 📈 GROWTH ──────────────────────────────────────────────────────────


st.markdown('<div id="growth" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 📈 Growth Tracker")


all_dates = get_report_dates()
if len(all_dates) < 2:
    st.info("Need at least 2 scans to track growth — run the crawler again tomorrow.")
else:
    audit_hist = load_audit_history()
    col_a, col_b = st.columns(2)
    with col_a:
        date_new = st.selectbox("Compare (newer)", all_dates, index=0, key="d_new")
    with col_b:
        older_options = [d for d in all_dates if d < date_new]
        date_old = st.selectbox("vs (older)", older_options, index=0, key="d_old") if older_options else None


    if date_old is None:
        st.warning("No older scan available.")
    else:
        snap_new = compute_audit_snapshot(load_audit(date_new))
        snap_old = compute_audit_snapshot(load_audit(date_old))
        if snap_new and snap_old:
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric(
                "Health %",
                snap_new["health_score"],
                delta=round(snap_new["health_score"] - snap_old["health_score"], 1),
            )
            c2.metric(
                "Pages",
                snap_new["total_pages"],
                delta=snap_new["total_pages"] - snap_old["total_pages"],
            )
            c3.metric(
                "Issues",
                snap_new["pages_with_issues"],
                delta=snap_new["pages_with_issues"] - snap_old["pages_with_issues"],
            )
            c4.metric(
                "Broken",
                snap_new["broken_pages"],
                delta=snap_new["broken_pages"] - snap_old["broken_pages"],
            )
            c5.metric(
                "Avg Load",
                snap_new["avg_load_time"],
                delta=round(
                    (snap_new["avg_load_time"] or 0) - (snap_old["avg_load_time"] or 0), 3
                ),
            )


        if not audit_hist.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=audit_hist["date"], y=audit_hist["health_score"],
                mode="lines+markers", name="Health %",
            ))
            fig.update_layout(title="Health score over time", yaxis_title="Health %")
            st.plotly_chart(fig, use_container_width=True, key="growth_health")


st.divider()



# ── 🔍 AUDIT ───────────────────────────────────────────────────────────


st.markdown('<div id="audit" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 🔍 Technical SEO Audit")


if audit_df is not None:
    c1, c2, c3 = st.columns(3)
    with c1:
        filt = st.selectbox("Filter", ["All", "With Issues", "Clean"], key="audit_filt")
    with c2:
        search = st.text_input("Search URL", key="audit_search")
    with c3:
        statuses = st.multiselect(
            "Status",
            sorted(audit_df["status"].astype(str).unique()),
            key="audit_statuses",
        )


    df_view = audit_df.copy()
    if filt == "With Issues":
        df_view = df_view[df_view["issues"].astype(str).str.len() > 0]
    elif filt == "Clean":
        df_view = df_view[(df_view["issues"].isna()) | (df_view["issues"].astype(str).str.len() == 0)]
    if statuses:
        df_view = df_view[df_view["status"].astype(str).isin(statuses)]
    if search:
        df_view = df_view[df_view["url"].str.contains(search, case=False, na=False)]


    st.markdown(f"**{len(df_view)} of {len(audit_df)} pages**")
    cols = [
        c for c in [
            "url", "status", "load_time_s", "title_length", "meta_desc_length",
            "h1_count", "images_missing_alt", "has_og_tags", "has_schema", "issues",
        ] if c in df_view.columns
    ]
    st.dataframe(df_view[cols], use_container_width=True, height=500, key="audit_tbl")
    st.download_button(
        "📥 Download CSV",
        df_view.to_csv(index=False).encode(),
        f"{SITE.domain}_audit_{selected_date}.csv",
        "text/csv",
        key="audit_dl",
    )
else:
    st.warning("No technical audit data found.")


st.divider()



# ── 📝 CONTENT ─────────────────────────────────────────────────────────


st.markdown('<div id="content" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 📝 Content Analysis")


kw_df = load_keywords(selected_date) if dates else None
if kw_df is not None and len(kw_df) > 0:
    c1, c2, c3 = st.columns(3)
    c1.metric("Pages", len(kw_df))
    c2.metric(
        "Avg Words",
        f"{kw_df['word_count'].mean():.0f}" if "word_count" in kw_df else "N/A",
    )
    c3.metric(
        "Total Words",
        f"{kw_df['word_count'].sum():,}" if "word_count" in kw_df else "N/A",
    )
    st.dataframe(kw_df, use_container_width=True, height=450, key="content_tbl")
else:
    st.info("No content analysis data found.")


st.divider()



# ── 🔑 KEYWORDS ────────────────────────────────────────────────────────


st.markdown('<div id="keywords" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 🔑 Keyword Clusters")


cl = load_clusters(selected_date) if dates else None
if cl is not None and len(cl) > 0:
    fig = px.treemap(
        cl.head(15), path=["cluster"], values="keyword_count", color="keyword_count",
    )
    st.plotly_chart(fig, use_container_width=True, key="kw_tree")
    st.dataframe(cl, use_container_width=True, key="kw_tbl")
else:
    st.info("No keyword cluster data found.")


st.markdown("### 🎯 Tracked Keywords")
st.write(", ".join(SITE.tracked_keywords))


st.divider()



# ── 🤖 CLICK BOT ───────────────────────────────────────────────────────


st.markdown('<div id="clickbot" class="seo-section-anchor"></div>', unsafe_allow_html=True)
st.markdown("## 🤖 Click bot results")


cf_today = load_clickbot_today()
if cf_today is None or len(cf_today) == 0:
    st.info(f"No click-bot CSV for today in `seo_reports/{SITE.slug}/`. Run `python bypass.py`.")
else:
    cf_today["clicks"] = pd.to_numeric(cf_today["clicks"], errors="coerce").fillna(0).astype(int)
    total_clicks = int(cf_today["clicks"].sum())
    by_engine = (
        cf_today.groupby("engine", as_index=False)["clicks"].sum().sort_values("clicks", ascending=False)
    )
    top_engine = by_engine.iloc[0]
    runs_today = cf_today["run_timestamp"].nunique() if "run_timestamp" in cf_today else 1


    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total clicks today", f"{total_clicks:,}")
    c2.metric("Engines tested", f"{len(by_engine):,}")
    c3.metric("Top engine", f"{top_engine['engine']} ({top_engine['clicks']})")
    c4.metric("Runs today", runs_today)


    fig_cf = px.bar(
        by_engine, x="engine", y="clicks", text="clicks",
        labels={"engine": "Engine", "clicks": "Clicks"},
        title="Click bot results, today", color="engine",
    )
    fig_cf.update_traces(textposition="outside")
    st.plotly_chart(fig_cf, use_container_width=True, key="overview_clickbot")
    st.dataframe(cf_today.reset_index(drop=True), use_container_width=True, height=250, key="cf_today_tbl")


st.markdown("### 📅 Trend (last 14 days)")
cf_window = load_clickbot_window(days=14)
if cf_window is None or cf_window.empty:
    st.info("No historical click-bot data yet.")
else:
    cf_window["clicks"] = pd.to_numeric(cf_window["clicks"], errors="coerce").fillna(0).astype(int)
    daily = cf_window.groupby(["date", "engine"], as_index=False)["clicks"].sum()
    fig = px.bar(
        daily.sort_values("date"),
        x="date", y="clicks", color="engine", barmode="stack",
        title="Daily click totals by engine",
    )
    st.plotly_chart(fig, use_container_width=True, key="cf_window_chart")
