let currentPlatform = 'jzt';
let uploadedAnalysis = null;
let currentConfirmedSheet = null;
let previewDataResult = null;

function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
  const btn = Array.from(document.querySelectorAll('.nav-tab')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(name));
  if (btn) btn.classList.add('active');
  const content = document.getElementById('tab-' + name);
  if (content) content.style.display = 'block';
  if (name === 'tasks') loadTasks();
  if (name === 'runs') loadRuns();
  if (name === 'settings') loadSettings();
}

function selectPlatform(code) {
  currentPlatform = code;
  document.querySelectorAll('.platform-card').forEach(c => c.classList.remove('selected'));
  const el = document.getElementById('card-' + code);
  if (el) el.classList.add('selected');
  if (uploadedAnalysis && document.getElementById('excelFileInput').files.length > 0) {
    reanalyzeUploadedFile();
  }
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    document.getElementById('loginModal').style.display = 'flex';
    throw new Error('未授权');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return await res.json();
}

async function submitLogin() {
  const pwd = document.getElementById('loginPasswordInput').value;
  try {
    await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    });
    document.getElementById('loginModal').style.display = 'none';
    window.location.reload();
  } catch (e) {
    alert('口令错误，请重试');
  }
}

async function checkAuth() {
  try {
    const res = await fetch('/api/auth/check');
    const d = await res.json();
    if (!d.authenticated) {
      document.getElementById('loginModal').style.display = 'flex';
    }
  } catch (e) {
    document.getElementById('loginModal').style.display = 'flex';
  }
}

async function handleFileSelected(event) {
  const file = event.target.files[0];
  if (!file) return;
  document.getElementById('uploadBoxText').innerText = '已选择: ' + file.name + ' (正在深度解析表头...)';
  await reanalyzeUploadedFile();
}

async function reanalyzeUploadedFile() {
  const file = document.getElementById('excelFileInput').files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  formData.append('selected_platform', currentPlatform);

  try {
    const res = await apiFetch('/api/upload', { method: 'POST', body: formData });
    uploadedAnalysis = res;
    renderAnalysisResult(res);
  } catch (e) {
    alert('上传分析失败: ' + e.message);
  }
}

function renderAnalysisResult(res) {
  const sheets = res.sheets;
  if (!sheets || sheets.length === 0) return;

  const first = sheets[0];
  const mismatchCard = document.getElementById('mismatchAlertCard');
  if (first.needs_confirm) {
    document.getElementById('mismatchAlertText').innerText = first.confirm_message;
    mismatchCard.style.display = 'block';
  } else {
    mismatchCard.style.display = 'none';
  }

  const container = document.getElementById('sheetsListContainer');
  container.innerHTML = '';
  sheets.forEach((s, idx) => {
    const isChecked = idx === 0 ? 'checked' : '';
    const unmappedCols = s.column_mapping.filter(c => !c.mapped && !c.is_key).map(c => c.column_name);
    const mappedCols = s.column_mapping.filter(c => c.mapped).map(c => c.column_name);

    const card = document.createElement('div');
    card.style.border = '1px solid var(--border)';
    card.style.borderRadius = '6px';
    card.style.padding = '16px';
    card.style.marginBottom = '12px';
    card.style.background = '#fafbfc';

    let mappedHtml = mappedCols.slice(0, 8).map(c => '<span class="ok-pill">' + c + '</span>').join('');
    if (mappedCols.length > 8) mappedHtml += '<span>等共' + mappedCols.length + '列</span>';

    let unmappedHtml = '';
    if (unmappedCols.length > 0) {
      unmappedHtml = '<div style="font-size: 12px; margin-top: 6px;"><span style="font-weight: 500; color: #b75e00;">未识别/自定义指标 (' + unmappedCols.length + '):</span> ' +
        unmappedCols.map(c => '<span class="unmapped-pill" title="接口无对应指标，将保留列结构并写空值">' + c + '</span>').join('') + '</div>';
    }

    card.innerHTML = 
      '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">' +
        '<label style="font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; cursor: pointer;">' +
          '<input type="checkbox" class="sheet-checkbox" data-idx="' + idx + '" ' + isChecked + ' onchange="updateSelectedSheets()">' +
          '<span>工作表: ' + s.sheet_title + '</span>' +
        '</label>' +
        '<span class="badge badge-success">维度: ' + s.dimension + '</span>' +
      '</div>' +
      '<div style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">' +
        '核心主键列: <strong style="color:var(--text)">' + s.id_column + '</strong> | 识别到 ' + s.detected_entity_ids.length + ' 个实体 ID (前几项: ' + (s.sample_id_values.join(', ') || '无') + ')' +
      '</div>' +
      '<div style="font-size: 12px;">' +
        '<span style="font-weight: 500;">标准指标列 (' + mappedCols.length + '):</span> ' + mappedHtml +
      '</div>' + unmappedHtml;

    container.appendChild(card);
  });

  document.getElementById('sheetAnalysisCard').style.display = 'block';
  updateSelectedSheets();
}

