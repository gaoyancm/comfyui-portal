Param(
  [string]$Port = "5000"
)

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path) | Out-Null
Set-Location ..

if (!(Test-Path .venv)) {
  python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$env:FLASK_ENV = "production"
if (-not $env:COMFY_URL) { $env:COMFY_URL = "http://127.0.0.1:8188" }
if (-not $env:UPLOAD_DIR) { $env:UPLOAD_DIR = "uploads" }
if (-not $env:RESULTS_DIR) { $env:RESULTS_DIR = "results" }

python -c "import os; os.makedirs(os.environ.get('UPLOAD_DIR','uploads'), exist_ok=True); os.makedirs(os.environ.get('RESULTS_DIR','results'), exist_ok=True)"

gunicorn -b 0.0.0.0:$Port app:app --chdir . --workers 2 --timeout 120

