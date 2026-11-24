# Run the dashboard on a PC: the server on http://localhost:8080 (system actions are
# only logged) plus the display window. Needs: pip install -r requirements-dev.txt
$root = Split-Path -Parent $PSScriptRoot
$server = Start-Process python -PassThru -NoNewWindow -WorkingDirectory "$root\app\server" `
    -ArgumentList "-m", "dashboard", "--dev", "--data", "$root\devdata", "--appdir", "$root\app", "--port", "8080"
try {
    Start-Sleep -Seconds 2
    python "$root\scripts\dev_display.py" "http://127.0.0.1:8080"
} finally {
    Stop-Process -Id $server.Id -ErrorAction SilentlyContinue
}
