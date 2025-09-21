from flask import Blueprint, current_app, request, jsonify
import os, uuid, threading, queue, time, json, requests
from functools import wraps

jobs_bp = Blueprint("jobs", __name__)

# In-memory queue and job table
_task_q = queue.Queue()
_jobs = {}  # job_id -> {status, progress, prompt_id, outputs:[], error, wf_path, mapping}


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


def _deep_set(obj, path, value):
    # path like nodes.5.inputs.text
    parts = [p for p in str(path).split('.') if p]
    cur = obj
    for i, p in enumerate(parts):
        is_last = i == len(parts) - 1
        try:
            key = int(p)
        except ValueError:
            key = p
        if is_last:
            if isinstance(cur, list) and isinstance(key, int):
                while len(cur) <= key:
                    cur.append(None)
                cur[key] = value
            elif isinstance(cur, dict):
                cur[key] = value
            return
        # descend
        if isinstance(cur, list) and isinstance(key, int):
            while len(cur) <= key:
                cur.append({})
            if cur[key] is None:
                cur[key] = {}
            cur = cur[key]
        else:
            if key not in cur or cur[key] is None:
                cur[key] = {}
            cur = cur[key]


def _apply_form_mapping(prompt_json, mapping, form_values, upload_map):
    if not isinstance(mapping, list):
        return prompt_json
    for m in mapping:
        path = m.get("path")
        val = m.get("value")
        if not path:
            continue
        v = val
        if isinstance(val, str) and val.startswith("$"):
            ref = val[1:]
            if ref.startswith("file:"):
                fld = ref.split(":", 1)[1]
                v = upload_map.get(fld)
            else:
                v = form_values.get(ref)
        _deep_set(prompt_json, path, v)
    return prompt_json


def _apply_overrides(prompt_json, overrides):
    if not isinstance(overrides, dict):
        return prompt_json
    return {**prompt_json, **overrides}


def _upload_to_comfy(file_path):
    # Best-effort upload to ComfyUI
    url = f"{current_app.config['COMFY_URL'].rstrip('/')}/upload/image"
    try:
        with open(file_path, 'rb') as fp:
            r = requests.post(url, files={'image': (os.path.basename(file_path), fp)}, timeout=60)
        if r.status_code == 200:
            if r.headers.get('content-type','').startswith('application/json'):
                data = r.json()
                return data.get('name') or os.path.basename(file_path)
    except Exception:
        pass
    return os.path.basename(file_path)


def _run_job(job_id):
    j = _jobs[job_id]
    comfy = current_app.config["COMFY_URL"]
    # load workflow json
    with open(j["wf_path"], "r", encoding="utf-8") as f:
        prompt_json = json.load(f)

    mapping = j.get("mapping") or []
    ov = j.get("overrides") or {}
    if mapping:
        form_values = ov.get("_form_values") or {}
        # if uploads exist, convert to comfy names
        upload_map = {}
        for meta in ov.get("_uploads", []):
            # meta: {field, name, path}
            comfy_name = _upload_to_comfy(meta.get("path"))
            upload_map[meta.get("field")] = comfy_name
        prompt_json = _apply_form_mapping(prompt_json, mapping, form_values, upload_map)
    else:
        # 若没有 mapping，但 overrides 仅包含内部键（_form_values/_uploads），则不改动工作流
        if set(ov.keys()) <= {"_form_values", "_uploads"}:
            pass
        else:
            prompt_json = _apply_overrides(prompt_json, ov)

    client_id = str(uuid.uuid4())
    j.update(status="submitting", progress=5)
    r = requests.post(f"{comfy}/prompt", json={"prompt": prompt_json, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    prompt_id = r.json().get("prompt_id") or r.json().get("promptId")
    if not prompt_id:
        raise RuntimeError("ComfyUI 未返回 prompt_id")
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


def _list_workflows_impl():
    root = "workflows"
    if not os.path.isdir(root):
        return []
    items = []
    for name in os.listdir(root):
        if name.lower().endswith(".json"):
            wf = name
            form = f"{os.path.splitext(name)[0]}.form.json"
            items.append({"workflow": wf, "has_form": os.path.isfile(os.path.join(root, form)), "form": form})
    return items


@jobs_bp.get("/workflows")
@login_required
def list_workflows_api():
    return jsonify({"ok": True, "items": _list_workflows_impl()})


@jobs_bp.get("/workflows/<wf>/form")
@login_required
def get_workflow_form(wf):
    root = "workflows"
    base = os.path.splitext(wf)[0]
    form_path = os.path.join(root, f"{base}.form.json")
    if os.path.isfile(form_path):
        try:
            with open(form_path, 'r', encoding='utf-8') as f:
                return jsonify({"ok": True, "form": json.load(f)})
        except Exception as e:
            return jsonify({"ok": False, "msg": f"读取表单失败: {e}"}), 400
    return jsonify({"ok": True, "form": {"name": base, "fields": [], "mapping": []}})


@jobs_bp.post("/jobs")
@login_required
def create_job():
    wf = request.form.get("workflow") or request.args.get("workflow") or "default.json"
    use_form = (request.form.get("form_mode") == "1")
    overrides_text = request.form.get("overrides") or request.args.get("overrides")
    overrides = {}
    if overrides_text and not use_form:
        try:
            overrides = json.loads(overrides_text)
        except Exception:
            return jsonify({"ok": False, "msg": "overrides 需为 JSON"}), 400
    wf_path = os.path.join("workflows", wf)
    if not os.path.isfile(wf_path):
        return jsonify({"ok": False, "msg": f"未找到工作流 {wf}"}), 404

    # file uploads
    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    files_meta = []
    for key in request.files:
        f = request.files[key]
        fname = f"{uuid.uuid4().hex}_{f.filename}"
        fpath = os.path.join(upload_dir, fname)
        f.save(fpath)
        files_meta.append({"field": key, "name": f.filename, "path": fpath})

    if use_form:
        base = os.path.splitext(wf)[0]
        form_path = os.path.join("workflows", f"{base}.form.json")
        form_def = {"fields": [], "mapping": []}
        if os.path.isfile(form_path):
            try:
                with open(form_path, 'r', encoding='utf-8') as f:
                    form_def = json.load(f)
            except Exception:
                pass
        form_values = {}
        for fld in form_def.get("fields", []):
            nm = fld.get("name")
            if nm:
                form_values[nm] = request.form.get(nm, fld.get("default"))
                if fld.get("type") in ("number", "integer"):
                    try:
                        form_values[nm] = int(form_values[nm]) if fld.get("type")=="integer" else float(form_values[nm])
                    except Exception:
                        pass
        overrides = {"_form_values": form_values, "_uploads": files_meta}
        mapping = form_def.get("mapping", [])
    else:
        if files_meta:
            overrides["_uploads"] = files_meta
        mapping = []

    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"status": "queued", "progress": 0, "wf_path": wf_path, "overrides": overrides, "mapping": mapping}
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
