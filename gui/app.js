
/* ══════════════════════════════════════════
   autocomputer GUI — Application Logic
   ══════════════════════════════════════════ */

// ── State ──
const state = {
  tab: 'dashboard',
  flows: [],
  editing: [],
  lastCapture: null,
};

// ── Navigation ──
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.tab = btn.dataset.tab;
    document.getElementById('pageTitle').textContent = btn.querySelector('span:not(.nav-icon):not(.nav-badge)').textContent.trim();
    render();
  });
});

// ── Rendering ──
async function render() {
  const content = document.getElementById('content');
  content.innerHTML = '';
  const node = await ({
    dashboard: renderDashboard, desktop: renderDesktop, editor: renderEditor,
    flows: renderFlows, monitor: renderMonitor, security: renderSecurity, memory: renderMemory,
  }[state.tab] || renderDashboard)();
  content.appendChild(node);
  updateBadges();
  attachJelly();
}

function updateBadges() {
  document.getElementById('flowCount').textContent = state.flows.length;
}

// ── Toast ──
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  el.innerHTML = `<span>${icons[type]}</span> ${msg}`;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 2500);
}

// ── API Base ──
const API = 'http://127.0.0.1:8765';

async function api(path, opts = {}) {
  try {
    const resp = await fetch(API + path, { headers: { 'Content-Type': 'application/json' }, ...opts });
    return await resp.json();
  } catch (e) {
    return { error: 'API 离线 — 请启动: python -m autocomputer serve' };
  }
}

// ── Refresh ──
function refreshAll() { render(); toast('已刷新', 'info'); }

function switchTab(name) {
  state.tab = name;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.getElementById('pageTitle').textContent = {
    dashboard:'📊 仪表盘', desktop:'🖥️ 桌面操作台', editor:'✏️ 录制编辑器', flows:'📋 流程管理',
    monitor:'👁️ 实时监控', security:'🛡️ 安全审计', memory:'🧠 记忆浏览'
  }[name];
  render();
}