function confirmPlatformChoice(doSwitch) {
  const first = uploadedAnalysis.sheets[0];
  if (doSwitch) {
    selectPlatform(first.detected_platform);
  } else {
    document.getElementById('mismatchAlertCard').style.display = 'none';
  }
}

function updateSelectedSheets() {
  const checkedBoxes = Array.from(document.querySelectorAll('.sheet-checkbox:checked'));
  if (checkedBoxes.length > 0) {
    const firstIdx = parseInt(checkedBoxes[0].getAttribute('data-idx'));
    currentConfirmedSheet = uploadedAnalysis.sheets[firstIdx];
    document.getElementById('previewCard').style.display = 'block';
    runPreviewFetch();
  } else {
    document.getElementById('previewCard').style.display = 'none';
    document.getElementById('scheduleConfigCard').style.display = 'none';
  }
}

async function runPreviewFetch() {
  if (!currentConfirmedSheet) return;
  const s = currentConfirmedSheet;
  document.getElementById('previewStatus').innerHTML = '⏳ 正在通过平台接口抓取部分数据进行验证...';

  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const yesterdayStr = yesterday.toISOString().slice(0, 10);
  
  // 智能决策预览日期窗口：如果用户上传的是历史归档表（如8月份），必须优先对齐样本真实起止日
  let startStr, endStr;
  if (s.min_sample_date && s.max_sample_date) {
    startStr = s.min_sample_date;
    endStr = s.max_sample_date <= yesterdayStr ? s.max_sample_date : yesterdayStr;
  } else {
    const startD = new Date();
    startD.setDate(startD.getDate() - 7);
    startStr = startD.toISOString().slice(0, 10);
    endStr = yesterdayStr;
  }

  try {
    const res = await apiFetch('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        platform: currentPlatform,
        sheet_title: s.sheet_title,
        headers: s.headers,
        entity_ids: s.detected_entity_ids,
        id_column: s.id_column,
        date_column: s.date_column,
        dimension: s.dimension,
        start_date: startStr,
        end_date: endStr
      })
    });

    previewDataResult = res;
    renderPreviewTable(res);
  } catch (e) {
    document.getElementById('previewStatus').innerHTML = '<span style="color:var(--danger)">❌ 抓取失败: ' + e.message + '</span>';
  }
}

