# run_dev.ps1
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
if (-Not (Test-Path .env)) { Copy-Item .env.example .env }
python -m app
