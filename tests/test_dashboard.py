"""
Unit Tests for Dashboard Helpers (dashboard/app.py)
"""

import sys
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

# Add dashboard directory to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "dashboard"))

from dashboard.app import (
    decimal_to_float,
    format_seconds_to_laptime,
    load_parquet_offline,
)


def test_format_seconds_to_laptime():
    """Verifies lap time conversion to M:SS.mmm format."""
    assert format_seconds_to_laptime(92.456) == "1:32.456"
    assert format_seconds_to_laptime(60.000) == "1:00.000"
    assert format_seconds_to_laptime(59.999) == "0:59.999"
    assert format_seconds_to_laptime(None) == "--:--.---"
    assert format_seconds_to_laptime(np.nan) == "--:--.---"
    assert format_seconds_to_laptime(-5.0) == "--:--.---"


def test_decimal_to_float():
    """Verifies Decimal conversion back to Python float/int."""
    data = {
        "dec_num": Decimal("92.1234"),
        "int_num": Decimal("10"),
        "nested": {"inner": Decimal("1.5")},
        "arr": [Decimal("3.14")],
    }
    result = decimal_to_float(data)
    assert isinstance(result["dec_num"], float)
    assert result["dec_num"] == 92.1234
    assert isinstance(result["nested"]["inner"], float)
    assert result["arr"][0] == 3.14


def test_load_parquet_offline():
    """Verifies loading and processing sample parquet offline."""
    sample_path = PROJECT_ROOT / "data" / "sample" / "sample_laps.parquet"
    if not sample_path.exists():
        pytest.skip("Sample parquet file not found")

    stints_df, laps_df = load_parquet_offline(str(sample_path))
    assert not stints_df.empty
    assert not laps_df.empty
    assert "driver" in stints_df.columns
    assert "degradation_slope_sec_per_lap" in stints_df.columns
    assert "lap_time_sec" in laps_df.columns
