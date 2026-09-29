// 浏览器端视图缓存状态（避免切换标签页重复加载和闪烁）
const viewCache = {
  tasks: { loaded: false, data: null },
  runs: { loaded: false, page: 1, pageSize: 20, total: 0, items: [] },
  admin: { loaded: false, data: null }
};

let currentRunsPage = 1;
let currentRunsPageSize = 20;
let totalRunsCount = 0;
let totalRunsPages = 1;

function selectRunsPageSize(size, label) {
  currentRunsPageSize = size;
  const labelEl = document.getElementById('runsPageSizeLabel');
  if (labelEl) labelEl.textContent = label;
  const container = document.getElementById('runsPageSizeSelect');
  if (container) {
    container.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.toggle('selected', parseInt(opt.getAttribute('data-value'), 10) === size);
    });
    container.classList.remove('open');
  }
  currentRunsPage = 1;
  loadRuns(1, true);
}

function changeRunsPage(delta) {
  const target = currentRunsPage + delta;
  if (target >= 1 && target <= totalRunsPages) {
    goToRunsPage(target);
  }
}

function goToRunsPage(p) {
  if (p < 1 || p > totalRunsPages) return;
  currentRunsPage = p;
  loadRuns(p, true);
}

function renderRunsPagination(total, page, pageSize, totalPages) {
  totalRunsCount = total;
  currentRunsPage = page;
  totalRunsPages = Math.max(1, totalPages);

  const totalEl = document.getElementById('runsTotalCount');
  if (totalEl) totalEl.textContent = total;

  const prevBtn = document.getElementById('runsPrevBtn');
  const nextBtn = document.getElementById('runsNextBtn');
  if (prevBtn) prevBtn.disabled = page <= 1;
  if (nextBtn) nextBtn.disabled = page >= totalRunsPages;

  const pageNumbers = document.getElementById('runsPageNumbers');
  if (!pageNumbers) return;
  pageNumbers.innerHTML = '';

  const createPageBtn = (p) => {
    const btn = document.createElement('button');
    btn.className = (p === page) ? 'btn btn-primary' : 'btn btn-outline';
    btn.style.cssText = 'height: 32px; min-width: 32px; padding: 0 8px; font-size: 13px; border-radius: var(--radius-sm);';
    btn.textContent = p;
    btn.onclick = () => goToRunsPage(p);
    return btn;
  };

  const createEllipsis = () => {
    const span = document.createElement('span');
    span.style.cssText = 'display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 32px; color: var(--text-muted); font-size: 13px; user-select: none;';
    span.textContent = '...';
    return span;
  };

  // 智能省略号折叠算法：页数超过 7 页时折叠中间
  if (totalRunsPages <= 7) {
    for (let i = 1; i <= totalRunsPages; i++) {
      pageNumbers.appendChild(createPageBtn(i));
    }
  } else {
    // 始终显示第 1 页
    pageNumbers.appendChild(createPageBtn(1));

    if (page > 4) {
      pageNumbers.appendChild(createEllipsis());
    }

    // 中间动态区间
    let start = Math.max(2, page - 1);
    let end = Math.min(totalRunsPages - 1, page + 1);

    if (page <= 4) {
      start = 2;
      end = 5;
    } else if (page >= totalRunsPages - 3) {
      start = totalRunsPages - 4;
      end = totalRunsPages - 1;
    }

    for (let i = start; i <= end; i++) {
      pageNumbers.appendChild(createPageBtn(i));
    }

    if (page < totalRunsPages - 3) {
      pageNumbers.appendChild(createEllipsis());
    }

    // 始终显示最后一页
    pageNumbers.appendChild(createPageBtn(totalRunsPages));
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showErrorModal(runId) {
  const runs = window.__runsCache || [];
  const r = runs.find(item => item.id === runId);
  if (!r) return;
  const modal = document.getElementById('errorDetailModal');
  const meta = document.getElementById('errorModalMeta');
  const content = document.getElementById('errorModalContent');
  if (!modal || !meta || !content) return;
  
  const trigMap = { scheduled: '定时触发', manual: '手动执行', catch_up: '错峰补跑' };
  const trig = trigMap[r.trigger_type] || r.trigger_type;
  const startTime = r.started_at ? r.started_at.slice(0, 19).replace('T', ' ') : '-';
  
  meta.innerHTML = '<div><strong>任务名称：</strong>' + escapeHtml(r.task_name || ('任务' + r.task_id)) + '</div>' +
                   '<div><strong>触发方式：</strong>' + trig + ' &nbsp;|&nbsp; <strong>执行时间：</strong>' + startTime + '</div>';
  content.textContent = r.error_detail || '无具体错误详情';
  modal.style.display = 'flex';
}

function closeErrorModal() {
  const modal = document.getElementById('errorDetailModal');
  if (modal) modal.style.display = 'none';
}

function copyErrorModalText() {
  const content = document.getElementById('errorModalContent');
  const btn = document.getElementById('copyErrorBtn');
  if (!content) return;
  const text = content.textContent;
  navigator.clipboard.writeText(text).then(() => {
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = '✅ 已复制到剪贴板';
      setTimeout(() => { btn.innerHTML = orig; }, 2000);
    }
  }).catch(err => {
    alert('复制失败，请手动选择复制：' + err);
  });
}

document.addEventListener('mouseover', function(e) {
  const target = e.target.closest('.error-tooltip-wrap');
  if (!target) return;
  const text = target.getAttribute('data-tooltip') || target.getAttribute('title') || '';
  if (!text) return;
  const tip = document.getElementById('globalHoverTooltip');
  if (!tip) return;
  tip.textContent = text;
  tip.style.display = 'block';
  const rect = target.getBoundingClientRect();
  const tipRect = tip.getBoundingClientRect();
  let top = rect.top - tipRect.height - 8;
  let left = rect.left + (rect.width - tipRect.width) / 2;
  if (top < 10) top = rect.bottom + 8;
  if (left < 10) left = 10;
  if (left + tipRect.width > window.innerWidth - 10) left = window.innerWidth - tipRect.width - 10;
  tip.style.top = top + 'px';
  tip.style.left = left + 'px';
});

document.addEventListener('mouseout', function(e) {
  const target = e.target.closest('.error-tooltip-wrap');
  if (!target) return;
  const tip = document.getElementById('globalHoverTooltip');
  if (tip) tip.style.display = 'none';
});

document.addEventListener('click', function(e) {
  const target = e.target.closest('.error-tooltip-wrap');
  if (!target) return;
  const runId = parseInt(target.getAttribute('data-run-id'), 10);
  if (runId) {
    const tip = document.getElementById('globalHoverTooltip');
    if (tip) tip.style.display = 'none';
    showErrorModal(runId);
  }
});

let currentPlatform = 'jzt';
let uploadedAnalysis = null;
let currentConfirmedSheet = null;
let previewDataResult = null;

function switchToKeywordSection(tab = 'search', updateUrl = true) {
  const syncMod = document.getElementById('module-sync');
  const kwMod = document.getElementById('module-keyword');
  const syncSide = document.getElementById('sidebar-group-sync');
  const kwSide = document.getElementById('sidebar-group-keyword');
  if (syncMod) syncMod.style.display = 'none';
  if (kwMod) kwMod.style.display = 'block';
  if (syncSide) syncSide.style.display = 'none';
  if (kwSide) kwSide.style.display = 'flex';

  switchKeywordTab(tab, updateUrl);
}

function switchToSyncSection(tab = 'import', updateUrl = true) {
  const syncMod = document.getElementById('module-sync');
  const kwMod = document.getElementById('module-keyword');
  const syncSide = document.getElementById('sidebar-group-sync');
  const kwSide = document.getElementById('sidebar-group-keyword');
  if (kwMod) kwMod.style.display = 'none';
  if (syncMod) syncMod.style.display = 'block';
  if (kwSide) kwSide.style.display = 'none';
  if (syncSide) syncSide.style.display = 'flex';

  switchTab(tab, updateUrl);
}

function switchKeywordTab(tab = 'search', updateUrl = true) {
  const syncMod = document.getElementById('module-sync');
  const kwMod = document.getElementById('module-keyword');
  const syncSide = document.getElementById('sidebar-group-sync');
  const kwSide = document.getElementById('sidebar-group-keyword');
  if (syncMod) syncMod.style.display = 'none';
  if (kwMod) kwMod.style.display = 'block';
  if (syncSide) syncSide.style.display = 'none';
  if (kwSide) kwSide.style.display = 'flex';

  document.querySelectorAll('#sidebar-group-keyword .sidebar-link').forEach(btn => {
    btn.classList.remove('active');
  });
  const activeBtn = document.getElementById('tab-btn-' + tab);
  if (activeBtn) activeBtn.classList.add('active');

  const frame = document.getElementById('keywordFrame');
  if (frame) {
    if (frame.contentWindow && typeof frame.contentWindow.switchMainTab === 'function') {
      frame.contentWindow.switchMainTab(tab, false);
    } else {
      frame.addEventListener('load', function() {
        if (frame.contentWindow && typeof frame.contentWindow.switchMainTab === 'function') {
          frame.contentWindow.switchMainTab(tab, false);
        }
      }, { once: true });
    }
  }

  if (updateUrl) {
    let target = '/keyword';
    if (tab === 'tasks') target = '/keyword/tasks';
    else if (tab === 'runs') target = '/keyword/runs';
    if (window.location.pathname !== target) {
      window.history.pushState({ tab: 'kw_' + tab }, '', target);
    }
  }
}

window.addEventListener('message', function(e) {
  if (e.data && e.data.type === 'kw_height' && e.data.height) {
    const frame = document.getElementById('keywordFrame');
    if (frame) {
      frame.style.height = (e.data.height + 40) + 'px';
      const kwMod = document.getElementById('module-keyword');
      if (kwMod) kwMod.style.height = (e.data.height + 40) + 'px';
    }
  }
  if (e.data && e.data.type === 'kw_tab_changed' && e.data.tab) {
    document.querySelectorAll('#sidebar-group-keyword .sidebar-link').forEach(btn => {
      btn.classList.remove('active');
    });
    const activeBtn = document.getElementById('tab-btn-' + e.data.tab);
    if (activeBtn) activeBtn.classList.add('active');
    let target = '/keyword';
    if (e.data.tab === 'tasks') target = '/keyword/tasks';
    else if (e.data.tab === 'runs') target = '/keyword/runs';
    if (window.location.pathname !== target) {
      window.history.pushState({ tab: 'kw_' + e.data.tab }, '', target);
    }
  }
  if (e.data && e.data.type === 'kw_tasks_count') {
    const b = document.getElementById('kwTaskCountBadge');
    if (b) b.innerText = e.data.count;
  }
});

function switchTab(name, updateUrl = true) {
  const syncMod = document.getElementById('module-sync');
  const kwMod = document.getElementById('module-keyword');
  const syncSide = document.getElementById('sidebar-group-sync');
  const kwSide = document.getElementById('sidebar-group-keyword');
  if (kwMod) kwMod.style.display = 'none';
  if (syncMod) syncMod.style.display = 'block';
  if (kwSide) kwSide.style.display = 'none';
  if (syncSide) syncSide.style.display = 'flex';

  // 如果进入 admin 且未认证，弹出管理员密码验证窗口
  if (name === 'admin') {
    const token = sessionStorage.getItem('admin_token');
    if (!token) {
      const modal = document.getElementById('adminAuthModal');
      if (modal) {
        modal.style.display = 'flex';
        const inp = document.getElementById('adminPasswordInput');
        if (inp) { inp.value = ''; setTimeout(() => inp.focus(), 50); }
      }
      return;
    }
  }

  // 1. 切换头部 tab 按钮激活态
  document.querySelectorAll('.nav-tab').forEach(t => {
    t.classList.remove('active');
    const oc = t.getAttribute('onclick') || '';
    if (oc.indexOf("'" + name + "'") !== -1 || oc.indexOf('"' + name + '"') !== -1) {
      t.classList.add('active');
    }
  });

  // 管理 Tab 仅在访问 admin 或已登录且处于 admin 时展现
  const navAdmin = document.getElementById('navTabAdmin');
  if (navAdmin) {
    navAdmin.style.display = (name === 'admin') ? 'inline-flex' : 'none';
  }

  // 2. 切换卡片内容容器显示
  const allTabs = ['import', 'tasks', 'runs', 'admin'];
  allTabs.forEach(tName => {
    const el = document.getElementById('tab-' + tName);
    if (el) {
      if (tName === name) {
        el.style.setProperty('display', 'block', 'important');
      } else {
        el.style.setProperty('display', 'none', 'important');
      }
    }
  });

  // 3. 触发异步数据加载（若已在浏览器缓存中，则直接复用已有视图，免除重新请求与 loading 闪烁）
  if (name === 'tasks') {
    const container = document.getElementById('tasksListContainer');
    const needsRender = !container || !container.querySelector('table') || container.innerHTML.includes('加载中');
    if (viewCache.tasks.data && needsRender) {
      renderTasksList(viewCache.tasks.data);
    } else if (!viewCache.tasks.data) {
      loadTasks(false);
    }
  }
  if (name === 'runs') {
    const tbody = document.getElementById('runsTableBody');
    const needsRender = !tbody || !tbody.querySelector('tr') || tbody.innerHTML.includes('加载中');
    if (viewCache.runs.items && viewCache.runs.items.length && needsRender) {
      renderRunsPagination(viewCache.runs.total, currentRunsPage, currentRunsPageSize, Math.ceil(viewCache.runs.total / currentRunsPageSize) || 1);
      renderRunsTable(viewCache.runs.items);
    } else if (!viewCache.runs.items || !viewCache.runs.items.length) {
      loadRuns(currentRunsPage, false);
    }
  }
  if (name === 'admin') {
    if (!viewCache.admin.loaded) loadSettings(false);
  }

  // 4. 同步浏览器地址栏路径
  if (updateUrl) {
    const targetPath = (name === 'import') ? '/' : ('/' + name);
    if (window.location.pathname !== targetPath) {
      window.history.pushState({ tab: name }, '', targetPath);
    }
  }
}

function updateKeywordTaskBadge() {
  try {
    const cached = sessionStorage.getItem('kw_tasks_cache');
    if (cached) {
      const parsed = JSON.parse(cached);
      if (parsed && Array.isArray(parsed.data)) {
        const b = document.getElementById('kwTaskCountBadge');
        if (b) b.innerText = parsed.data.length;
      }
    }
  } catch(e) {}
  fetch('/api/keyword/tasks').then(r => r.json()).then(tasks => {
    if (Array.isArray(tasks)) {
      const b = document.getElementById('kwTaskCountBadge');
      if (b) b.innerText = tasks.length;
      try {
        sessionStorage.setItem('kw_tasks_cache', JSON.stringify({ data: tasks, time: Date.now() }));
      } catch(e) {}
    }
  }).catch(function(){});
}

function initRouter() {
  updateTaskCountBadge();
  updateKeywordTaskBadge();
  const normPath = window.location.pathname.replace(/\/+$/, '') || '/';
  if (normPath === '/keyword/tasks') {
    switchToKeywordSection('tasks', false);
  } else if (normPath === '/keyword/runs') {
    switchToKeywordSection('runs', false);
  } else if (normPath === '/keyword') {
    switchToKeywordSection('search', false);
  } else if (normPath === '/admin' || normPath === '/settings') {
    switchToSyncSection('admin', false);
  } else if (normPath === '/tasks') {
    switchToSyncSection('tasks', false);
  } else if (normPath === '/runs') {
    switchToSyncSection('runs', false);
  } else {
    switchToSyncSection('import', false);
  }
}

window.addEventListener('popstate', function(e) {
  const normPath = window.location.pathname.replace(/\/+$/, '') || '/';
  if (normPath === '/keyword/tasks') {
    switchToKeywordSection('tasks', false);
  } else if (normPath === '/keyword/runs') {
    switchToKeywordSection('runs', false);
  } else if (normPath === '/keyword') {
    switchToKeywordSection('search', false);
  } else if (normPath === '/admin' || normPath === '/settings') {
    switchToSyncSection('admin', false);
  } else if (normPath === '/tasks') {
    switchToSyncSection('tasks', false);
  } else if (normPath === '/runs') {
    switchToSyncSection('runs', false);
  } else {
    switchToSyncSection('import', false);
  }
});

function selectPlatform(code) {
  updateWorkflowProgress(1);
  currentPlatform = code;
  document.querySelectorAll('.platform-card').forEach(c => c.classList.remove('selected'));
  const el = document.getElementById('card-' + code);
  if (el) el.classList.add('selected');
  
  // 控制聚光子账号选框显隐
  const subSection = document.getElementById('juguangSubAccountSection');
  if (subSection) {
    if (code === 'juguang') {
      subSection.style.display = 'block';
      loadJuguangSubaccounts();
    } else {
      subSection.style.display = 'none';
    }
  }

  if (uploadedAnalysis && document.getElementById('excelFileInput').files.length > 0) {
    reanalyzeUploadedFile();
  }
}

let cachedSubAccounts = [];

async function loadJuguangSubaccounts(force = false) {
  const container = document.getElementById('subAccountOptionsContainer');
  const tip = document.getElementById('subAccountCountTip');
  if (!force && cachedSubAccounts.length > 0) {
    renderSubAccountOptions(cachedSubAccounts);
    return;
  }
  if (container) {
    container.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 13px;"><div class="spinner"></div> 正在从 OSS 实时获取最新子账号清单...</div>';
  }
  try {
    const url = '/api/platforms/juguang/subaccounts' + (force ? '?refresh=true' : '');
    const list = await apiFetch(url);
    cachedSubAccounts = list || [];
    if (tip) {
      tip.innerHTML = '已从 OSS 动态获取 ' + cachedSubAccounts.length + ' 个子账号凭据 <a href="javascript:void(0)" onclick="loadJuguangSubaccounts(true)" style="margin-left:8px; color:var(--primary); text-decoration:none; font-weight:500;">🔄 刷新最新</a>';
    }
    renderSubAccountOptions(cachedSubAccounts);
    const curId = document.getElementById('selectedSubAccountId').value;
    if (!curId && cachedSubAccounts.length > 0) {
      selectSubAccount(cachedSubAccounts[0].id, cachedSubAccounts[0].name);
    }
  } catch (e) {
    if (container) {
      container.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--danger); font-size: 13px;">加载失败: ' + escapeHtml(e.message) + '</div>';
    }
  }
}

