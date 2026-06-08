import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
from urllib.request import urlopen

st.set_page_config(
    page_title="Property ROI Heat Map",
    page_icon="🏡",
    layout="wide"
)

st.title("🏡 Property Investment ROI Heat Map")
st.write("County-level investment analysis using historical property purchase and cash sale data.")

DATA_PATH = "data/Cash Sales - AI Stats.xlsx"

@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH)
    return df

@st.cache_data
def load_geojson():
    url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
    with urlopen(url) as response:
        counties = json.load(response)
    return counties

df = load_data()

st.sidebar.header("Filters")

# Clean column names
df.columns = df.columns.str.strip()

# Expected columns
purchase_col = "Total Purchase Price"
sale_col = "Cash Sales Price - amount"
county_col = "County, State"
purchase_date_col = "PURCHASE DATE"
sale_date_col = "SALE DATE - start"

# Remove empty rows
df = df.dropna(subset=[purchase_col, sale_col, county_col])

# Convert numeric columns
df[purchase_col] = pd.to_numeric(df[purchase_col], errors="coerce")
df[sale_col] = pd.to_numeric(df[sale_col], errors="coerce")

df = df[(df[purchase_col] > 0) & (df[sale_col] > 0)]

# ROI and Profit
df["Profit"] = df[sale_col] - df[purchase_col]
df["ROI_%"] = (df["Profit"] / df[purchase_col]) * 100

# Dates
df[purchase_date_col] = pd.to_datetime(df[purchase_date_col], errors="coerce")
df[sale_date_col] = pd.to_datetime(df[sale_date_col], errors="coerce")

df["Days_to_Sell"] = (df[sale_date_col] - df[purchase_date_col]).dt.days
df = df[df["Days_to_Sell"] >= 0]

# Split County and State
df["County_State_Clean"] = df[county_col].astype(str).str.strip()

df[["County", "State"]] = df["County_State_Clean"].str.split(",", expand=True, n=1)
df["County"] = df["County"].str.strip()
df["State"] = df["State"].str.strip()

df["County"] = df["County"].str.replace(" County", "", regex=False)

# State filter
states = sorted(df["State"].dropna().unique())
selected_states = st.sidebar.multiselect(
    "Select State",
    states,
    default=states
)

df_filtered = df[df["State"].isin(selected_states)]

# Acre filter
if "Acres" in df_filtered.columns:
    df_filtered["Acres"] = pd.to_numeric(df_filtered["Acres"], errors="coerce")
    min_acre = float(df_filtered["Acres"].min())
    max_acre = float(df_filtered["Acres"].max())

    acre_range = st.sidebar.slider(
        "Acre Range",
        min_value=min_acre,
        max_value=max_acre,
        value=(min_acre, max_acre)
    )

    df_filtered = df_filtered[
        (df_filtered["Acres"] >= acre_range[0]) &
        (df_filtered["Acres"] <= acre_range[1])
    ]

# Success definition
st.sidebar.subheader("Success Criteria")

roi_success = st.sidebar.number_input(
    "Minimum ROI % for Success",
    value=100
)

days_success = st.sidebar.number_input(
    "Maximum Days to Sell",
    value=180
)

df_filtered["Successful_Deal"] = (
    (df_filtered["ROI_%"] >= roi_success) &
    (df_filtered["Days_to_Sell"] <= days_success)
)

# County summary
county_summary = df_filtered.groupby(["County", "State"]).agg(
    Deals=("ROI_%", "count"),
    Avg_ROI=("ROI_%", "mean"),
    Median_ROI=("ROI_%", "median"),
    Avg_Profit=("Profit", "mean"),
    Total_Profit=("Profit", "sum"),
    Avg_Days_to_Sell=("Days_to_Sell", "mean"),
    Success_Rate=("Successful_Deal", "mean")
).reset_index()

county_summary["Success_Rate"] = county_summary["Success_Rate"] * 100

# Investment score
county_summary["ROI_Score"] = county_summary["Avg_ROI"].rank(pct=True) * 100
county_summary["Profit_Score"] = county_summary["Avg_Profit"].rank(pct=True) * 100
county_summary["Velocity_Score"] = (
    county_summary["Avg_Days_to_Sell"].rank(ascending=False, pct=True) * 100
)
county_summary["Success_Score"] = county_summary["Success_Rate"].rank(pct=True) * 100

county_summary["Investment_Score"] = (
    0.40 * county_summary["ROI_Score"] +
    0.25 * county_summary["Success_Score"] +
    0.20 * county_summary["Velocity_Score"] +
    0.15 * county_summary["Profit_Score"]
)

# KPI cards
col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Deals", f"{len(df_filtered):,}")
col2.metric("Avg ROI", f"{df_filtered['ROI_%'].mean():.1f}%")
col3.metric("Avg Profit", f"${df_filtered['Profit'].mean():,.0f}")
col4.metric("Avg Days to Sell", f"{df_filtered['Days_to_Sell'].mean():.0f}")
col5.metric("Counties", f"{county_summary.shape[0]:,}")

st.divider()

# Important note
st.warning(
    "For real county-level map coloring, the dataset needs FIPS codes. "
    "This version prepares the full county summary. Add a FIPS lookup file to enable exact county map coloring."
)

# Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "County Ranking",
    "ROI Chart",
    "Profit Chart",
    "Raw Data"
])

with tab1:
    st.subheader("County Investment Ranking")

    county_summary_display = county_summary.sort_values(
        "Investment_Score",
        ascending=False
    )

    st.dataframe(
        county_summary_display.style.format({
            "Avg_ROI": "{:.1f}%",
            "Median_ROI": "{:.1f}%",
            "Avg_Profit": "${:,.0f}",
            "Total_Profit": "${:,.0f}",
            "Avg_Days_to_Sell": "{:.0f}",
            "Success_Rate": "{:.1f}%",
            "Investment_Score": "{:.1f}"
        }),
        use_container_width=True
    )

with tab2:
    st.subheader("Top Counties by Average ROI")

    top_roi = county_summary.sort_values("Avg_ROI", ascending=False).head(20)

    fig_roi = px.bar(
        top_roi,
        x="Avg_ROI",
        y="County",
        orientation="h",
        color="Avg_ROI",
        hover_data=["State", "Deals", "Avg_Profit", "Success_Rate"],
        title="Top 20 Counties by Average ROI"
    )

    fig_roi.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_roi, use_container_width=True)

with tab3:
    st.subheader("Top Counties by Average Profit")

    top_profit = county_summary.sort_values("Avg_Profit", ascending=False).head(20)

    fig_profit = px.bar(
        top_profit,
        x="Avg_Profit",
        y="County",
        orientation="h",
        color="Avg_Profit",
        hover_data=["State", "Deals", "Avg_ROI", "Success_Rate"],
        title="Top 20 Counties by Average Profit"
    )

    fig_profit.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_profit, use_container_width=True)

with tab4:
    st.subheader("Filtered Raw Data")
    st.dataframe(df_filtered, use_container_width=True)
