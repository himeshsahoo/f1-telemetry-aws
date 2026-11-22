#!/usr/bin/env python3
"""
Streamlit F1 Telemetry & Strategy Dashboard
-------------------------------------------
Supports both:
1. Local / Offline Parquet Mode (Free, 100% offline, zero cloud setup needed)
2. Live AWS DynamoDB Mode (Queries partition key race_id in AWS Free Tier)

Visualizes:
- Driver comparison lap-time telemetry
- Interactive tire stint timelines with Pirelli compound styling
- Tire degradation linear regression slopes (s/lap)
- Theoretical vs actual best sectors and race pace distributions
"""

import glob
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Add directories to path for imports
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
LAMBDA_DIR = PROJECT_ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from components.header import render_dashboard_header
from components.stint_chart import render_stint_strategy_chart
from components.degradation_view import render_degradation_summary
from components.telemetry_trace import render_driver_telemetry_trace_comparison

from process_stints import (
    calculate_tire_degradation_slope,
    process_laps_dataframe,
)

# -----------------------------------------------------------------------------
# Configuration & Constants
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="F1 Telemetry & Strategy Pipeline",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Official Pirelli F1 Compound Colors
COMPOUND_COLORS = {
    "SOFT": "#FF1801",        # Bright Red
    "MEDIUM": "#FFF200",      # Yellow
    "HARD": "#EBEBEB",        # White / Light Silver
    "INTERMEDIATE": "#39B54A",# Green
    "WET": "#00A3E0",         # Cyan / Blue
    "UNKNOWN": "#888888",     # Grey
}

# F1 Constructor Team Colors
TEAM_COLORS = {
    "Red Bull Racing": "#3671C6",
    "Ferrari": "#E8002D",
    "Mercedes": "#6CD3BF",
    "Aston Martin": "#358C75",
    "McLaren": "#FF8000",
    "Alpine": "#2293D1",
    "Williams": "#64C4FF",
    "Haas": "#B6BABD",
    "Alfa Romeo": "#C92D4B",
    "AlphaTauri": "#5E8FAA",
    "Kick Sauber": "#52E252",
    "RB": "#6692FF",
}

DRIVER_COLORS = {
    "VER": "#3671C6",
    "PER": "#1B4F8C",
    "HAM": "#6CD3BF",
    "RUS": "#2AB093",
    "LEC": "#E8002D",
    "SAI": "#9E001F",
    "ALO": "#358C75",
    "STR": "#1C5243",
    "NOR": "#FF8000",
    "PIA": "#B35A00",
}


# -----------------------------------------------------------------------------
# Helper Functions: Data Loading & Conversion
# -----------------------------------------------------------------------------
def format_seconds_to_laptime(seconds: Optional[float]) -> str:
    """Formats float seconds into standard M:SS.mmm lap time string."""
    if seconds is None or np.isnan(seconds) or seconds <= 0:
        return "--:--.---"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:06.3f}"


def decimal_to_float(obj: Any) -> Any:
    """Recursively converts Decimal instances from DynamoDB to floats/ints."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(v) for v in obj]
    return obj


@st.cache_data(show_spinner=False)
def load_parquet_offline(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Loads a local Parquet file and runs the processor logic in-memory."""
    df = pd.read_parquet(file_path)
    stint_items, lap_items = process_laps_dataframe(df)

    stints_clean = [decimal_to_float(item) for item in stint_items]
    laps_clean = [decimal_to_float(item) for item in lap_items]

    stints_df = pd.DataFrame(stints_clean)
    laps_df = pd.DataFrame(laps_clean)
    return stints_df, laps_df


