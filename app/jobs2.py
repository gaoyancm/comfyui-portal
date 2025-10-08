from flask import Blueprint, current_app, request, jsonify, send_file
import os, uuid, threading, queue, time, json, requests, re, tempfile
from functools import wraps
import io, zipfile
from datetime import datetime
from PIL import Image
import mimetypes

jobs_bp = Blueprint("jobs", __name__)

# In-memory queue and job table
_task_q = queue.Queue()
_jobs = {}  # job_id -> {status, progress, prompt_id, outputs:[], error, wf_path, mapping}
_flask_app = None  # set via attach_app(app)
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
JOBS_STATE_DIR = os.path.join(DATA_DIR, "jobs")
MAX_HISTORY_ITEMS = 500

# Allowlisted local preview directories
ALLOWED_PREVIEW_DIRS = {
    "uploads": os.path.join(PROJECT_ROOT, "uploads"),
    "assets/images": os.path.join(PROJECT_ROOT, "assets", "images"),
    "assets/audio": os.path.join(PROJECT_ROOT, "assets", "audio"),
}

@jobs_bp.get("/assets/preview")
def preview_local_asset():
    """Preview local asset from uploads or assets (images/audio)."""
    d = request.args.get("dir", "")
    name = request.args.get("name", "")
    root = ALLOWED_PREVIEW_DIRS.get(d)
    if not root or not name:
        return jsonify({"ok": False, "msg": "bad params"}), 400
    # Normalize and prevent path traversal
    p = os.path.normpath(os.path.join(root, name))
    try:
        base = os.path.commonpath([root, p])
    except Exception:
        return jsonify({"ok": False, "msg": "bad path"}), 400
    if base != root or not os.path.isfile(p):
        return jsonify({"ok": False, "msg": "not found"}), 404
    mt, _ = mimetypes.guess_type(p)
    return send_file(p, mimetype=mt or "application/octet-stream")



def login_required(fn):
    @wraps(fn)
    def wrap(*a, **kw):
        from flask import session
        if "user" not in session:
            return jsonify({"ok": False, "msg": "未登录"}), 401
        return fn(*a, **kw)
    return wrap


def _ensure_job_storage():
    os.makedirs(JOBS_STATE_DIR, exist_ok=True)


def _job_state_path(job_id):
    return os.path.join(JOBS_STATE_DIR, f"{job_id}.json")


def _persist_job_state(job_id):
    job = _jobs.get(job_id)
    if not job:
        return
    _ensure_job_storage()
    payload = {**job, "job_id": job_id}
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=f".{job_id}.", suffix=".tmp", dir=JOBS_STATE_DIR)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, _job_state_path(job_id))
        try:
            files = [os.path.join(JOBS_STATE_DIR, name) for name in os.listdir(JOBS_STATE_DIR) if name.endswith(".json")]
            if len(files) > MAX_HISTORY_ITEMS:
                files.sort(key=lambda p: os.path.getmtime(p))
                for old_path in files[:-MAX_HISTORY_ITEMS]:
                    try:
                        os.remove(old_path)
                    except Exception:
                        pass
        except Exception:
            pass
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _load_job_state(job_id):
    path = _job_state_path(job_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    if isinstance(data, dict):
        data.setdefault("job_id", job_id)
        _jobs[job_id] = data
        return data
    return None


def _get_job(job_id):
    job = _jobs.get(job_id)
    if job:
        return job
    return _load_job_state(job_id)


def _update_job(job_id, **fields):
    job = _get_job(job_id)
    if job is None:
        job = {"job_id": job_id}
        _jobs[job_id] = job
    changed = False
    for key, value in fields.items():
        if job.get(key) != value:
            changed = True
        job[key] = value
    if changed:
        _persist_job_state(job_id)
    return job


def _bump_progress(job, *, step=5, ceiling=95, floor=10):
    """Increase job.progress while keeping value within bounds."""
    try:
        current = float(job.get("progress") or 0)
    except (TypeError, ValueError):
        current = 0
    base = current if current >= floor else floor
    new_value = min(ceiling, base + step)
    if new_value > current:
        job["progress"] = int(new_value)
        job_id = job.get("job_id")
        if job_id:
            _persist_job_state(job_id)


def _apply_history_progress(job, history_item):
    """Try to map ComfyUI history status fields to a percentage."""
    status = history_item.get("status") if isinstance(history_item, dict) else None
    if not isinstance(status, dict):
        return False

    ratios = []
    completed = status.get("completed")
    total = status.get("total") or status.get("max") or status.get("total_nodes")
    ratios.append((completed, total))

    # Comfy websocket progress payload sometimes uses value/max or current/total
    ratios.append((status.get("value"), status.get("max")))
    ratios.append((status.get("current"), status.get("total")))

    best_pct = None
    for done, total in ratios:
        if isinstance(done, (int, float)) and isinstance(total, (int, float)) and total > 0:
            pct = max(0, min(95, int(done / total * 100)))
            best_pct = pct if best_pct is None else max(best_pct, pct)

    if best_pct is None:
        return False

    current = job.get("progress", 0) or 0
    if best_pct > current:
        job["progress"] = best_pct
        job_id = job.get("job_id")
        if job_id:
            _persist_job_state(job_id)
        return True

    return False


def _worker():
    while True:
        job_id = _task_q.get()
        try:
            _run_job(job_id)
        except Exception as e:
            _update_job(job_id, status="error", error=str(e), done_at=time.time())
        finally:
            _task_q.task_done()

_worker_thread_started = False

def attach_app(app):
    global _flask_app, _worker_thread_started
    _flask_app = app
    _ensure_job_storage()
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
            existing.append({'label': entry, 'value': f'existing://{idx}/{entry}', 'preview': f"/api/assets/preview?dir={rel_dir}&name={entry}"})
    if existing:
        field['file_existing'] = existing
        default = field.get('default')
        if isinstance(default, str) and default and not default.startswith('existing://'):
            # 尝试按文件名或标签匹配默认值
            match = None
            for item in existing:
                if default == item.get('value'):
                    match = item
                    break
                label = item.get('label')
                if label and (default == label or default == os.path.basename(label)):
                    match = item
                    break
            if match:
                field['default'] = match.get('value')
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


_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mpg", ".mpeg"}
_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".aac", ".ogg", ".m4a"}