function renderSubAccountOptions(list) {
  const container = document.getElementById('subAccountOptionsContainer');
  if (!container) return;
  if (!list || list.length === 0) {
    container.innerHTML = '<div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 13px;">未找到匹配的子账号</div>';
    return;
  }
  const curId = document.getElementById('selectedSubAccountId').value;
  let html = '';
  list.forEach(item => {
    const isSelected = item.id === curId;
    html += '<div class="custom-select-option ' + (isSelected ? 'selected' : '') + '" ' +
            'data-value="' + escapeHtml(item.id) + '" ' +
            'data-name="' + escapeHtml(item.name) + '" ' +
            'onclick="selectSubAccount(\'' + escapeHtml(item.id) + '\', \'' + escapeHtml(item.name).replace(/'/g, "\\'") + '\')">' +
            '<div style="display: flex; flex-direction: column; overflow: hidden;">' +
            '<div style="display:flex; align-items:center;"><span style="font-weight: 500; color: ' + (item.status && item.status !== 1 ? '#86909c' : '#1d2129') + '; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">' + escapeHtml(item.name) + '</span>' + (item.status && item.status !== 1 ? '<span class="badge" style="background:#fff2e8; color:#fa541c; font-size:10px; margin-left:6px; border:1px solid #ffbb96;">已冻结</span>' : '') + '</div>' +
            '<span style="font-size: 11px; color: var(--text-muted); font-family: monospace;">ID: ' + escapeHtml(item.id) + '</span>' +
            '</div>' +
            '<svg class="check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>' +
            '</div>';
  });
  container.innerHTML = html;
}

function filterSubAccounts(keyword) {
  const kw = (keyword || '').trim().toLowerCase();
  if (!kw) {
    renderSubAccountOptions(cachedSubAccounts);
    return;
  }
  const filtered = cachedSubAccounts.filter(item => 
    (item.name && item.name.toLowerCase().includes(kw)) ||
    (item.id && item.id.toLowerCase().includes(kw))
  );
  renderSubAccountOptions(filtered);
}

function selectSubAccount(id, name) {
  const idInput = document.getElementById('selectedSubAccountId');
  const nameInput = document.getElementById('selectedSubAccountName');
  const display = document.getElementById('juguangSubAccountDisplay');
  const wrapper = document.getElementById('wrapper-juguangSubAccountSelect');

  if (idInput) idInput.value = id;
  if (nameInput) nameInput.value = name;
  if (display) {
    display.innerHTML = '<span style="font-weight: 600; color: var(--primary);">' + escapeHtml(name) + '</span> <span style="font-size: 12px; color: var(--text-muted); font-family: monospace;">(' + escapeHtml(id.slice(0, 8)) + '...)</span>';
  }
  if (wrapper) {
    wrapper.classList.remove('open');
    wrapper.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.toggle('selected', opt.getAttribute('data-value') === String(id));
    });
  }

  if (currentPlatform === 'juguang' && currentConfirmedSheet && document.getElementById('previewCard').style.display !== 'none') {
    runPreviewFetch();
  }
}

