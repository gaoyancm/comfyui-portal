// ComfyUI Portal main page logic
const $ = (s)=>document.querySelector(s);

function escapeHtml(str){
  return (str ?? '').toString()
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function isProbablyImageFile(file){
  if(!file){ return false; }
  const type = (file.type || '').toLowerCase();
  if(type.startsWith('image/')){ return true; }
  const name = (file.name || '').toLowerCase();
  return /(\.png|\.jpg|\.jpeg|\.bmp|\.gif|\.webp|\.tif|\.tiff)$/i.test(name);
}

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
      if(!val){
        previewBox.style.display = 'none';
        return;
      }

      if(fileKind === 'image'){
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
        return;
      }

      if(fileKind === 'audio'){
        const buildAudio = (src, label) => {
          const audio = document.createElement('audio');
          audio.controls = true;
          audio.preload = 'none';
          audio.src = src;
          audio.className = 'file-preview-audio';
          if(label){ audio.setAttribute('aria-label', label); }
          previewBox.appendChild(audio);
          previewBox.style.display = '';
        };

        if(val.startsWith('upload://') && fileInput && fileInput.files && fileInput.files.length){
          const file = fileInput.files[0];
          if(file && file.type && file.type.startsWith('audio/')){
            const url = URL.createObjectURL(file);
            buildAudio(url, file.name || '');
            previewBox.dataset.url = url;
          }else{
            previewBox.style.display = 'none';
          }
          return;
        }

        const existing = (f.file_existing || []).find(opt => opt.value === val);
        if(existing && existing.preview){
          buildAudio(existing.preview, existing.label || '');
          return;
        }

        previewBox.style.display = 'none';
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

  if(f.type === 'directory'){
    wrap.classList.add('field-directory');

    const hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.name = f.name;
    hidden.value = f.default || '';
    wrap.appendChild(hidden);

    const dirInput = document.createElement('input');
    dirInput.type = 'file';
    dirInput.name = `${f.name}__dir`;
    dirInput.multiple = true;
    dirInput.setAttribute('webkitdirectory', '');
    dirInput.setAttribute('mozdirectory', '');
    dirInput.setAttribute('directory', '');
    dirInput.style.display = 'none';
    dirInput.tabIndex = -1;
    if(f.accept){ dirInput.accept = f.accept; }
    wrap.appendChild(dirInput);

    const pickRow = document.createElement('div');
    pickRow.className = 'directory-picker';

    const pickBtn = document.createElement('button');
    pickBtn.type = 'button';
    pickBtn.className = 'btn pick-directory';
    pickBtn.textContent = f.pick_label || '选择文件夹';
    pickBtn.addEventListener('click', () => dirInput.click());
    pickRow.appendChild(pickBtn);

    const info = document.createElement('span');
    info.className = 'dir-info empty';
    pickRow.appendChild(info);

    wrap.appendChild(pickRow);

    const progressWrap = document.createElement('div');
    progressWrap.className = 'dir-progress';
    progressWrap.style.display = 'none';

    const progressTrack = document.createElement('div');
    progressTrack.className = 'dir-progress-track';
    const progressFill = document.createElement('div');
    progressFill.className = 'dir-progress-fill';
    progressTrack.appendChild(progressFill);
    progressWrap.appendChild(progressTrack);

    const progressText = document.createElement('div');
    progressText.className = 'dir-progress-text muted';
    progressWrap.appendChild(progressText);

    wrap.appendChild(progressWrap);

    const previewWrap = document.createElement('div');
    previewWrap.className = 'dir-preview';
    previewWrap.style.display = 'none';

    const previewImg = document.createElement('img');
    previewImg.className = 'dir-preview-img';
    previewImg.style.display = 'none';
    previewWrap.appendChild(previewImg);

    const previewInfo = document.createElement('div');
    previewInfo.className = 'dir-preview-info';
    previewWrap.appendChild(previewInfo);

    wrap.appendChild(previewWrap);

    const state = {
      dirInput,
      hidden,
      info,
      progressWrap,
      progressFill,
      progressText,
      previewWrap,
      previewImg,
      previewInfo,
      previewUrl: null,
      sortedFiles: [],
      lastImageFile: null,
      lastImagePath: '',
      folderName: '',
      totalBytes: 0,
      progressHideTimer: null,
    };

    const revokePreview = () => {
      if(state.previewUrl){
        URL.revokeObjectURL(state.previewUrl);
        state.previewUrl = null;
      }
    };

    const resetPreview = () => {
      revokePreview();
      state.previewWrap.style.display = 'none';
      state.previewImg.style.display = 'none';
      state.previewImg.removeAttribute('src');
      state.previewImg.alt = '';
      state.previewInfo.textContent = '';
    };

    const resetProgress = () => {
      if(state.progressHideTimer){
        clearTimeout(state.progressHideTimer);
        state.progressHideTimer = null;
      }
      state.progressWrap.style.display = 'none';
      state.progressWrap.classList.remove('error');
      state.progressFill.style.width = '0%';
      state.progressText.textContent = '';
    };

    state.revokePreview = revokePreview;
    state.resetPreview = resetPreview;
    state.resetProgress = resetProgress;

    const updateInfo = () => {
      const files = Array.from(dirInput.files || []);
      files.sort((a, b) => {
        const ap = (a.webkitRelativePath || a.name || '').toLowerCase();
        const bp = (b.webkitRelativePath || b.name || '').toLowerCase();
        return ap.localeCompare(bp);
      });
      state.sortedFiles = files;
      state.totalBytes = files.reduce((sum, file) => sum + (file.size || 0), 0);

      const imagesOnly = files.filter(isProbablyImageFile);
      state.lastImageFile = imagesOnly.length ? imagesOnly[imagesOnly.length - 1] : null;
      state.lastImagePath = state.lastImageFile ? (state.lastImageFile.webkitRelativePath || state.lastImageFile.name || '') : '';

      resetPreview();
      resetProgress();

      if(!files.length){
        hidden.value = '';
        info.textContent = '未选择文件夹';
        info.classList.add('empty');
        state.folderName = '';
        return;
      }
      const sample = files[0];
      const relPath = (sample && (sample.webkitRelativePath || sample.name || '')).replace(/\\+/g, '/');
      let folder = '';
      if(relPath.includes('/')){
        folder = relPath.split('/')[0];
      }
      if(!folder && sample && sample.name){
        folder = sample.name.replace(/\.[^/.]+$/, '');
      }
      state.folderName = folder || '';
      if(folder){
        hidden.value = `dir://${folder}`;
        info.textContent = `已选择文件夹：${folder}（${files.length} 个文件）`;
        info.classList.remove('empty');
      }else{
        hidden.value = `dir://${files.length}`;
        info.textContent = `已选择 ${files.length} 个文件`;
        info.classList.remove('empty');
      }
    };
    updateInfo();
    dirInput.addEventListener('change', updateInfo);

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn ghost';
    clearBtn.textContent = '清除';
    clearBtn.style.marginTop = '6px';
    clearBtn.addEventListener('click', () => {
      dirInput.value = '';
      hidden.value = '';
      info.textContent = '未选择文件夹';
      info.classList.add('empty');
      state.sortedFiles = [];
      state.lastImageFile = null;
      state.lastImagePath = '';
      state.folderName = '';
      state.totalBytes = 0;
      resetPreview();
      resetProgress();
    });
    wrap.appendChild(clearBtn);

    dirInput.dataset.directoryField = '1';
    dirInput._dirState = state;

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
      input.type = 'number'; input.step = 'any'; input.inputMode = 'decimal';
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

function shouldTrackDirectoryUpload(workflowName){
  const upper = (workflowName || '').toUpperCase();
  return upper.startsWith('L16_3_API');
}

function getDirectoryStates(form){
  return Array.from(form.querySelectorAll('input[type="file"][data-directory="1"]'))
    .map(input => input && input._dirState)
    .filter(state => state && state.dirInput);
}

function startDirectoryUploadProgress(states){
  states.forEach(state => {
    if(!state || !(state.dirInput.files && state.dirInput.files.length)){ return; }
    state.resetPreview();
    state.resetProgress();
    state.progressWrap.style.display = 'flex';
    state.progressWrap.classList.remove('error');
    state.progressFill.style.width = '0%';
    const count = state.sortedFiles ? state.sortedFiles.length : 0;
    const countText = count ? ` ${count} 张图片` : '';
    state.progressText.textContent = `正在上传帧文件${countText}... 0%`;
  });
}

function updateDirectoryUploadProgress(states, loaded, total){
  const computable = typeof total === 'number' && total > 0;
  const percent = computable ? Math.min(100, Math.round((loaded / total) * 100)) : null;
  states.forEach(state => {
    if(!state || !(state.dirInput.files && state.dirInput.files.length)){ return; }
    state.progressWrap.style.display = 'flex';
    state.progressWrap.classList.remove('error');
    const count = state.sortedFiles ? state.sortedFiles.length : 0;
    const countText = count ? ` ${count} 张图片` : '';
    if(percent !== null){
      state.progressFill.style.width = `${percent}%`;
      state.progressText.textContent = `正在上传帧文件${countText}... ${percent}%`;
    }else{
      state.progressText.textContent = `正在上传帧文件${countText}...`;
    }
  });
}

function markDirectoryUploadError(states, message){
  const text = message ? `帧文件上传失败：${message}` : '帧文件上传失败，请重试';
  states.forEach(state => {
    if(!state || !(state.dirInput.files && state.dirInput.files.length)){ return; }
    if(state.progressHideTimer){
      clearTimeout(state.progressHideTimer);
      state.progressHideTimer = null;
    }
    state.progressWrap.style.display = 'flex';
    state.progressWrap.classList.add('error');
    state.progressFill.style.width = '100%';
    state.progressText.textContent = text;
  });
}

function showDirectoryLastFramePreview(state, includePrompt){
  if(!state){ return; }
  const count = state.sortedFiles ? state.sortedFiles.length : 0;
  const detailParts = [];
  if(count){ detailParts.push(`共 ${count} 张图片`); }
  const file = state.lastImageFile;
  state.revokePreview();
  if(file && isProbablyImageFile(file)){
    const url = URL.createObjectURL(file);
    state.previewUrl = url;
    state.previewImg.src = url;
    state.previewImg.alt = state.lastImagePath || file.name || '';
    state.previewImg.style.display = 'block';
    let text = detailParts.length ? `${detailParts.join('，')}，` : '';
    text += `最后一帧：${state.lastImagePath || file.name || ''}`;
    if(text){ text += '。'; }
    if(includePrompt){
      text += '帧文件已全部上传，可点击“开始轮询”按钮。';
    }
    state.previewInfo.textContent = text;
    state.previewWrap.style.display = 'flex';
    return;
  }
  if(count){
    state.previewImg.style.display = 'none';
    state.previewImg.removeAttribute('src');
    let text = detailParts.length ? `${detailParts.join('，')}，` : '';
    text += '未检测到可预览的图像。';
    if(includePrompt){
      text += '帧文件已全部上传，可点击“开始轮询”按钮。';
    }
    state.previewInfo.textContent = text;
    state.previewWrap.style.display = 'flex';
    return;
  }
  state.resetPreview();
}

function completeDirectoryUploadSuccess(states){
  states.forEach(state => {
    if(!state || !(state.dirInput.files && state.dirInput.files.length)){ return; }
    if(state.progressHideTimer){
      clearTimeout(state.progressHideTimer);
      state.progressHideTimer = null;
    }
    state.progressWrap.style.display = 'flex';
    state.progressWrap.classList.remove('error');
    state.progressFill.style.width = '100%';
    const count = state.sortedFiles ? state.sortedFiles.length : 0;
    const countText = count ? `（共 ${count} 张图片）` : '';
    state.progressText.textContent = `帧文件上传完成${countText}，可点击“开始轮询”按钮。`;
    showDirectoryLastFramePreview(state, true);
  });
}

function uploadFormWithProgress(fd, onProgress){
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/jobs');
    xhr.responseType = 'text';
    xhr.upload.onprogress = event => {
      if(typeof onProgress === 'function'){
        const loaded = typeof event.loaded === 'number' ? event.loaded : 0;
        const total = typeof event.total === 'number' ? event.total : 0;
        onProgress(loaded, total);
      }
    };
    xhr.onload = () => {
      const status = xhr.status;
      const statusText = xhr.statusText || '';
      const contentType = xhr.getResponseHeader('content-type') || '未知类型';
      let data;
      try{
        data = parseJsonText(xhr.responseText || '', status, statusText, contentType, '提交任务');
      }catch(err){
        reject(err);
        return;
      }
      resolve({ status, statusText, data });
    };
    xhr.onerror = () => reject(new Error('网络错误，上传失败'));
    xhr.send(fd);
  });
}

function parseJsonText(raw, status, statusText, contentType, context){
  if(!raw){
    if(status >= 200 && status < 300){ return {}; }
    throw new Error(`${context}：服务器返回空响应（${status} ${statusText}）`);
  }
  try{
    return JSON.parse(raw);
  }catch(err){
    const snippet = raw.replace(/\s+/g, ' ').trim().slice(0, 160);
    const extra = snippet ? ` 内容片段：${snippet}` : '';
    throw new Error(`${context}：服务器返回了无法解析的响应（${status} ${statusText}，${contentType || '未知类型'}）。${extra}`);
  }
}

async function parseJsonResponse(res, context){
  const raw = await res.text();
  const type = res.headers && res.headers.get ? (res.headers.get('content-type') || '未知类型') : '未知类型';
  return parseJsonText(raw, res.status, res.statusText, type, context);
}

async function authGuard(){
  const r = await fetch('/auth/status');
  if(r.status === 401){ location.href = '/login'; return false; }
  const j = await parseJsonResponse(r, '获取登录状态');
  const bar = document.getElementById('userbar');
  const adminLink = j.role==='admin' ? ` | <a class="pill" href="/admin/settings">后台</a>` : '';
  bar.innerHTML = `已登录：${(j.user||'')}${adminLink} <a class="pill" href="/logout_page" style="margin-left:8px">退出</a>`;
  return true;
}

const LONG_WORKFLOW_PREFIXES = ['L15', 'L6', 'L16_1', 'L16_2'];
const LIMITED_PREVIEW_WORKFLOWS = ['L16_2'];
const AUDIO_SYNC_WORKFLOWS = ['L15_2', 'L16_1', 'L16_2'];

function isLongWorkflowName(name){
  const upper = (name || '').toUpperCase();
  return LONG_WORKFLOW_PREFIXES.some(prefix => upper.startsWith(prefix.toUpperCase()));
}

function shouldLimitPreview(name){
  const upper = (name || '').toUpperCase();
  return LIMITED_PREVIEW_WORKFLOWS.some(prefix => upper.startsWith(prefix.toUpperCase()));
}

function requiresAudioSync(name){
  const upper = (name || '').toUpperCase();
  return AUDIO_SYNC_WORKFLOWS.some(prefix => upper.startsWith(prefix.toUpperCase()));
}

function applyAudioDurationSync(workflowName){
  if(!requiresAudioSync(workflowName)){ return; }
  const form = document.getElementById('jobForm');
  if(!form){ return; }
  const audioField = form.querySelector('input[name="audio_duration"]');
  const durationField = form.querySelector('input[name="duration"]');
  if(!audioField || !durationField){ return; }

  const syncToAudio = () => {
    const audioVal = parseFloat(audioField.value);
    if(!Number.isFinite(audioVal) || audioVal <= 0){ return; }
    if(durationField.dataset.manualDuration === '1'){
      const current = parseFloat(durationField.value);
      if(!Number.isFinite(current) || current <= 0){
        durationField.value = audioVal;
      }
      return;
    }
    durationField.value = audioVal;
  };

  audioField.addEventListener('input', () => {
    delete durationField.dataset.manualDuration;
    syncToAudio();
  });
  audioField.addEventListener('change', () => {
    delete durationField.dataset.manualDuration;
    syncToAudio();
  });

  const markManual = () => {
    durationField.dataset.manualDuration = '1';
  };

  durationField.addEventListener('input', markManual);
  durationField.addEventListener('change', markManual);

  syncToAudio();
}

function filterOutputsForPreview(outputs, workflowName){
  if(!shouldLimitPreview(workflowName)){
    return outputs || [];
  }
  const result = [];
  let firstImageShown = false;
  (outputs || []).forEach(o => {
    if(!o){ return; }
    if(o.kind === 'video'){
      result.push(o);
      return;
    }
    if(o.kind === 'image'){
      if(!firstImageShown){
        result.push(o);
        firstImageShown = true;
      }
      return;
    }
  });
  return result.length ? result : (outputs || []);
}

function applyLongWorkflowNotice(workflowName){
  const notice = document.getElementById('longWorkflowNotice');
  if(!notice){ return; }
  if(isLongWorkflowName(workflowName)){
    notice.style.display = '';
  }else{
    notice.style.display = 'none';
  }
}

function getCurrentWorkflow(){
  const input = document.getElementById('wfInput');
  return input ? (input.value || '') : '';
}

function getCooldownSecondsForWorkflow(workflowName){
  return isLongWorkflowName(workflowName) ? 300 : 120;
}

async function loadWorkflows(){
  const sel = document.getElementById('wfSelect');
  const wfInput = document.getElementById('wfInput');
  const statusEl = document.getElementById('wfStatus');
  if(!sel){ return; }
  const showStatus = (message, isError=false) => {
    if(!statusEl){ return; }
    if(message){
      statusEl.style.display = '';
      statusEl.textContent = message;
    }else{
      statusEl.textContent = '';
      statusEl.style.display = 'none';
    }
    statusEl.classList.toggle('error-text', Boolean(isError && message));
  };
  const currentWorkflow = () => (sel.value || (wfInput ? wfInput.value : '') || '').trim();
  let selected = currentWorkflow();

  try{
    const resp = await fetch('/api/workflows');
    if(resp.status === 401){ location.href = '/login'; return; }
    const data = await parseJsonResponse(resp, '加载工作流列表');
    const items = Array.isArray(data.items) ? data.items : [];
    if(items.length){
      const prev = selected;
      sel.innerHTML = '';
      items.forEach(it => {
        const option = document.createElement('option');
        option.value = it.workflow;
        option.textContent = `${it.workflow}${it.has_form ? '' : ' (无表单)'}`;
        sel.appendChild(option);
      });
      if(prev && items.some(it => it.workflow === prev)){
        selected = prev;
      }else{
        selected = items[0].workflow;
      }
      sel.value = selected;
      showStatus('');
    }else{
      if(!sel.options.length){
        const option = document.createElement('option');
        option.value = '';
        option.disabled = true;
        option.selected = true;
        option.textContent = '暂无可用工作流';
        sel.appendChild(option);
      }
      selected = '';
      showStatus('暂无可用工作流', true);
    }
    if(data && data.ok === false && data.msg){
      showStatus(`加载工作流失败：${data.msg}`, true);
    }
  }catch(err){
    console.error(err);
    const msg = err && err.message ? err.message : String(err);
    showStatus(`加载工作流失败：${msg}`, true);
  }

  if(!selected){
    const fallback = Array.from(sel.options || []).find(opt => !opt.disabled && opt.value);
    if(fallback){
      selected = fallback.value;
      sel.value = selected;
    }
  }

  if(wfInput){
    wfInput.value = selected || '';
  }

  if(selected){
    await loadForm(selected);
    applyLongWorkflowNotice(selected);
  }else{
    applyLongWorkflowNotice('');
    const area = document.getElementById('formFields');
    if(area){
      area.innerHTML = '<div class="muted">请选择工作流后再填写表单。</div>';
    }
  }

  sel.onchange = async ()=>{
    const value = sel.value || '';
    if(wfInput){ wfInput.value = value; }
    if(value){
      await loadForm(value);
      applyLongWorkflowNotice(value);
    }else{
      applyLongWorkflowNotice('');
      const area = document.getElementById('formFields');
      if(area){
        area.innerHTML = '<div class="muted">请选择工作流后再填写表单。</div>';
      }
    }
  };
}

let submitCooldownTimer = null;

function startSubmitCooldown(seconds, prefixText){
  const submitBtn = document.querySelector('#jobForm button[type="submit"]');
  const respEl = document.getElementById('createResp');
  if(!submitBtn || !respEl){ return; }
  if(submitCooldownTimer){
    clearInterval(submitCooldownTimer);
    submitCooldownTimer = null;
  }
  let remaining = Math.max(0, seconds|0);
  const formatMessage = () => {
    const countdownText = `您在“${remaining}”秒之后才能再次提交`;
    if(prefixText){
      const suffix = prefixText.endsWith('。') ? '' : '。';
      respEl.textContent = `${prefixText}${suffix}${countdownText}`;
    }else{
      respEl.textContent = countdownText;
    }
  };
  submitBtn.disabled = true;
  formatMessage();
  if(remaining <= 0){
    submitBtn.disabled = false;
    if(prefixText){ respEl.textContent = prefixText; }
    return;
  }
  submitCooldownTimer = setInterval(() => {
    remaining -= 1;
    if(remaining <= 0){
      clearInterval(submitCooldownTimer);
      submitCooldownTimer = null;
      submitBtn.disabled = false;
      if(prefixText){
        respEl.textContent = prefixText;
      }else{
        respEl.textContent = '';
      }
      return;
    }
    formatMessage();
  }, 1000);
}

async function loadForm(wfname){
  const area = document.getElementById('formFields');
  if(!area){ return; }
  if(!wfname){
    area.innerHTML = '<div class="muted">请选择工作流后再填写表单。</div>';
    return;
  }
  area.innerHTML = '<div class="muted">正在加载表单…</div>';
  try{
    const r = await fetch(`/api/workflows/${encodeURIComponent(wfname)}/form`);
    if(r.status === 401){ location.href = '/login'; return; }
    const j = await parseJsonResponse(r, '加载表单');
    const fields = (j.form && j.form.fields) || [];
    area.innerHTML = '';
    if(!fields.length){
      area.innerHTML = '<div class="muted">该工作流暂未提供表单定义，可直接提交。</div>';
      return;
    }
    fields.forEach(f=>renderField(area, f));
    applyAudioDurationSync(wfname);
  }catch(err){
    const msg = err && err.message ? err.message : String(err);
    area.innerHTML = `<div class="error-text">加载表单失败：${escapeHtml(msg)}</div>`;
  }
}

function bindSubmit(){
  const form = document.getElementById('jobForm');
  const submitBtn = form.querySelector('button[type="submit"]');
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    if(submitBtn){ submitBtn.disabled = true; }
    const respBox = document.getElementById('createResp');
    if(respBox){ respBox.textContent = ''; }
    const wfName = getCurrentWorkflow();
    if(requiresAudioSync(wfName)){
      const audioField = form.querySelector('input[name="audio_duration"]');
      const durationField = form.querySelector('input[name="duration"]');
      if(audioField && durationField){
        const audioVal = parseFloat(audioField.value);
        const durationVal = parseFloat(durationField.value);
        if(Number.isFinite(audioVal) && Number.isFinite(durationVal)){
          if(audioVal <= 0 || durationVal <= 0){
            if(submitBtn){ submitBtn.disabled = false; }
            if(respBox){ respBox.textContent = '提交失败：音频时长和生成时长必须大于 0。'; }
            (durationVal <= 0 ? durationField : audioField).focus();
            return;
          }
          const maxAllowed = Math.max(audioVal * 2, audioVal + 10);
          if(durationVal > maxAllowed){
            if(submitBtn){ submitBtn.disabled = false; }
            if(respBox){ respBox.textContent = '提交失败：生成时长需要与音频时长接近，请调整“生成时长(秒)”字段。'; }
            durationField.focus();
            return;
          }
        }
      }
    }
    const fd = new FormData(e.target);
    let cooldownStarted = false;
    const dirStates = getDirectoryStates(form);
    const trackDirUpload = shouldTrackDirectoryUpload(wfName)
      && dirStates.some(state => state && state.dirInput.files && state.dirInput.files.length);
    try{
      let j;
      if(trackDirUpload){
        startDirectoryUploadProgress(dirStates);
        let uploadRes;
        try{
          uploadRes = await uploadFormWithProgress(fd, (loaded, total) => {
            updateDirectoryUploadProgress(dirStates, loaded, total);
          });
        }catch(uploadErr){
          const message = uploadErr && uploadErr.message ? uploadErr.message : String(uploadErr);
          if(respBox){ respBox.textContent = `提交失败：${message}`; }
          markDirectoryUploadError(dirStates, message);
          return;
        }
        j = uploadRes.data;
        if(!(uploadRes.status >= 200 && uploadRes.status < 300) && !j.ok){
          const msg = j && (j.error || j.message);
          const statusLabel = `${uploadRes.status || ''} ${uploadRes.statusText || ''}`.trim();
          const fallback = statusLabel ? `服务器返回错误（${statusLabel}）` : '服务器返回错误';
          if(respBox){ respBox.textContent = `提交失败：${msg || fallback}`; }
          markDirectoryUploadError(dirStates, msg || fallback);
          return;
        }
      }else{
        const res = await fetch('/api/jobs', {method:'POST', body:fd});
        try{
          j = await parseJsonResponse(res, '提交任务');
        }catch(parseErr){
          if(respBox){ respBox.textContent = `提交失败：${parseErr.message || parseErr}`; }
          return;
        }
        if(!res.ok && !j.ok){
          const msg = j && (j.error || j.message);
          const fallback = `服务器返回错误（${res.status} ${res.statusText}）`;
          if(respBox){ respBox.textContent = `提交失败：${msg || fallback}`; }
          return;
        }
      }
      if(j && j.ok){
        if(trackDirUpload){
          completeDirectoryUploadSuccess(dirStates);
        }
        if(j.job_id){ document.getElementById('jobId').value = j.job_id; }
        const baseSuccess = `提交成功，任务 ID：${j.job_id || ''}`.trim();
        const successText = trackDirUpload
          ? `${baseSuccess}。帧文件已上传完成，可点击“开始轮询”按钮查看任务状态。`
          : baseSuccess;
        const cooldownSeconds = getCooldownSecondsForWorkflow(wfName);
        startSubmitCooldown(cooldownSeconds, successText);
        applyLongWorkflowNotice(wfName);
        cooldownStarted = true;
      }else{
        const msg = j && j.error ? `提交失败：${j.error}` : '提交失败，请稍后重试。';
        if(respBox){ respBox.textContent = msg; }
        if(trackDirUpload){
          markDirectoryUploadError(dirStates, (j && j.error) || '提交失败，请稍后重试。');
        }
      }
    }catch(err){
      const message = err && err.message ? err.message : String(err);
      if(respBox){ respBox.textContent = `提交失败：${message}`; }
      if(trackDirUpload){
        markDirectoryUploadError(dirStates, message);
      }
    }finally{
      if(!cooldownStarted && submitBtn){ submitBtn.disabled = false; }
    }
  });
}

