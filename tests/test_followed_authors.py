import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))

from deskcore import engine
from deskcore.engine import ManagedConnection
from projects.research.desk_research import followed

SCHOLAR_HTML = b'''<table><tr class="gsc_a_tr"><td><a class="gsc_a_at" href="#">Example acoustic model for timestamped audio captions</a>
<div class="gs_gray">M Shi, A Other</div><div class="gs_gray">arXiv, 2026</div></td><td><span class="gsc_a_h">2026</span></td></tr>
<tr class="gsc_a_tr"><td><a class="gsc_a_at" href="#">A second new paper</a><div class="gs_gray">M Shi</div></td>
<td><span class="gsc_a_h">2026</span></td></tr></table>'''


def arxiv_entry(title, names):
    # 真实 deskcore.arxiv 返回的是 {id,name} 字典，这里按真实结构构造。
    return {'kind': 'paper', 'title': title, 'url': 'https://arxiv.org/abs/2611.0000' + str(len(title)),
            'external_id': 'arxiv:2611.' + str(abs(hash(title)) % 100000).zfill(5), 'published': '2026-11-25T00:00:00Z',
            'body': 'We propose a method and evaluate it with experiments. ' * 8, 'coverage': 'abstract',
            'authors': [{'id': 'name:' + n, 'name': n} for n in names], 'source': 'arXiv'}


class FollowedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'f.db'
        self.fetched = []
        self.entries = [arxiv_entry('Example acoustic model for timestamped audio captions', ['Alex Example', 'Someone Else']),
                        arxiv_entry('A second new paper about diarization', ['Alex Example']),
                        arxiv_entry('Unrelated paper by another Alex', ['Other Person'])]

        def conn():
            c = sqlite3.connect(self.db, factory=ManagedConnection)
            c.row_factory = sqlite3.Row
            return c

        def fetch(url, payload=None, headers=None, limit=0):
            self.fetched.append(url)
            return SCHOLAR_HTML

        def add_item(v):
            iid = 'i' + str(abs(hash(v['title'])) % 10 ** 8)
            with conn() as c:
                if c.execute('SELECT 1 FROM items WHERE id=?', (iid,)).fetchone():
                    return iid, False
                c.execute('INSERT INTO items(id,kind,title,url,published,added,body,coverage,source,authors,tags,workspace,removed,starred,seen_at,status,citations,external_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (iid, v['kind'], v['title'], v['url'], v['published'], '2026-11-26T12:00:00+08:00', v['body'], v['coverage'],
                           v['source'], json.dumps(v['authors']), '[]', 'research', 0, 0, '', 'unread', None, v['external_id']))
                c.execute('INSERT OR REPLACE INTO discoveries VALUES(?,?,?,?,?)', (iid, v.get('source_id', ''), v['source'], v.get('source_group', 'manual'), '2026-11-26T12:00:00+08:00'))
            return iid, True

        def items(workspace=None):
            with conn() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM items WHERE workspace=?", (workspace,))]
            for r in rows:
                r['authors'] = json.loads(r['authors'] or '[]')
                r.setdefault('published', '')
            return rows

        self.desk = SimpleNamespace(
            conn=conn, now=lambda: '2026-11-26T12:00:00+08:00', fetch=fetch,
            items=items, is_library_paper=engine.is_library_paper, add_item=add_item,
            resolve_author_alias=lambda a: a,
            arxiv=lambda query='', ids='', start=0, page_size=None: list(self.entries),
        )
        engine.DB = self.db
        with conn() as c:
            c.execute('CREATE TABLE items(id TEXT PRIMARY KEY, kind TEXT, title TEXT, url TEXT, published TEXT, added TEXT, body TEXT, coverage TEXT, source TEXT, authors TEXT, tags TEXT, workspace TEXT, removed INTEGER, starred INTEGER, seen_at TEXT, status TEXT, citations INTEGER, summary TEXT, external_id TEXT)')
            c.execute('CREATE TABLE discoveries(item TEXT, source_id TEXT, name TEXT, source_group TEXT, found TEXT, PRIMARY KEY(item,source_id))')
            c.execute('CREATE TABLE profiles(id TEXT PRIMARY KEY, name TEXT, scholar TEXT, homepage TEXT, external TEXT, verified INTEGER, affiliation TEXT, history TEXT, identity_evidence TEXT, candidates TEXT, education TEXT)')
            c.execute('CREATE TABLE sources(id TEXT PRIMARY KEY,name TEXT,type TEXT,query TEXT,kind TEXT,workspace TEXT,source_group TEXT,enabled INTEGER,refreshed TEXT,last_status TEXT,last_added INTEGER,last_received INTEGER,error TEXT,last_attempt TEXT)')
            c.execute("INSERT INTO profiles(id,name,scholar,verified,affiliation) VALUES('s2:1','Alex Example','https://scholar.google.com/citations?user=AB12cd34EF',1,'Example University')")
            c.execute("INSERT INTO profiles(id,name,scholar,verified,affiliation) VALUES('s2:2','Unverified Person','',0,'')")
        with conn() as c:c.execute('CREATE TABLE collection_runs(id TEXT PRIMARY KEY,source_id TEXT,source_name TEXT,started TEXT,finished TEXT,state TEXT,window_start TEXT,window_end TEXT,error TEXT)')
        followed.init(self.desk)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_verified_authors_can_be_followed(self):
        with self.assertRaises(ValueError):
            followed.save(self.desk, {'action': 'follow', 'id': 's2:2'})
        out = followed.save(self.desk, {'action': 'follow', 'id': 's2:1', 'note': '语音方向，读得很仔细'})
        self.assertEqual([a['id'] for a in out['authors']], ['s2:1'])
        self.assertEqual(out['authors'][0]['note'], '语音方向，读得很仔细')

    def test_checks_scholar_then_arxiv_and_keeps_only_this_author(self):
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        out = followed.check(self.desk)
        self.assertTrue(any('scholar.google.com' in u for u in self.fetched), 'scholar page is read first')
        titles = [a['title'] for a in out['authors'][0]['added']]
        self.assertIn('Example acoustic model for timestamped audio captions', titles)
        self.assertNotIn('Unrelated paper by another Alex', titles, 'same-name papers are not collected')
        with self.desk.conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM discoveries')]
            items = {r['id']: dict(r) for r in c.execute('SELECT * FROM items')}
        self.assertTrue(rows and all(r['source_group'] == 'followed' and r['source_id'] == 'follow:s2:1' for r in rows))
        self.assertTrue(all('收藏的作者 · Alex Example' == i['source'] for i in items.values()))

    def test_only_papers_in_the_library_are_listed(self):
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        followed.check(self.desk)
        self.assertEqual(followed.read(self.desk)['authors'][0]['papers'], [], 'collected but not saved papers stay out')
        with self.desk.conn() as c:
            c.execute("UPDATE items SET starred=1")
        listed = followed.read(self.desk)['authors'][0]['papers']
        self.assertEqual(sorted(p['title'] for p in listed),
                         ['A second new paper about diarization', 'Example acoustic model for timestamped audio captions'])
        self.assertTrue(all(p['starred'] for p in listed))

    def test_already_collected_papers_are_not_added_twice(self):
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        followed.check(self.desk)
        again = followed.check(self.desk)
        self.assertEqual(again['added'], 0)

    def test_scholar_failure_falls_back_to_arxiv(self):
        def boom(*_a, **_k):
            raise ValueError('blocked')
        self.desk.fetch = boom
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        out = followed.check(self.desk)
        self.assertEqual(out['authors'][0]['status'], 'partial', 'Scholar failure is reported, not hidden')
        self.assertIn('arXiv', out['authors'][0]['message'])
        self.assertTrue(out['authors'][0]['added'], 'arXiv still finds the papers')

    def test_errors_do_not_postpone_the_next_check(self):
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        def broken(*_a, **_k):
            raise ValueError('blocked')
        self.desk.arxiv = broken
        out = followed.check(self.desk)
        self.assertEqual(out['authors'][0]['status'], 'error')
        state = followed.read(self.desk)
        self.assertEqual(state['authors'][0]['last_checked'], '', 'last_checked stays empty so it retries soon')
        self.assertNotIn('s2:1', state['due'], 'failures wait three hours instead of hammering every 30 seconds')
        self.desk.now=lambda:'2026-11-26T15:00:01+08:00'
        self.assertIn('s2:1', followed.due(self.desk))

    def test_weekly_due_and_note_editing(self):
        followed.save(self.desk, {'action': 'follow', 'id': 's2:1'})
        self.assertEqual(followed.read(self.desk)['due'], ['s2:1'], 'never checked means due')
        followed.check(self.desk)
        self.assertEqual(followed.read(self.desk)['due'], [], 'fresh check is not due for 7 days')
        followed.save(self.desk, {'action': 'note', 'id': 's2:1', 'note': '改过'})
        self.assertEqual(followed.read(self.desk)['authors'][0]['note'], '改过')
        followed.save(self.desk, {'action': 'profile', 'id': 's2:1', 'notes': '手动备注：同事'})
        with self.desk.conn() as c:
            self.assertEqual(c.execute("SELECT notes FROM profiles WHERE id='s2:1'").fetchone()[0], '手动备注：同事')
        followed.save(self.desk, {'action': 'unfollow', 'id': 's2:1'})
        self.assertEqual(followed.read(self.desk)['authors'], [])

    def test_followed_papers_get_their_own_recommendation_budget(self):
        item = {'kind': 'paper', 'title': 'A followed author paper about captions', 'body': 'method and experiments ' * 20,
                'published': '2026-11-26T00:00:00+08:00', 'removed': 0, 'starred': 0, 'seen_at': '', 'coverage': 'abstract'}
        assessment = engine.assess_candidate({**item, 'discoveries': [{'source_group': 'followed', 'name': '收藏的作者 · Alex Example'}]},
                                             {'interest_topics': '声学', 'auto_screen': True})
        self.assertTrue(assessment['eligible'])
        self.assertEqual(assessment['group'], 'followed')
        self.assertIn('Alex Example', assessment['reason'])


if __name__ == '__main__':
    unittest.main()
