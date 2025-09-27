import os, sys

# Ensure project root is importable
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Prefer venv site-packages if present (Passenger doesn't auto-activate venv)
VENV = os.path.join(BASE_DIR, '.venv')
_candidates = [
    os.path.join(VENV, 'lib', 'python3.12', 'site-packages'),
    os.path.join(VENV, 'lib', 'python3.11', 'site-packages'),
    os.path.join(VENV, 'lib', 'python3.10', 'site-packages'),
    os.path.join(VENV, 'lib', 'python3.9', 'site-packages'),
    os.path.join(VENV, 'lib', 'site-packages'),
]
for p in _candidates:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)
        break

# Production defaults (can be overridden by .env or hosting panel)
os.environ.setdefault('FLASK_ENV', 'production')

# Expose WSGI application for Passenger
from app import app as application  # noqa: E402

