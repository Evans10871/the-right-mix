import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.express as px
from recommendations import rank_recommendations, explain_recommendation

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
    # This export supplies separate totals at each hierarchy level.
    # Select those rows directly instead of summing totals with their children.
    if level == "Category":
        selected = df[(df["Category"] != "") & (df["Subcategory"] == "")]
    elif level == "Subcategory":
        selected = df[df["Subcategory"] != ""]
    else:
        selected = df[df["Category"] == ""]
    return selected.rename(columns={
        "Willow Sales": "willow_sales", "RM Sales": "rm_sales",
        "Willow Units": "willow_units", "RM Units": "rm_units",
        "Opportunity Gap": "opportunity",
        "Willow Sales Growth": "sales_growth_willow",
        "RM Sales Growth": "sales_growth_rm",
        "Willow Unit Growth": "unit_growth_willow",
        "RM Unit Growth": "unit_growth_rm",
        "Market Share": "market_share",
        "Willow AUP": "willow_aup", "RM AUP": "rm_aup",
    }).copy()


def combined_growth(rows, sales_column, growth_column):
    # Reconstruct prior-year dollars; aggregate growth is not a current-sales
    # weighted average. Missing rates make the combined comparison unavailable.
    if rows.empty or rows[[sales_column, growth_column]].isna().any().any():
        return np.nan
    factors = 1 + rows[growth_column] / 100
    if (factors <= 0).any():
        return np.nan
    prior = (rows[sales_column] / factors).sum()
    return (rows[sales_column].sum() / prior - 1) * 100 if prior else np.nan


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
    try:
        df = load_data(uploaded.getvalue() if uploaded else None)
    except (ValueError, OSError, KeyError) as error:
        st.error("The workbook could not be loaded. Upload a valid Fake Local Markets .xlsx workbook containing the 1-Chart-1 sheet.")
        st.caption(str(error))
        st.stop()

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

    # Category choices respond to the selected market(s) and department(s).
    category_source = df.copy()
    if selected_markets:
        category_source = category_source[category_source["Market"].isin(selected_markets)]
    if selected_departments:
        category_source = category_source[category_source["Department"].isin(selected_departments)]

    categories = sorted(
        category_source["Category"].replace("", np.nan).dropna().unique().tolist()
    )
    selected_categories = st.multiselect(
        "Category",
        categories,
        default=[],
        help="Choose one or several categories. Leave blank to include all categories.",
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
if selected_categories:
    # Keep both the selected category rows and their subcategory children.
    filtered = filtered[filtered["Category"].isin(selected_categories)]

if filtered.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# Use the appropriate supplied total rows without double-counting children.
# When Category is filtered, department-total rows are no longer present, so
# category-total rows provide the KPI base.
if selected_categories:
    totals = filtered[(filtered["Category"] != "") & (filtered["Subcategory"] == "")]
else:
    totals = filtered[filtered["Category"] == ""]
willow_sales = totals["Willow Sales"].sum()
rm_sales = totals["RM Sales"].sum()
opportunity = totals["Opportunity Gap"].sum()
share = willow_sales / (willow_sales + rm_sales) * 100 if (willow_sales + rm_sales) else np.nan
w_growth = combined_growth(totals, "Willow Sales", "Willow Sales Growth")
r_growth = combined_growth(totals, "RM Sales", "RM Sales Growth")

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

st.subheader("Recommended to Analyze")
st.caption("Investigation priorities based on opportunity dollars and growth gaps. These are starting points for analysis, not guaranteed sales gains.")
with st.expander("How recommendations are ranked"):
    st.write("Score (0–100): opportunity dollars contribute up to 50 points relative to the largest eligible opportunity; sales growth trailing RM contributes up to 30 points; unit growth trailing RM contributes up to 20 points. Growth gaps reach their maximum weight at 10 percentage points. High priority starts at 70; Medium at 40. Missing growth receives no points. Scores are relative to the current filters and minimum gap.")
    st.write("Price differences are investigation prompts, not score components or evidence of causation. An expected-share benchmark is not supplied, so share gaps are not scored. Category and subcategory comparisons use the workbook's supplied totals and growth rates.")
category_tab, subcategory_tab = st.tabs(["Categories", "Subcategories"])
subcategories = aggregate(filtered, "Subcategory")
for target, recommendation_level in [(category_tab, "Category"), (subcategory_tab, "Subcategory")]:
    with target:
        ranked = rank_recommendations(aggregate(filtered, recommendation_level), min_gap)
        if ranked.empty:
            st.info("No positive opportunities meet the minimum gap for these filters.")
        for position, (_, recommendation) in enumerate(ranked.head(5).iterrows(), start=1):
            label = f"{position}. {recommendation[recommendation_level]} • {recommendation['Market']} • {recommendation['Department']}"
            with st.expander(label, expanded=position == 1):
                st.write(f"**{recommendation['priority']} priority · {recommendation['score']:.1f}/100**")
                st.write(explain_recommendation(recommendation))
                if recommendation_level == "Category":
                    children = subcategories[
                        (subcategories["Market"] == recommendation["Market"])
                        & (subcategories["Department"] == recommendation["Department"])
                        & (subcategories["Category"] == recommendation["Category"])
                        & (subcategories["opportunity"] > 0)
                    ].nlargest(3, "opportunity")
                    st.write("**Subcategories with the largest positive opportunities**")
                    if children.empty:
                        st.caption("No positive subcategory opportunities available.")
                    else:
                        st.dataframe(children[["Subcategory", "opportunity"]].rename(columns={"opportunity": "Opportunity Gap $"}), hide_index=True, use_container_width=True)
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

# Growth in the workbook is expressed in percentage points (e.g. 8.8 means 8.8%).
# Exclude clearly malformed/extreme growth rows from this visualization so they
# cannot stretch the axes into the thousands of percent.
plot_df = plot_df[
    plot_df["sales_growth_willow"].between(-100, 100)
    & plot_df["sales_growth_rm"].between(-100, 100)
].copy()

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
fig2.update_xaxes(ticksuffix="%")
fig2.update_yaxes(ticksuffix="%")
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
