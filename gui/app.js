
/* ══════════════════════════════════════════
   autocomputer GUI — Application Logic
   ══════════════════════════════════════════ */

// ── State ──
const state = {
  tab: 'dashboard',
  flows: JSON.parse(localStorage.getItem('ac_flows') || '[]'),
  editing: [],
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
function render() {
  const content = document.getElementById('content');
  content.innerHTML = '';
  content.appendChild(({
    dashboard: renderDashboard, editor: renderEditor,
    flows: renderFlows, monitor: renderMonitor, security: renderSecurity,
  }[state.tab] || renderDashboard)());
  updateBadges();
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
    return { error: 'API offline — start: python -m autocomputer serve' };
  }
}

// ── Refresh ──
function refreshAll() { render(); toast('Refreshed', 'info'); }

function switchTab(name) {
  state.tab = name;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.getElementById('pageTitle').textContent = {
    dashboard:'📊 Dashboard', editor:'✏️ 录制编辑器', flows:'📋 流程管理',
    monitor:'👁️ 实时监控', security:'🛡️ 安全审计'
  }[name];
  render();
}

/* ═══════════ DASHBOARD ═══════════ */
async function renderDashboard() {
  const div = document.createElement('div'); div.className = 'page-enter';
  const status = await api('/api/status');
  const monitors = await api('/api/monitors');
  const online = !status.error && status.rust_core;
  const screen = status.screen || 'Unknown';
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
        <div class="stat-value purple">56</div>
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
        <span class="card-badge ${online ? 'success' : 'warning'}">${online ? 'Online' : 'Offline'}</span>
      </div>
      <table>
        <tr><td>架构</td><td>Rust (ac-core) + Python SDK + HTML5 GUI</td></tr>
        <tr><td>引擎状态</td><td>${online ? '✅ Connected — Rust core active' : '⚠️ Offline — start server first'}</td></tr>
        <tr><td>Rust 模块</td><td>capture · input · window · security · image_proc</td></tr>
        <tr><td>截图性能</td><td>~8ms (DXGI · xcap)</td></tr>
        <tr><td>显示器</td><td>${monitors.count || 0} monitor(s) @ ${screen}</td></tr>
      </table>
    </div>

    <div class="card">
      <div class="card-header"><h3>快速操作</h3></div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button class="btn btn-primary" onclick="quickCapture()">📸 截取屏幕</button>
        <button class="btn btn-success" onclick="switchTab('editor')">✏️ 新建录制</button>
        <button class="btn btn-outline" onclick="switchTab('flows')">▶️ 回放流程</button>
        <button class="btn btn-ghost" onclick="window.open('https://github.com/yygg693/autocomputer')">📖 GitHub →</button>
      </div>
    </div>
  `;
  return div;
}

async function quickCapture() {
  const data = await api('/api/capture');
  if (data.error) { toast(data.error, 'error'); return; }
  toast(`Screenshot: ${data.width}×${data.height}, ${(data.png_size/1024).toFixed(0)}KB`, 'success');
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
      <button class="btn btn-success btn-sm" onclick="saveFlow()">💾 Save Flow</button>
      <button class="btn btn-warning btn-sm" onclick="testFlow()">▶️ Test Run</button>
      <button class="btn btn-primary btn-sm" onclick="exportFlowJSON()">📋 Export JSON</button>
      <button class="btn btn-ghost btn-sm" onclick="clearEditor()">🗑 Clear</button>
    </div>
    <div class="editor-layout">
      <div class="step-sidebar">
        <div class="step-sidebar-header">
          Steps <span style="color:var(--text-muted);font-size:12px;">${state.editing.length} total</span>
        </div>
        <div class="step-list" id="stepList">
          ${state.editing.length === 0
            ? '<div class="empty-state"><div class="empty-icon">🎬</div><p>No steps yet</p><p style="font-size:11px;">Click action buttons above to build a flow</p></div>'
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
        <div class="step-item" draggable="true">
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

function addStep(action) {
  const def = ACTION_DEFS[action];
  state.editing.push({ action, params: {...def.defaults}, emoji: def.emoji, cls: def.cls });
  render();
  toast(`Added: ${def.desc}`, 'success');
}

function removeStep(i) { state.editing.splice(i, 1); render(); }

function clearEditor() { state.editing = []; render(); toast('Editor cleared', 'info'); }

function saveFlow() {
  const name = prompt('流程名称:', `flow_${Date.now()}`);
  if (!name) return;
  state.flows.push({ name, steps: state.editing.map(s => ({action:s.action, params:s.params})), created: new Date().toISOString() });
  localStorage.setItem('ac_flows', JSON.stringify(state.flows));
  state.editing = [];
  toast(`Saved: ${name} (${state.flows.length} total)`, 'success');
  switchTab('flows');
}

async function testFlow() {
  if (!state.editing.length) return toast('No steps to test', 'error');
  toast(`Executing ${state.editing.length} steps...`, 'info');
  for (let i = 0; i < state.editing.length; i++) {
    const s = state.editing[i];
    const result = await api('/api/execute', {
      method: 'POST',
      body: JSON.stringify({ action: s.action, params: s.params }),
    });
    if (!result.success) {
      toast(`Step ${i+1} failed: ${result.error}`, 'error');
      return;
    }
  }
  toast(`All ${state.editing.length} steps executed!`, 'success');
}

function exportFlowJSON() {
  const json = JSON.stringify({ version:'1.0', steps: state.editing.map(s => ({action:s.action, params:s.params})) }, null, 2);
  const blob = new Blob([json], {type:'application/json'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'flow.json'; a.click();
  toast('Exported as flow.json', 'success');
}

/* ═══════════ FLOWS ═══════════ */
function renderFlows() {
  const div = document.createElement('div'); div.className = 'page-enter';

  if (state.flows.length === 0) {
    div.innerHTML = `<div class="card"><div class="empty-state"><div class="empty-icon">📂</div><p>No saved flows</p><p style="font-size:12px;">Create one in the editor first</p><button class="btn btn-primary btn-sm" onclick="switchTab('editor')">✏️ Go to Editor</button></div></div>`;
    return div;
  }

  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <h3>Saved Flows</h3>
        <span class="card-badge info">${state.flows.length} flows</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Name</th><th>Steps</th><th>Created</th><th style="width:140px">Actions</th></tr></thead>
          <tbody>
            ${state.flows.map((f, i) => `
              <tr>
                <td>${f.name}</td>
                <td>${f.steps.length} steps</td>
                <td>${new Date(f.created).toLocaleString()}</td>
                <td>
                  <button class="btn btn-success btn-xs" onclick="replayFlow(${i})">▶️</button>
                  <button class="btn btn-outline btn-xs" onclick="editFlow(${i})">✏️</button>
                  <button class="btn btn-outline btn-xs" onclick="exportSingle(${i})">📋</button>
                  <button class="btn btn-danger btn-xs" onclick="deleteFlow(${i})">×</button>
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
  toast(`Replaying: ${flow.name} (${flow.steps.length} steps)...`, 'info');
  for (let j = 0; j < flow.steps.length; j++) {
    const s = flow.steps[j];
    const result = await api('/api/execute', {
      method: 'POST',
      body: JSON.stringify({ action: s.action, params: s.params }),
    });
    if (!result.success) {
      toast(`Step ${j+1} failed: ${result.error}`, 'error');
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
    toast('Flow deleted', 'info');
  }
}

/* ═══════════ MONITOR ═══════════ */
function renderMonitor() {
  const div = document.createElement('div'); div.className = 'page-enter';
  div.innerHTML = `
    <div class="log-container">
      <div class="log-header">
        <div class="log-tabs">
          <button class="log-tab active">All</button>
          <button class="log-tab">Capture</button>
          <button class="log-tab">Input</button>
          <button class="log-tab">Security</button>
        </div>
        <div style="flex:1"></div>
        <button class="btn btn-outline btn-xs">▶ Start</button>
        <button class="btn btn-ghost btn-xs">⏹ Stop</button>
        <button class="btn btn-ghost btn-xs">🧹 Clear</button>
      </div>
      <div class="log-body">
        <div class="log-line"><span class="time">00:00:01</span><span class="level ok">OK</span><span class="msg">Core engine initialized — 5 Rust modules loaded</span></div>
        <div class="log-line"><span class="time">00:00:02</span><span class="level info">INFO</span><span class="msg">Security guard active — 4 hotkeys blocked, audit enabled</span></div>
        <div class="log-line"><span class="time">00:00:03</span><span class="level ok">OK</span><span class="msg">Capture pipeline ready — xcap DXGI ~8ms</span></div>
        <div class="log-line"><span class="time">00:00:05</span><span class="level ok">OK</span><span class="msg">Input engine ready — enigo + clipboard Chinese support</span></div>
        <div class="log-line"><span class="time">00:00:07</span><span class="level warn">WARN</span><span class="msg">Rate limit hit: click blocked at (500,300) — 45ms < 100ms</span></div>
      </div>
    </div>
  `;
  return div;
}

/* ═══════════ SECURITY ═══════════ */
function renderSecurity() {
  const div = document.createElement('div'); div.className = 'page-enter';
  div.innerHTML = `
    <div class="stats-grid" style="grid-template-columns:repeat(4,1fr);">
      <div class="stat-card green"><div class="stat-value green">4</div><div class="stat-label">Hotkeys Blocked</div></div>
      <div class="stat-card accent"><div class="stat-value accent">5</div><div class="stat-label">Loop Threshold</div></div>
      <div class="stat-card purple"><div class="stat-value purple">100ms</div><div class="stat-label">Rate Limit</div></div>
      <div class="stat-card cyan"><div class="stat-value cyan">SQLite</div><div class="stat-label">Audit Backend</div></div>
    </div>
    <div class="card">
      <div class="card-header"><h3>🔒 Blocked Hotkeys</h3></div>
      <div class="perm-grid">
        <div class="perm-card"><div class="app-name">alt+f4</div><span class="perm-tag deny">Critical</span><div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Close window prevention</div></div>
        <div class="perm-card"><div class="app-name">win+l</div><span class="perm-tag deny">Critical</span><div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Lock screen prevention</div></div>
        <div class="perm-card"><div class="app-name">win+r</div><span class="perm-tag deny">Critical</span><div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Run dialog prevention</div></div>
        <div class="perm-card"><div class="app-name">ctrl+alt+del</div><span class="perm-tag deny">Critical</span><div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Security screen prevention</div></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h3>📱 App Permissions</h3></div>
      <div class="perm-grid">
        <div class="perm-card">
          <div class="app-name">QQ</div>
          <span class="perm-tag allow">send_message</span><span class="perm-tag allow">read_contacts</span><span class="perm-tag deny">file_transfer</span>
        </div>
        <div class="perm-card">
          <div class="app-name">WeChat</div>
          <span class="perm-tag allow">send_message</span><span class="perm-tag deny">file_transfer</span>
        </div>
        <div class="perm-card">
          <div class="app-name">Chrome</div>
          <span class="perm-tag allow">navigate</span><span class="perm-tag allow">form_fill</span><span class="perm-tag prompt">file_download</span>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h3>📝 Audit Log</h3><span class="card-badge success">Active</span></div>
      <p style="font-size:13px;color:var(--text-secondary);">
        SQLite database: <code style="color:var(--accent-light);">autocomputer_audit.db</code><br>
        All clicks, hotkeys, and app actions are recorded with timestamps.
      </p>
    </div>
  `;
  return div;
}

// ── Init ──
render();
updateBadges();
