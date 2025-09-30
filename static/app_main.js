// ComfyUI Portal main page logic
const $ = (s)=>document.querySelector(s);

function renderField(container, f){
  const wrap = document.createElement('div');
  wrap.className = 'field';
  const label = document.createElement('label');
  label.textContent = f.label || f.name;
  wrap.appendChild(label);

  if(f.type === 'file'){
    wrap.classList.add('field-file');
    const hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = f.name;
    hidden.value = f.default || '';
    wrap.appendChild(hidden);

    const existingMap = new Map();
    let select = null;
    const fileSpec = f.file || {};
    const fileKind = fileSpec.kind || 'image';

    if(Array.isArray(f.file_existing) && f.file_existing.length){
      select = document.createElement('select');
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '请选择文件';
      select.appendChild(placeholder);
      f.file_existing.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value || '';
        option.textContent = opt.label || opt.value || '';
        select.appendChild(option);
        if(option.value){ existingMap.set(option.value, option.textContent); }
      });
      if(hidden.value && existingMap.has(hidden.value)){
        select.value = hidden.value;
      }
      select.addEventListener('change', () => {
        if(select.value){
          hidden.value = select.value;
          if(fileInput){ fileInput.value = ''; }
        } else if(!(fileInput && fileInput.files.length)){
          hidden.value = '';
        }
        refreshInfo();
      });
      wrap.appendChild(select);
    }

    let fileInput = null;
    if(f.allow_upload !== false){
      fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.name = `${f.name}__upload`;
      if(f.accept){ fileInput.accept = f.accept; }
      fileInput.addEventListener('change', () => {
        if(fileInput.files && fileInput.files.length){
          hidden.value = `upload://${fileInput.files[0].name}`;
          if(select){ select.value = ''; }
        } else if(select && select.value){
          hidden.value = select.value;
        } else {
          hidden.value = '';
        }
        refreshInfo();
      });
      wrap.appendChild(fileInput);
    }

    const info = document.createElement('div');
    info.className = 'muted';
    const previewBox = document.createElement('div');
    previewBox.className = 'file-preview';
    previewBox.style.display = 'none';

    const revokePreviewUrl = () => {
      if(previewBox.dataset.url){
        URL.revokeObjectURL(previewBox.dataset.url);
        delete previewBox.dataset.url;
      }
    };

    const updatePreview = (val) => {
      revokePreviewUrl();
      previewBox.innerHTML = '';
      if(!val || fileKind !== 'image'){
        previewBox.style.display = 'none';
        return;
      }
      if(val.startsWith('upload://') && fileInput && fileInput.files && fileInput.files.length){
        const file = fileInput.files[0];
        if(file && file.type && file.type.startsWith('image/')){
          const url = URL.createObjectURL(file);
          const img = document.createElement('img');
          img.src = url;
          img.alt = file.name || '';
          img.className = 'file-preview-img';
          previewBox.appendChild(img);
          previewBox.style.display = '';
          previewBox.dataset.url = url;
        }else{
          previewBox.style.display = 'none';
        }
        return;
      }
      const existing = (f.file_existing || []).find(opt => opt.value === val);
      if(existing && existing.preview){
        const img = document.createElement('img');
        img.src = existing.preview;
        img.alt = existing.label || '';
        img.className = 'file-preview-img';
        previewBox.appendChild(img);
        previewBox.style.display = '';
        return;
      }
      previewBox.style.display = 'none';
    };
    const refreshInfo = () => {
      const val = hidden.value;
      if(!val){
        info.textContent = '未选择文件';
      }else if(existingMap.has(val)){
        info.textContent = `已选择库文件：${existingMap.get(val)}`;
      }else if(val.startsWith('upload://')){
        info.textContent = `将上传本地文件：${val.slice('upload://'.length)}`;
      }else{
        info.textContent = val;
      }
      updatePreview(val);
    };
    refreshInfo();
    wrap.appendChild(info);
    wrap.appendChild(previewBox);

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn ghost';
    clearBtn.textContent = '清除';
    clearBtn.style.marginTop = '6px';
    clearBtn.addEventListener('click', () => {
      if(select){ select.value = ''; }
      if(fileInput){ fileInput.value = ''; }
      hidden.value = '';
      revokePreviewUrl();
      refreshInfo();
    });
    wrap.appendChild(clearBtn);

    if(f.help){
      const hint = document.createElement('div');
      hint.className = 'muted';
      hint.textContent = f.help;
      wrap.appendChild(hint);
    }

    container.appendChild(wrap);
    return;
  }

  let input;
  switch(f.type){
    case 'textarea':
      input = document.createElement('textarea');
      input.rows = f.rows || 4;
      break;
    case 'number':
    case 'integer':
      input = document.createElement('input');
      input.type = 'number';
      if(f.min !== undefined) input.min = f.min;
      if(f.max !== undefined) input.max = f.max;
      if(f.step !== undefined) input.step = f.step;
      if(f.type === 'integer') input.step = f.step || '1';
      break;
    case 'select':
      input = document.createElement('select');
      (f.options || []).forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value ?? opt;
        option.textContent = opt.label ?? opt;
        input.appendChild(option);
      });
      break;
    default:
      input = document.createElement('input');
      input.type = 'text';
      break;
  }
  input.name = f.name;
  if(f.placeholder){
    input.placeholder = f.placeholder;
  }
  if(f.default !== undefined && f.default !== null){
    input.value = f.default;
  }
  wrap.appendChild(input);
  if(f.help){
    const hint = document.createElement('div');
    hint.className = 'muted';
    hint.textContent = f.help;
    wrap.appendChild(hint);
  }
  container.appendChild(wrap);
}



