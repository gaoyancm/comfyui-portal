import os, sys

# 确保项目根目录在 sys.path 里
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 加载虚拟环境 site-packages（Passenger 默认不会激活 venv）
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

# 默认环境为生产
os.environ.setdefault('FLASK_ENV', 'production')

# ----------------- 核心 -----------------
# 这里从 app/__init__.py 导入 Flask 实例
from app import app as application
