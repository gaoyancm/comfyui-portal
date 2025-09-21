from flask import Blueprint, jsonify, request, session, render_template
import os, json, time, requests

admin_bp = Blueprint("admin", __name__)

ROOT = os.path.dirname(os.path.dirname(__file__))
SERVERS_JSON = os.path.join(ROOT, "workflows", "servers.json")


def is_admin():
    return session.get("role") == "admin"


@admin_bp.get("/admin/settings")
def admin_settings_page():
    if not is_admin():
        return ("Forbidden", 403)
    return render_template("admin_settings.html")


@admin_bp.get("/api/admin/servers")
def get_servers():
    if not is_admin():
        return jsonify({"ok": False, "msg": "forbidden"}), 403
    try:
        with open(SERVERS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    return jsonify({"ok": True, "servers": data})


@admin_bp.post("/api/admin/servers")
def set_servers():
    if not is_admin():
        return jsonify({"ok": False, "msg": "forbidden"}), 403
    try:
        payload = request.get_json(force=True)
        servers = payload.get("servers") if isinstance(payload, dict) else None
        if not isinstance(servers, dict):
            return jsonify({"ok": False, "msg": "invalid payload"}), 400
        os.makedirs(os.path.dirname(SERVERS_JSON), exist_ok=True)
        tmp = SERVERS_JSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(servers, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SERVERS_JSON)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