def _normalize_artifact(data, *, default_kind=None):
    if not isinstance(data, dict):
        return None
    filename = data.get("filename") or data.get("name")
    if not filename:
        return None
    subfolder = data.get("subfolder", "")
    typ = data.get("type", "output")
    fmt = data.get("format") or data.get("mime") or data.get("mimetype")
    kind = data.get("kind") or default_kind

    if not kind and isinstance(fmt, str):
        if fmt.startswith("video/"):
            kind = "video"
        elif fmt.startswith("audio/"):
            kind = "audio"
        elif fmt.startswith("image/"):
            kind = "image"

    if not kind:
        ext = os.path.splitext(filename)[1].lower()
        if ext in _VIDEO_EXTS:
            kind = "video"
        elif ext in _AUDIO_EXTS:
            kind = "audio"
        elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}:
            kind = "image"

    if not kind:
        kind = "file"

    artifact = {
        "kind": kind,
        "filename": filename,
        "subfolder": subfolder,
        "type": typ,
    }

    if fmt:
        artifact["format"] = fmt
    elif kind in {"video", "audio"}:
        guess = mimetypes.guess_type(filename)[0]
        if guess:
            artifact["format"] = guess

    if data.get("text") and kind == "text":
        artifact["text"] = data.get("text")

    return artifact


def _add_artifact(artifact, outputs, file_outputs, seen):
    if not artifact:
        return
    outputs.append(artifact)
    fname = artifact.get("filename")
    if fname:
        key = (fname, artifact.get("subfolder", ""), artifact.get("type", "output"))
        if key in seen:
            return
        seen.add(key)
        file_outputs.append(artifact)


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