def load_dynamodb_live(table_name: str, race_id: str, region: str = "ap-south-1") -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Queries live DynamoDB table for partition key race_id."""
    import boto3
    from boto3.dynamodb.conditions import Key

    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    response = table.query(
        KeyConditionExpression=Key("race_id").eq(race_id)
    )
    items = response.get("Items", [])

    # Handle pagination if items > 1MB
    while "LastEvaluatedKey" in response:
        response = table.query(
            KeyConditionExpression=Key("race_id").eq(race_id),
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    stint_items = []
    lap_items = []

    for item in items:
        clean = decimal_to_float(item)
        entity_type = clean.get("entity_type", "")
        if entity_type == "STINT_SUMMARY":
            stint_items.append(clean)
        elif entity_type == "LAP_RECORD":
            lap_items.append(clean)

    stints_df = pd.DataFrame(stint_items)
    laps_df = pd.DataFrame(lap_items)
    return stints_df, laps_df


# -----------------------------------------------------------------------------
# Streamlit UI Header & Styling
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(90deg, #FF1801, #FF8000, #FFF200);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .sub-header {
        color: #8b949e;
        font-size: 1rem;
        margin-top: -10px;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px;
        text-align: center;
    }
    .metric-val {
        font-size: 1.6rem;
        font-weight: 700;
        color: #f0f6fc;
    }
    .metric-lbl {
        font-size: 0.85rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-header">🏎️ Serverless F1 Telemetry & Strategy Pipeline</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">AWS Free-Tier Event-Driven Architecture • S3 • DynamoDB • Lambda • Athena</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Sidebar: Mode & Filters
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Data Source & Settings")

    data_mode = st.radio(
        "Operating Mode",
        ["Offline Parquet (Local)", "AWS DynamoDB (Live)"],
        index=0,
        help="Choose between 100% offline local Parquet files or live AWS DynamoDB queries.",
    )

    stints_df = pd.DataFrame()
    laps_df = pd.DataFrame()
    current_race_id = "season#2023#round#1#session#R"

    if data_mode == "Offline Parquet (Local)":
        st.caption("📂 Offline Parquet Mode (Free, no AWS credentials required)")

        # Scan for existing parquet files
        discovered_files = list(Path(PROJECT_ROOT).glob("data/**/*.parquet"))
        file_options = {str(f.relative_to(PROJECT_ROOT)): str(f) for f in discovered_files}

        if file_options:
            selected_file_label = st.selectbox(
                "Select Parquet File",
                options=list(file_options.keys()),
                index=0,
            )
            selected_path = file_options[selected_file_label]
            try:
                stints_df, laps_df = load_parquet_offline(selected_path)
                st.success(f"Loaded {len(laps_df)} laps from local Parquet!")
            except Exception as e:
                st.error(f"Failed to load file: {e}")
        else:
            st.warning("No local Parquet files found in data/. Run ingest/ingest_f1_telemetry.py --dry-run --mock")

        # Custom file uploader option
        uploaded_file = st.file_uploader("Or Upload Custom .parquet File", type=["parquet"])
        if uploaded_file is not None:
            try:
                temp_df = pd.read_parquet(uploaded_file)
                stints_raw, laps_raw = process_laps_dataframe(temp_df)
                stints_df = pd.DataFrame([decimal_to_float(i) for i in stints_raw])
                laps_df = pd.DataFrame([decimal_to_float(i) for i in laps_raw])
                st.success(f"Custom file loaded: {len(laps_df)} laps.")
            except Exception as e:
                st.error(f"Error parsing uploaded file: {e}")

    else:
        st.caption("☁️ AWS Live DynamoDB Mode")
        aws_region = st.text_input("AWS Region", value=os.getenv("AWS_DEFAULT_REGION", "ap-south-1"))
        table_name = st.text_input("DynamoDB Table", value=os.getenv("F1_DYNAMODB_TABLE", "f1-telemetry-stints"))
        current_race_id = st.text_input("Race Partition Key (race_id)", value="season#2023#round#1#session#R")

        if st.button("🚀 Query DynamoDB", type="primary"):
            try:
                with st.spinner("Querying DynamoDB..."):
                    stints_df, laps_df = load_dynamodb_live(table_name, current_race_id, region=aws_region)
                if not laps_df.empty:
                    st.success(f"Fetched {len(laps_df)} laps and {len(stints_df)} stints!")
                else:
                    st.warning("No records returned. Check partition key or run ingestion pipeline.")
            except Exception as e:
                st.error(f"AWS DynamoDB Query Error: {e}")
                st.info("💡 Tip: Switch to 'Offline Parquet (Local)' mode to explore the dataset without AWS credentials.")

    st.divider()

    # Driver & Lap Filter Controls
    selected_drivers = []
    if not laps_df.empty and "driver" in laps_df.columns:
        all_drivers = sorted(laps_df["driver"].unique().tolist())
        st.subheader("🏎️ Driver Selection")
        col_all, col_none = st.columns(2)
        if col_all.button("Select All"):
            st.session_state["sel_drivers"] = all_drivers
        if col_none.button("Clear"):
            st.session_state["sel_drivers"] = [all_drivers[0]] if all_drivers else []

        default_sel = st.session_state.get("sel_drivers", all_drivers[:4] if len(all_drivers) >= 4 else all_drivers)
        selected_drivers = st.multiselect("Drivers to Compare", options=all_drivers, default=default_sel)

        clean_only = st.checkbox("Accurate Green-Flag Laps Only", value=True, help="Excludes pit in/out laps and yellow/SC laps.")


# -----------------------------------------------------------------------------
# Empty State Check
# -----------------------------------------------------------------------------
if laps_df.empty:
    st.info("👋 Welcome to the Serverless F1 Telemetry Pipeline Dashboard!")
    st.markdown(
        """
        To visualize race data:
        1. **Run Ingestion Locally (Dry-Run / Offline)**:
           ```bash
           python ingest/ingest_f1_telemetry.py --year 2023 --round 1 --session R --dry-run --mock
           ```
        2. Refresh this page or choose the generated parquet file in the sidebar.
        """
    )
    st.stop()


# -----------------------------------------------------------------------------
# Filter Laps according to user sidebar options
# -----------------------------------------------------------------------------
filtered_laps = laps_df.copy()
if selected_drivers:
    filtered_laps = filtered_laps[filtered_laps["driver"].isin(selected_drivers)]

if clean_only and "is_accurate" in filtered_laps.columns:
    filtered_laps = filtered_laps[
        (filtered_laps["is_accurate"] == True)
        & (~filtered_laps["is_pit_in"])
        & (~filtered_laps["is_pit_out"])
        & (filtered_laps["lap_time_sec"].notna())
    ]

# -----------------------------------------------------------------------------
# Top KPI Row
# -----------------------------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

total_laps = len(laps_df)
drivers_count = laps_df["driver"].nunique() if "driver" in laps_df.columns else 0

fastest_lap_row = None
if not filtered_laps.empty and "lap_time_sec" in filtered_laps.columns:
    valid_times = filtered_laps[filtered_laps["lap_time_sec"] > 50]
    if not valid_times.empty:
        fastest_lap_row = valid_times.loc[valid_times["lap_time_sec"].idxmin()]

with col1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-lbl">Total Laps Recorded</div>
            <div class="metric-val">{total_laps:,}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:
    fastest_time_str = format_seconds_to_laptime(fastest_lap_row["lap_time_sec"]) if fastest_lap_row is not None else "--:--.---"
    fastest_driver_str = fastest_lap_row["driver"] if fastest_lap_row is not None else "N/A"
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-lbl">Fastest Lap</div>
            <div class="metric-val">{fastest_time_str} <span style="font-size:1rem;color:#FF8000">({fastest_driver_str})</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:
    stint_count = len(stints_df) if not stints_df.empty else 0
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-lbl">Stints Analyzed</div>
            <div class="metric-val">{stint_count}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col4:
    best_deg_str = "N/A"
    if not stints_df.empty and "degradation_slope_sec_per_lap" in stints_df.columns:
        valid_deg = stints_df[stints_df["green_flag_laps"] >= 8]
        if not valid_deg.empty:
            min_deg_row = valid_deg.loc[valid_deg["degradation_slope_sec_per_lap"].idxmin()]
            best_deg_str = f"{min_deg_row['driver']} (+{min_deg_row['degradation_slope_sec_per_lap']:.3f} s/lap)"

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-lbl">Lowest Tire Degradation</div>
            <div class="metric-val" style="font-size:1.2rem;padding-top:6px">{best_deg_str}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")

# -----------------------------------------------------------------------------
# Main Tabs
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "⏱️ Lap Times & Pace",
    "🛞 Stint Strategy Timeline",
    "📉 Tire Degradation Analysis",
    "🔍 Raw Data & Athena SQL",
])

# -----------------------------------------------------------------------------
# TAB 1: Lap Times & Pace
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Driver Lap Time Progression")

    if filtered_laps.empty:
        st.warning("No lap data available for selected driver filters.")
    else:
        fig_laps = px.line(
            filtered_laps,
            x="lap_number",
            y="lap_time_sec",
            color="driver",
            color_discrete_map=DRIVER_COLORS,
            markers=True,
            hover_data=["compound", "tyre_life", "stint"],
            labels={
                "lap_number": "Lap Number",
                "lap_time_sec": "Lap Time (Seconds)",
                "driver": "Driver",
                "compound": "Tire Compound",
                "tyre_life": "Tyre Life",
            },
            title="Lap Times by Lap Number (Pace Progression)",
        )
        fig_laps.update_layout(
            template="plotly_dark",
            hovermode="x unified",
            margin=dict(l=40, r=40, t=50, b=40),
            yaxis=dict(autorange="reversed", title="Lap Time (Lower is Faster) [s]"),
        )
        st.plotly_chart(fig_laps, use_container_width=True)

        col_box, col_sec = st.columns(2)
        with col_box:
            st.subheader("Pace Distribution per Compound")
            fig_box = px.box(
                filtered_laps,
                x="compound",
                y="lap_time_sec",
                color="compound",
                color_discrete_map=COMPOUND_COLORS,
                points="all",
                labels={"compound": "Compound", "lap_time_sec": "Lap Time (s)"},
                title="Lap Time Consistency per Tire Compound",
            )
            fig_box.update_layout(template="plotly_dark", showlegend=False)
            st.plotly_chart(fig_box, use_container_width=True)

        with col_sec:
            st.subheader("Sector Pace Breakdown")
            if "sector1_time_sec" in filtered_laps.columns:
                sector_summary = (
                    filtered_laps.groupby("driver")[["sector1_time_sec", "sector2_time_sec", "sector3_time_sec"]]
                    .mean()
                    .reset_index()
                )
                fig_bar = px.bar(
                    sector_summary,
                    x="driver",
                    y=["sector1_time_sec", "sector2_time_sec", "sector3_time_sec"],
                    barmode="stack",
                    title="Average Sector Time Distribution (s)",
                    labels={"value": "Seconds", "variable": "Sector"},
                )
                fig_bar.update_layout(template="plotly_dark")
                st.plotly_chart(fig_bar, use_container_width=True)


# -----------------------------------------------------------------------------
# TAB 2: Stint Strategy Timeline
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Tire Stint Strategy Timeline")

    if stints_df.empty:
        st.warning("No stint data available.")
    else:
        stints_display = stints_df.copy()
        if selected_drivers and "driver" in stints_display.columns:
            stints_display = stints_display[stints_display["driver"].isin(selected_drivers)]

        # Sort drivers for clean Gantt display
        stints_display = stints_display.sort_values(by=["driver", "stint"])

        # Timeline Bar Chart
        fig_timeline = go.Figure()

        for _, row in stints_display.iterrows():
            driver = row["driver"]
            start_lap = row["start_lap"]
            end_lap = row["end_lap"]
            length = end_lap - start_lap + 1
            compound = str(row["compound"]).upper()
            color = COMPOUND_COLORS.get(compound, "#888888")

            hover_text = (
                f"<b>{driver} - Stint {row['stint']}</b><br>"
                f"Compound: {compound}<br>"
                f"Laps: {start_lap} -> {end_lap} ({length} laps)<br>"
                f"Avg Pace: {format_seconds_to_laptime(row['avg_lap_time_sec'])}<br>"
                f"Degradation: +{row['degradation_slope_sec_per_lap']:.3f} s/lap"
            )

            fig_timeline.add_trace(
                go.Bar(
                    y=[driver],
                    x=[length],
                    base=[start_lap],
                    orientation="h",
                    name=compound,
                    marker=dict(color=color, line=dict(color="#1f242c", width=1.5)),
                    hoverinfo="text",
                    hovertext=hover_text,
                    showlegend=False,
                )
            )

        fig_timeline.update_layout(
            template="plotly_dark",
            barmode="stack",
            xaxis=dict(title="Lap Number in Race", range=[1, laps_df["lap_number"].max() + 1]),
            yaxis=dict(title="Driver", autorange="reversed"),
            title="Race Stint Duration & Compound Strategy",
            margin=dict(l=60, r=40, t=50, b=40),
            height=400,
        )
        st.plotly_chart(fig_timeline, use_container_width=True)

        st.subheader("Stint Summary Data")
        table_cols = [
            "driver",
            "stint",
            "compound",
            "start_lap",
            "end_lap",
            "total_stint_laps",
            "green_flag_laps",
            "avg_lap_time_sec",
            "fastest_lap_sec",
            "degradation_slope_sec_per_lap",
        ]
        available_table_cols = [c for c in table_cols if c in stints_display.columns]
        st.dataframe(
            stints_display[available_table_cols].style.format(
                {
                    "avg_lap_time_sec": "{:.3f} s",
                    "fastest_lap_sec": "{:.3f} s",
                    "degradation_slope_sec_per_lap": "{:+.4f} s/lap",
                }
            ),
            use_container_width=True,
        )


# -----------------------------------------------------------------------------
# TAB 3: Tire Degradation Analysis
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("Tire Degradation Slope: OLS Linear Regression")
    st.markdown(
        """
        The **Tire Degradation Slope** measures the rate at which lap time increases as the tire wears:
        $$\\text{LapTime} = m \\times \\text{TyreLife} + c$$
        - **Positive Slope ($m > 0$)**: Lap times increase as tires degrade. Lower is better.
        - **Calculated strictly on accurate green-flag laps**, excluding pit-in/out and safety car laps.
        """
    )

    if not filtered_laps.empty:
        # Scatter Plot with Custom Regression Trendlines (no statsmodels dependency)
        fig_deg = px.scatter(
            filtered_laps,
            x="tyre_life",
            y="lap_time_sec",
            color="driver",
            symbol="compound",
            color_discrete_map=DRIVER_COLORS,
            labels={
                "tyre_life": "Tyre Life (Laps Completed on Tire)",
                "lap_time_sec": "Lap Time (Seconds)",
                "driver": "Driver",
                "compound": "Compound",
            },
            title="Lap Time vs Tyre Age with Linear Regression Slopes",
        )

        # Add regression trendlines per driver using numpy
        for d in filtered_laps["driver"].unique():
            d_laps = filtered_laps[filtered_laps["driver"] == d]
            if len(d_laps) >= 2 and d_laps["tyre_life"].nunique() > 1:
                x_vals = np.array(sorted(d_laps["tyre_life"].unique()))
                slope, r2 = calculate_tire_degradation_slope(d_laps["tyre_life"], d_laps["lap_time_sec"])
                # Calculate mean y and intercept
                mean_y = d_laps["lap_time_sec"].mean()
                mean_x = d_laps["tyre_life"].mean()
                intercept = mean_y - slope * mean_x
                y_vals = slope * x_vals + intercept
                
                driver_color = DRIVER_COLORS.get(d, "#CCCCCC")
                fig_deg.add_trace(
                    go.Scatter(
                        x=x_vals,
                        y=y_vals,
                        mode="lines",
                        name=f"{d} Trend (+{slope:.3f} s/lap)",
                        line=dict(color=driver_color, dash="dot", width=2),
                        hoverinfo="text",
                        hovertext=f"{d} Degradation: +{slope:.4f} s/lap (R²={r2:.1%})",
                    )
                )

        fig_deg.update_layout(template="plotly_dark", margin=dict(l=40, r=40, t=50, b=40))
        st.plotly_chart(fig_deg, use_container_width=True)

        # Leaderboard Table
        if not stints_df.empty:
            st.subheader("Tire Management Efficiency Leaderboard")
            leaderboard_df = stints_df[stints_df["green_flag_laps"] >= 5].copy()
            if not leaderboard_df.empty:
                leaderboard_df = leaderboard_df.sort_values(by="degradation_slope_sec_per_lap", ascending=True)
                cols_lead = [
                    "driver",
                    "team",
                    "compound",
                    "stint",
                    "total_stint_laps",
                    "degradation_slope_sec_per_lap",
                    "degradation_r2",
                    "avg_lap_time_sec",
                ]
                avail_lead = [c for c in cols_lead if c in leaderboard_df.columns]
                st.dataframe(
                    leaderboard_df[avail_lead].style.format(
                        {
                            "degradation_slope_sec_per_lap": "{:+.4f} s/lap",
                            "degradation_r2": "{:.2%}",
                            "avg_lap_time_sec": "{:.3f} s",
                        }
                    ),
                    use_container_width=True,
                )


# -----------------------------------------------------------------------------
# TAB 4: Raw Data & Athena SQL
# -----------------------------------------------------------------------------
with tab4:
    st.subheader("Raw Lap Telemetry Dataset")
    st.dataframe(filtered_laps, use_container_width=True)

    csv_data = filtered_laps.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Filtered Telemetry (CSV)",
        data=csv_data,
        file_name="f1_telemetry_laps.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Amazon Athena Analytical SQL Queries")
    st.markdown("Use these queries directly in the Amazon Athena console against the partitioned S3 bucket:")

    athena_sql_path = PROJECT_ROOT / "athena" / "create_table.sql"
    if athena_sql_path.exists():
        sql_content = athena_sql_path.read_text(encoding="utf-8")
        st.code(sql_content, language="sql")
    else:
        st.code("SELECT * FROM f1_telemetry_db.laps LIMIT 10;", language="sql")