async function apiFetch(url, options = {}) {
  const opts = { ...options };
  opts.headers = { ...(opts.headers || {}) };
  const adminToken = sessionStorage.getItem('admin_token');
  if (adminToken) {
    opts.headers['X-Access-Token'] = adminToken;
  }
  const res = await fetch(url, opts);
  if (res.status === 401) {
    const modal = document.getElementById('adminAuthModal');
    if (modal) modal.style.display = 'flex';
    throw new Error('未授权，需要管理员权限');
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return await res.json();
}

async function submitAdminLogin() {
  const input = document.getElementById('adminPasswordInput');
  const pwd = input ? input.value.trim() : '';
  if (!pwd) {
    alert('请输入管理密码');
    return;
  }
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd })
    });
    if (!res.ok) throw new Error('口令验证失败');
    const data = await res.json();
    if (data.success) {
      sessionStorage.setItem('admin_token', pwd);
      const modal = document.getElementById('adminAuthModal');
      if (modal) modal.style.display = 'none';
      const navAdmin = document.getElementById('navTabAdmin');
      if (navAdmin) navAdmin.style.display = 'inline-flex';
      switchTab('admin', true);
    }
  } catch (e) {
    alert('管理密码错误，请重新输入');
    if (input) {
      input.value = '';
      input.focus();
    }
  }
}