def _upload_to_comfy(file_path, kind='image', comfy_base=None):
    """
    Upload local file to the selected Comfy server's input folder.
    - Supports endpoints: /upload/image|audio|video
    - Auto converts .webp to .png for compatibility
    Returns: filename on Comfy side
    """
    import io as _io, os as _os, mimetypes as _mimetypes, requests as _requests

    if comfy_base is None:
        comfy_base = _comfy_url()

    basename = _os.path.basename(file_path)
    ext = _os.path.splitext(basename)[1].lower()

    fp = None
    try:
        # WEBP -> PNG
        if kind == 'image' and ext == '.webp':
            with open(file_path, 'rb') as _fp_raw:
                _raw = _fp_raw.read()
            _img = Image.open(_io.BytesIO(_raw)).convert('RGBA')
            _buf = _io.BytesIO()
            _img.save(_buf, format='PNG')
            _buf.seek(0)
            newname = _os.path.splitext(basename)[0] + '.png'
            file_handle = _buf
            upload_name = newname
            mime = 'image/png'
        else:
            fp = open(file_path, 'rb')
            file_handle = fp
            upload_name = basename
            mime = _mimetypes.guess_type(basename)[0]

        def _build_candidates():
            base_url = comfy_base.rstrip('/')
            if kind == 'audio':
                return [
                    (f"{base_url}/upload/audio", 'audio'),
                    (f"{base_url}/upload", 'audio'),
                    (f"{base_url}/upload", 'file'),
                    (f"{base_url}/upload/image", 'image'),
                ]
            if kind == 'video':
                return [
                    (f"{base_url}/upload/video", 'video'),
                    (f"{base_url}/upload", 'video'),
                    (f"{base_url}/upload", 'file'),
                ]
            # 默认 image
            return [
                (f"{base_url}/upload/image", 'image'),
                (f"{base_url}/upload", 'image'),
                (f"{base_url}/upload", 'file'),
            ]

        last_error = None

        for url, field in _build_candidates():
            try:
                if hasattr(file_handle, 'seek'):
                    file_handle.seek(0)
                files = {field: (upload_name, file_handle, mime)} if mime else {field: (upload_name, file_handle)}
                r = _requests.post(url, files=files, data={'type': 'input', 'subfolder': ''}, timeout=120)
            except _requests.RequestException as exc:
                last_error = f"请求 {url} 失败：{exc}"
                continue

            ct = r.headers.get('content-type', '')
            if r.status_code == 200 and ct.startswith('application/json'):
                data = r.json() or {}
                name = data.get('name') or data.get('filename')
                if not name and isinstance(data.get('files'), list) and data['files']:
                    name = data['files'][0].get('filename') or data['files'][0].get('name')
                if name:
                    return name
                last_error = f"接口 {url} 返回异常数据：{data}"
                continue

            snippet = (r.text or '').replace('\n', ' ')[:200]
            last_error = (
                f"接口 {url} 返回 {r.status_code} {r.reason or ''}，Content-Type={ct or '未知'}"
                + (f"，响应片段：{snippet}" if snippet else '')
            )

        raise RuntimeError(f"上传文件到 ComfyUI 失败：{last_error or '未知错误'}")
    finally:
        try:
            if fp and not fp.closed:
                fp.close()
        except Exception:
            pass

