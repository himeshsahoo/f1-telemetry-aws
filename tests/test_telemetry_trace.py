import pytest
import numpy as np
from dashboard.components.telemetry_trace import generate_mock_telemetry_trace

def test_telemetry_trace_generation():
    df = generate_mock_telemetry_trace("VER", 94.120)
    assert not df.empty
    assert len(df) == 300
    assert "distance" in df.columns
    assert "speed" in df.columns
    assert "throttle" in df.columns
    assert "brake" in df.columns

    # Verify realistic physical limits
    assert df["speed"].min() >= 60.0
    assert df["speed"].max() <= 350.0
    assert df["throttle"].min() >= 0.0
    assert df["throttle"].max() <= 100.0
    assert df["brake"].min() >= 0.0
    assert df["brake"].max() <= 100.0

def test_telemetry_trace_distinct_drivers():
    df_ver = generate_mock_telemetry_trace("VER", 94.0)
    df_lec = generate_mock_telemetry_trace("LEC", 94.2)
    # Traces should differ due to seeded noise
    assert not np.array_equal(df_ver["speed"].values, df_lec["speed"].values)
