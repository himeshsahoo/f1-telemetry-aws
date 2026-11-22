from typing import Optional
from pydantic import BaseModel, Field, field_validator

class LapTelemetryModel(BaseModel):
    driver: str = Field(..., min_length=2, max_length=4, description="3-letter driver code e.g. VER")
    lap_number: int = Field(..., ge=1, le=100, description="Lap number")
    stint: int = Field(..., ge=1, le=10, description="Stint index")
    compound: str = Field(..., description="Tire compound e.g. SOFT, MEDIUM, HARD")
    lap_time_sec: Optional[float] = Field(None, ge=50.0, le=200.0, description="Lap time in seconds")
    sector1_sec: Optional[float] = Field(None, ge=10.0, le=90.0)
    sector2_sec: Optional[float] = Field(None, ge=10.0, le=90.0)
    sector3_sec: Optional[float] = Field(None, ge=10.0, le=90.0)
    is_pit_in: bool = Field(default=False)
    is_pit_out: bool = Field(default=False)
    is_accurate: bool = Field(default=True)
    track_status: str = Field(default="1")

    @field_validator("compound")
    @classmethod
    def validate_compound(cls, v: str) -> str:
        return v.strip().upper()

class SessionMetadataModel(BaseModel):
    year: int = Field(..., ge=2018, le=2030)
    round_number: int = Field(..., ge=1, le=30)
    session_type: str = Field(default="R", description="FP1, FP2, FP3, Q, SQ, S, R")
    track_name: Optional[str] = None
    total_laps: Optional[int] = Field(None, ge=1, le=100)

class DriverStintSummary(BaseModel):
    driver: str
    stint: int
    compound: str
    total_stint_laps: int
    avg_lap_time_sec: float
    fastest_lap_sec: float
    degradation_slope_sec_per_lap: float
    degradation_r2: float
