from flask import Blueprint, request, jsonify, session
import pandas as pd
import hashlib
import os
import csv
from datetime import datetime

auth_bp = Blueprint("auth", __name__)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, "users.xlsx")
CSV_PATH = os.path.join(BASE_DIR, os.environ.get("USERS_CSV", "users.csv"))

ACTIVE_SESSIONS = {}
INACTIVITY_SECONDS = 30 * 60


@auth_bp.before_app_request
def _enforce_single_session():
    u = session.get("user")
    sid = session.get("sid")
    if not u or not sid:
        return
    rec = ACTIVE_SESSIONS.get(u)
    now = datetime.utcnow().timestamp()
    if not rec or rec.get("sid") != sid or now - rec.get("last_seen", 0) > INACTIVITY_SECONDS:
        if rec and now - rec.get("last_seen", 0) > INACTIVITY_SECONDS:
            ACTIVE_SESSIONS.pop(u, None)
        session.clear()
        return
    rec["last_seen"] = now


def _parse_dt(val):
    if val in (None, "", "null", "None"):
        return datetime.max
    try:
        dt = pd.to_datetime(val, errors="coerce")
        if pd.isna(dt):
            return datetime.max
        return dt.to_pydatetime()
    except Exception:
        try:
            return datetime.fromisoformat(str(val))
        except Exception:
            return datetime.max


def load_users():
    users = {}
    # prefer CSV if present
    if os.path.isfile(CSV_PATH):
        try:
            with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    username = str(row.get("username", "")).strip()
                    if not username:
                        continue
                    pwd_hash = str(row.get("password_hash", "")).strip()
                    expire_dt = _parse_dt(row.get("expire_at"))
                    active = str(row.get("active", "true")).strip().lower() not in ("0", "false", "no")
                    role = (row.get("role") or "user").strip() or "user"
                    users[username] = {
                        "password_hash": pwd_hash,
                        "expire_at": expire_dt,
                        "active": active,
                        "role": role,
                    }
            return users
        except Exception:
            pass
    # fallback to Excel
    if os.path.isfile(EXCEL_PATH):
        df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
        for _, row in df.iterrows():
            username = str(row.get("username", "")).strip()
            if not username:
                continue
            pwd_hash = str(row.get("password_hash", "")).strip()
            expire_dt = _parse_dt(row.get("expire_at"))
            users[username] = {
                "password_hash": pwd_hash,
                "expire_at": expire_dt,
                "active": True,
                "role": "user",
            }
    return users


@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    u = (data.get("username") or "").strip()
    p = data.get("password") or ""
    if not u or not p:
        return jsonify({"ok": False, "msg": "用户名或密码为空"}), 400
    users = load_users()
    info = users.get(u)
    if not info:
        return jsonify({"ok": False, "msg": "用户不存在"}), 401
    if not info.get("active", True):
        return jsonify({"ok": False, "msg": "账号已停用"}), 401
    if datetime.utcnow() > info["expire_at"]:
        return jsonify({"ok": False, "msg": "密码已过期"}), 401
    if hashlib.sha256(p.encode()).hexdigest() != info["password_hash"]:
        return jsonify({"ok": False, "msg": "密码错误"}), 401
    import secrets, time

    now = time.time()
    rec = ACTIVE_SESSIONS.get(u)
    if rec and now - rec.get("last_seen", 0) <= INACTIVITY_SECONDS:
        return jsonify({"ok": False, "msg": "该账号已在其他位置登录"}), 409
    sid = secrets.token_urlsafe(24)
    session.permanent = True
    session["user"] = u
    session["sid"] = sid
    ACTIVE_SESSIONS[u] = {"sid": sid, "last_seen": now}
    session["role"] = info.get("role", "user")
    return jsonify({"ok": True, "user": u, "role": session["role"]})


@auth_bp.get("/auth/status")
def status():
    u = session.get("user")
    if not u:
        return jsonify({"ok": False}), 401
    return jsonify({"ok": True, "user": u})


@auth_bp.get("/logout")
def logout():
    u = session.get("user")
    sid = session.get("sid")
    rec = ACTIVE_SESSIONS.get(u)
    if rec and rec.get("sid") == sid:
        ACTIVE_SESSIONS.pop(u, None)
    session.clear()
    return jsonify({"ok": True})