def _run_job(job_id):
    j = _get_job(job_id)
    if j is None:
        _update_job(job_id, status="error", error="无法加载任务状态", done_at=time.time())
        return
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
            comfy_name = _upload_to_comfy(meta.get("path"), kind, comfy_base=comfy)
            upload_map[meta.get("field")] = comfy_name
        prompt_json = _apply_form_mapping(prompt_json, mapping, form_values, upload_map)
    else:
        # 若没有 mapping，但 overrides 仅包含内部键（_form_values/_uploads），则不改动工作流
        if set(ov.keys()) <= {"_form_values", "_uploads"}:
            pass
        else:
            prompt_json = _apply_overrides(prompt_json, ov)

    client_id = str(uuid.uuid4())
    _update_job(job_id, status="submitting", progress=5)
    r = requests.post(f"{comfy}/prompt", json={"prompt": prompt_json, "client_id": client_id}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(r.text)
    prompt_id = r.json().get("prompt_id") or r.json().get("promptId")
    if not prompt_id:
        raise RuntimeError("ComfyUI 未返回 prompt_id")
    _update_job(job_id, status="running", progress=10, prompt_id=prompt_id)

    # poll history
    wf_name = (j.get("workflow") or "").lower()
    long_running_prefixes = ("l15", "l6", "l16_1", "l16_2")
    wait_seconds = 1800 if any(wf_name.startswith(prefix) for prefix in long_running_prefixes) else 600
    deadline = time.time() + wait_seconds
    outputs = []
    file_outputs = []  # 记录可下载产物，用于 ZIP
    seen_files = set()
    last_item = None
    while time.time() < deadline:
        try:
            h = requests.get(f"{comfy}/history/{prompt_id}", timeout=30)
        except requests.RequestException:
            _bump_progress(j, step=2, ceiling=90)
            time.sleep(1)
            continue
        if h.status_code != 200:
            _bump_progress(j, step=2, ceiling=90)
            time.sleep(1)
            continue
        try:
            payload = h.json() or {}
        except ValueError:
            _bump_progress(j, step=2, ceiling=90)
            time.sleep(1)
            continue
        item = payload.get(prompt_id)
        if not item:
            _bump_progress(j, step=2, ceiling=90)
            time.sleep(1)
            continue
        last_item = item
        if item.get("node_errors"):
            _update_job(job_id, status="error", error=str(item.get("node_errors")))
            return
        outs = item.get("outputs") or {}
        for node_out in outs.values():
            if not isinstance(node_out, dict):
                continue

            for img in node_out.get("images", []):
                _add_artifact(_normalize_artifact(img, default_kind="image"), outputs, file_outputs, seen_files)

            for video in node_out.get("videos", []):
                _add_artifact(_normalize_artifact(video, default_kind="video"), outputs, file_outputs, seen_files)

            for audio in node_out.get("audio", []):
                _add_artifact(_normalize_artifact(audio, default_kind="audio"), outputs, file_outputs, seen_files)

            for gif in node_out.get("gifs", []):
                _add_artifact(_normalize_artifact(gif, default_kind="video"), outputs, file_outputs, seen_files)

            for file_item in node_out.get("files", []):
                _add_artifact(_normalize_artifact(file_item), outputs, file_outputs, seen_files)

            single_file = node_out.get("file")
            if single_file:
                _add_artifact(_normalize_artifact(single_file), outputs, file_outputs, seen_files)

            single_image = node_out.get("image")
            if single_image:
                _add_artifact(_normalize_artifact(single_image, default_kind="image"), outputs, file_outputs, seen_files)

            text_items = node_out.get("text") or []
            if isinstance(text_items, dict):
                text_items = [text_items]
            for text_item in text_items:
                if isinstance(text_item, dict):
                    content = text_item.get("text") or text_item.get("content") or ""
                    extra = {k: v for k, v in text_item.items() if k not in {"text", "content"}}
                else:
                    content = str(text_item)
                    extra = {}
                if content:
                    artifact = {"kind": "text", "text": content}
                    if extra:
                        artifact.update({"meta": extra})
                    outputs.append(artifact)

        if outputs:
            break
        if not _apply_history_progress(j, item):
            _bump_progress(j)
        time.sleep(1)
    if not outputs:
        status_info = last_item.get("status") if isinstance(last_item, dict) else {}
        state_val = status_info.get("status") if isinstance(status_info, dict) else None
        if state_val in {"success", "finished", "completed"}:
            _update_job(job_id, status="finished", progress=100, outputs=[], done_at=time.time(), file_outputs=[])
            return
        _update_job(job_id, status="timeout", progress=100, done_at=time.time())
        return
    _update_job(job_id, status="finished", progress=100, outputs=outputs, done_at=time.time(), file_outputs=file_outputs)


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
def list_workflows_api():
    return jsonify({"ok": True, "items": _list_workflows_impl()})


@jobs_bp.get("/workflows/<wf>/form")
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
        "job_id": job_id,
    }
    _persist_job_state(job_id)
    _task_q.put(job_id)
    return jsonify({"ok": True, "job_id": job_id})


@jobs_bp.get("/jobs/<job_id>/status")
def job_status(job_id):
    j = _get_job(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    return jsonify({"ok": True, **j})


@jobs_bp.get("/queue")
def queue_overview():
    return jsonify({"ok": True, "queued": _task_q.qsize()})


@jobs_bp.get("/comfy/view")
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
def job_proxy_view(job_id):
    # Image preview that respects the server used by the specific job
    from flask import Response
    j = _get_job(job_id)
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
def job_artifacts(job_id):
    j = _get_job(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    return jsonify({"ok": True, "artifacts": j.get("outputs", [])})


@jobs_bp.get("/jobs")
def list_jobs():
    # return light-weight summaries
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100
    records = {}
    if os.path.isdir(JOBS_STATE_DIR):
        for name in os.listdir(JOBS_STATE_DIR):
            if not name.endswith(".json"):
                continue
            job_id = name[:-5]
            data = _load_job_state(job_id)
            if not isinstance(data, dict):
                continue
            records[job_id] = data
    for jid, job in _jobs.items():
        records[jid] = job

    items = []
    for jid, job in records.items():
        outputs = job.get("outputs") or []
        items.append({
            "job_id": jid,
            "status": job.get("status"),
            "progress": job.get("progress"),
            "workflow": job.get("workflow"),
            "created_at": job.get("created_at"),
            "done_at": job.get("done_at"),
            "outputs": len(outputs),
            "error": job.get("error"),
        })
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    if limit <= 0:
        limit = MAX_HISTORY_ITEMS
    limit = min(limit, MAX_HISTORY_ITEMS)
    return jsonify({"ok": True, "items": items[:limit]})


@jobs_bp.get("/jobs/<job_id>/download")
def download_single(job_id):
    j = _get_job(job_id)
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
def download_zip(job_id):
    j = _get_job(job_id)
    if not j:
        return jsonify({"ok": False, "msg": "不存在的任务"}), 404
    artifacts = j.get("file_outputs") or [a for a in j.get("outputs", []) if a.get("filename")]
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