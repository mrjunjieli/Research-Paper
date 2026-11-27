/* Editing-session history. Never persisted; autosave receives ordinary input events. */
(() => {
  'use strict';
  const MAX_STEPS = 50, MAX_CHARS = 2000000, TYPE_DELAY = 750;
  const histories = new Map();
  let bindings = new WeakMap(), restoring = false, scheduled = false;
  const excluded = /search|filter|password|secret|api.?key|token|chat|question/i;
  const scopeSelector = '[data-edit-history], form';
  const controls = 'textarea, input, select';
  const english = () => /^en\b/i.test(document.documentElement.lang);
  function eligible(el) {
    if (!el.matches?.(controls) || el.readOnly || el.closest('[data-no-edit-history]')) return false;
    if (excluded.test([el.id, el.name, el.autocomplete, el.closest('form')?.id].join(' '))) return false;
    return el.tagName !== 'INPUT' || ['text', 'url', 'email', 'tel', 'number', 'date', 'time', 'datetime-local'].includes(el.type);
  }
  function scopeFor(el) {
    return el.closest(scopeSelector) || (el.matches('textarea') ? el : null);
  }
  function members(scope) {
    return (scope.matches(controls) ? [scope] : [...scope.querySelectorAll(controls)])
      .filter(el => eligible(el) && scopeFor(el) === scope);
  }
  function fieldMap(scope) {
    const result = new Map(), counts = new Map();
    for (const el of members(scope)) {
      const base = el.id || el.name || el.dataset.nwInput || el.getAttribute('aria-label') || el.tagName;
      const index = counts.get(base) || 0; counts.set(base, index + 1);
      result.set(base + ':' + index, el);
    }
    return result;
  }
  const values = fields => Object.fromEntries([...fields].map(([k, el]) => [k, el.value]));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const size = step => JSON.stringify(step.before).length + JSON.stringify(step.after).length;
  function selection(el) {
    return el && typeof el.selectionStart === 'number' ? [el.selectionStart, el.selectionEnd] : null;
  }
  function identity(scope) {
    if (scope.dataset.editHistory) return 'explicit:' + scope.dataset.editHistory;
    const id = scope.id || scope.dataset.nwInput;
    if (!id) return null;
    return scope.tagName + ':' + id + ':' + (scope.dataset.paper || scope.dataset.drop || '');
  }
  function makeToolbar(scope) {
    const bar = document.createElement('div');
    bar.className = 'edit-history-tools'; bar.setAttribute('role', 'group');
    bar.innerHTML = '<button type="button" data-edit-history-action="undo"><span aria-hidden="true">↶</span> <span data-history-label></span></button><button type="button" data-edit-history-action="redo"><span aria-hidden="true">↷</span> <span data-history-label></span></button>';
    // Keep the toolbar inside editor cards so parent grids retain their layout.
    if (scope.matches(controls)) scope.before(bar);
    else scope.prepend(bar);
    return bar;
  }
  function update(h) {
    if (!h.bar?.isConnected) return;
    const en = english(), mac = /Mac|iPhone|iPad/.test(navigator.platform);
    h.bar.setAttribute('aria-label', en ? 'Edit history' : '编辑记录');
    h.bar.title = en ? 'This editing session only; leaving clears history' : '仅保留本次编辑记录，退出编辑后清空';
    for (const action of ['undo', 'redo']) {
      const button = h.bar.querySelector('[data-edit-history-action="' + action + '"]');
      const label = action === 'undo' ? (en ? 'Undo' : '撤销') : (en ? 'Redo' : '重做');
      const key = (mac ? '⌘' : 'Ctrl+') + (action === 'redo' ? (mac ? '⇧Z' : 'Shift+Z') : 'Z');
      const enabled = !h.composing && (action === 'undo' ? h.at > 0 : h.at < h.steps.length)
        && [...fieldMap(h.scope).values()].some(el => !el.disabled);
      button.disabled = !enabled;
      button.title = label + ' (' + key + ')';
      button.setAttribute('aria-label', label);
      const text = button.querySelector('[data-history-label]');
      if (text.textContent !== label) text.textContent = label;
    }
  }
  function reset(h, state) {
    h.current = state; h.steps = []; h.at = 0; h.pending = null; h.composing = null; update(h);
  }
  function ensure(scope) {
    let h = bindings.get(scope);
    const fields = fieldMap(scope), state = values(fields);
    if (!fields.size) return null;
    if (h) {
      if (!same(Object.keys(h.current), Object.keys(state))) reset(h, state);
      return h;
    }
    const key = identity(scope);
    if (!key) return null;
    h = histories.get(key);
    if (!h) { h = {key, steps: [], at: 0, current: state, initiallyDisabled: new Set([...fields].filter(([, el]) => el.disabled).map(([k]) => k))}; histories.set(key, h); }
    // A redraw of the same editor retains history. Different fields/data start a fresh edit.
    if (!same(h.current, state)) reset(h, state);
    h.bar?.remove(); h.scope = scope; h.bar = makeToolbar(scope);
    bindings.set(scope, h); bindings.set(h.bar, h); update(h);
    return h;
  }
  function trim(h) {
    let total = h.steps.reduce((n, step) => n + size(step), 0);
    while (h.steps.length && (h.steps.length > MAX_STEPS || total > MAX_CHARS)) {
      total -= size(h.steps.shift()); h.at = Math.max(0, h.at - 1);
    }
  }
  function record(h, target, type = '') {
    if (restoring || h.composing) return;
    const fields = fieldMap(h.scope), after = values(fields), field = [...fields].find(([, el]) => el === target)?.[0];
    if (!field || same(after, h.current)) { h.pending = null; update(h); return; }
    const before = h.current, start = h.pending?.selection, end = selection(target), now = performance.now();
    const plain = type === 'insertText' && start && start[0] === start[1];
    const last = h.steps[h.at - 1];
    const merge = plain && h.at === h.steps.length && last?.plain && last.field === field
      && now - last.time < TYPE_DELAY && same(last.end, start);
    h.steps.splice(h.at);
    if (merge) Object.assign(last, {after, end, time: now});
    else { h.steps.push({before, after, field, start, end, time: now, plain}); h.at++; }
    h.current = after; h.pending = null; trim(h); update(h);
  }
  function prepare(el) {
    if (!eligible(el) || el.disabled) return null;
    const scope = scopeFor(el), h = scope && ensure(scope);
    if (!h) return null;
    const fields = fieldMap(scope), state = values(fields);
    if (!h.composing && !same(state, h.current)) {
      const changed = [...fields].filter(([key, field]) => field.value !== h.current[key]);
      // Async note loading enables an initially disabled field. That is a baseline.
      // Native date pickers/autofill may change value before focus/input: keep those
      // replacements in history instead of discarding all previous edits on focus.
      if (!h.steps.length && changed.every(([key]) => h.initiallyDisabled.has(key))) reset(h, state);
      else { h.pending = null; record(h, changed[0][1], 'replacement'); }
    }
    for (const [key, field] of fields) if (!field.disabled) h.initiallyDisabled.delete(key);
    h.pending = {selection: selection(el)};
    return h;
  }
  function apply(h, action) {
    if (!h || h.composing || restoring) return;
    const undo = action === 'undo', step = h.steps[undo ? h.at - 1 : h.at];
    if (!step) return;
    const fields = fieldMap(h.scope), target = fields.get(step.field);
    if (!target || target.disabled || !same(values(fields), h.current)) return;
    const state = undo ? step.before : step.after, changed = [];
    restoring = true;
    try {
      for (const [key, el] of fields) if (el.value !== state[key]) { el.value = state[key]; changed.push(el); }
      h.at += undo ? -1 : 1; h.current = state; h.pending = null;
      // Break typing coalescence across an undo/redo command.
      h.steps.forEach(s => { s.plain = false; });
      for (const el of changed) {
        el.dispatchEvent(new Event('input', {bubbles: true}));
        if (el.tagName === 'SELECT' || ['date', 'time', 'number', 'datetime-local'].includes(el.type))
          el.dispatchEvent(new Event('change', {bubbles: true}));
      }
      const focused = fieldMap(h.scope).get(step.field);
      if (focused?.isConnected) {
        focused.focus({preventScroll: true});
        const range = undo ? step.start : step.end;
        if (range && typeof focused.selectionStart === 'number') focused.setSelectionRange(...range);
      }
    } finally { restoring = false; update(h); }
  }
  function scan() {
    scheduled = false;
    const live = new Set();
    for (const el of document.querySelectorAll(controls)) {
      if (!eligible(el)) continue;
      const scope = scopeFor(el), h = scope && ensure(scope);
      if (h) { live.add(h.key); update(h); }
    }
    for (const [key, h] of histories) if (!live.has(key)) { bindings.delete(h.scope); if(h.bar)bindings.delete(h.bar); h.bar?.remove(); histories.delete(key); }
  }
  function scheduleScan() {
    if (!scheduled) { scheduled = true; queueMicrotask(scan); }
  }
  function clear() {
    for (const h of histories.values()) h.bar?.remove();
    histories.clear(); bindings = new WeakMap(); scheduleScan();
  }
  document.addEventListener('focusin', e => { if (!restoring) prepare(e.target); });
  document.addEventListener('beforeinput', e => {
    if (restoring) return;
    if (e.inputType === 'historyUndo' || e.inputType === 'historyRedo') {
      const scope = eligible(e.target) && scopeFor(e.target), h = scope && ensure(scope);
      if (h && e.cancelable) { e.preventDefault(); apply(h, e.inputType === 'historyUndo' ? 'undo' : 'redo'); }
      return;
    }
    prepare(e.target);
  });
  document.addEventListener('compositionstart', e => {
    const h = prepare(e.target); if (h) { h.composing = e.target; update(h); }
  });
  document.addEventListener('compositionend', e => {
    const scope = eligible(e.target) && scopeFor(e.target), h = scope && bindings.get(scope);
    if (h) { h.composing = null; record(h, e.target, 'composition'); }
  });
  for (const type of ['input', 'change']) document.addEventListener(type, e => {
    if (restoring || !eligible(e.target)) return;
    const scope = scopeFor(e.target), h = scope && ensure(scope);
    if (h) record(h, e.target, e.inputType);
  });
  document.addEventListener('click', e => {
    const button = e.target.closest('[data-edit-history-action]');
    if (!button) return;
    e.preventDefault(); e.stopPropagation();
    if (!button.disabled) apply(bindings.get(button.closest('.edit-history-tools')), button.dataset.editHistoryAction);
  }, true);
  document.addEventListener('keydown', e => {
    if (!(e.metaKey || e.ctrlKey) || e.altKey || e.isComposing) return;
    const key = e.key.toLowerCase();
    if (key !== 'z' && !(key === 'y' && e.ctrlKey)) return;
    const scope = eligible(e.target) && scopeFor(e.target);
    const h = scope && ensure(scope) || bindings.get(e.target.closest('.edit-history-tools'));
    if (!h) return;
    e.preventDefault(); e.stopPropagation(); apply(h, key === 'y' || e.shiftKey ? 'redo' : 'undo');
  }, true);
  // Formatting buttons must capture before programmatic replacement and record after it.
  window.EditHistory = {
    before: prepare,
    record(el) { const scope = scopeFor(el), h = scope && ensure(scope); if (h) record(h, el, 'format'); },
    reset(el) { const scope = scopeFor(el), h = scope && ensure(scope); if (h) reset(h, values(fieldMap(scope))); },
    clear
  };
  new MutationObserver(scheduleScan).observe(document.documentElement, {childList: true, subtree: true});
  window.addEventListener('hashchange', clear);
  window.addEventListener('pagehide', clear);
  scan();
})();