function renderPreviewTable(res) {
  const thead = document.getElementById('previewThead');
  const tbody = document.getElementById('previewTbody');
  thead.innerHTML = '';
  tbody.innerHTML = '';

  const tr = document.createElement('tr');
  res.headers.forEach(h => {
    const th = document.createElement('th');
    th.innerText = h;
    tr.appendChild(th);
  });
  thead.appendChild(tr);

  if (!res.rows || res.rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="' + res.headers.length + '" style="text-align:center; padding:20px;">平台接口返回 0 条数据（可能是选定实体在对应日期内未投放）</td></tr>';
  } else {
    res.rows.slice(0, 15).forEach(row => {
      const rTr = document.createElement('tr');
      row.forEach(val => {
        const td = document.createElement('td');
        td.innerText = val !== null ? val : '';
        rTr.appendChild(td);
      });
      tbody.appendChild(rTr);
    });
  }

  document.getElementById('previewStatus').innerHTML = '✅ 成功拉取到 <strong>' + res.total_fetched + '</strong> 行数据明细（下表展示前 ' + Math.min(res.rows.length, 15) + ' 行预览，未映射指标已安全留空）';
}

// replaced
function old_proceedToSchedule() {
  document.getElementById('scheduleConfigCard').style.display = 'block';
  const file = document.getElementById('excelFileInput').files[0];
  const baseName = file ? file.name.replace(/\.[^/.]+$/, '') : '数据同步表';
  document.getElementById('taskNameInput').value = baseName + '_' + (currentPlatform === 'jzt' ? '京准通' : currentPlatform === 'taobao' ? '淘宝星河' : '聚光');
  applyFreqPreset();
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

function applyFreqPreset() {
  const val = document.getElementById('freqPresetSelect').value;
  const rruleInput = document.getElementById('rruleInput');
  if (val === 'daily_0900') rruleInput.value = 'RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0';
  if (val === 'daily_1330') rruleInput.value = 'RRULE:FREQ=DAILY;BYHOUR=13;BYMINUTE=30';
  if (val === 'workdays_0900') rruleInput.value = 'RRULE:FREQ=WEEKLY;BYHOUR=9;BYMINUTE=0;BYDAY=MO,TU,WE,TH,FR';
  if (val === 'mondays_0900') rruleInput.value = 'RRULE:FREQ=WEEKLY;BYHOUR=9;BYMINUTE=0;BYDAY=MO';
  if (val === 'every_4h') rruleInput.value = 'RRULE:FREQ=HOURLY;INTERVAL=4';
  updateNextRunPreview();
}

function updateNextRunPreview() {
  const rrule = document.getElementById('rruleInput').value;
  document.getElementById('nextRunPreviewText').innerText = '当前规则: ' + rrule + ' (自动按北京时间调度执行)';
}

async function submitCreateTask() {
  const taskName = document.getElementById('taskNameInput').value.trim();
  if (!taskName) {
    alert('请输入飞书表格名称');
    return;
  }
  const updateMode = document.getElementById('updateModeSelect').value;
  const calEl = document.getElementById('calibrationDaysSelect'); const calibrationDays = calEl ? (parseInt(calEl.value, 10) || 0) : 2;
  const rrule = document.getElementById('rruleInput').value;
  const writeInitial = document.getElementById('writeInitialCheck').checked;

  const checkedBoxes = Array.from(document.querySelectorAll('.sheet-checkbox:checked'));
  const sheetsPayload = [];
  checkedBoxes.forEach(b => {
    const idx = parseInt(b.getAttribute('data-idx'));
    const s = uploadedAnalysis.sheets[idx];
    sheetsPayload.push({
      sheet_title: s.sheet_title,
      dimension: s.dimension,
      id_column: s.id_column,
      date_column: s.date_column,
      headers: s.headers,
      entity_ids: s.detected_entity_ids,
      column_mapping: s.column_mapping,
      initial_rows: (previewDataResult && previewDataResult.rows) ? previewDataResult.rows : []
    });
  });

  const btn = document.getElementById('createTaskSubmitBtn');
  btn.innerText = '⏳ 正在飞书创建表格并配置权限...';
  btn.disabled = true;

  try {
    const res = await apiFetch('/api/create_task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_name: taskName,
        platform: currentPlatform,
        update_mode: updateMode,
        calibration_days: calibrationDays,
        rrule: rrule,
        sheets: sheetsPayload,
        write_initial_data: writeInitial
      })
    });

    alert('🎉 飞书表格创建成功！\n已自动存入共享文件夹并开启全员可编辑权限。\n定时任务已正式生效！');
    btn.innerText = '🚀 立即生成飞书表格并启用定时任务';
    btn.disabled = false;
    switchTab('tasks');
  } catch (e) {
    alert('创建失败: ' + e.message);
    btn.innerText = '🚀 立即生成飞书表格并启用定时任务';
    btn.disabled = false;
  }
}

