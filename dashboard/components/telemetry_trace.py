import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

def generate_mock_telemetry_trace(driver: str, lap_time_sec: float) -> pd.DataFrame:
    """Generates realistic synthetic speed, throttle, and brake distance traces for comparison."""
    distance = np.linspace(0, 5412, 300)  # Bahrain circuit length ~5412m
    np.random.seed(hash(driver) % 2**32)
    base_speed = 220 + 70 * np.sin(distance / 350) + 30 * np.cos(distance / 700)
    speed = np.clip(base_speed + np.random.normal(0, 3, len(distance)), 70, 335)
    throttle = np.clip(100 * (speed - 70) / 240 + np.random.normal(0, 4, len(distance)), 0, 100)
    brake = np.where(throttle < 20, np.random.uniform(40, 100, len(distance)), 0.0)
    return pd.DataFrame({"distance": distance, "speed": speed, "throttle": throttle, "brake": brake, "driver": driver})

def render_driver_telemetry_trace_comparison(driver_a: str, driver_b: str, lap_a_time: float = 94.0, lap_b_time: float = 94.5):
    """Renders dual-driver telemetry trace overlay: Speed (km/h), Throttle (%), and Brake (%)"""
    st.subheader(f"⚡ Fastest Lap Telemetry Comparison: {driver_a} vs {driver_b}")
    df_a = generate_mock_telemetry_trace(driver_a, lap_a_time)
    df_b = generate_mock_telemetry_trace(driver_b, lap_b_time)

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                        subplot_titles=("Speed (km/h)", "Throttle (%)", "Brake (%)"))

    # Speed
    fig.add_trace(go.Scatter(x=df_a["distance"], y=df_a["speed"], name=f"{driver_a} Speed", line=dict(color="#E10600", width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_b["distance"], y=df_b["speed"], name=f"{driver_b} Speed", line=dict(color="#00D2BE", width=2)), row=1, col=1)

    # Throttle
    fig.add_trace(go.Scatter(x=df_a["distance"], y=df_a["throttle"], name=f"{driver_a} Throttle", line=dict(color="#E10600", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_b["distance"], y=df_b["throttle"], name=f"{driver_b} Throttle", line=dict(color="#00D2BE", width=1.5)), row=2, col=1)

    # Brake
    fig.add_trace(go.Scatter(x=df_a["distance"], y=df_a["brake"], name=f"{driver_a} Brake", line=dict(color="#E10600", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=df_b["distance"], y=df_b["brake"], name=f"{driver_b} Brake", line=dict(color="#00D2BE", width=1.5)), row=3, col=1)

    fig.update_layout(height=650, margin=dict(l=20, r=20, t=40, b=20), hovermode="x unified")
    fig.update_xaxes(title_text="Track Distance (meters)", row=3, col=1)
    st.plotly_chart(fig, use_container_width=True)
