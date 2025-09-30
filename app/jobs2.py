from flask import Blueprint, current_app, request, jsonify, send_file
import os, uuid, threading, queue, time, json, requests, re
from functools import wraps
import io, zipfile
from datetime import datetime

jobs_bp = Blueprint("jobs", __name__)

# In-memory queue and job table
_task_q = queue.Queue()
_jobs = {}  # job_id -> {status, progress, prompt_id, outputs:[], error, wf_path, mapping}
_flask_app = None  # set via attach_app(app)
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


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
            _jobs[job_id].update(status="error", error=str(e), done_at=time.time())
        finally:
            _task_q.task_done()

_worker_thread_started = False

def attach_app(app):
    global _flask_app, _worker_thread_started
    _flask_app = app
    if not _worker_thread_started:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_thread_started = True

# servers mapping helpers
SERVERS_JSON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workflows", "servers.json")

def _load_servers_map():
    try:
        with open(SERVERS_JSON, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def _resolve_server_default():
    return (_flask_app or current_app).config["COMFY_URL"].rstrip('/')

def _resolve_server_for_workflow(wf_name, explicit=None, form_default=None):
    if explicit:
        return explicit.rstrip('/')
    if form_default:
        return form_default.rstrip('/')
    m = _load_servers_map()
    v = m.get(wf_name) or m.get(os.path.splitext(wf_name)[0])
    if v:
        return str(v).rstrip('/')
    return _resolve_server_default()


def _workflow_sort_key(name):
    base = os.path.splitext(name)[0]
    parts = re.findall(r'\d+|[^\d]+', base)
    key = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def _prepare_file_field(field):
    spec = field.get('file') or {}
    dirs = spec.get('dirs') or ['uploads']
    cleaned_dirs = [d for d in dirs if d]
    if not cleaned_dirs:
        cleaned_dirs = ['uploads']
    spec['dirs'] = cleaned_dirs
    extensions = [ext.lower() for ext in spec.get('extensions', [])]
    existing = []
    for idx, rel_dir in enumerate(cleaned_dirs):
        abs_dir = os.path.normpath(os.path.join(PROJECT_ROOT, rel_dir))
        if not os.path.isdir(abs_dir):
            continue
        try:
            entries = sorted(os.listdir(abs_dir))
        except Exception:
            continue
        for entry in entries:
            if entry.startswith('.') and not spec.get('include_hidden'):
                continue
            abs_file = os.path.join(abs_dir, entry)
            if not os.path.isfile(abs_file):
                continue
            if extensions and not any(entry.lower().endswith(ext) for ext in extensions):
                continue
            existing.append({'label': entry, 'value': f'existing://{idx}/{entry}'})
    if existing:
        field['file_existing'] = existing
    if spec.get('accept') and 'accept' not in field:
        field['accept'] = spec['accept']
    if 'allow_upload' not in field:
        field['allow_upload'] = spec.get('allow_upload', True)
    field['file'] = spec


def _guess_file_kind(filename):
    lower = (filename or '').lower()
    if lower.endswith(('.wav', '.mp3', '.flac', '.aac', '.ogg')):
        return 'audio'
    if lower.endswith(('.mp4', '.mov', '.mkv', '.avi', '.webm')):
        return 'video'
    return 'image'


def _resolve_existing_file(field, value):
    if not isinstance(value, str) or not value.startswith('existing://'):
        return None
    spec = field.get('file') or {}
    dirs = spec.get('dirs') or []
    payload = value[len('existing://'):]
    if '/' not in payload:
        return None
    idx_str, filename = payload.split('/', 1)
    try:
        idx = int(idx_str)
    except ValueError:
        return None
    if idx < 0 or idx >= len(dirs):
        return None
    rel_dir = dirs[idx]
    abs_dir = os.path.normpath(os.path.join(PROJECT_ROOT, rel_dir))
    if not os.path.isdir(abs_dir):
        return None
    candidate = os.path.normpath(os.path.join(abs_dir, filename))
    try:
        base = os.path.commonpath([abs_dir, candidate])
    except ValueError:
        return None
    if base != abs_dir:
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def _deep_set(obj, path, value):
    # path like 3.inputs.seed or nodes.5.inputs.text
    parts = [p for p in str(path).split('.') if p]
    cur = obj
    for i, token in enumerate(parts):
        is_last = i == len(parts) - 1
        # numeric tokens are only treated as list indices when current container is a list
        try:
            idx = int(token)
        except ValueError:
            idx = None
        use_index = isinstance(cur, list) and idx is not None
        key = idx if use_index else token  # dict keys stay as strings

        if is_last:
            if isinstance(cur, list) and use_index:
                while len(cur) <= key:
                    cur.append(None)
                cur[key] = value
            else:
                cur[key] = value
            return

        # descend into next level
        if isinstance(cur, list) and use_index:
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
                if v is None:
                    v = form_values.get(fld)
            else:
                v = form_values.get(ref)
        _deep_set(prompt_json, path, v)
    return prompt_json


def _apply_overrides(prompt_json, overrides):
    if not isinstance(overrides, dict):
        return prompt_json
    return {**prompt_json, **overrides}


def _comfy_url():
    if _flask_app is not None:
        return _flask_app.config["COMFY_URL"].rstrip('/')
    # fallback (inside request context only)
    return current_app.config["COMFY_URL"].rstrip('/')


def _upload_to_comfy(file_path, kind='image'):
    endpoint = 'image'
    field = 'image'
    if kind == 'audio':
        endpoint = 'audio'
        field = 'audio'
    elif kind == 'video':
        endpoint = 'video'
        field = 'video'
    url = f"{_comfy_url()}/upload/{endpoint}"
    try:
        with open(file_path, 'rb') as fp:
            r = requests.post(url, files={field: (os.path.basename(file_path), fp)}, timeout=120)
        if r.status_code == 200 and r.headers.get('content-type', '').startswith('application/json'):
            data = r.json()
            name = data.get('name') or data.get('filename')
            if name:
                return name
    except Exception:
        pass
    return os.path.basename(file_path)


def _run_job(job_id):
    j = _jobs[job_id]
    comfy = j.get("comfy_url") or _comfy_url()
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
            # meta: {field, name, path, kind}
            kind = meta.get('kind') or _guess_file_kind(meta.get('name'))
            comfy_name = _upload_to_comfy(meta.get("path"), kind)
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
        j.update(status="timeout", progress=100, done_at=time.time()); return
    j.update(status="finished", progress=100, outputs=outputs, done_at=time.time())


def _list_workflows_impl():
    root = os.path.join(PROJECT_ROOT, "workflows")
    if not os.path.isdir(root):
        return []
    items = []
    for name in os.listdir(root):
        lname = name.lower()
        if lname.endswith(".json") and not lname.endswith(".form.json") and lname not in {"default.json", "servers.json"}:
            form_name = f"{os.path.splitext(name)[0]}.form.json"
            form_path = os.path.join(root, form_name)
            items.append({"workflow": name, "has_form": os.path.isfile(form_path), "form": form_name})
    items.sort(key=lambda it: _workflow_sort_key(it["workflow"]))
    return items


@jobs_bp.get("/workflows")
@login_required
def list_workflows_api():
    return jsonify({"ok": True, "items": _list_workflows_impl()})


@jobs_bp.get("/workflows/<wf>/form")
@login_required
def get_workflow_form(wf):
    root = os.path.join(PROJECT_ROOT, "workflows")
    base = os.path.splitext(wf)[0]
    form_path = os.path.join(root, f"{base}.form.json")
    if os.path.isfile(form_path):
        try:
            with open(form_path, 'r', encoding='utf-8') as f:
                form_data = json.load(f)
            for field in form_data.get('fields', []):
                if field.get('type') == 'file':
                    _prepare_file_field(field)
            return jsonify({"ok": True, "form": form_data})
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
            return jsonify({"ok": False, "msg": "overrides 不是合法 JSON"}), 400
    wf_path = os.path.join(PROJECT_ROOT, "workflows", wf)
    if not os.path.isfile(wf_path):
        return jsonify({"ok": False, "msg": f"未找到工作流 {wf}"}), 404

    upload_dir = current_app.config["UPLOAD_DIR"]
    os.makedirs(upload_dir, exist_ok=True)
    files_meta = []
    for key, storage in request.files.items():
        field_name = key[:-len('__upload')] if key.endswith('__upload') else key
        fname = f"{uuid.uuid4().hex}_{storage.filename}"
        fpath = os.path.join(upload_dir, fname)
        storage.save(fpath)
        files_meta.append({"field": field_name, "name": storage.filename, "path": fpath})

    explicit_server = request.form.get("server") or request.args.get("server")
    form_default_server = None
    mapping = []

    if use_form:
        base = os.path.splitext(wf)[0]
        form_path = os.path.join(PROJECT_ROOT, "workflows", f"{base}.form.json")
        form_def = {"fields": [], "mapping": []}
        if os.path.isfile(form_path):
            try:
                with open(form_path, 'r', encoding='utf-8') as f:
                    form_def = json.load(f)
            except Exception:
                pass
        form_default_server = form_def.get("server")
        file_specs = {}
        for fld in form_def.get("fields", []):
            if fld.get('type') == 'file':
                _prepare_file_field(fld)
                rel_dirs = fld.get('file', {}).get('dirs', [])
                abs_dirs = [os.path.normpath(os.path.join(PROJECT_ROOT, d)) for d in rel_dirs]
                file_specs[fld.get('name')] = {"dirs": abs_dirs, "kind": fld.get('file', {}).get('kind', 'image')}

        form_values = {}
        for fld in form_def.get("fields", []):
            nm = fld.get("name")
            if not nm:
                continue
            value = request.form.get(nm, fld.get("default"))
            if fld.get("type") in ("number", "integer") and value not in (None, ""):
                try:
                    value = int(value) if fld.get("type")=="integer" else float(value)
                except Exception:
                    pass
            form_values[nm] = value
        # annotate file uploads with kind information
        for meta in files_meta:
            spec = file_specs.get(meta["field"])
            if spec:
                meta["kind"] = spec.get("kind", 'image')
            else:
                meta["kind"] = _guess_file_kind(meta.get('name', ''))
        # handle existing file selections
        for fld in form_def.get("fields", []):
            if fld.get('type') != 'file':
                continue
            nm = fld.get('name')
            if not nm:
                continue
            existing_path = _resolve_existing_file(fld, form_values.get(nm))
            if existing_path:
                spec = file_specs.get(nm) or {}
                files_meta.append({"field": nm, "name": os.path.basename(existing_path), "path": existing_path, "kind": spec.get('kind', 'image'), "from_existing": True})
        overrides = {"_form_values": form_values, "_uploads": files_meta}
        mapping = form_def.get("mapping", [])
    else:
        for meta in files_meta:
            if 'kind' not in meta:
                meta['kind'] = _guess_file_kind(meta.get('name', ''))
        if files_meta:
            overrides["_uploads"] = files_meta

    job_id = uuid.uuid4().hex
    from flask import session
    comfy_url = _resolve_server_for_workflow(wf, explicit_server, form_default_server)
    _jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "wf_path": wf_path,
        "workflow": wf,
        "created_at": time.time(),
        "comfy_url": comfy_url,
        "user": session.get("user"),
        "overrides": overrides,
        "mapping": mapping,
    }
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
    # fallback proxy (uses default server). Prefer job-specific route below
    r = requests.get(f"{_comfy_url()}/view", params={"filename": filename, "subfolder": subfolder, "type": typ}, stream=True, timeout=60)
    if r.status_code != 200:
        return jsonify({"ok": False, "msg": r.text}), 502
    return Response(r.iter_content(8192), content_type=r.headers.get("Content-Type","image/png"))