async function loadTasks() {
  try {
    const tasks = await apiFetch('/api/tasks');
    document.getElementById('taskCountBadge').innerText = tasks.length;
    const container = document.getElementById('tasksListContainer');
    if (!tasks || tasks.length === 0) {
      container.innerHTML = '<div style="text-align:center; padding: 30px; color: var(--text-muted);">暂无运行中的同步任务，请先在“导入与新建”中生成。</div>';
      return;
    }
    let html = '<table><thead><tr><th>ID</th><th>任务名称</th><th>平台</th><th>模式</th><th>飞书表格链接</th><th>下次执行时间</th><th>最后状态</th><th>操作</th></tr></thead><tbody>';
    tasks.forEach(t => {
      const statusBadge = t.status === 'active' ? '<span class="badge badge-success">运行中</span>' : '<span class="badge badge-gray">已暂停</span>';
      const lastBadge = t.last_status === 'success' ? '<span class="badge badge-success">成功</span>' : (t.last_status === 'failed' ? '<span class="badge badge-danger">异常</span>' : '<span class="badge badge-gray">未跑</span>');
      html += '<tr>' +
        '<td>' + t.id + '</td>' +
        '<td><strong>' + t.name + '</strong> ' + statusBadge + '</td>' +
        '<td>' + t.platform + '</td>' +
        '<td>' + (t.update_mode === 'append' ? '增量追加' : '全量覆写') + '</td>' +
        '<td><a href="' + t.spreadsheet_url + '" target="_blank" style="color:var(--primary); font-weight:500;">打开飞书表格 ↗</a></td>' +
        '<td>' + (t.next_run_at ? t.next_run_at.slice(0, 19).replace('T', ' ') : '-') + '</td>' +
        '<td>' + lastBadge + '</td>' +
        '<td>' +
          '<button class="btn btn-outline btn-sm" onclick="runTaskNow(' + t.id + ')">立即同步一次</button> ' +
          '<button class="btn btn-outline btn-sm" onclick="toggleTask(' + t.id + ')">' + (t.status === 'active' ? '暂停' : '启用') + '</button> ' +
          '<button class="btn btn-danger btn-sm" onclick="archiveTask(' + t.id + ')">归档</button>' +
        '</td>' +
      '</tr>';
    });
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    console.error(e);
  }
}

async function runTaskNow(id) {
  if (!confirm('确定立即触发一次手动同步吗？')) return;
  try {
    const res = await apiFetch('/api/tasks/' + id + '/run_now', { method: 'POST' });
    alert('同步完成！\n状态: ' + res.status + '\n拉取: ' + res.rows_fetched + ' 行\n追加: ' + res.rows_appended + ' 行');
    loadTasks();
  } catch (e) {
    alert('执行失败: ' + e.message);
  }
}