function cancelAdminLogin() {
  const modal = document.getElementById('adminAuthModal');
  if (modal) modal.style.display = 'none';
  switchTab('import', true);
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
  
  const subId = currentPlatform === 'juguang' ? document.getElementById('selectedSubAccountId').value : null;
  if (currentPlatform === 'juguang' && !subId) {
    document.getElementById('previewStatus').innerHTML = '<span style="color:var(--warning)">⚠️ 请先在上方选择聚光子账号</span>';
    return;
  }

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
        end_date: endStr,
        sub_account_id: subId
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
  const subId = currentPlatform === 'juguang' ? document.getElementById('selectedSubAccountId').value : null;
  const subName = currentPlatform === 'juguang' ? document.getElementById('selectedSubAccountName').value : null;
  if (currentPlatform === 'juguang' && !subId) {
    alert('请选择聚光子账号');
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
        sub_account_id: subId,
        sub_account_name: subName,
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

function renderTasksList(tasks) {
  const container = document.getElementById('tasksListContainer');
  if (!container) return;
  if (!tasks || tasks.length === 0) {
    container.innerHTML = '<div style="text-align:center; padding: 40px; color: var(--text-muted); font-size: 14px;">暂无运行中的同步任务，请先在“导入与新建”中配置并生成。</div>';
    return;
  }
  const platformNames = { jzt: '京准通', taobao: '淘宝星河', juguang: '聚光' };
  let html = '<div class="table-container"><table><thead><tr><th style="width:60px;">ID</th><th>任务名称</th><th>投放平台</th><th>更新机制</th><th>飞书在线表格</th><th>下次执行时间 (北京时间)</th><th>最近运行</th><th style="text-align:center;">快捷操作</th></tr></thead><tbody>';
  tasks.forEach(t => {
    const statusBadge = t.status === 'active' ? '<span class="badge badge-success">运行中</span>' : '<span class="badge badge-gray">已暂停</span>';
    const lastBadge = t.last_status === 'success' ? '<span class="badge badge-success">成功</span>' : (t.last_status === 'failed' ? '<span class="badge badge-danger">异常</span>' : '<span class="badge badge-gray">未跑</span>');
    const pName = platformNames[t.platform] || t.platform;
    const subBadge = (t.platform === 'juguang' && t.sub_account_name) ? '<div style="font-size:12px; color:var(--text-secondary); margin-top:3px;"><span style="background:#e8f3ff; color:var(--primary); padding:1px 6px; border-radius:4px; font-weight:500;">子账号: ' + escapeHtml(t.sub_account_name) + '</span></div>' : '';
    const modeText = t.update_mode === 'append' ? '<span class="ok-pill">增量追加</span>' : '<span class="unmapped-pill">全量覆写</span>';
    const nextTime = t.next_run_at ? t.next_run_at.slice(0, 19).replace('T', ' ') : '-';
    html += '<tr>' +
      '<td>' + t.id + '</td>' +
      '<td><div style="font-weight:600; font-size:14px; margin-bottom:2px;">' + t.name + '</div>' + statusBadge + '</td>' +
      '<td><strong style="color:var(--primary)">' + pName + '</strong>' + subBadge + '</td>' +
      '<td>' + modeText + '</td>' +
      '<td><a href="' + t.spreadsheet_url + '" target="_blank" style="color:var(--primary); font-weight:500; text-decoration:none; display:inline-flex; align-items:center; gap:4px;">查看飞书表格 <span style="font-size:11px;">↗</span></a></td>' +
      '<td>' + nextTime + '</td>' +
      '<td>' + lastBadge + '</td>' +
      '<td style="text-align:center;">' +
        '<div style="display:inline-flex; gap:6px;">' +
          '<button class="btn btn-outline btn-sm" onclick="runTaskNow(' + t.id + ')">⚡ 立即同步</button>' +
          '<button class="btn btn-outline btn-sm" onclick="toggleTask(' + t.id + ')">' + (t.status === 'active' ? '暂停' : '恢复') + '</button>' +
          '<button class="btn btn-danger btn-sm" onclick="archiveTask(' + t.id + ')">归档</button>' +
        '</div>' +
      '</td>' +
    '</tr>';
  });
  html += '</tbody></table></div>';
  container.innerHTML = html;
}

async function updateTaskCountBadge() {
  try {
    const cached = sessionStorage.getItem('sync_tasks_cache');
    if (cached) {
      const parsed = JSON.parse(cached);
      if (parsed && Array.isArray(parsed.data)) {
        const badge = document.getElementById('taskCountBadge');
        if (badge) badge.innerText = parsed.data.length;
        if (!viewCache.tasks.loaded) {
          viewCache.tasks.loaded = true;
          viewCache.tasks.data = parsed.data;
          renderTasksList(parsed.data);
        }
      }
    }
  } catch (e) {}
  try {
    const tasks = await apiFetch('/api/tasks');
    viewCache.tasks.loaded = true;
    viewCache.tasks.data = tasks;
    try {
      sessionStorage.setItem('sync_tasks_cache', JSON.stringify({ data: tasks, time: Date.now() }));
    } catch (e) {}
    const badge = document.getElementById('taskCountBadge');
    if (badge) badge.innerText = tasks.length;
    const tabTasks = document.getElementById('tab-tasks');
    if (tabTasks && tabTasks.style.display !== 'none') {
      renderTasksList(tasks);
    }
  } catch (e) {
    console.error('Failed to update task count badge:', e);
  }
}

async function loadTasks(force = false) {
  const container = document.getElementById('tasksListContainer');
  if (!force && viewCache.tasks.data && container && container.querySelector('table')) {
    return;
  }
  if (!force && viewCache.tasks.data) {
    renderTasksList(viewCache.tasks.data);
    return;
  }
  if (!force && !viewCache.tasks.data) {
    try {
      const cached = sessionStorage.getItem('sync_tasks_cache');
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed && Array.isArray(parsed.data)) {
          viewCache.tasks.loaded = true;
          viewCache.tasks.data = parsed.data;
          const badge = document.getElementById('taskCountBadge');
          if (badge) badge.innerText = parsed.data.length;
          renderTasksList(parsed.data);
          return;
        }
      }
    } catch (e) {}
  }
  if (container && (!viewCache.tasks.loaded || force)) {
    container.innerHTML = '<div style="text-align:center; padding: 30px;"><div class="spinner"></div> 正在加载同步任务...</div>';
  }
  try {
    const tasks = await apiFetch('/api/tasks');
    viewCache.tasks.loaded = true;
    viewCache.tasks.data = tasks;
    try {
      sessionStorage.setItem('sync_tasks_cache', JSON.stringify({ data: tasks, time: Date.now() }));
    } catch (e) {}
    const badge = document.getElementById('taskCountBadge');
    if (badge) badge.innerText = tasks.length;
    renderTasksList(tasks);
  } catch (e) {
    if (container) container.innerHTML = '<div style="text-align:center; padding: 20px; color:var(--danger)">加载任务失败: ' + e.message + '</div>';
  }
}