@jobs_bp.get("/jobs/<job_id>/comfy/view")
@login_required
def job_proxy_view(job_id):
    # Image preview that respects the server used by the specific job
    from flask import Response
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    filename = request.args.get("filename"); subfolder = request.args.get("subfolder","" ); typ = request.args.get("type","output")
    if not filename:
        return jsonify({"ok": False, "msg": "缺少 filename"}), 400
    comfy = j.get("comfy_url") or _comfy_url()
    r = requests.get(f"{comfy}/view", params={"filename": filename, "subfolder": subfolder, "type": typ}, stream=True, timeout=60)
    if r.status_code != 200:
        return jsonify({"ok": False, "msg": r.text}), 502
    return Response(r.iter_content(8192), content_type=r.headers.get("Content-Type","image/png"))


@jobs_bp.get("/jobs/<job_id>/artifacts")
@login_required
def job_artifacts(job_id):
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    return jsonify({"ok": True, "artifacts": j.get("outputs", [])})


@jobs_bp.get("/jobs")
@login_required
def list_jobs():
    # return light-weight summaries
    limit = int(request.args.get("limit", 100))
    items = []
    for jid, j in _jobs.items():
        items.append({
            "job_id": jid,
            "status": j.get("status"),
            "progress": j.get("progress"),
            "workflow": j.get("workflow"),
            "created_at": j.get("created_at"),
            "done_at": j.get("done_at"),
            "outputs": len(j.get("outputs", [])),
            "error": j.get("error"),
        })
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    return jsonify({"ok": True, "items": items[:limit]})