async function authGuard(){
  const r = await fetch('/auth/status');
  if(r.status === 401){ location.href = '/login'; return false; }
  const j = await r.json();
  const bar = document.getElementById('userbar');
  const adminLink = j.role==='admin' ? ` | <a class="pill" href="/admin/settings">后台</a>` : '';
  bar.innerHTML = `已登录：${(j.user||'')}${adminLink} <a class="pill" href="/logout_page" style="margin-left:8px">退出</a>`;
  return true;
}

async function loadWorkflows(){
  const sel = document.getElementById('wfSelect');
  const resp = await fetch('/api/workflows'); const j = await resp.json();
  sel.innerHTML = '';
  (j.items||[]).forEach(it=>{ const o=document.createElement('option'); o.value=it.workflow; o.textContent=it.workflow+(it.has_form?'':' (无表单)'); sel.appendChild(o)});
  if(j.items&&j.items.length){ sel.value = j.items[0].workflow; document.getElementById('wfInput').value = sel.value; await loadForm(sel.value); }
  sel.onchange = async ()=>{ document.getElementById('wfInput').value = sel.value; await loadForm(sel.value); };
}

async function loadForm(wfname){
  const area = document.getElementById('formFields'); area.innerHTML='';
  const r = await fetch(`/api/workflows/${encodeURIComponent(wfname)}/form`); const j = await r.json();
  const fields = (j.form && j.form.fields) || [];
  if(!fields.length){ area.innerHTML = '<div class="muted">该工作流暂未提供表单定义，可直接提交。</div>'; }
  fields.forEach(f=>renderField(area, f));
}

function bindSubmit(){
  document.getElementById('jobForm').addEventListener('submit', async (e)=>{
    e.preventDefault();
    const fd = new FormData(e.target);
    try{
      const res = await fetch('/api/jobs', {method:'POST', body:fd});
      const j = await res.json();
      document.getElementById('createResp').textContent = JSON.stringify(j);
      if(j.ok){ document.getElementById('jobId').value = j.job_id; }
    }catch(err){ document.getElementById('createResp').textContent = err+''; }
  });
}

async function updateQueue(){
  try{
    const r = await fetch('/api/queue');
    const j = await r.json();
    if(j && typeof j.queued !== 'undefined'){
      document.getElementById('queueCount').textContent = j.queued;
    }
  }catch{}
}

function bindPoll(){
  document.getElementById('btnPoll').addEventListener('click', async ()=>{
    const id = document.getElementById('jobId').value.trim();
    if(!id) return;
    async function step(){
      const r = await fetch(`/api/jobs/${id}/status`);
      const j = await r.json();
      // 仅在详情中保留原始 JSON
      const detail = document.getElementById('detailsPre');
      if(detail) detail.textContent = JSON.stringify(j,null,2);
      // 顶部简要信息
      document.getElementById('stateText').textContent = j.status || '-';
      updateQueue();
      const pw = document.getElementById('progWrap');
      const pb = document.getElementById('progBar');
      const pt = document.getElementById('progText');
      if(j.ok){
        const p = Math.max(0, Math.min(100, j.progress||0));
        pb.style.width = p + '%';
        pt.textContent = `${j.status||''} · ${p}%`;
        const show = (j.status==='queued' || j.status==='submitting' || j.status==='running');
        pw.style.display = show ? 'block' : 'none';
      }
      if(j.ok && j.outputs){
        const imgs = (j.outputs||[]).map(o=>{
          const url = `/api/jobs/${id}/comfy/view?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
          const dl = `/api/jobs/${id}/download?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
          return `<div style=\"display:inline-block;text-align:center;margin:4px\"><img class=\"thumb\" style=\"max-width:180px;display:block\" src=\"${url}\" /><a href=\"${dl}\">下载</a></div>`
        }).join('');
        const zip = `<div style=\"margin:8px 0\"><a href=\"/api/jobs/${id}/download.zip\">下载全部为 ZIP</a></div>`;
        document.getElementById('images').innerHTML = zip + imgs;
      } else if(j.ok && (j.status==='queued' || j.status==='running' || j.status==='submitting')){
        setTimeout(step, 1200);
      }
    }
    step();
  });
}

async function PortalMain(){
  const ok = await authGuard();
  if(!ok) return;
  await loadWorkflows();
  bindSubmit();
  bindPoll();
  // 详情开关
  const tgl = document.getElementById('btnToggleDetails');
  if(tgl){
    tgl.onclick = ()=>{
      const d = document.getElementById('details');
      const visible = d.style.display !== 'none';
      d.style.display = visible ? 'none' : 'block';
      tgl.textContent = visible ? '显示详情' : '隐藏详情';
    };
  }
}

window.PortalMain = PortalMain;