async function runTaskNow(id) {
  if (!confirm('确定立即触发一次手动同步吗？')) return;
  try {
    const res = await apiFetch('/api/tasks/' + id + '/run_now', { method: 'POST' });
    alert('同步完成！\n状态: ' + res.status + '\n拉取: ' + res.rows_fetched + ' 行\n追加: ' + res.rows_appended + ' 行');
    loadTasks(true);
  } catch (e) {
    alert('执行失败: ' + e.message);
  }
}

async function toggleTask(id) {
  try {
    await apiFetch('/api/tasks/' + id + '/toggle_status', { method: 'POST' });
    loadTasks(true);
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

async function archiveTask(id) {
  if (!confirm('确定归档并停止此任务吗？（飞书表格不会被删除）')) return;
  try {
    await apiFetch('/api/tasks/' + id, { method: 'DELETE' });
    loadTasks(true);
  } catch (e) {
    alert('操作失败: ' + e.message);
  }
}

function renderRunsTable(runs) {
  const tbody = document.getElementById('runsTableBody');
  if (!tbody) return;
  if (!runs || runs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:30px; color:var(--text-muted);">暂无任何历史运行记录</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  const triggerMap = { scheduled: '定时触发', manual: '手动执行', catch_up: '错峰补跑' };
  window.__runsCache = runs;
  runs.forEach(r => {
    const tr = document.createElement('tr');
    const badge = r.status === 'success' ? '<span class="badge badge-success">成功</span>' : '<span class="badge badge-danger">异常</span>';
    const trig = triggerMap[r.trigger_type] || r.trigger_type;
    const startTime = r.started_at ? r.started_at.slice(0, 19).replace('T', ' ') : '-';
    const finishTime = r.finished_at ? r.finished_at.slice(0, 19).replace('T', ' ') : '-';
    tr.innerHTML = 
      '<td>' + r.id + '</td>' +
      '<td><strong>' + (r.task_name || ('任务' + r.task_id)) + '</strong></td>' +
      '<td><span class="badge badge-gray">' + trig + '</span></td>' +
      '<td>' + startTime + '</td>' +
      '<td>' + finishTime + '</td>' +
      '<td>' + badge + '</td>' +
      '<td>' + (r.message || '-') + '</td>' +
      (!r.error_detail ? '<td><span style="color:var(--text-muted);">-</span></td>' : '<td><div class="error-tooltip-wrap" data-run-id="' + r.id + '" data-tooltip="' + escapeHtml(r.error_detail) + '"><span>⚠️</span><span class="error-text">' + escapeHtml(r.error_detail) + '</span></div></td>');
    tbody.appendChild(tr);
  });
}

async function loadRuns(page = currentRunsPage, force = false) {
  const tbody = document.getElementById('runsTableBody');
  if (!force && viewCache.runs.page === page && viewCache.runs.pageSize === currentRunsPageSize && viewCache.runs.items && viewCache.runs.items.length && tbody && tbody.querySelector('tr') && !tbody.innerHTML.includes('加载中')) {
    return;
  }
  if (!force && viewCache.runs.items && viewCache.runs.items.length && viewCache.runs.page === page && viewCache.runs.pageSize === currentRunsPageSize) {
    renderRunsPagination(viewCache.runs.total, page, currentRunsPageSize, Math.ceil(viewCache.runs.total / currentRunsPageSize) || 1);
    if (viewCache.runs.items) renderRunsTable(viewCache.runs.items);
    return;
  }
  const cacheKey = 'sync_runs_cache_p' + page + '_s' + currentRunsPageSize;
  if (!force && !viewCache.runs.loaded) {
    try {
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached);
        if (parsed && Array.isArray(parsed.items)) {
          viewCache.runs.loaded = true;
          viewCache.runs.page = page;
          viewCache.runs.pageSize = currentRunsPageSize;
          viewCache.runs.total = parsed.total;
          viewCache.runs.items = parsed.items;
          renderRunsPagination(parsed.total, page, currentRunsPageSize, parsed.totalPages || 1);
          renderRunsTable(parsed.items);
          return;
        }
      }
    } catch (e) {}
  }
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:20px;"><div class="spinner"></div> 正在加载运行记录...</td></tr>';
  }
  try {
    currentRunsPage = page;
    const res = await apiFetch('/api/runs?page=' + currentRunsPage + '&page_size=' + currentRunsPageSize);

    let runs = [];
    let total = 0;
    let totalPages = 1;
    if (res && res.items) {
      runs = res.items;
      total = res.total;
      totalPages = res.total_pages;
    } else if (Array.isArray(res)) {
      runs = res;
      total = runs.length;
      totalPages = Math.ceil(total / currentRunsPageSize) || 1;
    }

    viewCache.runs.loaded = true;
    viewCache.runs.page = currentRunsPage;
    viewCache.runs.pageSize = currentRunsPageSize;
    viewCache.runs.total = total;
    viewCache.runs.items = runs;
    try {
      sessionStorage.setItem(cacheKey, JSON.stringify({ items: runs, total: total, totalPages: totalPages, time: Date.now() }));
    } catch (e) {}

    renderRunsPagination(total, currentRunsPage, currentRunsPageSize, totalPages);
    renderRunsTable(runs);
  } catch (e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--danger); padding:20px;">加载运行日志失败: ' + e.message + '</td></tr>';
  }
}