@jobs_bp.get("/jobs/<job_id>/download")
@login_required
def download_single(job_id):
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    filename = request.args.get("filename")
    subfolder = request.args.get("subfolder", "")
    ftype = request.args.get("type", "output")
    if not filename:
        return jsonify({"ok": False, "msg": "缺少 filename"}), 400
    # proxy from the specific ComfyUI server used by this job
    comfy = j.get("comfy_url") or _comfy_url()
    r = requests.get(f"{comfy}/view", params={"filename": filename, "subfolder": subfolder, "type": ftype}, stream=True, timeout=120)
    if r.status_code != 200:
        return jsonify({"ok": False, "msg": r.text}), 502
    from flask import Response
    resp = Response(r.iter_content(8192), content_type=r.headers.get("Content-Type","application/octet-stream"))
    disp_name = filename
    resp.headers['Content-Disposition'] = f'attachment; filename="{disp_name}"'
    return resp


@jobs_bp.get("/jobs/<job_id>/download.zip")
@login_required
def download_zip(job_id):
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    artifacts = j.get("outputs", [])
    if not artifacts:
        return jsonify({"ok": False, "msg": "该任务没有可下载的产物"}), 400
    comfy = j.get("comfy_url") or _comfy_url()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for a in artifacts:
            params = {"filename": a.get("filename"), "subfolder": a.get("subfolder",""), "type": a.get("type","output")}
            try:
                r = requests.get(f"{comfy}/view", params=params, timeout=120)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            arcname = a.get("filename") or f"file_{len(zf.namelist())+1}"
            zf.writestr(arcname, r.content)
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name=f'{job_id}.zip')


@jobs_bp.get("/health")
@login_required
def health():
    server = (request.args.get("server") or _resolve_server_default()).rstrip('/')
    t0 = time.time()
    try:
        r = requests.get(f"{server}/system_stats", timeout=5)
        if r.status_code != 200:
            r = requests.get(server, timeout=5)
        latency = int((time.time() - t0) * 1000)
        return jsonify({"ok": True, "server": server, "latency_ms": latency})
    except Exception as e:
        return jsonify({"ok": False, "server": server, "error": str(e)}), 502
