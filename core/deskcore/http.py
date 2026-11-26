#!/usr/bin/env python3
"""deskcore.http — 本地 HTTP 服务：项目路由优先、失败隔离、静态文件。"""
import gzip, json, re, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from deskcore.engine import *
from deskcore import hooks

CORE_STATIC = Path(__file__).resolve().parent / 'static'



class _MissingProject:
    def __getattr__(self, _attr):
        raise ValueError('该模块未安装或加载失败')
    def __call__(self, *_a, **_k):
        raise ValueError('该模块未安装或加载失败')


for _name in ['TODOS', 'REMINDERS', 'EXPERIMENTS', 'CREATOR', 'DIRECTIONS', 'ENRICH']:
    if globals().get(_name) is None:
        globals()[_name] = _MissingProject()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        compressed=len(raw)>4096 and 'gzip' in self.headers.get('Accept-Encoding','')
        if compressed:raw=gzip.compress(raw,compresslevel=1)
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Vary','Accept-Encoding')
        if compressed:self.send_header('Content-Encoding','gzip')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def local_request(self):
        allowed={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
        origin=self.headers.get('Origin')
        if self.headers.get('Host') not in allowed or (origin and origin not in {'http://'+h for h in allowed}) or self.headers.get('Sec-Fetch-Site')=='cross-site':
            self.reply({'error':'不允许外部网站访问本地服务'},403);return False
        return True
    def do_GET(self):
        if not self.local_request():return
        path=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(path.query)
        try:
            if hooks.dispatch(self,'GET',path.path,q):return
            if path.path=='/api/projects': return self.reply(hooks.projects_payload())
            workspace=q.get('workspace',['research'])[0]
            if workspace not in ['research','news']: raise ValueError('未知工作空间')
            math_asset=re.fullmatch(r'/katex/(katex\.min\.(?:js|css)|fonts/[A-Za-z0-9_-]+\.(?:woff2?|ttf))',path.path)
            if math_asset:
                file=CORE_STATIC/'katex'/math_asset[1]
                if not file.is_file():return self.reply({'error':'公式资源不存在'},404)
                mime={'.js':'application/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.woff':'font/woff','.woff2':'font/woff2','.ttf':'font/ttf'}[file.suffix]
                self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Cache-Control','public, max-age=86400');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(file.read_bytes());return
            if path.path=='/api/research-directions':return self.reply(DIRECTIONS.read(enrichment_desk(),q.get('history',[''])[0]=='1'))
            if path.path=='/api/creator':return self.reply(CREATOR.read(enrichment_desk(),urllib.parse.parse_qs(path.query).get('id',[None])[0]))
            if path.path=='/api/todos':return self.reply(TODOS.read(enrichment_desk()))
            if path.path=='/api/todo-reminders':return self.reply(REMINDERS.read(enrichment_desk()))
            if path.path=='/api/experiments':return self.reply(EXPERIMENTS.read(enrichment_desk(),q.get('day',[''])[0]))
            if path.path=='/api/tasks':return self.reply(task_center())
            if path.path=='/api/paper-note':
                if workspace!='research':raise ValueError('笔记仅适用于论文')
                return self.reply(paper_note(q.get('id',[''])[0]))
            if path.path=='/api/paper-chat':
                if workspace!='research':raise ValueError('问答仅适用于论文')
                return self.reply(paper_chat_messages(q.get('id',[''])[0]))
            if path.path=='/api/paper-prompt':
                iid=q.get('id',[''])[0]
                with conn() as c:row=c.execute("SELECT summary FROM items WHERE id=? AND workspace='research'",(iid,)).fetchone()
                report=json.loads(row['summary']) if row and row['summary'] else {}
                digest=report.get('prompt_hash','')
                snapshot=DATA/'report-prompts'/(digest+'.txt')
                if re.fullmatch(r'[a-f0-9]{64}',digest) and snapshot.is_file():return self.reply({'text':snapshot.read_text()+'\n\n---\n附加存储、素材与长度约定（User message）\n\n'+report.get('output_instructions',''),'hash':digest,'name':report.get('prompt_name')})
                text,digest=current_paper_prompt();return self.reply({'text':text,'hash':digest,'name':'当前生成流程的 Prompt（该旧报告没有保存 Prompt 快照）'})
            asset=re.fullmatch(r'/paper-assets/([a-f0-9]{20})/(original\.pdf|page-\d+\.png|(?:figure|table)-\d+-p\d+\.png)',path.path)
            if asset:
                iid,name=asset.groups(); file=DATA/(iid+'.pdf') if name=='original.pdf' else DATA/'visuals'/iid/name
                if name=='original.pdf' and (DATA/'materials'/iid/'original.pdf').exists():file=DATA/'materials'/iid/'original.pdf'
                if name=='original.pdf' and (DATA/'materials'/iid/'original.pdf').exists():file=DATA/'materials'/iid/'original.pdf'
                if not file.is_file(): return self.reply({'error':'图表文件不存在'},404)
                self.send_response(200);self.send_header('Content-Type','application/pdf' if name=='original.pdf' else 'image/png');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(file.read_bytes());return
            if path.path=='/api/similar': return self.reply(similar_papers(q.get('id',[''])[0]) if workspace=='research' else [])
            if path.path=='/api/collection-history':return self.reply(collection_history(urllib.parse.parse_qs(path.query).get('date',[now()[:10]])[0]))
            if path.path=='/api/delivery-history':return self.reply(DELIVERY.history(enrichment_desk()))
            if path.path=='/api/state':return self.reply(UI_READS.state(enrichment_desk(),workspace))
            if path.path=='/api/status':return self.reply(UI_READS.status(enrichment_desk(),workspace))
            if path.path=='/api/item':
                item=UI_READS.detail(enrichment_desk(),workspace,q.get('id',[''])[0])
                return self.reply(item if item else {'error':'未找到内容'},200 if item else 404)
            if path.path=='/api/author':
                author=UI_READS.author(enrichment_desk(),workspace,q.get('id',[''])[0])
                return self.reply(author if author else {'error':'未找到作者'},200 if author else 404)
            if path.path=='/api/graph': return self.reply(graph(q.get('mode',['papers'])[0],q.get('limit',[None])[0]) if workspace=='research' else {'nodes':[],'edges':[]})
            if path.path=='/api/export': return self.reply({'version':1,'exported':now(),'workspace':workspace,'items':items(workspace),'authors':author_list(workspace),'topic_library':topic_library() if workspace=='research' else [],'graph':graph('papers') if workspace=='research' else {}})
            asset=hooks.STATIC.get(path.path)
            if not asset: return self.reply({'error':'页面不存在'},404)
            file=Path(asset)
            if not file.is_file(): return self.reply({'error':'页面资源不存在'},404)
            data=file.read_bytes(); self.send_response(200); self.send_header('Cache-Control','no-store'); self.send_header('Content-Type',hooks.MIME.get(file.suffix,'application/octet-stream')); self.end_headers(); self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:
            # Log only route, error type and code locations; never response data or secrets.
            import traceback
            print(json.dumps({'event':'http_read_failed','route':path.path,'type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)]}),flush=True)
            try:self.reply({'error':'无法读取本地数据'},500)
            except (BrokenPipeError,ConnectionResetError):pass
    def do_POST(self):
        if not self.local_request():return
        try:
            if self.headers.get('Origin') and self.headers['Origin'] not in ['http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)]: return self.reply({'error':'不允许跨站请求'},403)
            if 'application/json' not in self.headers.get('Content-Type',''): return self.reply({'error':'需要 JSON 请求'},415)
            size=int(self.headers.get('Content-Length','0'))
            if size>25_000_000: return self.reply({'error':'请求过大'},413)
            v=json.loads(self.rfile.read(size)); path=urllib.parse.urlparse(self.path).path
            workspace=v.get('workspace','research')
            if workspace not in ['research','news']: raise ValueError('未知工作空间')
            if hooks.dispatch(self,'POST',path,v):return
            if path in ['/api/update','/api/opened','/api/viewed','/api/feedback','/api/summarize','/api/review','/api/fulltext','/api/citations','/api/author-metadata','/api/reading-advice','/api/paper-chat']:
                with conn() as c: item=c.execute('SELECT * FROM items WHERE id=? AND workspace=?',(v['id'],workspace)).fetchone()
                if not item: raise ValueError('该内容不属于当前页面')
            if path=='/api/creator':return self.reply(CREATOR.save(enrichment_desk(),v))
            if path=='/api/todos':return self.reply(TODOS.save(enrichment_desk(),v))
            if path=='/api/todo-reminders':return self.reply(REMINDERS.save(enrichment_desk(),v))
            if path=='/api/experiments':return self.reply(EXPERIMENTS.save(enrichment_desk(),v))
            if path=='/api/experiments/organize':return self.reply(EXPERIMENTS.organize(enrichment_desk(),v))
            if path=='/api/experiments/report':return self.reply(EXPERIMENTS.report_draft(enrichment_desk(),v))
            if path=='/api/todos/organize':return self.reply(TODOS.organize(enrichment_desk(),v))
            if path=='/api/research-directions/refresh':
                if workspace!='research':raise ValueError('Research workspace required')
                return self.reply(enqueue_direction_refresh())
            if path=='/api/paper-note':
                if workspace!='research':raise ValueError('笔记仅适用于论文')
                if not isinstance(v.get('content'),str):raise ValueError('笔记内容无效')
                return self.reply(paper_note(v.get('id',''),v['content'],v.get('revision')))
            if path=='/api/paper-chat':
                if workspace!='research':raise ValueError('问答仅适用于论文')
                if not ai_ready(settings()):raise ValueError('请先配置 AI 模型')
                question=v.get('message','')
                if not isinstance(question,str) or not question.strip() or len(question)>3000:raise ValueError('请输入1–3000字的问题')
                with LOCK:
                    if paper_chat_messages(v['id'])['pending']:raise ValueError('当前论文正在回复，请等待完成')
                    with conn() as c:
                        message_id=c.execute('INSERT INTO paper_chat(item,role,content,created) VALUES(?,?,?,?)',(v['id'],'user',question.strip(),now())).lastrowid
                    return self.reply(enqueue('论文问答',lambda:answer_paper_question(v['id'],message_id),workspace,v['id']))
            if path=='/api/topics':
                if workspace!='research': raise ValueError('标签库仅适用于论文')
                return self.reply(edit_topic(v))
            if path=='/api/topic-classify':
                if workspace!='research': raise ValueError('标签整理仅适用于论文')
                pending=next((j for j in list(JOBS.values()) if j['kind']=='AI 标签整理' and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('AI 标签整理',classify_topics,workspace))
            if path=='/api/opened': return self.reply(opened(v['id']))
            if path=='/api/viewed': return self.reply(viewed(v['id']))
            if path=='/api/folders':
                if workspace!='research':raise ValueError('收藏文件夹仅适用于论文')
                return self.reply(create_favorite_folder(v.get('name','')))
            if path=='/api/feedback':
                if 'folder_id' in v:
                    if workspace!='research' or v['value']!='interested':raise ValueError('请先收藏论文，再选择文件夹')
                    validate_favorite_folder(v['folder_id'])
                result=feedback(v['id'],v['value'])
                if 'folder_id' in v:
                    with conn() as c:c.execute('UPDATE items SET folder_id=? WHERE id=?',(v['folder_id'],v['id']))
                return self.reply(result)
            if path=='/api/report-english':
                pending=next((j for j in list(JOBS.values()) if j.get('item_id')==v['id'] and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('补充英文版本',lambda:supplement_english_report(v['id']),workspace,v['id']))
            if path=='/api/reading-advice':
                pending=next((j for j in list(JOBS.values()) if j.get('item_id')==v['id'] and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('阅读建议',lambda:generate_reading_advice(v['id']),workspace,v['id']))
            if path=='/api/review':
                if not ai_ready(settings(workspace=workspace)): raise ValueError('请先配置独立 AI Key，才能生成综合 Review。')
                pending=next((j for j in list(JOBS.values()) if j.get('item_id')==v['id'] and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('论文综合 Review',lambda:review_pipeline(v['id']),workspace,v['id']))
            if path=='/api/screen':
                if workspace!='research': raise ValueError('初审仅适用于论文模块')
                if not ai_ready(settings()): raise ValueError('请先配置论文 AI Key')
                pending=next((j for j in list(JOBS.values()) if j['workspace']==workspace and j['kind']=='推荐初审' and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('推荐初审',screen_daily_candidates,workspace))
            if path=='/api/search-test':
                if workspace!='research': raise ValueError('作者搜索仅适用于论文')
                cfg=settings(workspace=workspace)
                if cfg['search_provider']!='deepseek': raise ValueError('请先选择并保存 DeepSeek 原生搜索')
                pending=next((j for j in JOBS.values() if j['kind']=='联网搜索测试' and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('联网搜索测试',lambda:ENRICH.deepseek_search(enrichment_desk(),cfg,'Zixun Guo Nicolas Queen Mary University personal homepage education',use_cache=False),workspace))
            if path=='/api/ai-test-start': return self.reply(start_ai_test(workspace))
            if path=='/api/ai-test': return self.reply(test_ai_connection(workspace))
            if path=='/api/tasks/dismiss': return self.reply(dismiss_task_message(str(v.get('id','')),str(v.get('version',''))))
            if path=='/api/model-capabilities': return self.reply(model_capability_options(v))
            if path=='/api/models': return self.reply(discover_api_models(v))
            if path=='/api/settings': return self.reply(save_settings(v))
            if path=='/api/items':
                iid,new=add_item(v); return self.reply({'id':iid,'new':new})
            if path=='/api/update':
                allowed=['status','starred','notes','body','coverage','tags']; updates={k:v[k] for k in allowed if k in v}
                if 'status' in updates and updates['status'] not in ['unread','reading','read']: raise ValueError('无效阅读状态')
                if 'tags' in updates: updates['tags']=json.dumps(updates['tags'],ensure_ascii=False)
                if 'body' in updates: updates['summary']=None
                with conn() as c:
                    if updates: c.execute('UPDATE items SET '+','.join(k+'=?' for k in updates)+' WHERE id=?',list(updates.values())+[v['id']])
                if 'starred' in updates: feedback(v['id'],'interested' if updates['starred'] else 'neutral')
                return self.reply({'ok':True})
            if path=='/api/source':
                if v.get('delete'):
                    with conn() as c: c.execute('DELETE FROM sources WHERE id=? AND workspace=?',(v['id'],workspace))
                elif 'enabled' in v and 'id' in v:
                    with conn() as c: c.execute('UPDATE sources SET enabled=? WHERE id=? AND workspace=?',(bool(v['enabled']),v['id'],workspace))
                else:
                    if v['type'] not in (['arxiv','hf','alphaxiv'] if workspace=='research' else ['rss','github']): raise ValueError('论文来源支持 arXiv、Hugging Face 和 alphaXiv')
                    if not v.get('name','').strip() or not v.get('query','').strip(): raise ValueError('请填写来源名称与查询或地址')
                    if v['type']=='alphaxiv': alphaxiv_url(v['query'])
                    if v.get('id'):
                        with conn() as c:
                            if not c.execute('SELECT 1 FROM sources WHERE id=? AND workspace=?',(v['id'],workspace)).fetchone(): raise ValueError('来源不存在')
                            c.execute("UPDATE sources SET name=?,type=?,query=?,kind=?,source_group=?,error='' WHERE id=? AND workspace=?",(v['name'].strip(),v['type'],v['query'].strip(),v.get('kind','paper' if workspace=='research' else 'news'),v.get('source_group','manual'),v['id'],workspace))
                        return self.reply({'ok':True})
                    sid=uid(workspace+':'+v['type']+':'+v['query'])
                    with conn() as c: c.execute('INSERT INTO sources(id,name,type,query,kind,workspace,source_group) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,source_group=excluded.source_group',(sid,v['name'],v['type'],v['query'],v.get('kind','paper' if workspace=='research' else 'news'),workspace,v.get('source_group','manual')))
                return self.reply({'ok':True})
            if path=='/api/refresh':
                pending=next((j for j in list(JOBS.values()) if j['workspace']==workspace and j['kind'] in ['采集来源','每日采集'] and j['state'] in ['queued','running']),None)
                if pending: return self.reply(pending)
                holder={}
                def run_collection():
                    return refresh_all(workspace,stop=lambda:job_cancelled(holder['id']))
                job=enqueue('采集来源',run_collection,workspace);holder['id']=job['id'];JOBS[job['id']]['cancelable']=True
                return self.reply(JOBS[job['id']].copy())
            if path=='/api/cancel-task':
                return self.reply(cancel_job(str(v.get('id',''))))
            if path=='/api/paper-link':
                if workspace!='research':raise ValueError('论文链接导入仅适用于论文库')
                value=str(v.get('url','')).strip();parsed=urllib.parse.urlsplit(value)
                if parsed.scheme not in ['http','https'] or not parsed.hostname or parsed.username or parsed.password:raise ValueError('请填写公开论文的 HTTP/HTTPS 链接')
                validate_favorite_folder(v.get('folder_id',''))
                return self.reply(enqueue('链接导入论文',lambda:import_paper_link(v),workspace))
            if path=='/api/arxiv':
                aid=normalize_arxiv(v['value'])
                return self.reply(enqueue('导入论文',lambda: [{'id':add_item({**i,'workspace':workspace,'source_group':'manual'})[0]} for i in arxiv(ids=aid)],workspace))
            if path=='/api/summarize': return self.reply(enqueue('AI 总结',lambda:summary(v['id']),workspace,v['id']))
            if path=='/api/author-metadata':
                pending=next((j for j in list(JOBS.values()) if j.get('item_id')==v['id'] and j['kind']=='补充作者与单位' and j['state'] in ['queued','running']),None)
                return self.reply(pending or enqueue('补充作者与单位',lambda:refresh_author_metadata(v['id']),workspace,v['id']))
            if path=='/api/fulltext': return self.reply(enqueue('获取正文',lambda:load_arxiv_text(v['id']),workspace,v['id']))
            if path=='/api/citations': return self.reply(enqueue('更新引用',lambda:citations(v['id']),workspace,v['id']))
            if path=='/api/account-summary': return self.reply(enqueue('账号发布总结',lambda:summarize_author(v['id'],workspace),workspace))
            if path=='/api/import-authors': raise ValueError('关注作者导入已停用')
            if path=='/api/author-lookup':
                if v['id'] not in {a['id'] for a in author_list(workspace)}: raise ValueError('作者不属于当前页面')
                return self.reply(enqueue('检索作者身份',lambda:lookup_author(v['id']),workspace))
            if path=='/api/profile':
                if v['id'] not in {a['id'] for a in author_list(workspace)}: raise ValueError('该作者不属于当前页面')
                for field in ['scholar','homepage','external']:
                    if v.get(field) and not re.match(r'^https?://',v[field]): raise ValueError('主页必须是 HTTP/HTTPS 链接')
                with conn() as c:
                    old=c.execute('SELECT * FROM profiles WHERE id=?',(v['id'],)).fetchone()
                    if not v.get('verified') or any(old[k]!=v.get(k,'') for k in ['homepage','scholar']):
                        ids=[v['id']]+[r[0] for r in c.execute('SELECT alias FROM author_aliases WHERE canonical=?',(v['id'],))]
                        for aid in ids:c.execute('DELETE FROM author_identity_links WHERE author=?',(aid,))
                    c.execute('UPDATE profiles SET scholar=?,homepage=?,verified=?,affiliation=?,history=?,identity_evidence=?,education=? WHERE id=?',(v.get('scholar',''),v.get('homepage',''),bool(v.get('verified')),str(v.get('affiliation',''))[:1000],str(v.get('history',''))[:3000],str(v.get('identity_evidence',''))[:3000],str(v.get('education',''))[:3000],v['id']))
                reconcile_author_profiles()
                return self.reply({'ok':True})
            if path=='/api/author-merge':
                if workspace!='research': raise ValueError('作者合并只在 Research Paper 中可用')
                return self.reply(merge_authors(v))
            if path=='/api/edge':
                if workspace!='research': raise ValueError('引用关系只在 Research Paper 中维护')
                if v['src']==v['dst'] or not v.get('evidence','').strip(): raise ValueError('请选择两篇不同论文并填写引用依据')
                with conn() as c:
                    found=c.execute("SELECT COUNT(*) FROM items WHERE id IN (?,?) AND kind='paper' AND workspace='research'",(v['src'],v['dst'])).fetchone()[0]
                    if found!=2: raise ValueError('论文不存在')
                    c.execute('INSERT OR REPLACE INTO edges VALUES(?,?,?,?)',(v['src'],v['dst'],'cites','手动核实：'+v['evidence']))
                return self.reply({'ok':True})
            if path=='/api/pdf':return self.reply(import_pdf(v))
            if path=='/api/email':
                msg=email.message_from_bytes(base64.b64decode(v['data']),policy=policy.default)
                texts=[]
                for part in msg.walk():
                    if part.get_content_type() in ['text/plain','text/html'] and not part.get_filename():
                        content=part.get_content(); texts.append(plain(content) if part.get_content_type()=='text/html' else content)
                body='\n'.join(texts); urls=list(dict.fromkeys(re.findall(r'https?://[^\s<>"\)]+',body))); count=0
                for url in urls:
                    if 'arxiv.org/abs/' in url:
                        try:
                            for item in arxiv(ids=normalize_arxiv(url)): count+=add_item({**item,'workspace':workspace,'source':'Google Scholar 邮件提醒','source_group':'authors'})[1]
                            time.sleep(3)
                        except Exception: pass
                iid,_=add_item({'kind':'post','workspace':workspace,'source_group':'authors','title':str(msg.get('subject','邮件导入')),'body':body,'coverage':'email','source':'邮件文件','tags':['Scholar alerts']})
                return self.reply({'id':iid,'papers_imported':count})
            return self.reply({'error':'接口不存在'},404)
        except (ValueError,KeyError,TypeError) as e: self.reply({'error':str(e)},400)
        except Exception: self.reply({'error':'处理失败，请检查输入或稍后重试。'},500)
