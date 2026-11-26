"""Bounded, read-only UI projections. Full reports are served one paper at a time."""
import collections
import hashlib
import json
import threading
import time

_lock=threading.RLock()
_snapshots={}
_preferences={}


def initialize(desk):
    with desk.conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ui_item_revisions(item TEXT PRIMARY KEY, revision INTEGER NOT NULL);
        INSERT OR IGNORE INTO ui_item_revisions SELECT id,1 FROM items;
        CREATE TRIGGER IF NOT EXISTS ui_item_insert AFTER INSERT ON items BEGIN
          INSERT OR REPLACE INTO ui_item_revisions VALUES(NEW.id,1);
        END;
        CREATE TRIGGER IF NOT EXISTS ui_item_update AFTER UPDATE ON items BEGIN
          INSERT INTO ui_item_revisions VALUES(NEW.id,1) ON CONFLICT(item) DO UPDATE SET revision=revision+1;
        END;
        CREATE TRIGGER IF NOT EXISTS ui_item_delete AFTER DELETE ON items BEGIN
          DELETE FROM ui_item_revisions WHERE item=OLD.id;
        END;
        CREATE INDEX IF NOT EXISTS idx_discoveries_item ON discoveries(item);
        CREATE INDEX IF NOT EXISTS idx_item_topics_item ON item_topics(item);
        ''')


def revision(desk,workspace):
    # Includes external worker writes, config edits and midnight; no persistent connection.
    files=[desk.DB,str(desk.DB)+'-wal',desk.CONFIG if workspace=='research' else desk.DATA/'settings-news.json']
    stamps=[]
    for file in files:
        try:
            st=desk.Path(file).stat();stamps.append((str(file),st.st_mtime_ns,st.st_size))
        except FileNotFoundError:stamps.append((str(file),0,0))
    return hashlib.sha256(repr((stamps,desk.now()[:10])).encode()).hexdigest()[:24]


def jobs(desk,workspace):
    return sorted([dict(j) for j in list(desk.JOBS.values()) if j.get('workspace')==workspace],key=lambda j:(j['state'] in ['running','queued'],j['started']))[-150:]


def status(desk,workspace):
    return {'workspace':workspace,'revision':revision(desk,workspace),'jobs':jobs(desk,workspace)}


def public_settings(desk,workspace):
    # Rendering must not need to unlock the keychain. Expose only configured flags.
    path=desk.CONFIG if workspace=='research' else desk.DATA/'settings-news.json'
    raw=json.loads(path.read_text()) if path.exists() else {}
    cfg={**desk.DEFAULT,**{k:v for k,v in raw.items() if k not in desk.SECRET_STORE.RETIRED_FIELDS}}
    for name in desk.SECRET_STORE.SECRET_FIELDS:
        configured=bool(cfg.pop(name,''))
        if name=='api_key':configured=configured or bool(desk.os.environ.get('SUMMARY_API_KEY'))
        cfg[name+'_configured']=configured
    for k,env in [('base_url','SUMMARY_BASE_URL'),('model','SUMMARY_MODEL')]:
        if desk.os.environ.get(env):cfg[k]=desk.os.environ[env]
    cfg.update(ai_available=bool(desk.codex_binary()) if cfg.get('ai_engine')=='codex' else cfg['api_key_configured'],
      api_providers=desk.API_PROVIDERS,codex_models=desk.CODEX_MODELS,api_effort_catalog=desk.API_EFFORT_CATALOG,
      api_efforts=desk.API_EFFORTS,codex_installed=bool(desk.codex_binary()))
    return cfg


def cards(desk,workspace):
    # Do not SELECT the full body/report/notes, even temporarily. Keep just the existing
    # 6k ranking excerpt internally so recommendation scores retain their semantics.
    with desk.conn() as c:
        columns=[r['name'] for r in c.execute('PRAGMA table_info(items)') if r['name'] not in ['body','summary','notes']]
        projection=','.join('i."'+col+'"' for col in columns)
        rows=c.execute('SELECT '+projection+''',substr(i.body,1,6000) body,
          CASE WHEN json_valid(i.summary) THEN json_object(
            'topics',json_extract(i.summary,'$.topics'),
            'reading_recommendation',json_extract(i.summary,'$.reading_recommendation'),
            'main_idea',substr(json_extract(i.summary,'$.main_idea'),1,300)) ELSE NULL END summary,
          COALESCE(r.revision,1) _revision FROM items i LEFT JOIN ui_item_revisions r ON r.item=i.id
          WHERE i.workspace=? ORDER BY i.added DESC''',(workspace,)).fetchall()
        aliases={r['alias']:r['canonical'] for r in c.execute('SELECT alias,canonical FROM author_aliases')}
        processing={r['item']:dict(r) for r in c.execute('SELECT item,state,updated,details FROM paper_processing')}
        topics=collections.defaultdict(list)
        for r in c.execute('SELECT it.item,t.name,t.category FROM item_topics it JOIN topic_library t ON t.name=it.topic ORDER BY t.name'):topics[r['item']].append(dict(r))
        provenance=collections.defaultdict(list)
        for r in c.execute('SELECT * FROM discoveries'):provenance[r['item']].append(dict(r))
        source_types={r['id']:r['type'] for r in c.execute('SELECT id,type FROM sources')}
        heat={r['item']:json.loads(r['snapshot']) for r in c.execute('SELECT * FROM paper_heat')}
        incremental={r[0] for r in c.execute("SELECT DISTINCT item FROM collection_events WHERE outcome='new'")}
    result=[]
    for row in rows:
        item=desk.decode_item(row,aliases,processing)
        if item['kind']=='paper':
            item['topics']=[r['name'] for r in topics[item['id']]]
            item['topic_groups']={k:[r['name'] for r in topics[item['id']] if r['category']==k] for k in desk.TOPIC_CATEGORIES}
        else:item['topics']=item['tags']
        found=discovery_list(provenance[item['id']],source_types)
        item.update(discoveries=found,heat=heat.get(item['id']),_detail_loaded=False,_incremental_collected=item['id'] in incremental)
        result.append(item)
    if workspace=='research':
        fields=['id','title','body','tags','topics','authors','feedback']
        key=hashlib.sha256(json.dumps([[p.get(k) for k in fields] for p in result],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        cached=_preferences.get(str(desk.DB))
        if cached and cached[0]==key:
            for item in result:item.update(cached[1].get(item['id'],{}))
        else:
            desk.attach_preferences(result)
            _preferences.clear() # one current local corpus, bounded memory
            _preferences[str(desk.DB)]=(key,{i['id']:{k:i.get(k) for k in ['preference_score','preference_details','recommendation_reason']} for i in result})
    return result


def discovery_list(ds, source_types):
    """一篇论文的来源（可能多个）：去重、标注平台，用户手动收录的排在前面。

    采集来源以信息源列表为准，用来过滤早期迁移留下的 legacy 记录；
    手动导入（链接、PDF、arXiv 号）没有对应的信息源，必须保留。
    """
    actual=[d for d in ds if d['source_id'] in source_types or d['source_group']=='manual' and not d['source_id'].startswith('legacy:')]
    clean={}
    for d in actual or ds:
        typ=source_types.get(d['source_id'])
        platform={'arxiv':'arXiv','hf':'Hugging Face Daily Papers','alphaxiv':'alphaXiv'}.get(typ,d['name'])
        if not typ and (d['name']=='arXiv' or 'cs.SD' in d['name'] or 'eess.AS' in d['name']):platform='arXiv'
        if not typ and 'Hugging' in d['name']:platform='Hugging Face Daily Papers'
        clean[(platform,d['source_group'])]={**d,'platform':platform}
    return sorted(clean.values(),key=lambda d:(d['source_group']!='manual',d.get('found','')))


def compact(item):
    out=dict(item)
    out['abstract']=(item.get('abstract') or (item.get('body','') if item.get('coverage')=='abstract' else ''))[:600]
    out['body']=item.get('body','')[:300] if item['kind']!='paper' else ''
    out['has_summary']=bool(item.get('summary'))
    out['summary']={'main_idea':item['summary'].get('main_idea','')} if item['kind']!='paper' and item.get('summary') else None
    out['authors']=[{k:a[k] for k in ['id','name','affiliation','affiliation_source','identity_status'] if k in a} for a in item['authors']]
    out.pop('_incremental_collected',None)
    out.pop('processing',None) # full diagnostic material belongs on the detail page
    return out


def state(desk,workspace):
    # A single build per process, shared by tabs; reading the homepage never writes data
    # or re-admits papers. Collection/screening workers retain those responsibilities.
    with _lock:
        key=(str(desk.DB),workspace);rev=revision(desk,workspace);cached=_snapshots.get(key)
        if cached and cached[0]==rev and time.monotonic()-cached[1]<30:
            return {**cached[2],'jobs':jobs(desk,workspace)}
        current=cards(desk,workspace)
        daily=desk.daily_recommendations(current,read_only=True) if workspace=='research' else None
        if daily:
            daily={**daily,'items':[{k:v for k,v in i.items() if k=='id' or k=='recommended_date' or k.startswith('daily_')} for i in daily['items']]}
        with desk.conn() as c:sources=[dict(r) for r in c.execute('SELECT * FROM sources WHERE workspace=? ORDER BY name',(workspace,))]
        payload={'workspace':workspace,'revision':rev,'items':[compact(i) for i in current],'daily':daily,
          'research_directions':desk.DIRECTIONS.read(desk) if workspace=='research' and getattr(desk,'DIRECTIONS',None) else None,
          'sources':sources,'authors':[], 'topic_library':desk.topic_library() if workspace=='research' else [],
          'folders':desk.favorite_folders() if workspace=='research' else [],'settings':public_settings(desk,workspace)}
        _snapshots[key]=(rev,time.monotonic(),payload)
        return {**payload,'jobs':jobs(desk,workspace)}


def detail(desk,workspace,iid):
    with desk.conn() as c:
        row=c.execute('SELECT i.*,COALESCE(r.revision,1) _revision FROM items i LEFT JOIN ui_item_revisions r ON r.item=i.id WHERE i.id=? AND i.workspace=?',(iid,workspace)).fetchone()
    if row is None:return None
    item=desk.decode_item(row)
    # Reuse only the small display metadata; never serialize the whole state here.
    with _lock:
        cached=_snapshots.get((str(desk.DB),workspace))
        base=next((i for i in cached[2]['items'] if i['id']==iid),{}) if cached else {}
    return {**base,**item,'_detail_loaded':True}


def author(desk,workspace,aid):
    with _lock:current=cards(desk,workspace)
    found=next((a for a in desk.author_list(workspace,papers=current) if a['id']==aid or aid in a.get('aliases',[])),None)
    return {**found,'_profile_loaded':True} if found else None