/* ═══════════ DESKTOP (操作台) ═══════════ */
async function renderDesktop() {
  const div = document.createElement('div'); div.className = 'page-enter';
  let data = { windows: [], engine: 'offline' };
  try { const d = await api('/api/windows'); if (d) data = d; } catch (e) {}
  const online = data.engine === 'online';
  const winRows = data.windows.length ? data.windows.map((w, i) => `
    <div class="window-item">
      <span class="window-icon">🪟</span>
      <span class="window-title" title="${String(w.title).replace(/"/g, '&quot;')}">${w.title || '(无标题)'}</span>
      <span class="perm-tag ${w.visible ? 'allow' : 'prompt'}">${w.visible ? '可见' : '隐藏'}</span>
      <div class="window-actions">
        <button class="btn btn-success btn-xs" onclick="focusWindow('${String(w.title).replace(/'/g, "\\'")}')">聚焦</button>
      </div>
    </div>
  `).join('') : `<div class="empty-state"><div class="empty-icon">🖥️</div><p>${online ? '没有检测到窗口' : '引擎离线'}</p><p style="font-size:12px;">${online ? '' : 'Rust 核心未编译,窗口列表不可用(纯 Python 模式)'}</p></div>`;
  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3>🖥️ 窗口列表</h3>
        <span class="card-badge ${online ? 'success' : 'warning'}">${online ? '引擎在线' : '引擎离线'}</span>
      </div>
      <div class="window-list">${winRows}</div>
    </div>
    <div class="card">
      <div class="card-header"><h3>🎯 坐标操作</h3><span class="card-badge info">经 /api/execute</span></div>
      <div class="desktop-toolbar">
        <input class="coord-input" id="clickX" type="number" placeholder="X" value="500">
        <input class="coord-input" id="clickY" type="number" placeholder="Y" value="300">
        <button class="btn btn-primary btn-sm" onclick="desktopClick()">🖱️ 点击</button>
        <button class="btn btn-outline btn-sm" onclick="desktopMove()">➡️ 移动</button>
      </div>
      <p style="font-size:12px;color:var(--text-tertiary);">${online ? '点击后自动执行并记录审计。' : '引擎离线:操作不会真正执行(避免误操作),仅记录日志。'}</p>
    </div>
  `;
  return div;
}

async function focusWindow(title) {
  const res = await api('/api/execute', { method: 'POST', body: JSON.stringify({ action: 'focus', params: { title } }) });
  if (res && res.success) toast('已聚焦: ' + title, 'success');
  else toast('聚焦失败: ' + ((res && res.error) || '引擎离线'), 'error');
}

async function desktopClick() {
  const x = parseInt(document.getElementById('clickX').value || '0', 10);
  const y = parseInt(document.getElementById('clickY').value || '0', 10);
  const res = await api('/api/execute', { method: 'POST', body: JSON.stringify({ action: 'click', params: { x, y } }) });
  if (res && res.success) toast(`已点击 (${x}, ${y})`, 'success');
  else toast('执行失败: ' + ((res && res.error) || '未知'), 'error');
  render();
}

async function desktopMove() {
  const x = parseInt(document.getElementById('clickX').value || '0', 10);
  const y = parseInt(document.getElementById('clickY').value || '0', 10);
  await api('/api/execute', { method: 'POST', body: JSON.stringify({ action: 'move', params: { x, y } }) });
  toast(`已移动至 (${x}, ${y})`, 'info');
}

/* ═══════════ MEMORY (记忆) ═══════════ */
async function renderMemory() {
  const div = document.createElement('div'); div.className = 'page-enter';
  let data = { learned_actions: [], permissions: [], available: false };
  try { const d = await api('/api/memory'); if (d) data = d; } catch (e) {}
  if (!data.available) {
    div.innerHTML = `<div class="card"><div class="empty-state"><div class="empty-icon">🧠</div><p>记忆库不可用</p><p style="font-size:12px;">${data.db || ''} 不存在 — 使用 MCP 技能执行过操作后自动创建</p></div></div>`;
    return div;
  }
  const actions = data.learned_actions || [];
  const perms = data.permissions || [];
  const actionCards = actions.length ? actions.map(a => `
    <div class="memory-item">
      <div class="memory-head">
        <span class="memory-app">${a.app}</span>
        <span class="memory-task">${a.task}</span>
        <span class="memory-meta">使用 ${a.used_count} 次 · ${a.success ? '成功' : '失败'}</span>
      </div>
      <div class="steps-list">${(a.steps || []).map(s => `<div class="step-line">${typeof s === 'string' ? s : JSON.stringify(s)}</div>`).join('')}</div>
    </div>
  `).join('') : `<div class="empty-state"><div class="empty-icon">📭</div><p>暂无已学习的操作</p></div>`;
  const permCards = perms.length ? perms.map(pm => `
    <div class="perm-card">
      <div class="app-name">${pm.app}</div>
      <span class="perm-tag ${pm.policy === 'allow' ? 'allow' : pm.policy === 'deny' ? 'deny' : 'prompt'}">${pm.policy}</span>
      ${pm.reason ? `<div style="font-size:11px;color:var(--text-tertiary);margin-top:4px;">${pm.reason}</div>` : ''}
    </div>
  `).join('') : `<div class="empty-state"><div class="empty-icon">🔒</div><p>暂无权限配置</p></div>`;
  div.innerHTML = `
    <div class="card"><div class="card-header"><h3>🧠 已学习操作</h3><span class="card-badge info">${actions.length} 条</span></div><div class="memory-list">${actionCards}</div></div>
    <div class="card"><div class="card-header"><h3>🔒 应用权限</h3><span class="card-badge info">${perms.length} 项</span></div><div class="perm-grid">${permCards}</div></div>
  `;
  return div;
}

/* ═══════════ DASHBOARD ═══════════ */
async function renderDashboard() {
  const div = document.createElement('div'); div.className = 'page-enter';
  const status = await api('/api/status');
  const monitors = await api('/api/monitors');
  const online = !status.error && status.rust_core;
  const screen = status.screen || '未知';
  const modules = status.modules || [];
  const pyPackages = status.python_packages || [];

  div.innerHTML = `
    <div class="stats-grid">
      <div class="stat-card accent">
        <div class="stat-value accent">${state.flows.length}</div>
        <div class="stat-label">录制流程</div>
      </div>
      <div class="stat-card green">
        <div class="stat-value green">${online ? (modules ? modules.length : 5) : 0}</div>
        <div class="stat-label">Rust 核心模块</div>
      </div>
      <div class="stat-card purple">
        <div class="stat-value purple">${status.tests_passed ?? 56}</div>
        <div class="stat-label">测试通过</div>
      </div>
      <div class="stat-card cyan">
        <div class="stat-value cyan">${screen}</div>
        <div class="stat-label">屏幕分辨率</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <h3>系统概览</h3>
        <span class="card-badge ${online ? 'success' : 'warning'}">${online ? '引擎在线' : '引擎离线'}</span>
      </div>
      <div class="overview-grid">
        <table class="overview-table">
          <tr><td>架构</td><td>Rust (ac-core) + Python SDK</td></tr>
          <tr><td>引擎状态</td><td>${online ? '✅ 已连接 — Rust 核心运行中' : '⚠️ 离线 — 纯 Python 模式'}</td></tr>
          <tr><td>Rust 模块</td><td>capture · input · window · security · image_proc</td></tr>
          <tr><td>版本</td><td>${status.version || '-'} (${status.tests_passed ?? '?'} 项测试)</td></tr>
          <tr><td>截图性能</td><td>~8ms (DXGI · xcap)</td></tr>
          <tr><td>显示器</td><td>${monitors.count || 0} 个显示器 @ ${screen}</td></tr>
          <tr><td>运行时长</td><td>${status.uptime_seconds ? Math.floor(status.uptime_seconds / 60) + ' 分钟' : '-'}</td></tr>
          <tr><td>Python 包</td><td>${(pyPackages || []).join(' · ')}</td></tr>
        </table>
        <div class="overview-side">
          <div class="quick-actions">
            <button class="btn btn-primary" onclick="quickCapture()">📸 截取屏幕</button>
            <button class="btn btn-success" onclick="switchTab('editor')">✏️ 新建录制</button>
            <button class="btn btn-outline" onclick="switchTab('flows')">▶️ 回放流程</button>
            <button class="btn btn-ghost" onclick="window.open('https://github.com/yygg693/autocomputer')">📖 GitHub</button>
          </div>
          ${state.lastCapture ? `
          <div class="capture-preview">
            <img src="data:image/png;base64,${state.lastCapture.png_b64}" alt="截图预览"/>
            <div class="capture-meta">${state.lastCapture.width}×${state.lastCapture.height} · ${(state.lastCapture.png_size/1024).toFixed(0)}KB</div>
          </div>` : `
          <div class="engine-hint">
            <div class="empty-icon">🦀</div>
            <p>Rust 引擎 ${online ? '运行中' : '离线'}</p>
            <p style="font-size:12px;">${online ? '窗口列表 / 点击 / 聚焦 / 记忆均可用' : '请编译 _core.pyd 或使用纯 Python 模式'}</p>
          </div>`}
        </div>
      </div>
    </div>
  `;
  return div;
}

async function quickCapture() {
  const data = await api('/api/capture');
  if (data.error) { toast(data.error, 'error'); return; }
  state.lastCapture = data;
  toast(`截图成功: ${data.width}×${data.height}, ${(data.png_size/1024).toFixed(0)}KB`, 'success');
  render();
}

/* ═══════════ EDITOR ═══════════ */
const ACTION_DEFS = {
  click: { emoji:'🖱️', cls:'click', defaults:{x:0,y:0,button:'left'}, desc:'鼠标点击' },
  type: { emoji:'⌨️', cls:'type', defaults:{text:'hello',method:'auto'}, desc:'输入文字' },
  press: { emoji:'🔑', cls:'press', defaults:{key:'enter'}, desc:'按键操作' },
  wait: { emoji:'⏳', cls:'wait', defaults:{ms:1000}, desc:'等待延迟' },
  scroll: { emoji:'📜', cls:'scroll', defaults:{clicks:1}, desc:'滚轮滚动' },
  move: { emoji:'➡️', cls:'move', defaults:{x:0,y:0}, desc:'移动鼠标' },
};

function renderEditor() {
  const div = document.createElement('div'); div.className = 'page-enter';

  div.innerHTML = `
    <div class="editor-toolbar">
      ${Object.entries(ACTION_DEFS).map(([action, def]) =>
        `<button class="btn btn-outline btn-sm" onclick="addStep('${action}')">${def.emoji} ${def.desc}</button>`
      ).join('')}
      <div style="flex:1"></div>
      <button class="btn btn-success btn-sm" onclick="saveFlow()">💾 保存流程</button>
      <button class="btn btn-warning btn-sm" onclick="testFlow()">▶️ 试运行</button>
      <button class="btn btn-primary btn-sm" onclick="exportFlowJSON()">📋 导出 JSON</button>
      <button class="btn btn-ghost btn-sm" onclick="clearEditor()">🗑 清空</button>
    </div>
    <div class="editor-layout">
      <div class="step-sidebar">
        <div class="step-sidebar-header">
          步骤 <span style="color:var(--text-muted);font-size:12px;">共 ${state.editing.length} 个</span>
        </div>
        <div class="step-list" id="stepList">
          ${state.editing.length === 0
            ? '<div class="empty-state"><div class="empty-icon">🎬</div><p>暂无步骤</p><p style="font-size:11px;">点击上方动作按钮添加步骤</p></div>'
            : ''}
        </div>
      </div>
      <div class="step-preview">
        ${state.editing.length === 0
          ? '<div class="preview-icon">✏️</div><p style="font-size:13px;">添加步骤来构建自动化流程</p><p style="font-size:11px;">拖拽步骤可调整顺序</p>'
          : `<div class="preview-icon">🤖</div><p style="font-size:14px;color:var(--text-primary);">${state.editing.length} 个步骤就绪</p><p style="font-size:12px;">点击 ▶️ Test Run 执行</p>`
        }
      </div>
    </div>
  `;

  setTimeout(() => {
    const list = document.getElementById('stepList');
    if (list && state.editing.length > 0) {
      list.innerHTML = state.editing.map((s, i) => `
        <div class="step-item" draggable="true" ondragstart="dragStart(${i}, event)" ondragover="dragOver(event)" ondrop="dropReorder(${i}, event)">
          <span class="step-icon ${s.cls}">${s.emoji}</span>
          <div class="step-info">
            <div class="step-title">#${i+1} ${s.action.toUpperCase()}</div>
            <div class="step-detail">${JSON.stringify(s.params)}</div>
          </div>
          <span class="step-remove" onclick="removeStep(${i})">×</span>
        </div>
      `).join('');
    }
  }, 0);

  return div;
}

let _dragIndex = null;

function dragStart(i, ev) {
  _dragIndex = i;
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move';
}
function dragOver(ev) { ev.preventDefault(); }
function dropReorder(i, ev) {
  ev.preventDefault();
  if (_dragIndex === null || _dragIndex === i) { _dragIndex = null; return; }
  const [item] = state.editing.splice(_dragIndex, 1);
  state.editing.splice(i, 0, item);
  _dragIndex = null;
  render();
  toast('步骤已重排', 'info');
}

function addStep(action) {
  const def = ACTION_DEFS[action];
  state.editing.push({ action, params: {...def.defaults}, emoji: def.emoji, cls: def.cls });
  render();
  toast(`已添加: ${def.desc}`, 'success');
}

function removeStep(i) { state.editing.splice(i, 1); render(); }

function clearEditor() { state.editing = []; render(); toast('已清空编辑器', 'info'); }

async function saveFlow() {
  const name = prompt('流程名称:', `flow_${Date.now()}`);
  if (!name) return;
  const steps = state.editing.map(s => ({action:s.action, params:s.params}));
  const res = await api('/api/flows', { method: 'POST', body: JSON.stringify({ name, steps }) });
  if (res && res.ok) {
    state.editing = [];
    await loadFlows();
    toast(`已保存: ${name}`, 'success');
    switchTab('flows');
  } else {
    toast('保存失败: ' + ((res && res.error) || '未知错误'), 'error');
  }
}

let _running = false;
async function testFlow() {
  if (_running) return toast('正在执行,请稍候...', 'info');
  if (!state.editing.length) return toast('没有可执行的步骤', 'error');
  _running = true;
  toast(`正在执行 ${state.editing.length} 个步骤...`, 'info');
  for (let i = 0; i < state.editing.length; i++) {
    const s = state.editing[i];
    const result = await api('/api/execute', {
      method: 'POST',
      body: JSON.stringify({ action: s.action, params: s.params }),
    });
    if (!result.success) {
      toast(`第 ${i+1} 步失败: ${result.error}`, 'error');
      _running = false;
      return;
    }
  }
  toast(`全部 ${state.editing.length} 个步骤执行成功!`, 'success');
  _running = false;
}

function exportFlowJSON() {
  const json = JSON.stringify({ version:'1.0', steps: state.editing.map(s => ({action:s.action, params:s.params})) }, null, 2);
  const blob = new Blob([json], {type:'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'flow.json'; a.click();
  toast('已导出为 flow.json', 'success');
}

/* ═══════════ FLOWS ═══════════ */
async function loadFlows() {
  try {
    const d = await api('/api/flows');
    if (d && Array.isArray(d.flows)) state.flows = d.flows;
  } catch (e) { /* keep current */ }
  updateBadges();
}

async function deleteFlow(name) {
  if (!confirm(`确定删除流程 "${name}" 吗?`)) return;
  await api('/api/flows?name=' + encodeURIComponent(name), { method: 'DELETE' });
  await loadFlows();
  toast('已删除: ' + name, 'info');
  render();
}

function renderFlows() {
  const div = document.createElement('div'); div.className = 'page-enter';

  if (state.flows.length === 0) {
    div.innerHTML = `<div class="card"><div class="empty-state"><div class="empty-icon">📂</div><p>暂无保存的流程</p><p style="font-size:12px;">先在编辑器中创建流程</p><button class="btn btn-primary btn-sm" onclick="switchTab('editor')">✏️ 去编辑器</button></div></div>`;
    return div;
  }

  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3>已保存流程</h3>
        <span class="card-badge info">${state.flows.length} 个</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>名称</th><th>步骤数</th><th>创建时间</th><th style="width:150px">操作</th></tr></thead>
          <tbody>
            ${state.flows.map((f, i) => `
              <tr>
                <td>${f.name}</td>
                <td>${f.steps.length} 步</td>
                <td>${f.created ? new Date(f.created).toLocaleString() : '-'}</td>
                <td>
                  <button class="btn btn-success btn-xs" onclick="replayFlow(${i})" title="回放">▶️</button>
                  <button class="btn btn-outline btn-xs" onclick="editFlow(${i})" title="编辑">✏️</button>
                  <button class="btn btn-danger btn-xs" onclick="deleteFlow('${String('${f.name}').replace(/'/g, "\\'")}')" title="删除">🗑</button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
  return div;
}

