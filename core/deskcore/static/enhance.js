/* 增强层：视图过渡、命令面板（Cmd/Ctrl+K）、快捷键。
   只依赖 app.js 暴露的全局函数与变量，不修改其内部状态结构。 */
(() => {
const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? '⌘' : 'Ctrl';
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------- 动效 ---------- */
window.enterView = () => {
  const c = document.getElementById('content');
  if (!c || reduce) return;
  c.classList.remove('view-enter');
  void c.offsetWidth;
  c.classList.add('view-enter');
};

/* ---------- 命令面板 ---------- */
let palette = null, items = [], active = 0, pendingG = 0;

function paletteOpen() { return !!palette; }

function ensurePalette() {
  if (palette) return palette;
  palette = document.createElement('div');
  palette.className = 'cmd-overlay';
  palette.hidden = true;
  palette.innerHTML = `<div class="cmd-panel" role="dialog" aria-modal="true" aria-label="命令面板">
    <input class="cmd-input" type="text" placeholder="搜索页面或操作，例如：论文、待办、导出、任务中心" autocomplete="off" spellcheck="false" aria-label="命令搜索">
    <div class="cmd-list" role="listbox"></div>
    <div class="cmd-foot"><span>↑↓ 选择</span><span>↵ 执行</span><span>esc 关闭</span><span>${MOD}K 随时打开</span></div>
  </div>`;
  document.body.append(palette);
  const input = palette.querySelector('.cmd-input');
  input.addEventListener('input', () => renderPalette(input.value));
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' || (e.key === 'n' && e.ctrlKey)) { e.preventDefault(); movePalette(1); }
    else if (e.key === 'ArrowUp' || (e.key === 'p' && e.ctrlKey)) { e.preventDefault(); movePalette(-1); }
    else if (e.key === 'Enter') { e.preventDefault(); runPalette(); }
  });
  palette.addEventListener('mousedown', e => { if (e.target === palette) closePalette(); });
  palette.addEventListener('mousemove', e => {
    const row = e.target.closest('.cmd-item');
    if (row) { active = Number(row.dataset.index); paintActive(); }
  });
  return palette;
}

function currentWorkspace() { return typeof workspace !== 'undefined' ? workspace : 'research'; }

function buildItems() {
  const ws = currentWorkspace();
  const research = [
    ['每日推荐', 'inbox', 'inbox'], ['我的论文库', 'paper', 'book'], ['标签库', 'topics', 'tag'],
    ['关系网络', 'graph', 'network'], ['收集与推荐流程', 'pipeline', 'flow'],
  ];
  const news = [['新闻收件箱', 'inbox', 'inbox'], ['新闻库', 'news', 'newspaper']];
  const list = [];
  for (const [label, view, icon] of (ws === 'news' ? news : research)) {
    list.push({ group: '导航', label, icon, key: '', run: () => navTo(ws, view) });
  }
  if (typeof window.renderTodos === 'function') list.push({ group: '导航', label: '待办与日程', icon: 'calendar', key: 'G D', run: () => navTo(ws, 'todos') });
  if (typeof window.renderCreator === 'function') list.push({ group: '导航', label: '创作工作台', icon: 'pen', key: 'G W', run: () => navTo(ws, 'studio') });
  if (typeof window.renderExperiments === 'function') list.push({ group: '导航', label: '实验记录', icon: 'flask', key: 'G E', run: () => navTo(ws, 'lab') });
  if (typeof window.renderTodos === 'function' || typeof window.renderCreator === 'function' || typeof window.renderExperiments === 'function') {
    list.push({ group: '导航', label: '每日信息源 / 订阅来源', icon: 'rss', key: 'G S', run: () => navTo(ws, 'sources') });
    list.push({ group: '导航', label: 'AI 设置', icon: 'spark', key: 'G A', run: () => navTo(ws, 'ai') });
    list.push({ group: '导航', label: ws === 'news' ? '刷新与推荐设置' : '采集与推荐设置', icon: 'settings', key: 'G ,', run: () => navTo(ws, 'settings') });
  }
  if (!window.DESK_SECTIONS || window.DESK_SECTIONS.length > 1) list.push({ group: '导航', label: ws === 'news' ? '切换到 Research Paper' : '切换到 News', icon: 'layers', key: '', run: () => switchWorkspace(ws === 'news' ? 'research' : 'news') });
  list.push({ group: '操作', label: ws === 'news' ? '添加新闻' : '添加论文', icon: 'plus', key: '', run: () => document.getElementById('add')?.click() });
  list.push({ group: '操作', label: ws === 'news' ? '刷新新闻' : '获取最新论文', icon: 'rss', key: '', run: () => document.getElementById('refresh')?.click() });
  list.push({ group: '操作', label: '任务中心', icon: 'tasks', key: '', run: () => { document.getElementById('task-center-toggle')?.click(); } });
  list.push({ group: '操作', label: '切换界面语言', icon: 'compass', key: '', run: () => {
    const select = document.getElementById('ui-language');
    if (!select) return;
    select.value = select.value === 'en' ? 'zh' : 'en';
    select.dispatchEvent(new Event('change'));
  } });
  list.push({ group: '帮助', label: '查看键盘快捷键', icon: 'tasks', key: '?', run: showShortcuts });
  return list;
}

function navTo(ws, view) {
  const step = () => { if (typeof go === 'function') go(view); else location.hash = view; };
  if (currentWorkspace() !== ws && typeof switchWorkspace === 'function') switchWorkspace(ws, true).then(step);
  else step();
}

