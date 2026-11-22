Write-Host "🏎️ Setting up F1 Telemetry development environment (Windows)..." -ForegroundColor Cyan
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
Write-Host "✓ Dev environment ready! Run 'pytest' to verify tests." -ForegroundColor Green
