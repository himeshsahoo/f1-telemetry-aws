import streamlit as st

def render_dashboard_header(season: int, round_num: int, session: str, data_source: str, total_laps: int = 0):
    """Renders a styled header with status badges and telemetry metadata."""
    st.markdown(
        """
        <div style="background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); 
                    padding: 1.2rem; border-radius: 10px; border-left: 5px solid #E10600; margin-bottom: 1.5rem;">
            <h1 style="color: white; margin: 0; font-size: 2rem;">🏎️ F1 Telemetry & Strategy Pipeline</h1>
            <p style="color: #94a3b8; margin: 0.3rem 0 0 0; font-size: 0.95rem;">
                Event-Driven Serverless Race Pace & Degradation Analytics
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Season", season)
    with col2:
        st.metric("Round", round_num)
    with col3:
        st.metric("Session", session)
    with col4:
        st.metric("Mode", data_source)