async function toggleTask(id) {
  try {
    await apiFetch('/api/tasks/' + id + '/toggle_status', { method: 'POST' });
    loadTasks();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function archiveTask(id) {
  if (!confirm('确定归档并停止此任务吗？（飞书表格不会被删除）')) return;
  try {
    await apiFetch('/api/tasks/' + id, { method: 'DELETE' });
    loadTasks();
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function loadRuns() {
  try {
    const runs = await apiFetch('/api/runs');
    const tbody = document.getElementById('runsTableBody');
    if (!runs || runs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">暂无运行记录</td></tr>';
      return;
    }
    tbody.innerHTML = '';
    runs.forEach(r => {
      const tr = document.createElement('tr');
      const badge = r.status === 'success' ? '<span class="badge badge-success">成功</span>' : '<span class="badge badge-danger">失败</span>';
      tr.innerHTML = 
        '<td>' + r.id + '</td>' +
        '<td><strong>' + (r.task_name || ('任务' + r.task_id)) + '</strong></td>' +
        '<td>' + r.trigger_type + '</td>' +
        '<td>' + (r.started_at ? r.started_at.slice(0, 19).replace('T', ' ') : '-') + '</td>' +
        '<td>' + (r.finished_at ? r.finished_at.slice(0, 19).replace('T', ' ') : '-') + '</td>' +
        '<td>' + badge + '</td>' +
        '<td>' + (r.message || '-') + '</td>' +
        '<td style="color:var(--danger)">' + (r.error_detail || '-') + '</td>';
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error(e);
  }
}

async function loadSettings() {
  try {
    const s = await apiFetch('/api/settings');
    document.getElementById('settingFolderToken').value = s.shared_folder_token || '未配置';
    document.getElementById('settingChatId').value = s.feishu_chat_id || '';
    document.getElementById('settingWebhook').value = s.notification_webhook || '';
  } catch (e) {
    console.error(e);
  }
}

async function createNotificationGroup() {
  const name = prompt('请输入新建飞书告警群名称：', '广告数据自动同步告警群');
  if (!name) return;
  try {
    const res = await apiFetch('/api/feishu/create_chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name })
    });
    document.getElementById('settingChatId').value = res.chat_id;
    alert('告警群创建成功！Chat ID: ' + res.chat_id);
  } catch (e) {
    alert('创建群聊失败: ' + e.message);
  }
}

checkAuth();


function onCodexFreqChange() {
  const freq = document.getElementById('codexFreqSelect').value;
  document.getElementById('weekdayPickerGroup').style.display = (freq === 'weekly') ? 'block' : 'none';
  document.getElementById('monthdayPickerGroup').style.display = (freq === 'monthly') ? 'block' : 'none';
  document.getElementById('hourlyPickerGroup').style.display = (freq === 'hourly') ? 'block' : 'none';
  document.getElementById('timePickerGroup').style.display = (freq === 'hourly') ? 'none' : 'block';
  updateCodexSchedule();
}

function updateCodexSchedule() {
  const freq = document.getElementById('codexFreqSelect').value;
  const timeVal = document.getElementById('timeInput').value || '09:00';
  const [hour, min] = timeVal.split(':').map(n => parseInt(n, 10));
  
  let rrule = '';
  let humanSummary = '';
  
  if (freq === 'daily') {
    rrule = 'RRULE:FREQ=DAILY;BYHOUR=' + hour + ';BYMINUTE=' + min;
    humanSummary = '⏰ 调度设置：每天 ' + timeVal + ' 执行（北京时间）';
  } else if (freq === 'workday') {
    rrule = 'RRULE:FREQ=WORKDAY;BYHOUR=' + hour + ';BYMINUTE=' + min;
    humanSummary = '⏰ 调度设置：工作日 (周一至周五) ' + timeVal + ' 执行（北京时间）';
  } else if (freq === 'weekly') {
    const checkedDays = Array.from(document.querySelectorAll('.weekday-cb:checked')).map(cb => cb.value);
    const dayNames = { MO:'周一', TU:'周二', WE:'周三', TH:'周四', FR:'周五', SA:'周六', SU:'周日' };
    const dayLabels = checkedDays.map(d => dayNames[d] || d).join('、') || '周一';
    const dayStr = checkedDays.length > 0 ? checkedDays.join(',') : 'MO';
    rrule = 'RRULE:FREQ=WEEKLY;BYHOUR=' + hour + ';BYMINUTE=' + min + ';BYDAY=' + dayStr;
    humanSummary = '⏰ 调度设置：每周 ' + dayLabels + ' ' + timeVal + ' 执行（北京时间）';
  } else if (freq === 'monthly') {
    const mday = document.getElementById('monthdaySelect').value;
    rrule = 'RRULE:FREQ=MONTHLY;BYMONTHDAY=' + mday + ';BYHOUR=' + hour + ';BYMINUTE=' + min;
    humanSummary = '⏰ 调度设置：每月 ' + mday + ' 日 ' + timeVal + ' 执行（北京时间）';
  } else if (freq === 'hourly') {
    const interval = document.getElementById('hourlyIntervalSelect').value;
    rrule = 'RRULE:FREQ=HOURLY;INTERVAL=' + interval;
    humanSummary = '⏰ 调度设置：每 ' + interval + ' 小时执行一次';
  }
  
  document.getElementById('rruleInput').value = rrule;
  // summary removed
}

function proceedToSchedule() {
  document.getElementById('scheduleConfigCard').style.display = 'block';
  const file = document.getElementById('excelFileInput').files[0];
  const baseName = file ? file.name.replace(/\.[^/.]+$/, '') : '数据同步表';
  document.getElementById('taskNameInput').value = baseName + '_' + (currentPlatform === 'jzt' ? '京准通' : currentPlatform === 'taobao' ? '淘宝星河' : '聚光');
  onCodexFreqChange();
  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
}

function toggleWeekday(el) {
  el.classList.toggle('active');
  updateCodexSchedule();
}

function setUploadLoadingState(isLoading, filename, fileSize) {
  const box = document.getElementById('uploadBox');
  const icon = document.getElementById('uploadIcon');
  const title = document.getElementById('uploadTitle');
  const desc = document.getElementById('uploadDesc');
  if (!box) return;
  
  if (isLoading) {
    box.className = 'upload-box loading';
    if (icon) icon.innerHTML = '<div class="spinner" style="width:32px; height:32px; border-width:3px;"></div>';
    if (title) title.innerHTML = '正在深度解析 Excel 表头与数据结构...';
    if (desc) desc.innerText = '正在核对字段、主键与实体，请稍候';
  } else {
    box.className = 'upload-box success';
    if (icon) icon.innerHTML = '✅';
    if (title) title.innerHTML = '已成功解析: <strong>' + filename + '</strong> (' + Math.round(fileSize / 1024) + ' KB)';
    if (desc) desc.innerText = '解析完毕！可在下方查看匹配结果；点击可更换文件。';
  }
}

function setupDragAndDrop() {
  const box = document.getElementById('uploadBox');
  if (!box) return;
  ['dragenter', 'dragover'].forEach(name => {
    box.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      box.classList.add('dragging');
    });
  });
  ['dragleave', 'drop'].forEach(name => {
    box.addEventListener(name, (e) => {
      e.preventDefault();
      e.stopPropagation();
      box.classList.remove('dragging');
    });
  });
  box.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      document.getElementById('excelFileInput').files = files;
      processUploadedFile(files[0]);
    }
  });
}

