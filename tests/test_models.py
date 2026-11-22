import pytest
from pydantic import ValidationError
from ingest.models import LapTelemetryModel, SessionMetadataModel, DriverStintSummary

def test_valid_lap_telemetry():
    lap = LapTelemetryModel(
        driver="VER",
        lap_number=1,
        stint=1,
        compound="SOFT",
        lap_time_sec=94.521,
        sector1_sec=30.123,
        sector2_sec=38.456,
        sector3_sec=25.942,
        is_pit_in=False,
        is_pit_out=False,
        is_accurate=True,
    )
    assert lap.driver == "VER"
    assert lap.lap_number == 1
    assert lap.compound == "SOFT"
    assert lap.lap_time_sec == 94.521

def test_invalid_driver_code():
    with pytest.raises(ValidationError):
        LapTelemetryModel(
            driver="V",  # Too short
            lap_number=1,
            stint=1,
            compound="SOFT",
        )

def test_session_metadata():
    session = SessionMetadataModel(year=2023, round_number=1, session_type="R", track_name="Bahrain")
    assert session.year == 2023
    assert session.round_number == 1
    assert session.track_name == "Bahrain"

def test_stint_summary_model():
    stint = DriverStintSummary(
        driver="HAM",
        stint=1,
        compound="MEDIUM",
        total_stint_laps=18,
        avg_lap_time_sec=95.120,
        fastest_lap_sec=94.880,
        degradation_slope_sec_per_lap=0.045,
        degradation_r2=0.72,
    )
    assert stint.driver == "HAM"
    assert stint.degradation_slope_sec_per_lap == 0.045
