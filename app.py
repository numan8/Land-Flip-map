import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import json
from urllib.request import urlopen

st.set_page_config(
    page_title="Property Investment Intelligence",
    page_icon="🏡",
    layout="wide"
)

st.title("🏡 Property Investment Intelligence Dashboard")
st.write("County-level ROI, profit, velocity, and investment score analysis.")

DATA_PATH = "Cash Sales - AI Stats.xlsx"


def make_unique_columns(columns):
    seen = {}
    new_cols = []
    for col in columns:
        col = str(col).strip()
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    return new_cols


@st.cache_data
def load_data():
    df = pd.read_excel(DATA_PATH)
    df.columns = make_unique_columns(df.columns)
    return df


@st.cache_data
def load_county_geojson():
    url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
    with urlopen(url) as response:
        return json.load(response)


@st.cache_data
def load_fips_lookup():
    url = "https://raw.githubusercontent.com/kjhealy/fips-codes/master/county_fips_master.csv"
    fips = pd.read_csv(url, dtype={"fips": str})
    fips["county_name"] = (
        fips["name"]
        .astype(str)
        .str.replace(" County", "", regex=False)
        .str.replace(" Parish", "", regex=False)
        .str.replace(" Borough", "", regex=False)
        .str.strip()
        .str.upper()
    )
    fips["state"] = fips["state"].astype(str).str.upper().str.strip()
    fips["fips"] = fips["fips"].str.zfill(5)
    return fips[["fips", "county_name", "state"]]


df = load_data()

purchase_col = "Total Purchase Price"
sale_col = "Cash Sales Price - amount"
county_col = "County, State"
purchase_date_col = "PURCHASE DATE"
sale_date_col = "SALE DATE - start"

required_cols = [
    purchase_col,
    sale_col,
    county_col,
    purchase_date_col,
    sale_date_col
]

missing_cols = [col for col in required_cols if col not in df.columns]

if missing_cols:
    st.error(f"Missing required columns: {missing_cols}")
    st.stop()

df = df.dropna(subset=[purchase_col, sale_col, county_col]).copy()

df[purchase_col] = pd.to_numeric(df[purchase_col], errors="coerce")
df[sale_col] = pd.to_numeric(df[sale_col], errors="coerce")

df = df[(df[purchase_col] > 0) & (df[sale_col] > 0)].copy()

df["Profit"] = df[sale_col] - df[purchase_col]
df["ROI_%"] = (df["Profit"] / df[purchase_col]) * 100

df[purchase_date_col] = pd.to_datetime(df[purchase_date_col], errors="coerce")
df[sale_date_col] = pd.to_datetime(df[sale_date_col], errors="coerce")

df["Days_to_Sell"] = (df[sale_date_col] - df[purchase_date_col]).dt.days
df = df[df["Days_to_Sell"] >= 0].copy()

df["County_State_Clean"] = df[county_col].astype(str).str.strip()

split_cols = df["County_State_Clean"].str.split(",", expand=True, n=1)

df["County"] = split_cols[0].astype(str).str.strip()
df["State"] = split_cols[1].astype(str).str.strip() if split_cols.shape[1] > 1 else ""

df["County"] = (
    df["County"]
    .str.replace(" County", "", regex=False)
    .str.strip()
)

df["State"] = (
    df["State"]
    .astype(str)
    .str.upper()
    .str.replace(".", "", regex=False)
    .str.strip()
)

df["County_Key"] = df["County"].astype(str).str.upper().str.strip()

st.sidebar.header("Filters")

states = sorted(df["State"].dropna().unique())

selected_states = st.sidebar.multiselect(
    "Select State",
    states,
    default=states
)

df_filtered = df[df["State"].isin(selected_states)].copy()

if "Acres" in df_filtered.columns:
    df_filtered["Acres"] = pd.to_numeric(df_filtered["Acres"], errors="coerce")

    if df_filtered["Acres"].notna().sum() > 0:
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
        ].copy()

st.sidebar.subheader("Success Criteria")

roi_success = st.sidebar.number_input(
    "Minimum ROI % for Success",
    value=100
)

days_success = st.sidebar.number_input(
    "Maximum Days to Sell",
    value=180
)

min_deals = st.sidebar.number_input(
    "Minimum Deals per County",
    min_value=1,
    value=5
)

df_filtered["Successful_Deal"] = (
    (df_filtered["ROI_%"] >= roi_success) &
    (df_filtered["Days_to_Sell"] <= days_success)
)

county_summary = df_filtered.groupby(["County", "State", "County_Key"]).agg(
    Deals=("ROI_%", "count"),
    Avg_ROI=("ROI_%", "mean"),
    Median_ROI=("ROI_%", "median"),
    Avg_Profit=("Profit", "mean"),
    Total_Profit=("Profit", "sum"),
    Avg_Days_to_Sell=("Days_to_Sell", "mean"),
    Success_Rate=("Successful_Deal", "mean")
).reset_index()

county_summary["Success_Rate"] = county_summary["Success_Rate"] * 100

county_summary = county_summary[county_summary["Deals"] >= min_deals].copy()

if county_summary.empty:
    st.warning("No counties match the selected filters. Reduce minimum deals or adjust filters.")
    st.stop()