async function replayFlow(i) {
  const flow = state.flows[i];
  toast(`正在回放: ${flow.name} (共 ${flow.steps.length} 步)...`, 'info');
  for (let j = 0; j < flow.steps.length; j++) {
    const s = flow.steps[j];
    const result = await api('/api/execute', {
      method: 'POST',
      body: JSON.stringify({ action: s.action, params: s.params }),
    });
    if (!result.success) {
      toast(`第 ${j+1} 步失败: ${result.error}`, 'error');
      return;
    }
  }
  toast(`${flow.name} replay complete!`, 'success');
}
function editFlow(i) {
  state.editing = state.flows[i].steps.map(s => {
    const def = ACTION_DEFS[s.action] || { emoji:'❓', cls:'click' };
    return { ...s, emoji: def.emoji, cls: def.cls };
  });
  switchTab('editor');
}
function exportSingle(i) {
  const json = JSON.stringify({version:'1.0', name:state.flows[i].name, steps:state.flows[i].steps}, null, 2);
  const blob = new Blob([json], {type:'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = state.flows[i].name + '.json'; a.click();
}
function deleteFlow(i) {
  if (confirm(`Delete "${state.flows[i].name}"?`)) {
    state.flows.splice(i, 1);
    localStorage.setItem('ac_flows', JSON.stringify(state.flows));
    render();
    toast('流程已删除', 'info');
  }
}

/* ═══════════ MONITOR ═══════════ */
async function renderMonitor() {
  const div = document.createElement('div'); div.className = 'page-enter';
  let logs = [];
  try { const d = await api('/api/logs'); logs = (d && d.logs) || []; } catch (e) {}
  const lines = logs.length ? logs.map(l => `
    <div class="log-line"><span class="time">${l.ts}</span><span class="level ${l.ok ? 'ok' : 'error'}">${l.ok ? 'OK' : 'ERR'}</span><span class="msg">[${l.action}] ${l.detail}</span></div>
  `).join('') : `
    <div class="empty-state"><div class="empty-icon">📭</div><p>暂无操作记录</p><p style="font-size:12px;">在编辑器试运行后,这里会显示真实执行日志</p></div>`;
  div.innerHTML = `
    <div class="card">
      <div class="card-header"><h3>👁️ 操作日志</h3><span class="card-badge info">${logs.length} 条</span></div>
      <div class="log-container">${lines}</div>
    </div>
  `;
  return div;
}
/* ═══════════ SECURITY ═══════════ */
async function renderSecurity() {
  const div = document.createElement('div'); div.className = 'page-enter';
  let sec = { audit: { total: 0, by_action: {}, recent: [] }, hotkeys: [], thresholds: {} };
  try { const d = await api('/api/security'); if (d) sec = d; } catch (e) {}
  const actions = Object.entries(sec.audit.by_action || {});
  const maxCnt = Math.max(1, ...actions.map(([, c]) => c));
  const hotkeys = (sec.hotkeys || []).map(h => `
    <div class="perm-card"><div class="app-name">${h.keys}</div><span class="perm-tag deny">${h.severity}</span></div>
  `).join('') || '<p style="font-size:13px;color:var(--text-muted);">无</p>';
  const bars = actions.length ? actions.map(([a, c]) => `
    <div class="bar-row"><span class="bar-label">${a}</span><div class="bar-track"><div class="bar-fill" style="width:${(c / maxCnt * 100).toFixed(0)}%"></div></div><span class="bar-count">${c}</span></div>
  `).join('') : '<p style="font-size:13px;color:var(--text-muted);">暂无审计数据 — 执行操作后自动记录</p>';
  const recent = (sec.audit.recent || []).length ? sec.audit.recent.map(r => `
    <div class="log-line"><span class="time">${r.time}</span><span class="level ${r.result === 'ok' ? 'ok' : 'error'}">${r.result}</span><span class="msg">[${r.action}] ${r.detail}</span></div>
  `).join('') : '<p style="font-size:13px;color:var(--text-muted);">暂无记录</p>';
  div.innerHTML = `
    <div class="stats-grid" style="grid-template-columns:repeat(4,1fr);">
      <div class="stat-card green"><div class="stat-value green">${sec.audit.total}</div><div class="stat-label">审计记录总数</div></div>
      <div class="stat-card accent"><div class="stat-value accent">${sec.thresholds.max_clicks_same_position ?? 5}</div><div class="stat-label">同点点击阈值</div></div>
      <div class="stat-card purple"><div class="stat-value purple">${sec.thresholds.rate_limit_ms ?? 100}ms</div><div class="stat-label">操作限速</div></div>
      <div class="stat-card cyan"><div class="stat-value cyan">${sec.thresholds.audit_retention_days ?? 90}天</div><div class="stat-label">审计保留</div></div>
    </div>
    <div class="card"><div class="card-header"><h3>🔒 拦截的热键</h3></div><div class="perm-grid">${hotkeys}</div></div>
    <div class="card"><div class="card-header"><h3>📊 审计统计(按动作)</h3></div><div class="bar-chart">${bars}</div></div>
    <div class="card"><div class="card-header"><h3>📝 最近审计记录</h3></div><div class="log-container">${recent}</div></div>
  `;
  return div;
}
/* ═══════════ JELLY + PARTICLES (参考 StockPilot Obsidian 交互) ═══════════ */

// ---- 粒子系统:背景漂浮 + 点击爆发 ----
let _particles = [];
let _pCanvas = null, _pCtx = null;

function initParticles() {
  const c = document.createElement('canvas');
  c.id = 'fx-canvas';
  document.body.appendChild(c);
  _pCanvas = c; _pCtx = c.getContext('2d');
  const resize = () => { c.width = window.innerWidth; c.height = window.innerHeight; };
  resize();
  window.addEventListener('resize', resize);
  for (let i = 0; i < 34; i++) _particles.push(mkParticle(true));
  requestAnimationFrame(pStep);
}

function mkParticle(ambient) {
  return {
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.28,
    vy: (Math.random() - 0.5) * 0.28 - 0.08,
    life: 1, decay: 0.012 + Math.random() * 0.02,
    size: 1 + Math.random() * 1.9,
    hue: Math.random() > 0.35 ? '201,169,98' : '79,214,255', // 金铜为主,青点缀
    ambient: !!ambient,
  };
}

function burstParticles(x, y) {
  for (let i = 0; i < 12; i++) {
    const a = Math.random() * Math.PI * 2;
    const sp = 1 + Math.random() * 2.6;
    _particles.push({ ...mkParticle(false), x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 0.6 });
  }
  if (_particles.length > 180) _particles.splice(0, _particles.length - 180);
}

function pStep() {
  const ctx = _pCtx;
  if (!ctx) return;
  ctx.clearRect(0, 0, _pCanvas.width, _pCanvas.height);
  for (let i = _particles.length - 1; i >= 0; i--) {
    const p = _particles[i];
    p.x += p.vx; p.y += p.vy;
    if (!p.ambient) {
      p.life -= p.decay;
      if (p.life <= 0 || p.x < -10 || p.x > window.innerWidth + 10 || p.y < -10 || p.y > window.innerHeight + 10) {
        _particles.splice(i, 1); continue;
      }
    } else {
      if (p.x < -10) p.x = window.innerWidth + 10;
      if (p.x > window.innerWidth + 10) p.x = -10;
      if (p.y < -10) p.y = window.innerHeight + 10;
      if (p.y > window.innerHeight + 10) p.y = -10;
    }
    ctx.globalAlpha = p.ambient ? 0.22 : p.life * 0.75;
    ctx.fillStyle = 'rgba(' + p.hue + ', 0.95)';
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
  requestAnimationFrame(pStep);
}

// 点击任意处发射粒子(忽略侧栏/按钮原生点击冲突——粒子只是视觉)
document.addEventListener('click', function (e) { burstParticles(e.clientX, e.clientY); });

// ---- 果冻弹性:按压压扁 + 释放弹性回弹 + 光标跟随倾斜 ----
const JELLY_SEL = '.card, .stat-card, .btn, .window-item, .perm-card, .memory-item, .flow-item, .step-item';

function attachJelly() {
  const els = document.querySelectorAll(JELLY_SEL);
  els.forEach(el => {
    if (el.dataset.jelly) return;
    el.dataset.jelly = '1';
    el.addEventListener('mousedown', () => {
      el.style.transition = 'transform 0.08s ease';
      el.style.transform = 'scale(0.965)';
    });
    const release = () => {
      // 回弹:先快速回弹略过头,再归位(弹性 cubic-bezier)
      el.style.transition = 'transform 0.38s cubic-bezier(0.34, 1.56, 0.64, 1)';
      el.style.transform = 'scale(1)';
    };
    el.addEventListener('mouseup', release);
    el.addEventListener('mouseleave', release);
  });
}

// ── Init ──
loadFlows();
updateEngineStatus();
render();
updateBadges();

async function updateEngineStatus() {
  const el = document.getElementById('engineStatus');
  if (!el) return;
  try {
    const s = await api('/api/status');
    const online = !s.error && s.rust_core;
    el.innerHTML = `<span class="status-dot ${online ? 'online' : 'offline'}"></span><span>${online ? 'Rust 引擎在线' : '纯 Python 模式(引擎离线)'}</span>`;
  } catch (e) { /* keep default */ }
}