function match(text, query) {
  if (!query) return true;
  const hay = text.toLowerCase(), q = query.toLowerCase().trim();
  if (hay.includes(q)) return true;
  let i = 0;
  for (const ch of q.replace(/\s+/g, '')) {
    i = hay.indexOf(ch, i);
    if (i < 0) return false;
    i += 1;
  }
  return true;
}

function renderPalette(query = '') {
  items = buildItems().filter(it => match(it.label + ' ' + it.group, query));
  active = Math.min(active, Math.max(0, items.length - 1));
  const list = palette.querySelector('.cmd-list');
  if (!items.length) {
    list.innerHTML = `<p class="cmd-empty">没有匹配的命令。试试“论文”“待办”“导出”“任务”。</p>`;
    return;
  }
  let html = '', lastGroup = '';
  items.forEach((item, index) => {
    if (item.group !== lastGroup) { html += `<div class="cmd-group">${esc(item.group)}</div>`; lastGroup = item.group; }
    html += `<button type="button" class="cmd-item${index === active ? ' active' : ''}" data-index="${index}" role="option" aria-selected="${index === active}">
      <svg class="i" aria-hidden="true"><use href="#i-${item.icon}"/></svg><span>${esc(item.label)}</span>${item.key ? `<span class="cmd-key">${esc(item.key)}</span>` : ''}</button>`;
  });
  list.innerHTML = html;
  list.querySelectorAll('.cmd-item').forEach(btn => btn.addEventListener('click', () => { active = Number(btn.dataset.index); runPalette(); }));
}

function paintActive() {
  palette?.querySelectorAll('.cmd-item').forEach(row => {
    const on = Number(row.dataset.index) === active;
    row.classList.toggle('active', on);
    row.setAttribute('aria-selected', String(on));
    if (on) row.scrollIntoView({ block: 'nearest' });
  });
}

function movePalette(delta) {
  if (!items.length) return;
  active = (active + delta + items.length) % items.length;
  paintActive();
}

function runPalette() {
  const item = items[active];
  closePalette();
  if (item) setTimeout(() => item.run(), 20);
}

function openPalette() {
  ensurePalette();
  active = 0;
  palette.hidden = false;
  palette.querySelector('.cmd-input').value = '';
  renderPalette('');
  palette.querySelector('.cmd-input').focus();
}

function closePalette() {
  if (palette) palette.hidden = true;
}

/* ---------- 项目可用性（失败隔离在前端的表现） ---------- */
(() => {
  const sectionId = { research: 'switch-research', news: 'switch-news', todos: 'switch-todos', studio: 'switch-studio', lab: 'switch-lab' };
  fetch('/api/projects').then(r => r.ok ? r.json() : null).then(data => {
    if (!data || !Array.isArray(data.projects)) return;
    for (const p of data.projects) {
      if (p.ok) continue;
      const button = document.getElementById(sectionId[p.id]);
      if (button) { button.hidden = true; button.title = '该模块暂时不可用'; }
    }
  }).catch(() => {});
})();

/* ---------- 快捷键 ---------- */
function typingInField(target) {
  if (!target) return false;
  const tag = target.tagName;
  return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
}

function showShortcuts() {
  const rows = [
    [MOD + ' K', '打开命令面板'],
    ['/', '聚焦搜索框'],
    ['G 然后 D', '每日推荐 / 新闻收件箱'],
    ['G 然后 P', '论文库'],
    ['G 然后 T', '标签库'],
    ['G 然后 R', '关系网络'],
    ['G 然后 S', '信息源'],
    ['G 然后 A', 'AI 设置'],
    ['G 然后 W', '创作工作台'],
    ['G 然后 E', '实验记录'],
    ['G 然后 D（在待办页）', '先按 G 再按 I 打开待办'],
    ['?', '打开这份快捷键清单'],
    ['Esc', '关闭弹窗、命令面板或任务中心'],
  ];
  modal('键盘快捷键', `<table class="shortcut-table">${rows.map(([k, d]) => `<tr><td><kbd>${esc(k)}</kbd></td><td>${esc(d)}</td></tr>`).join('')}</table><p class="subtle">命令面板里也可以直接找到下面所有页面和操作。</p>`);
}

document.addEventListener('keydown', e => {
  const mod = isMac ? e.metaKey : e.ctrlKey;
  if (mod && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); paletteOpen() && !palette.hidden ? closePalette() : openPalette(); return; }
  if (e.key === 'Escape') {
    if (palette && !palette.hidden) { closePalette(); return; }
    const dialog = document.getElementById('dialog');
    if (dialog?.open) { dialog.close(); return; }
    const panel = document.getElementById('task-center-panel');
    if (panel && !panel.hidden) document.getElementById('task-center-toggle')?.click();
    return;
  }
  if (typingInField(e.target) || mod || e.altKey) return;
  if (e.key === '?') { e.preventDefault(); showShortcuts(); return; }
  if (e.key === '/') { const search = document.getElementById('search'); if (search) { e.preventDefault(); search.focus(); search.select(); } return; }
  if (e.key === 'g' || e.key === 'G') { pendingG = Date.now(); return; }
  if (Date.now() - pendingG < 1200) {
    const map = { d: 'inbox', i: 'todos', p: 'paper', t: 'topics', r: 'graph', s: 'sources', a: 'ai', w: 'studio', e: 'lab', ',': 'settings' };
    const view = map[e.key.toLowerCase()];
    if (view) { e.preventDefault(); pendingG = 0; navTo(currentWorkspace(), view); }
  }
});
})();
