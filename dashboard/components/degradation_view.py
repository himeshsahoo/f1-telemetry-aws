import pandas as pd
import plotly.express as px
import streamlit as st

def render_degradation_summary(stint_df: pd.DataFrame):
    """Renders tire degradation statistics cards and distribution chart."""
    if stint_df.empty or "degradation_slope_sec_per_lap" not in stint_df.columns:
        st.info("No degradation metrics available.")
        return

    st.subheader("📉 Stint Tire Degradation Slopes (OLS Regression)")
    valid_deg = stint_df[stint_df["degradation_slope_sec_per_lap"] > 0]
    if not valid_deg.empty:
        avg_deg = valid_deg["degradation_slope_sec_per_lap"].mean()
        max_deg_stint = valid_deg.loc[valid_deg["degradation_slope_sec_per_lap"].idxmax()]
        min_deg_stint = valid_deg.loc[valid_deg["degradation_slope_sec_per_lap"].idxmin()]

        c1, c2, c3 = st.columns(3)
        c1.metric("Avg Field Degradation", f"+{avg_deg:.4f} s/lap")
        c2.metric("Highest Degradation", f"{max_deg_stint['driver']} ({max_deg_stint['compound']})", f"+{max_deg_stint['degradation_slope_sec_per_lap']:.4f} s/lap")
        c3.metric("Best Tire Management", f"{min_deg_stint['driver']} ({min_deg_stint['compound']})", f"+{min_deg_stint['degradation_slope_sec_per_lap']:.4f} s/lap")

    fig = px.scatter(
        stint_df,
        x="total_stint_laps",
        y="degradation_slope_sec_per_lap",
        color="compound",
        size="total_stint_laps",
        hover_name="driver",
        title="<b>Tire Degradation Rate vs Stint Length</b> (Positive = Pace Decay)",
        labels={"total_stint_laps": "Stint Length (Laps)", "degradation_slope_sec_per_lap": "Degradation Slope (s/lap)"},
    )
    st.plotly_chart(fig, use_container_width=True)