async function loadSettings(force = false) {
  if (!force && viewCache.admin.loaded && viewCache.admin.data) {
    return;
  }
  try {
    const s = await apiFetch('/api/settings');
    viewCache.admin.loaded = true;
    viewCache.admin.data = s;
    const tokenEl = document.getElementById('settingFolderToken');
    if (tokenEl) tokenEl.value = s.shared_folder_token || '未配置';
  } catch (e) {
    console.error('加载系统配置失败:', e);
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

// 初始化路由分发
document.addEventListener('DOMContentLoaded', initRouter);
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  initRouter();
}

function updateWorkflowProgress(step) {
  document.querySelectorAll('.workflow-step').forEach((item, index) => {
    const current = index + 1;
    item.classList.toggle('active', current === step);
    item.classList.toggle('completed', current < step);
  });
}

function goToValidation() {
  const input = document.getElementById('excelFileInput');
  if (!uploadedAnalysis || !input || !input.files || input.files.length === 0) {
    if (input) input.click();
    return;
  }
  updateWorkflowProgress(3);
  const mismatchCard = document.getElementById('mismatchAlertCard');
  const target = mismatchCard && mismatchCard.style.display !== 'none'
    ? mismatchCard
    : document.getElementById('sheetAnalysisCard');
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderRecentTasks(tasks) {
  const rail = document.getElementById('recentTasksRail');
  if (!rail) return;
  if (!tasks || tasks.length === 0) {
    rail.className = 'recent-empty';
    rail.innerHTML = '任务创建后会显示在这里<br>便于快速查看运行状态';
    return;
  }
  const platformNames = { jzt: '京准通', taobao: '淘宝星河', juguang: '小红书聚光' };
  const statusNames = { active: '运行中', paused: '已暂停' };
  rail.className = 'recent-task-list';
  rail.innerHTML = tasks.slice(0, 4).map(t => {
    const cls = ['jzt', 'taobao', 'juguang'].includes(t.platform) ? t.platform : 'jzt';
    const nextTime = t.next_run_at ? t.next_run_at.slice(5, 16).replace('T', ' ') : '等待调度';
    const badgeClass = t.status === 'active' ? 'badge-success' : 'badge-gray';
    return '<div class="recent-task"><img class="recent-task-mark" src="/static/assets/platform-' + cls + '.png" alt="' + (platformNames[t.platform] || '同步') + '">' +
      '<div style="min-width:0"><div class="recent-task-name">' + escapeHtml(t.name || ('同步任务 ' + t.id)) + '</div><div class="recent-task-meta">下次执行：' + nextTime + '</div></div>' +
      '<span class="badge ' + badgeClass + '">' + (statusNames[t.status] || t.status) + '</span></div>';
  }).join('');
}