async function processUploadedFile(file) {
  setUploadLoadingState(true, file.name, file.size);
  const formData = new FormData();
  formData.append('file', file);
  formData.append('selected_platform', currentPlatform);

  try {
    const res = await apiFetch('/api/upload', { method: 'POST', body: formData });
    uploadedAnalysis = res;
    setUploadLoadingState(false, file.name, file.size);
    renderAnalysisResult(res);
  } catch (e) {
    const box = document.getElementById('uploadBox');
    if (box) box.className = 'upload-box';
    const icon = document.getElementById('uploadIcon');
    if (icon) icon.innerHTML = '❌';
    const title = document.getElementById('uploadTitle');
    if (title) title.innerText = '解析失败: ' + e.message;
    const desc = document.getElementById('uploadDesc');
    if (desc) desc.innerText = '点击重新上传有效 Excel 文件';
    alert('上传分析失败: ' + e.message);
  }
}

window.handleFileSelected = function(event) {
  const file = event.target.files[0];
  if (!file) return;
  processUploadedFile(file);
};

window.addEventListener('DOMContentLoaded', () => {
  checkAuth();
  setupDragAndDrop();
});


// 自定义下拉选框驱动引擎
function toggleCustomSelect(wrapperId) {
  const el = document.getElementById(wrapperId);
  if (!el) return;
  const wasOpen = el.classList.contains('open');
  closeAllCustomPopups();
  if (!wasOpen) {
    el.classList.add('open');
  }
}

