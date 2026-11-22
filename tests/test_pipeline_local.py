import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.run_pipeline_local import run_local_pipeline

@patch("subprocess.run")
def test_run_local_pipeline_success(mock_subproc):
    mock_subproc.return_value = MagicMock(returncode=0, stdout="Success output", stderr="")
    result = run_local_pipeline(year=2023, round_id=1, session="R")
    assert result is True
    assert mock_subproc.call_count == 2

@patch("subprocess.run")
def test_run_local_pipeline_failure(mock_subproc):
    mock_subproc.return_value = MagicMock(returncode=1, stdout="", stderr="Mock error")
    result = run_local_pipeline(year=2023, round_id=1, session="R")
    assert result is False
