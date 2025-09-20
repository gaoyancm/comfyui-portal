from flask import Blueprint, current_app, request, jsonify, send_from_directory
import os, uuid, threading, queue, time, json, requests
from functools import wraps

jobs_bp = Blueprint("jobs", __name__)

# simple in-memory queue
_task_q = queue.Queue()
_jobs = {}  # job_id -> {status, progress, prompt_id, outputs:[], error}


def login_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        from flask import session
        if "user" not in session:
            return jsonify({"ok": False, "msg": "未登录"}), 401
        return fn(*a, **kw)
    return wrap


def _worker():
    while True:
        job_id = _task_q.get()
        try:
            _run_job(job_id)
        except Exception as e:
            _jobs[job_id].update(status="error", error=str(e))
        finally:
            _task_q.task_done()

threading.Thread(target=_worker, daemon=True).start()


def _apply_overrides(prompt_json, overrides):
    if not isinstance(overrides, dict):
        return prompt_json
    return {**prompt_json, **overrides}


def _run_job(job_id):
    j = _jobs[job_id]
    app = current_app
    comfy = app.config["COMFY_URL"]
    # load workflow json
    wf_path = j["wf_path"]
    with open(wf_path, "r", encoding="utf-8") as f:
        prompt_json = json.load(f)
    prompt_json = _apply_overrides(prompt_json, j.get("overrides") or {})
    client_id = str(uuid.uuid4())
    j.update(status="submitting", progress=5)
    r = requests.post(f"{comfy}/prompt", json={"prompt": prompt_json, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    prompt_id = r.json().get("prompt_id")
    if not prompt_id:
        raise RuntimeError("No prompt_id")
    j.update(status="running", progress=10, prompt_id=prompt_id)

    # poll history
    deadline = time.time() + 600
    outputs = []
    while time.time() < deadline:
        h = requests.get(f"{comfy}/history/{prompt_id}", timeout=30)
        if h.status_code != 200:
            time.sleep(1); continue
        item = (h.json() or {}).get(prompt_id)
        if not item:
            time.sleep(1); continue
        if item.get("node_errors"):
            j.update(status="error", error=str(item.get("node_errors")))
            return
        outs = item.get("outputs") or {}
        for node_out in outs.values():
            for img in node_out.get("images", []):
                outputs.append({
                    "filename": img.get("filename"),
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output")
                })
        if outputs:
            break
        j["progress"] = min(95, j.get("progress", 10) + 5)
        time.sleep(1)
    if not outputs:
        j.update(status="timeout", progress=100); return
    j.update(status="finished", progress=100, outputs=outputs)


@jobs_bp.post("/jobs")
@login_required
def create_job():
    wf = request.form.get("workflow") or request.args.get("workflow") or "default.json"
    overrides_text = request.form.get("overrides") or request.args.get("overrides")
    overrides = {}
    if overrides_text:
        try:
            overrides = json.loads(overrides_text)
        except Exception:
            return jsonify({"ok": False, "msg": "overrides 需为 JSON"}), 400
    wf_path = os.path.join("workflows", wf)
    if not os.path.isfile(wf_path):
        return jsonify({"ok": False, "msg": f"未找到工作流 {wf}"}), 404

    # handle file uploads
    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    files_meta = []
    for f in request.files.values():
        fname = f"{uuid.uuid4().hex}_{f.filename}"
        fpath = os.path.join(upload_dir, fname)
        f.save(fpath)
        files_meta.append({"name": f.filename, "path": fpath})
    if files_meta:
        overrides["_uploads"] = files_meta

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "queued", "progress": 0, "wf_path": wf_path, "overrides": overrides}
    _task_q.put(job_id)
    return jsonify({"ok": True, "job_id": job_id})

@jobs_bp.get("/jobs/<job_id>/status")
@login_required
def job_status(job_id):
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    return jsonify({"ok": True, **j})

@jobs_bp.get("/queue")
@login_required
def queue_overview():
    return jsonify({"ok": True, "queued": _task_q.qsize()})

@jobs_bp.get("/comfy/view")
@login_required
def proxy_view():
    from flask import Response
    filename = request.args.get("filename"); subfolder = request.args.get("subfolder","" ); typ = request.args.get("type","output")
    if not filename:
        return jsonify({"ok": False, "msg": "缺少 filename"}), 400
    r = requests.get(f"{current_app.config['COMFY_URL']}/view", params={"filename": filename, "subfolder": subfolder, "type": typ}, stream=True, timeout=60)
    if r.status_code != 200:
        return jsonify({"ok": False, "msg": r.text}), 502
    return Response(r.iter_content(8192), content_type=r.headers.get("Content-Type","image/png"))
