import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.express as px

st.set_page_config(
    page_title="The Right Mix",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR = Path(__file__).parent
DEFAULT_FILE = APP_DIR / "Fake Local Markets.xlsx"

COLUMN_NAMES = [
    "Market", "Department", "Category", "Subcategory",
    "Willow Sales", "RM Sales",
    "Willow Sales Growth", "RM Sales Growth",
    "Willow Units", "RM Units",
    "Willow Unit Growth", "RM Unit Growth",
    "Market Share", "Share Change",
    "Opportunity Gap", "Willow AUP", "RM AUP",
]

@st.cache_data(show_spinner="Loading market data…")
def load_data(file_bytes=None):
    if file_bytes is not None:
        from io import BytesIO
        source = BytesIO(file_bytes)
    else:
        source = DEFAULT_FILE

    df = pd.read_excel(
        source,
        sheet_name="1-Chart-1",
        header=None,
        skiprows=7,
        usecols="B:R",
        names=COLUMN_NAMES,
        engine="openpyxl",
    )

    df = df[df["Market"].notna()].copy()

    numeric_cols = [c for c in COLUMN_NAMES if c not in
                    ["Market", "Department", "Category", "Subcategory"]]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # The source contains spelling variants; the app presents the intended
    # fictional retailer name consistently.
    df["Market"] = df["Market"].astype(str).str.replace("_PRI", "", regex=False)
    df["Market"] = df["Market"].replace({
        "Williow Creak Foods": "Willow Creek Foods",
        "Williow Creek Foods": "Willow Creek Foods",
    })

    for c in ["Department", "Category", "Subcategory"]:
        df[c] = df[c].fillna("").astype(str).str.strip()

    return df


def money(x):
    if pd.isna(x):
        return "—"
    x = float(x)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_000_000:
        return f"{sign}${x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"{sign}${x/1_000:.0f}K"
    return f"{sign}${x:,.0f}"


def pct(x):
    if pd.isna(x):
        return "—"
    return f"{x:.1f}%"


def aggregate(df, level):
    group = ["Market", "Department"]
    if level in ["Category", "Subcategory"]:
        group.append("Category")
    if level == "Subcategory":
        group.append("Subcategory")

    agg = df.groupby(group, dropna=False).agg(
        willow_sales=("Willow Sales", "sum"),
        rm_sales=("RM Sales", "sum"),
        willow_units=("Willow Units", "sum"),
        rm_units=("RM Units", "sum"),
        opportunity=("Opportunity Gap", "sum"),
    ).reset_index()

    # Recalculate aggregate-level rates from aggregate dollars/units.
    agg["sales_growth_willow"] = np.nan
    agg["sales_growth_rm"] = np.nan
    agg["unit_growth_willow"] = np.nan
    agg["unit_growth_rm"] = np.nan

    # Weighted-average rates where source rates exist.
    work = df.copy()
    work["w_sales_growth_num"] = work["Willow Sales"] * work["Willow Sales Growth"] / 100
    work["r_sales_growth_num"] = work["RM Sales"] * work["RM Sales Growth"] / 100
    work["w_unit_growth_num"] = work["Willow Units"] * work["Willow Unit Growth"] / 100
    work["r_unit_growth_num"] = work["RM Units"] * work["RM Unit Growth"] / 100
    rates = work.groupby(group).agg(
        wsg=("w_sales_growth_num", "sum"),
        rsg=("r_sales_growth_num", "sum"),
        wug=("w_unit_growth_num", "sum"),
        rug=("r_unit_growth_num", "sum"),
    ).reset_index()
    agg = agg.merge(rates, on=group, how="left")
    agg["sales_growth_willow"] = np.where(
        agg["willow_sales"] != 0, agg["wsg"] / agg["willow_sales"] * 100, np.nan
    )
    agg["sales_growth_rm"] = np.where(
        agg["rm_sales"] != 0, agg["rsg"] / agg["rm_sales"] * 100, np.nan
    )
    agg["unit_growth_willow"] = np.where(
        agg["willow_units"] != 0, agg["wug"] / agg["willow_units"] * 100, np.nan
    )
    agg["unit_growth_rm"] = np.where(
        agg["rm_units"] != 0, agg["rug"] / agg["rm_units"] * 100, np.nan
    )

    total = agg["willow_sales"] + agg["rm_sales"]
    agg["market_share"] = np.where(total != 0, agg["willow_sales"] / total * 100, np.nan)

    return agg


st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .hero {
        padding: 1.2rem 1.4rem;
        border-radius: 14px;
        background: linear-gradient(120deg, #102a43, #1f4e79);
        color: white;
        margin-bottom: 1rem;
    }
    .hero h1 {margin: 0; font-size: 2.1rem;}
    .hero p {margin: .35rem 0 0; opacity: .9;}
    div[data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,.22);
        border-radius: 12px;
        padding: 10px 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><h1>The Right Mix</h1>'
    '<p>Find the fastest opportunities and performance gaps for Willow Creek Foods vs. the Remaining Market.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Controls")

    uploaded = st.file_uploader(
        "Use a different workbook",
        type=["xlsx"],
        help="Optional. The bundled workbook is used by default.",
    )
    df = load_data(uploaded.getvalue() if uploaded else None)

    markets = sorted(df["Market"].dropna().unique().tolist())
    selected_markets = st.multiselect(
        "Market",
        markets,
        default=markets,
        help="Choose one or several markets.",
    )

    departments = sorted(df["Department"].replace("", np.nan).dropna().unique().tolist())
    selected_departments = st.multiselect(
        "Department",
        departments,
        default=[],
    )

    level = st.radio(
        "Opportunity level",
        ["Category", "Subcategory"],
        index=1,
        horizontal=True,
    )

    min_gap = st.number_input(
        "Minimum opportunity gap ($)",
        min_value=-10_000_000.0,
        max_value=10_000_000.0,
        value=0.0,
        step=10_000.0,
        help="Use 0 to show positive opportunity only.",
    )

filtered = df.copy()
if selected_markets:
    filtered = filtered[filtered["Market"].isin(selected_markets)]
if selected_departments:
    filtered = filtered[filtered["Department"].isin(selected_departments)]

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# Overall KPIs
willow_sales = filtered["Willow Sales"].sum()
rm_sales = filtered["RM Sales"].sum()
opportunity = filtered["Opportunity Gap"].sum()
share = willow_sales / (willow_sales + rm_sales) * 100 if (willow_sales + rm_sales) else np.nan

# Weighted growth
w_growth = (
    (filtered["Willow Sales"] * filtered["Willow Sales Growth"]).sum()
    / filtered["Willow Sales"].sum()
    if filtered["Willow Sales"].sum() else np.nan
)
r_growth = (
    (filtered["RM Sales"] * filtered["RM Sales Growth"]).sum()
    / filtered["RM Sales"].sum()
    if filtered["RM Sales"].sum() else np.nan
)

st.caption(
    f"{len(filtered):,} source rows • "
    f"{len(selected_markets) if selected_markets else 0} selected market(s) • "
    f"Latest 52 weeks"
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Willow Creek Sales", money(willow_sales))
k2.metric("RM Sales", money(rm_sales))
k3.metric("Willow Share", pct(share))
k4.metric("Opportunity Gap", money(opportunity))
k5.metric("Sales Growth", pct(w_growth), f"RM {pct(r_growth)}")

st.divider()

agg = aggregate(filtered, level)

# Display labels
if level == "Category":
    agg["Mix"] = agg["Category"]
else:
    agg["Mix"] = agg["Subcategory"]

opp = agg[agg["opportunity"] >= min_gap].copy()
opp = opp.sort_values("opportunity", ascending=False)

left, right = st.columns([1.35, 1])

with left:
    st.subheader("Opportunity Finder")
    st.caption("Positive Opportunity Gap indicates estimated sales opportunity versus the Remaining Market.")

    display = opp.head(30).copy()
    display["Opportunity"] = display["opportunity"].map(money)
    display["Willow Sales"] = display["willow_sales"].map(money)
    display["RM Sales"] = display["rm_sales"].map(money)
    display["Willow Growth"] = display["sales_growth_willow"].map(pct)
    display["RM Growth"] = display["sales_growth_rm"].map(pct)
    display["Willow Share"] = display["market_share"].map(pct)

    cols = ["Market", "Mix", "Opportunity", "Willow Sales", "RM Sales",
            "Willow Growth", "RM Growth", "Willow Share"]
    st.dataframe(
        display[cols],
        use_container_width=True,
        hide_index=True,
        height=560,
    )

with right:
    st.subheader("Where to Look First")
    top = opp.head(12).copy()
    top["Label"] = top["Market"] + " • " + top["Mix"].str[:45]
    fig = px.bar(
        top.sort_values("opportunity"),
        x="opportunity",
        y="Label",
        orientation="h",
        labels={"opportunity": "Opportunity Gap $", "Label": ""},
        hover_data={
            "opportunity": ":$,.0f",
            "willow_sales": ":$,.0f",
            "rm_sales": ":$,.0f",
            "market_share": ":.1f",
        },
    )
    fig.update_layout(height=560, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Performance Comparison")
st.caption("Use this view to find categories where Willow is growing faster/slower than the Remaining Market.")

plot_df = agg.dropna(subset=["sales_growth_willow", "sales_growth_rm"]).copy()
plot_df["Mix"] = plot_df["Mix"].fillna("Unknown")
plot_df["Gap"] = plot_df["opportunity"].clip(lower=0)

fig2 = px.scatter(
    plot_df,
    x="sales_growth_rm",
    y="sales_growth_willow",
    size="rm_sales",
    color="Gap",
    hover_name="Mix",
    hover_data={
        "Market": True,
        "sales_growth_rm": ":.1f",
        "sales_growth_willow": ":.1f",
        "market_share": ":.1f",
        "opportunity": ":$,.0f",
        "rm_sales": ":$,.0f",
        "Gap": False,
    },
    labels={
        "sales_growth_rm": "Remaining Market Sales Growth %",
        "sales_growth_willow": "Willow Creek Sales Growth %",
        "Gap": "Opportunity Gap $",
        "rm_sales": "RM Sales",
    },
)
fig2.add_shape(
    type="line", x0=0, x1=1, y0=0, y1=1,
    xref="paper", yref="paper",
    line=dict(dash="dash")
)
fig2.update_layout(height=600)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Market / Mix Detail")
detail = agg.sort_values("opportunity", ascending=False).copy()
detail["Willow Sales"] = detail["willow_sales"].map(money)
detail["RM Sales"] = detail["rm_sales"].map(money)
detail["Opportunity Gap"] = detail["opportunity"].map(money)
detail["Willow Growth"] = detail["sales_growth_willow"].map(pct)
detail["RM Growth"] = detail["sales_growth_rm"].map(pct)
detail["Share"] = detail["market_share"].map(pct)
detail = detail.rename(columns={"Mix": "Category / Subcategory"})
st.dataframe(
    detail[[
        "Market", "Category / Subcategory", "Willow Sales", "RM Sales",
        "Opportunity Gap", "Willow Growth", "RM Growth", "Share"
    ]].head(100),
    use_container_width=True,
    hide_index=True,
)

st.caption("Source: supplied Fake Local Markets workbook. RM = Remaining Market.")