async function updateQueue(){
  try{
    const r = await fetch('/api/queue');
    const j = await parseJsonResponse(r, '获取队列信息');
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
      let j;
      try{
        const r = await fetch(`/api/jobs/${id}/status`);
        j = await parseJsonResponse(r, '获取任务状态');
      }catch(err){
        console.error(err);
        document.getElementById('stateText').textContent = '获取任务状态失败';
        const detailErr = document.getElementById('detailsPre');
        if(detailErr) detailErr.textContent = `${err}`;
        return;
      }
      // 仅在详情中保留原始 JSON
      const detail = document.getElementById('detailsPre');
      if(detail) detail.textContent = JSON.stringify(j,null,2);
      // 顶部简要信息
      document.getElementById('stateText').textContent = j.status || '-';
      if(j.workflow){
        applyLongWorkflowNotice(j.workflow);
      }else{
        applyLongWorkflowNotice(getCurrentWorkflow());
      }
      const jobErrorEl = document.getElementById('jobError');
      if(jobErrorEl){
        let message = '';
        if(j.status === 'error'){
          message = j.error ? `任务失败：${j.error}` : '任务失败：未返回具体原因。';
        }else if(j.status === 'timeout'){
          message = j.error ? `任务超时：${j.error}` : '任务超时：长时间未收到服务器响应。';
        }else if(j.error && j.status !== 'finished'){
          message = j.error.startsWith('提示：') ? j.error : `提示：${j.error}`;
        }
        jobErrorEl.textContent = message;
        jobErrorEl.style.display = message ? '' : 'none';
      }
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
      if(j.ok && Array.isArray(j.outputs) && j.outputs.length){
        const workflowName = j.workflow || getCurrentWorkflow();
        const rawOutputs = j.outputs || [];
        const outputs = filterOutputsForPreview(rawOutputs, workflowName);
        const fileOutputs = (j.file_outputs || rawOutputs).filter(o => o && o.filename);
        const parts = outputs.map(o => {
          if(!o){ return ''; }
          if(o.kind === 'text' && o.text){
            return `<div class=\"artifact artifact-text\"><div class=\"artifact-caption\">文本输出</div><pre>${escapeHtml(o.text)}</pre></div>`;
          }
          if(o.kind === 'video' && o.filename){
            const url = `/api/jobs/${id}/comfy/view?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            const dl = `/api/jobs/${id}/download?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            const type = o.format || 'video/mp4';
            return `<div class=\"artifact artifact-video\"><div class=\"artifact-caption\">视频输出：${escapeHtml(o.filename || '')}</div><video controls preload=\"metadata\" src=\"${url}\" type=\"${escapeHtml(type)}\"></video><div><a href=\"${dl}\">下载</a></div></div>`;
          }
          if(o.kind === 'audio' && o.filename){
            const url = `/api/jobs/${id}/comfy/view?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            const dl = `/api/jobs/${id}/download?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            return `<div class=\"artifact artifact-audio\"><div class=\"artifact-caption\">音频输出：${escapeHtml(o.filename || '')}</div><audio controls preload=\"none\" src=\"${url}\"></audio><div><a href=\"${dl}\">下载</a></div></div>`;
          }
          if(o.kind === 'image' && o.filename){
            const url = `/api/jobs/${id}/comfy/view?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            const dl = `/api/jobs/${id}/download?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            return `<div class=\"artifact artifact-image\"><img class=\"thumb\" src=\"${url}\" alt=\"${escapeHtml(o.filename || '')}\" /><div><a href=\"${dl}\">下载</a></div></div>`;
          }
          if(o.filename){
            const url = `/api/jobs/${id}/comfy/view?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            const dl = `/api/jobs/${id}/download?filename=${encodeURIComponent(o.filename)}&subfolder=${encodeURIComponent(o.subfolder||'')}&type=${encodeURIComponent(o.type||'output')}`;
            return `<div class=\"artifact\"><div class=\"artifact-caption\">${escapeHtml(o.filename || '文件')}</div><a href=\"${url}\" target=\"_blank\">预览</a> · <a href=\"${dl}\">下载</a></div>`;
          }
          return '';
        }).join('');
        const zip = fileOutputs.length ? `<div class=\"artifact-zip\"><a href=\"/api/jobs/${id}/download.zip\">下载全部文件为 ZIP</a></div>` : '';
        document.getElementById('images').innerHTML = zip + parts;
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