county_summary["ROI_Score"] = county_summary["Avg_ROI"].rank(pct=True) * 100
county_summary["Profit_Score"] = county_summary["Avg_Profit"].rank(pct=True) * 100
county_summary["Velocity_Score"] = county_summary["Avg_Days_to_Sell"].rank(
    ascending=False,
    pct=True
) * 100
county_summary["Success_Score"] = county_summary["Success_Rate"].rank(pct=True) * 100

county_summary["Investment_Score"] = (
    0.40 * county_summary["ROI_Score"] +
    0.25 * county_summary["Success_Score"] +
    0.20 * county_summary["Velocity_Score"] +
    0.15 * county_summary["Profit_Score"]
)

fips_lookup = load_fips_lookup()

county_summary = county_summary.merge(
    fips_lookup,
    left_on=["County_Key", "State"],
    right_on=["county_name", "state"],
    how="left"
)

matched_counties = county_summary["fips"].notna().sum()
total_counties = len(county_summary)

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Deals", f"{len(df_filtered):,}")
col2.metric("Avg ROI", f"{df_filtered['ROI_%'].mean():.1f}%")
col3.metric("Avg Profit", f"${df_filtered['Profit'].mean():,.0f}")
col4.metric("Avg Days to Sell", f"{df_filtered['Days_to_Sell'].mean():.0f}")
col5.metric("Ranked Counties", f"{total_counties:,}")

st.divider()

best_county = county_summary.sort_values("Investment_Score", ascending=False).iloc[0]

st.success(
    f"Top recommended county based on Investment Score: "
    f"{best_county['County']}, {best_county['State']} "
    f"with score {best_county['Investment_Score']:.1f}"
)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺 Investment Heat Map",
    "🏆 County Ranking",
    "📈 ROI Chart",
    "💰 Profit Chart",
    "📄 Raw Data"
])

with tab1:
    st.subheader("US County Investment Heat Map")

    metric_choice = st.selectbox(
        "Color map by",
        [
            "Investment_Score",
            "Avg_ROI",
            "Avg_Profit",
            "Success_Rate",
            "Avg_Days_to_Sell",
            "Deals"
        ]
    )

    map_data = county_summary.dropna(subset=["fips"]).copy()

    st.caption(
        f"County FIPS matched: {matched_counties} out of {total_counties} counties."
    )

    if map_data.empty:
        st.warning("No FIPS matches found. Check county/state formatting.")
    else:
        counties_geojson = load_county_geojson()

        fig_map = px.choropleth(
            map_data,
            geojson=counties_geojson,
            locations="fips",
            color=metric_choice,
            scope="usa",
            hover_name="County",
            hover_data={
                "State": True,
                "Deals": True,
                "Avg_ROI": ":.1f",
                "Avg_Profit": ":,.0f",
                "Avg_Days_to_Sell": ":.0f",
                "Success_Rate": ":.1f",
                "Investment_Score": ":.1f",
                "fips": False
            },
            color_continuous_scale="RdYlGn",
            title=f"County Heat Map by {metric_choice}"
        )

        fig_map.update_layout(
            margin={"r": 0, "t": 50, "l": 0, "b": 0},
            height=650
        )

        st.plotly_chart(fig_map, use_container_width=True)

with tab2:
    st.subheader("County Investment Ranking")

    county_summary_display = county_summary.sort_values(
        "Investment_Score",
        ascending=False
    ).copy()

    show_cols = [
        "County",
        "State",
        "Deals",
        "Avg_ROI",
        "Median_ROI",
        "Avg_Profit",
        "Total_Profit",
        "Avg_Days_to_Sell",
        "Success_Rate",
        "Investment_Score"
    ]

    st.dataframe(
        county_summary_display[show_cols].style.format({
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

with tab3:
    st.subheader("Top Counties by Average ROI")

    top_roi = county_summary.sort_values("Avg_ROI", ascending=False).head(20)

    fig_roi = px.bar(
        top_roi,
        x="Avg_ROI",
        y="County",
        orientation="h",
        color="Avg_ROI",
        hover_data=["State", "Deals", "Avg_Profit", "Success_Rate"],
        title="Top 20 Counties by Average ROI",
        color_continuous_scale="RdYlGn"
    )

    fig_roi.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_roi, use_container_width=True)

    st.subheader("ROI vs Days to Sell")

    fig_scatter = px.scatter(
        county_summary,
        x="Avg_Days_to_Sell",
        y="Avg_ROI",
        size="Deals",
        color="Investment_Score",
        hover_name="County",
        hover_data=["State", "Deals", "Avg_Profit", "Success_Rate"],
        title="High ROI + Fast Sale Counties",
        color_continuous_scale="RdYlGn"
    )

    st.plotly_chart(fig_scatter, use_container_width=True)

with tab4:
    st.subheader("Top Counties by Average Profit")

    top_profit = county_summary.sort_values("Avg_Profit", ascending=False).head(20)

    fig_profit = px.bar(
        top_profit,
        x="Avg_Profit",
        y="County",
        orientation="h",
        color="Avg_Profit",
        hover_data=["State", "Deals", "Avg_ROI", "Success_Rate"],
        title="Top 20 Counties by Average Profit",
        color_continuous_scale="RdYlGn"
    )

    fig_profit.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_profit, use_container_width=True)

with tab5:
    st.subheader("Filtered Raw Data")

    df_display = df_filtered.copy()
    df_display.columns = make_unique_columns(df_display.columns)

    st.dataframe(df_display, use_container_width=True)