function selectCustomOption(wrapperId, inputId, value, label) {
  const wrapper = document.getElementById(wrapperId);
  const input = document.getElementById(inputId);
  if (wrapper) {
    const labelSpan = wrapper.querySelector('.custom-select-label');
    if (labelSpan) labelSpan.innerText = label;
    wrapper.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.remove('selected');
      if (opt.getAttribute('data-value') === String(value)) {
        opt.classList.add('selected');
      }
    });
    wrapper.classList.remove('open');
  }
  if (input) {
    input.value = value;
    if (typeof input.onchange === 'function') {
      input.onchange();
    }
  }
}

// 自定义时间选择器驱动引擎
let selectedHour = '09';
let selectedMinute = '00';

function toggleCustomTimepicker() {
  const wrapper = document.getElementById('wrapper-timeInput');
  if (!wrapper) return;
  const wasOpen = wrapper.classList.contains('open');
  closeAllCustomPopups();
  if (!wasOpen) {
    wrapper.classList.add('open');
  }
}

function initCustomTimepicker() {
  const hourCol = document.getElementById('timeHourCol');
  const minCol = document.getElementById('timeMinCol');
  if (!hourCol || !minCol) return;

  hourCol.innerHTML = '';
  minCol.innerHTML = '';

  for (let h = 0; h < 24; h++) {
    const hStr = h < 10 ? '0' + h : '' + h;
    const item = document.createElement('div');
    item.className = 'time-item' + (hStr === selectedHour ? ' active' : '');
    item.innerText = hStr + ' 时';
    item.onclick = (e) => {
      e.stopPropagation();
      selectedHour = hStr;
      hourCol.querySelectorAll('.time-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      commitCustomTime();
    };
    hourCol.appendChild(item);
  }

  for (let m = 0; m < 60; m += 5) {
    const mStr = m < 10 ? '0' + m : '' + m;
    const item = document.createElement('div');
    item.className = 'time-item' + (mStr === selectedMinute ? ' active' : '');
    item.innerText = mStr + ' 分';
    item.onclick = (e) => {
      e.stopPropagation();
      selectedMinute = mStr;
      minCol.querySelectorAll('.time-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
      commitCustomTime();
      closeAllCustomPopups();
    };
    minCol.appendChild(item);
  }
}

function commitCustomTime() {
  const timeStr = selectedHour + ':' + selectedMinute;
  const display = document.getElementById('customTimeDisplay');
  const input = document.getElementById('timeInput');
  if (display) display.innerText = timeStr;
  if (input) {
    input.value = timeStr;
    updateCodexSchedule();
  }
}

function closeAllCustomPopups() {
  document.querySelectorAll('.custom-select.open').forEach(el => el.classList.remove('open'));
  const tp = document.getElementById('wrapper-timeInput');
  if (tp) tp.classList.remove('open');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.custom-select') && !e.target.closest('.custom-timepicker')) {
    closeAllCustomPopups();
  }
});

// 在 DOMContentLoaded 中初始化
window.addEventListener('DOMContentLoaded', () => {
  initCustomTimepicker();
});
