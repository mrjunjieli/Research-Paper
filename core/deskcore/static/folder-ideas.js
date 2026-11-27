/* Folder-scoped ideas. Drafts survive navigation; edit history remains session-only. */
(() => {
  'use strict';
  const docs = new Map(), prefix = 'knowledge-folder-ideas-v1:';
  const en = () => /^en\b/i.test(document.documentElement.lang);
  const t = (zh, eng) => en() ? eng : zh;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function doc(id) {
    if (!docs.has(id)) {
      let draft;
      try { draft = JSON.parse(localStorage.getItem(prefix + id)); } catch {}
      const valid = draft && typeof draft.content === 'string' && draft.content.length <= 100000;
      docs.set(id, {id, content: valid ? draft.content : '', revision: valid && Number.isInteger(draft.revision) ? draft.revision : null,
        editing: false, finishing: false, dirty: !!valid, loaded: false, loading: false, saving: false, version: 0, timer: null, conflict: false, error: '', storageError: false});
    }
    return docs.get(id);
  }
  const panels = d => [...document.querySelectorAll('[data-folder-ideas]')].filter(el => el.dataset.folderIdeas === d.id);
  function persist(d) {
    try {
      if (d.dirty) localStorage.setItem(prefix+d.id, JSON.stringify({content:d.content,revision:d.revision}));
      else localStorage.removeItem(prefix+d.id);
      d.storageError = false;
    } catch { d.storageError = true; }
  }
  function status(d) {
    if(d.finishing && (d.error||d.conflict))d.finishing=false;
    if(d.finishing && d.loaded && !d.loading && !d.saving && !d.dirty){d.editing=false;d.finishing=false;}
    for (const panel of panels(d)) {
      const label = panel.querySelector('[data-idea-status]'); if (!label) continue;
      const input=panel.querySelector('textarea');input.readOnly=!d.editing;
      panel.querySelector('[data-idea-edit]').disabled=d.editing||d.loading;
      const saveButton=panel.querySelector('[data-idea-save]');saveButton.disabled=!d.editing||d.finishing||d.loading||d.conflict;
      const saveLabel=d.finishing?t('正在保存…','Saving…'):t('保存','Save');if(saveButton.textContent!==saveLabel)saveButton.textContent=saveLabel;
      const mode=panel.querySelector('[data-idea-mode]'),modeText=d.editing?t('编辑中 · 草稿自动保存；点击保存后锁定。','Editing · Drafts autosave; Save locks this note.'):t('只读 · 点击编辑后可修改。','Read only · Click Edit to make changes.');
      if(mode.textContent!==modeText)mode.textContent=modeText;
      let text = d.conflict ? t('另一页面已有修改，草稿已保留；请复制后加载已保存版本。','Changed elsewhere. Copy your draft before loading the saved version.') :
        d.error ? t('保存未完成，草稿已保留；可重试。','Not saved yet; draft kept. You can retry.') :
        d.saving ? t('正在保存…','Saving…') : d.loading ? t('正在加载…','Loading…') :
        d.dirty ? t('待自动保存…','Waiting to save…') : t('已保存到此收藏夹','Saved to this folder');
      if (d.storageError) text += t(' 本机草稿暂存不可用，请勿关闭页面。',' Browser draft storage unavailable; keep this page open.');
      if (label.textContent !== text) label.textContent = text;
      label.classList.toggle('is-error',!!(d.error||d.conflict||d.storageError));
      const retry=panel.querySelector('[data-idea-retry]'); retry.hidden=!(d.error||d.conflict);retry.disabled=d.saving||d.loading;
      retry.textContent=d.conflict?t('加载已保存版本','Load saved version'):t('重试','Retry');
    }
  }
  async function request(id, payload) {
    const response = await fetch('/api/folder-ideas?folder_id='+encodeURIComponent(id), payload === undefined ? {signal:AbortSignal.timeout(15000)} :
      {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,folder_id:id}),signal:AbortSignal.timeout(15000),keepalive:JSON.stringify(payload).length<20000});
    const result = await response.json();
    if (!response.ok) { const error=new Error(result.error||String(response.status)); error.conflict=result.conflict;throw error; }
    return result;
  }
  function schedule(d, delay=650) {clearTimeout(d.timer);if(!d.conflict)d.timer=setTimeout(()=>save(d),delay);}
  async function load(d, replace=false) {
    if(d.loading)return;d.loading=true;status(d);
    try {
      const remote=await request(d.id);
      if(!replace && d.dirty && d.content!==remote.content && (d.revision??0)!==remote.revision) {
        d.conflict=true;d.error='conflict';d.loaded=true;return;
      }
      if(replace||!d.dirty) {
        d.content=remote.content;d.dirty=false;d.conflict=false;persist(d);
        for(const panel of panels(d)){const input=panel.querySelector('textarea');if(input){input.value=d.content;input.disabled=false;window.EditHistory?.reset(input);}}
      }
      d.revision=remote.revision;d.loaded=true;d.error='';
      if(d.dirty&&d.content===remote.content){d.dirty=false;persist(d);}
      if(d.dirty)schedule(d);
    } catch(error) { d.error=error.message; }
    finally { d.loading=false;for(const panel of panels(d)){const input=panel.querySelector('textarea');if(input)input.disabled=false;}status(d); }
  }
  async function save(d) {
    clearTimeout(d.timer);
    if(!d.dirty||d.saving||d.conflict)return;
    if(!d.loaded){await load(d);return;}
    const content=d.content,version=d.version;d.saving=true;d.error='';status(d);
    try {
      const remote=await request(d.id,{content,revision:d.revision});d.revision=remote.revision;
      if(d.version===version&&d.content===content)d.dirty=false;
      persist(d);
    } catch(error) {d.conflict=!!error.conflict;d.error=error.message;persist(d);}
    finally {d.saving=false;status(d);if(d.dirty&&!d.error)schedule(d,0);}
  }
  function mount(panel) {
    if(panel.dataset.ideaMounted)return;
    panel.dataset.ideaMounted='true';const d=doc(panel.dataset.folderIdeas);
    panel.innerHTML=`<div class="folder-ideas-head"><h3>${esc(t('本收藏夹的研究想法','Research ideas for this folder'))}</h3><div class="folder-ideas-actions"><span class="folder-ideas-status" data-idea-status role="status"></span><button type="button" class="secondary" data-idea-edit>${esc(t('编辑','Edit'))}</button><button type="button" class="primary" data-idea-save disabled>${esc(t('保存','Save'))}</button></div></div><p>${esc(t('这些记录仅属于收藏夹「','These notes belong only to “'))}${esc(panel.dataset.folderName)}${esc(t('」，用于总结其中论文带来的想法。','” and the ideas inspired by its papers.'))}</p><div data-edit-history="folder-ideas:${esc(d.id)}"><label class="sr-only" for="folder-idea-text">${esc(t('个人研究想法','Personal research ideas'))}</label><textarea ${d.editing?'':'readonly'} id="folder-idea-text" rows="5" maxlength="100000" translate="no" ${!d.loaded&&!d.dirty?'disabled':''} placeholder="${esc(t('记下研究问题、方法设想、论文之间的联系，或粘贴 AI 辅助整理的想法…','Capture research questions, methods, connections between papers, or ideas drafted with AI…'))}">${esc(d.content)}</textarea></div><p class="folder-ideas-mode" data-idea-mode></p><button type="button" class="secondary folder-ideas-retry" data-idea-retry hidden></button>`;
    panel.querySelector('textarea').addEventListener('input',e=>{if(!d.editing)return;d.content=e.target.value;d.version++;d.dirty=true;persist(d);status(d);schedule(d);});
    panel.querySelector('[data-idea-edit]').addEventListener('click',()=>{d.editing=true;status(d);panel.querySelector('textarea').focus();});
    panel.querySelector('[data-idea-save]').addEventListener('click',async()=>{if(!d.editing)return;d.finishing=true;await save(d);status(d);});
    panel.querySelector('[data-idea-retry]').addEventListener('click',()=>{
      if(d.conflict){if(!confirm(t('请先复制要保留的草稿。继续将用已保存版本替换当前内容。','Copy any draft you want to keep. Continue to replace it with the saved version?')))return;load(d,true);}
      else if(d.loaded)save(d);else load(d);
    });
    status(d);if(!d.loaded)load(d);
  }
  function scan(){document.querySelectorAll('[data-folder-ideas]').forEach(mount);}
  new MutationObserver(scan).observe(document.documentElement,{childList:true,subtree:true});
  window.addEventListener('online',()=>{for(const d of docs.values())if(d.dirty&&!d.conflict)save(d);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)for(const d of docs.values())if(d.dirty)save(d);});
  window.addEventListener('pagehide',()=>{for(const d of docs.values())if(d.dirty){persist(d);save(d);}});
  scan();
})();
