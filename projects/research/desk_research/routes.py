"""Research project HTTP routes: author intelligence, citations, graph, paper queue."""
from deskcore.engine import (ai_ready, author_list, conn, enqueue, LOCK, now,
                             settings, enrichment_desk, JOBS)
from . import domain
from . import research_directions as DIRECTIONS

PROJECT = 'research'


def _ws(payload):
    value = payload.get('workspace', 'research')
    # GET 的查询参数经 parse_qs 后是列表；POST 的 JSON 是字符串。
    if isinstance(value, (list, tuple)):
        value = value[0] if value else 'research'
    return value


def _pending(item_id, kinds=None):
    return next((j for j in list(JOBS.values())
                 if j.get('item_id') == item_id and j['state'] in ['queued', 'running']
                 and (not kinds or j['kind'] in kinds)), None)


def get_directions(handler, q):
    return DIRECTIONS.read(enrichment_desk(), q.get('history', [''])[0] == '1')


def get_paper_note(handler, q):
    if _ws(q) != 'research':
        raise ValueError('笔记仅适用于论文')
    return domain.paper_note(q.get('id', [''])[0])


def get_paper_chat(handler, q):
    if _ws(q) != 'research':
        raise ValueError('问答仅适用于论文')
    return domain.paper_chat_messages(q.get('id', [''])[0])


def get_graph(handler, q):
    if _ws(q) != 'research':
        return {'nodes': [], 'edges': []}
    return domain.graph(q.get('mode', ['papers'])[0], q.get('limit', [None])[0])


def post_paper_note(handler, v):
    if _ws(v) != 'research':
        raise ValueError('笔记仅适用于论文')
    if not isinstance(v.get('content'), str):
        raise ValueError('笔记内容无效')
    return domain.paper_note(v.get('id', ''), v['content'], v.get('revision'))


def post_paper_chat(handler, v):
    if _ws(v) != 'research':
        raise ValueError('问答仅适用于论文')
    if not ai_ready(settings()):
        raise ValueError('请先配置 AI 模型')
    question = v.get('message', '')
    if not isinstance(question, str) or not question.strip() or len(question) > 3000:
        raise ValueError('请输入1–3000字的问题')
    with LOCK:
        if domain.paper_chat_messages(v['id'])['pending']:
            raise ValueError('当前论文正在回复，请等待完成')
        with conn() as c:
            message_id = c.execute('INSERT INTO paper_chat(item,role,content,created) VALUES(?,?,?,?)',
                                   (v['id'], 'user', question.strip(), now())).lastrowid
    return enqueue('论文问答', lambda: domain.answer_paper_question(v['id'], message_id), 'research', v['id'])


def post_review(handler, v):
    if not ai_ready(settings(workspace=_ws(v))):
        raise ValueError('请先配置独立 AI Key，才能生成综合 Review。')
    return _pending(v['id']) or enqueue('论文综合 Review', lambda: domain.review_pipeline(v['id']), 'research', v['id'])


def post_author_metadata(handler, v):
    return _pending(v['id'], ['补充作者与单位']) or enqueue(
        '补充作者与单位', lambda: domain.refresh_author_metadata(v['id']), 'research', v['id'])


def post_citations(handler, v):
    return enqueue('更新引用', lambda: domain.citations(v['id']), 'research', v['id'])


def post_account_summary(handler, v):
    return enqueue('账号发布总结', lambda: domain.summarize_author(v['id'], _ws(v)), 'research')


def post_author_lookup(handler, v):
    if v['id'] not in {a['id'] for a in author_list('research')}:
        raise ValueError('作者不属于当前页面')
    return enqueue('检索作者身份', lambda: domain.lookup_author(v['id']), 'research')


def post_profile(handler, v):
    if v['id'] not in {a['id'] for a in author_list('research')}:
        raise ValueError('该作者不属于当前页面')
    for field in ['scholar', 'homepage', 'external']:
        if v.get(field) and not __import__('re').match(r'^https?://', v[field]):
            raise ValueError('主页必须是 HTTP/HTTPS 链接')
    with conn() as c:
        old = c.execute('SELECT * FROM profiles WHERE id=?', (v['id'],)).fetchone()
        if not v.get('verified') or any(old[k] != v.get(k, '') for k in ['homepage', 'scholar']):
            ids = [v['id']] + [r[0] for r in c.execute('SELECT alias FROM author_aliases WHERE canonical=?', (v['id'],))]
            for aid in ids:
                c.execute('DELETE FROM author_identity_links WHERE author=?', (aid,))
        c.execute('UPDATE profiles SET scholar=?,homepage=?,verified=?,affiliation=?,history=?,identity_evidence=?,education=? WHERE id=?',
                  (v.get('scholar', ''), v.get('homepage', ''), bool(v.get('verified')),
                   str(v.get('affiliation', ''))[:1000], str(v.get('history', ''))[:3000],
                   str(v.get('identity_evidence', ''))[:3000], str(v.get('education', ''))[:3000], v['id']))
    domain.reconcile_author_profiles()
    return {'ok': True}


def post_author_merge(handler, v):
    if _ws(v) != 'research':
        raise ValueError('作者合并只在 Research Paper 中可用')
    return domain.merge_authors(v)
