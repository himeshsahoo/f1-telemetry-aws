import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

COMPOUND_COLORS = {
    "SOFT": "#FF1801",
    "MEDIUM": "#FFF200",
    "HARD": "#EBEBEB",
    "INTERMEDIATE": "#39B54A",
    "WET": "#00A3E0",
    "UNKNOWN": "#888888",
}

def render_stint_strategy_chart(stint_df: pd.DataFrame):
    """Renders an interactive Gantt chart visualizing tire stint choices across all drivers."""
    if stint_df.empty:
        st.info("No stint data available for strategy chart.")
        return

    fig = px.bar(
        stint_df,
        x="total_stint_laps",
        y="driver",
        color="compound",
        orientation="h",
        color_discrete_map=COMPOUND_COLORS,
        title="<b>Tire Strategy Timeline by Driver</b> (Stint Length & Compound)",
        labels={"total_stint_laps": "Laps in Stint", "driver": "Driver", "compound": "Compound"},
        hover_data={"stint": True, "avg_lap_time_sec": ":.3f", "fastest_lap_sec": ":.3f"},
    )
    fig.update_layout(
        barmode="stack",
        height=max(350, len(stint_df["driver"].unique()) * 24),
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_title="Accumulated Laps",
        yaxis_title="Driver",
        legend_title="Tire Compound",
    )
    st.plotly_chart(fig, use_container_width=True)
