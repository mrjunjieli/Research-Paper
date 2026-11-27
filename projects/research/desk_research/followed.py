"""收藏的作者：只看身份已经核实过的作者，每 7 天查一次他们的新论文。

新论文按普通条目存进论文库（来源记为“收藏的作者”），并进入每日推荐的独立栏目，
不占用每日 50 篇的配额。优先读作者自己的 Google Scholar 主页（按发表日期排序），
取不到时退回 arXiv 作者检索；两种结果都要求作者名出现在作者列表里，避免同名误收。
"""
import datetime as dt
import html
import json
import re
import urllib.parse
import uuid
from deskcore.engine import publication_window_reason

WEEK_DAYS = 7
GROUP = 'followed'
SOURCE_ID = 'followed-authors'
SOURCE_NAME = '我收藏的作者'
MAX_PAPERS_PER_AUTHOR = 30
SCHOLAR_PAGE = 'https://scholar.google.com/citations?hl=en&sortby=pubdate&pagesize=20&user='
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'


def init(desk):
    with desk.conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS author_follows(
          author TEXT PRIMARY KEY, note TEXT NOT NULL DEFAULT '',
          created TEXT NOT NULL, updated TEXT NOT NULL,
          last_checked TEXT NOT NULL DEFAULT '', last_found TEXT NOT NULL DEFAULT '',
          last_status TEXT NOT NULL DEFAULT '', last_message TEXT NOT NULL DEFAULT '')''')
        columns = {r[1] for r in c.execute('PRAGMA table_info(profiles)')}
        if 'notes' not in columns:
            c.execute("ALTER TABLE profiles ADD COLUMN notes TEXT NOT NULL DEFAULT ''")   # 作者页里的手动注释
        c.execute("INSERT OR IGNORE INTO sources(id,name,type,query,kind,workspace,source_group,enabled) VALUES(?,?,?,?,?,?,?,1)",
                  (SOURCE_ID, SOURCE_NAME, 'followed', 'followed', 'paper', 'research', GROUP))


def follow_map(desk):
    with desk.conn() as c:
        return {r['author']: dict(r) for r in c.execute('SELECT * FROM author_follows')}


def _profile(desk, author_id):
    with desk.conn() as c:
        row = c.execute('SELECT * FROM profiles WHERE id=?', (author_id,)).fetchone()
    return dict(row) if row else None


def canonical(desk, author_id):
    return desk.resolve_author_alias(author_id)


def read(desk):
    """收藏页数据：每位作者 + 他已经进入论文库的论文。

    只列论文库里的（收藏、看过或标为读过），不列这位作者在本地缓存里的全部论文：
    一位高产作者会把页面塞满。想看全部就去 Google Scholar。
    """
    followed = follow_map(desk)
    library = [i for i in desk.items('research') if i['kind'] == 'paper' and not i['removed'] and desk.is_library_paper(i)]
    rows = []
    for author_id, follow in followed.items():
        profile = _profile(desk, author_id) or {'id': author_id, 'name': author_id, 'verified': 0}
        papers = [p for p in library if any(a['id'] == author_id for a in p['authors'])]
        papers.sort(key=lambda p: (p.get('published') or '', p['id']), reverse=True)
        rows.append({
            'id': author_id, 'name': profile.get('name', ''), 'verified': bool(profile.get('verified')),
            'affiliation': profile.get('affiliation', ''), 'scholar': profile.get('scholar', ''),
            'homepage': profile.get('homepage', ''), 'notes': profile.get('notes', ''),
            'note': follow['note'], 'followed_at': follow['created'],
            'last_checked': follow['last_checked'], 'last_found': follow['last_found'],
            'last_status': follow['last_status'], 'last_message': follow['last_message'],
            'papers': [{'id': p['id'], 'title': p['title'], 'published': p['published'], 'url': p['url'],
                        'starred': bool(p['starred']), 'coverage': p['coverage'], 'citations': p['citations']}
                       for p in papers[:60]],
            'paper_total': len(papers),
        })
    rows.sort(key=lambda r: (r['last_checked'] or '', r['name'].casefold()))
    return {'authors': rows, 'due': due(desk), 'week_days': WEEK_DAYS, 'source_id': SOURCE_ID}


def days_since(stamp, current=None):
    if not stamp:
        return 10 ** 6
    try:
        return ((dt.datetime.fromisoformat(current) if current else dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))) - dt.datetime.fromisoformat(stamp)).total_seconds()/86400
    except (TypeError, ValueError):
        return 10 ** 6


def save(desk, data):
    action = data.get('action', 'follow')
    author_id = canonical(desk, str(data.get('id') or ''))
    if not author_id:
        raise ValueError('请选择作者')
    if action == 'unfollow':
        with desk.conn() as c:
            c.execute('DELETE FROM author_follows WHERE author=?', (author_id,))
        return read(desk)
    if action == 'note':
        note = str(data.get('note') or '')[:2000]
        if author_id not in follow_map(desk):
            raise ValueError('先收藏这位作者，再写备注')
        with desk.conn() as c:
            c.execute('UPDATE author_follows SET note=?,updated=? WHERE author=?', (note, desk.now(), author_id))
        return read(desk)
    if action == 'profile':
        # 作者资料里的手动注释（所有人可写），与收藏备注分开。
        notes = str(data.get('notes') or '')[:4000]
        with desk.conn() as c:
            c.execute('UPDATE profiles SET notes=? WHERE id=?', (notes, author_id))
        return read(desk)
    if action != 'follow':
        raise ValueError('操作无效')
    profile = _profile(desk, author_id)
    if not profile:
        raise ValueError('作者不存在')
    if not profile.get('verified'):
        raise ValueError('只有身份已核实的作者才能收藏；先点“检索作者身份”确认身份')
    with desk.conn() as c:
        c.execute("INSERT OR IGNORE INTO author_follows(author,note,created,updated) VALUES(?,?,?,?)",
                  (author_id, str(data.get('note') or '')[:2000], desk.now(), desk.now()))
    return read(desk)


# ---------------- 每周检查 ----------------

def _clean(text):
    return ' '.join(re.sub(r'<[^>]+>', ' ', html.unescape(str(text or ''))).split())


def scholar_recent(desk, scholar_url, after=None):
    """读作者 Scholar 主页（按时间排序）的最近条目。只取标题和年份，链接再回 arXiv 找。"""
    match = re.search(r'[?&]user=([A-Za-z0-9_-]{5,40})', scholar_url or '')
    if not match:
        return []
    raw = desk.fetch(SCHOLAR_PAGE + match.group(1), None, {'User-Agent': UA, 'Accept-Language': 'en'}).decode('utf-8', 'replace')
    rows = re.findall(r'<tr class="gsc_a_tr">(.*?)</tr>', raw, re.S)
    if not rows and 'gsc_a_tr' not in raw:
        raise ValueError('Google Scholar 主页暂时读不到（可能需要验证或访问被限制）')
    out = []
    for row in rows[:MAX_PAPERS_PER_AUTHOR]:
        title = _clean(re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', row, re.S).group(1)) if re.search(r'class="gsc_a_at"[^>]*>(.*?)</a>', row, re.S) else ''
        year = re.search(r'class="gsc_a_h[^"]*"[^>]*>(\d{4})<', row)
        if not title or len(title) < 8:
            continue
        # A year alone cannot prove that a paper was published this week.
        # Use it only to avoid matching obviously older Scholar entries.
        if after and year and int(year.group(1))<after.year:
            continue
        out.append({'title': title, 'year': int(year.group(1)) if year else None, 'source': 'Google Scholar'})
    return out


def arxiv_recent(desk, name, page_size=MAX_PAPERS_PER_AUTHOR):
    """arXiv 作者检索。失败时抛错，让这次检查记为 error 并尽快重试，而不是假装“没有新论文”。"""
    end=dt.datetime.fromisoformat(desk.now()).astimezone(dt.timezone.utc)
    start=end-dt.timedelta(days=WEEK_DAYS)
    query = '(au:"%s") AND submittedDate:[%s TO %s]' % (name.replace('"', ''),start.strftime('%Y%m%d%H%M'),end.strftime('%Y%m%d%H%M'))
    return desk.arxiv(query=query, page_size=page_size)


def _same_title(a, b):
    key = lambda s: re.sub(r'[^a-z0-9]+', ' ', str(s or '').casefold()).strip()
    return key(a) and key(a) == key(b)


def _person_name(person):
    if isinstance(person, dict):
        return str(person.get('name') or person.get('id') or '')
    return str(person or '')


def _has_author(entry, name):
    """arXiv 结果的 authors 可能是字符串，也可能是 {id,name} 字典，两种都要认。"""
    parts = [p for p in re.split(r'[\s,]+', str(name or '')) if p]
    if not parts:
        return False
    people = entry.get('authors') or []
    if not isinstance(people, list):
        people = [people]
    # Tokens must belong to one person, never two different coauthors.
    return any(all(p.casefold() in re.findall(r'\w+',_person_name(person).casefold()) for p in parts) for person in people)


def check(desk, author_ids=None, force=False):
    """给收藏的作者找新论文。返回每位作者的结果，新增的论文进入论文库与每日推荐。"""
    followed = follow_map(desk)
    targets = [a for a in followed if not author_ids or a in author_ids]
    results = []
    for author_id in targets:
        follow = followed[author_id]
        profile = _profile(desk, author_id) or {}
        name = profile.get('name', '')
        status, message, added, scholar_note = 'ok', '', [], ''
        skipped={'old_or_undated':0,'duplicate':0,'author_mismatch':0,'scholar_mismatch':0}
        stamp=desk.now()
        end=dt.datetime.fromisoformat(stamp);start=end-dt.timedelta(days=WEEK_DAYS)
        run_id='follow:'+uuid.uuid4().hex
        with desk.conn() as c:
            c.execute('INSERT INTO collection_runs(id,source_id,source_name,started,state,window_start,window_end) VALUES(?,?,?,?,?,?,?)',
                      (run_id,'follow:'+author_id,'关注的作者 · '+name,stamp,'running',start.isoformat(),end.isoformat()))
        try:
            if not profile.get('verified') or not name:
                raise ValueError('作者身份尚未核实，暂停自动推荐')
            self_entries = []
            if profile.get('scholar'):
                try:
                    self_entries = scholar_recent(desk, profile['scholar'],after=start)
                except Exception as exc:
                    # Scholar 读不到（访问受限或需要验证）不算失败，退回 arXiv 作者检索。
                    scholar_note = 'Google Scholar 暂时读不到（' + type(exc).__name__ + '），已改用 arXiv 作者检索'
            seen = [{w for w in re.sub(r'[^a-z0-9]+', ' ', e['title'].casefold()).split() if len(w) > 2} for e in self_entries]
            # Scholar is an identity/source signal, not evidence of indexing date.
            # arXiv's original publication date is checked before storage and admission.
            arxiv_entries = arxiv_recent(desk, name) if name else []
            if self_entries and not arxiv_entries:
                status = 'partial'
                message = 'Scholar 列表含 %d 条待核验记录；arXiv 最近7天未检索到可核验的新论文。列表记录不等于本周新发表。' % len(self_entries)
            if scholar_note:
                status, message = 'partial', scholar_note
            picked = [e for e in arxiv_entries if _has_author(e, name)]
            skipped['author_mismatch']=len(arxiv_entries)-len(picked)
            if self_entries:
                def known_to_scholar(title):
                    # Scholar 的标题常被截断或少了几个词，按词的重合度判断是否同一条。
                    words = {w for w in re.sub(r'[^a-z0-9]+', ' ', title.casefold()).split() if len(w) > 2}
                    if not words:
                        return False
                    for other in seen:
                        shared = len(words & other)
                        if shared / len(words) >= 0.6 and shared / max(1,len(other)) >= 0.6:
                            return True
                    return False
                matched=[e for e in picked if known_to_scholar(e['title'])]
                skipped['scholar_mismatch']=len(picked)-len(matched)
                picked=matched
            if not self_entries and not scholar_note:
                status='partial'
                message='Scholar 未提供可核验的条目，使用 arXiv 原始发表日期检查近7天新论文'
            for entry in picked[:MAX_PAPERS_PER_AUTHOR]:
                if publication_window_reason(entry.get('published'),stamp):
                    skipped['old_or_undated']+=1
                    continue
                # 作者 id 必须用档案里的 id（可能是学术索引 id），否则论文和作者页对不上。
                authors = []
                for person in entry.get('authors') or []:
                    label = person if isinstance(person, str) else person.get('name', '')
                    if label and label.strip().casefold() == name.strip().casefold():
                        authors.append({'id': author_id, 'name': name})
                    else:
                        authors.append(person)
                iid, new = desk.add_item({**entry, 'authors': authors, 'workspace': 'research', 'kind': 'paper',
                                          'source': '收藏的作者 · ' + name, 'source_id': 'follow:' + author_id,
                                          'source_group': GROUP,'_collection_run':run_id})
                if new:
                    added.append({'id': iid, 'title': entry.get('title', '')})
                else:skipped['duplicate']+=1
        except Exception as exc:
            status = 'error'
            message = ('检查出错（' + type(exc).__name__ + '）：' + str(exc))[:300]
        stamp = desk.now()
        summary='近7天新增 %d 篇；历史重复 %d 篇；旧文或日期不明 %d 篇。' % (len(added),skipped['duplicate'],skipped['old_or_undated'])
        message=summary+message
        with desk.conn() as c:
            # 出错时不推进“上次检查”，否则要白等一周；下次打开页面仍会显示待检查。
            c.execute('UPDATE author_follows SET last_checked=CASE WHEN ? THEN ? ELSE last_checked END,last_found=?,last_status=?,last_message=?,updated=? WHERE author=?',
                      (int(status != 'error'), stamp, added[0]['title'] if added else follow['last_found'], status, message, stamp, author_id))
            c.execute('UPDATE collection_runs SET finished=?,state=?,error=? WHERE id=?',(stamp,status,message if status!='ok' else '',run_id))
        results.append({'id': author_id, 'name': name, 'status': status, 'message': message,
                        'added': added, 'checked': stamp,'skipped':skipped,'window_start':start.isoformat(),'window_end':end.isoformat()})
    # 立刻按独立配额准入每日推荐，并排队生成 Review，不必等到明天的每日采集。
    try:
        admitted = desk.daily_recommendations(admit_during_collection=True)
        fresh = [i['id'] for i in admitted.get('items', []) if i.get('daily_group') == GROUP]
        if fresh:
            desk.queue_collected_reviews(fresh)
    except Exception as exc:
        results.append({'id': '', 'name': '排入每日推荐', 'status': 'error', 'message': str(exc)[:200], 'added': [], 'checked': desk.now()})
    with desk.conn() as c:
        errors=[r['message'] for r in results if r['status']=='error']
        state='error' if errors and len(errors)==len(results) else 'partial' if any(r['status']!='ok' for r in results) else 'done'
        c.execute("UPDATE sources SET refreshed=?,last_status=?,last_added=?,last_received=?,error=? WHERE id=?",
                  (desk.now(), state, sum(len(r['added']) for r in results), len(results),'; '.join(errors)[:600], SOURCE_ID))
    total=sum(len(r['added']) for r in results)
    return {'authors': results, 'added': total, 'failed':len(errors),
            'message':'关注作者检查：新增 %d 篇。'%total+'；'.join(r['name']+'：'+r['message'] for r in results)}


def due(desk):
    return [a for a, f in follow_map(desk).items() if days_since(f['last_checked'],desk.now()) >= WEEK_DAYS
            and (f['last_status']!='error' or days_since(f['updated'],desk.now())>=3/24)]


def failed(desk):
    """上次检查出错、需要重试的作者（不等到下一个七天）。"""
    return [a for a, f in follow_map(desk).items() if f['last_status'] == 'error']


def withdraw_invalid_admissions(desk):
    """Repair legacy author deliveries without deleting papers, notes or history.

    Test freshness at ORIGINAL delivery time, not today: valid unread recommendations
    must not disappear merely because a week passed after delivery.
    """
    withdrawn=[]
    with desk.conn() as c:
        c.execute('BEGIN IMMEDIATE')
        rows=c.execute('SELECT r.*,i.title,i.published,i.external_id,i.url FROM recommendation_inbox r JOIN items i ON i.id=r.item ORDER BY r.recommended_date,i.added,r.item').fetchall()
        seen=set()
        for row in rows:
            keys=set(desk.collection_keys(row['title'],row['external_id'],row['url']))
            reason=''
            if row['source_group']==GROUP:
                reason=publication_window_reason(row['published'],row['recommended_date']+'T23:59:59+08:00')
                if not reason and keys & seen:reason='同一论文已在历史推荐出现'
            if reason:
                c.execute('INSERT OR IGNORE INTO recommendation_suppressions VALUES(?,?,?)',(row['item'],reason,desk.now()))
                withdrawn.append({'id':row['item'],'title':row['title'],'reason':reason})
            seen.update(keys)
    return withdrawn
