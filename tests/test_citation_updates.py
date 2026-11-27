import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'core'))
from projects.research.desk_research import domain as server
from projects.research.desk_research import citation_transport as transport

class CitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.sqlite3'
        def conn():
            c=sqlite3.connect(self.db,factory=server.ManagedConnection);c.row_factory=sqlite3.Row;return c
        self.conn=conn
        with conn() as c:
            c.execute("CREATE TABLE items(id TEXT,external_id TEXT,workspace TEXT DEFAULT 'research',kind TEXT DEFAULT 'paper',removed INTEGER DEFAULT 0,starred INTEGER DEFAULT 1,seen_at TEXT DEFAULT '',status TEXT DEFAULT '',citations INTEGER DEFAULT 12,citation_source TEXT DEFAULT 'old',citation_updated TEXT DEFAULT '',citation_checked TEXT DEFAULT '',citation_error TEXT DEFAULT '',citation_retry_at TEXT DEFAULT '')")
        self.patches=[patch.object(server,'conn',conn),patch.object(server,'now',return_value='2026-11-21T12:00:00+08:00'),patch.object(server,'settings',return_value={'scholar_key':''}),patch.object(server,'sync_library_references',return_value=0)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def add(self,i='a',**kw):
        data={'id':i,'external_id':'arxiv:2308.08143',**kw}
        with self.conn() as c:c.execute('INSERT INTO items('+','.join(data)+') VALUES('+','.join('?' for _ in data)+')',list(data.values()))
    def row(self):
        with self.conn() as c:return dict(c.execute('SELECT * FROM items').fetchone())
    def ids(self):return [r['id'] for r in server.citation_refresh_candidates()]
    def test_due_intervals_and_scope(self):
        self.add('new');self.add('recent',citation_checked='2026-11-20T12:00:00+08:00')
        self.add('week',citation_checked='2026-11-14T12:00:00+08:00')
        self.add('legacy_error',citation_checked='2026-11-16T12:00:00+08:00',citation_error='连接失败')
        self.add('waiting',citation_error='连接失败',citation_retry_at='2026-11-21T15:00:00+08:00')
        self.add('removed',removed=1);self.add('unread',starred=0);self.add('non_arxiv',external_id='doi:1')
        self.assertEqual(set(self.ids()),{'new','week','legacy_error'})
    def test_failure_preserves_old_count_and_retries_after_three_hours(self):
        self.add()
        with patch.object(transport,'read_batch',side_effect=transport.CitationLookupError('网络连接失败')):
            self.assertEqual(server.refresh_citation_counts()['failed'],1)
        self.assertEqual(self.row()['citations'],12);self.assertEqual(self.ids(),[])
        with patch.object(server,'now',return_value='2026-11-21T15:00:00+08:00'):self.assertEqual(self.ids(),['a'])
    def test_success_clears_failure_and_becomes_due_in_seven_days(self):
        self.add(citation_error='old failure')
        with patch.object(transport,'read_batch',return_value=[{'citationCount':37,'externalIds':{'ArXiv':'2308.08143'}}]):
            self.assertEqual(server.refresh_citation_counts()['updated'],1)
        self.assertEqual(self.row()['citations'],37);self.assertEqual(self.row()['citation_error'],'');self.assertEqual(self.ids(),[])
        with patch.object(server,'now',return_value='2026-11-28T12:00:00+08:00'):self.assertEqual(self.ids(),['a'])
    def test_missing_is_not_zero_and_rechecks_next_day(self):
        self.add()
        with patch.object(transport,'read_batch',return_value=[None]):self.assertEqual(server.refresh_citation_counts()['not_indexed'],1)
        self.assertEqual(self.row()['citations'],12);self.assertEqual(self.ids(),[])
        with patch.object(server,'now',return_value='2026-11-22T12:00:00+08:00'):self.assertEqual(self.ids(),['a'])
    def test_scheduler_enqueues_only_due_and_deduplicates_active_job(self):
        self.add()
        with patch.object(server,'JOBS',{}),patch.object(server,'enqueue',return_value={'id':'task'}) as enqueue:
            self.assertEqual(server.enqueue_citation_refresh(),{'id':'task'});enqueue.assert_called_once()
        with patch.object(server,'JOBS',{'task':{'kind':'每周引用更新','state':'running'}}),patch.object(server,'enqueue') as enqueue:
            server.enqueue_citation_refresh();enqueue.assert_not_called()
    def test_retry_connection_then_success(self):
        with patch.object(transport.urllib.request,'urlopen',side_effect=[urllib.error.URLError(ConnectionRefusedError(61,'refused')),io.BytesIO(b'[{"citationCount":0}]')]) as req,patch.object(transport.time,'sleep') as sleep:
            self.assertEqual(transport.read_batch(['ARXIV:1'])[0]['citationCount'],0)
            self.assertEqual(req.call_count,2);sleep.assert_called_once_with(2)
    def test_bounded_retries_and_safe_errors(self):
        with patch.object(transport.urllib.request,'urlopen',side_effect=urllib.error.URLError('SECRET')),patch.object(transport.time,'sleep') as sleep:
            with self.assertRaises(transport.CitationLookupError) as err:transport.read_batch(['ARXIV:1'])
            self.assertNotIn('SECRET',str(err.exception));self.assertEqual(sleep.call_count,2)
    def test_long_rate_limit_defers_without_sleeping(self):
        self.add()
        error=urllib.error.HTTPError(transport.URL,429,'rate',{'Retry-After':'14400'},io.BytesIO(b'SECRET'))
        with patch.object(transport.urllib.request,'urlopen',side_effect=error) as req,patch.object(transport.time,'sleep') as sleep:
            server.refresh_citation_counts();self.assertEqual(req.call_count,1);sleep.assert_not_called()
        self.assertEqual(self.row()['citation_retry_at'],'2026-11-21T16:00:00+08:00');self.assertNotIn('SECRET',self.row()['citation_error'])

class CitationIsolationTests(CitationTests):
    def test_manual_reference_refresh_clears_retry_state(self):
        self.add(citation_error='old failure',citation_retry_at='2026-11-22T12:00:00+08:00')
        with self.conn() as c:c.execute('CREATE TABLE edges(src TEXT,dst TEXT,relation TEXT,evidence TEXT)')
        with patch.object(server,'getjson',return_value={'citationCount':9,'references':[],'authors':[]}):
            self.assertEqual(server.citations('a')['citationCount'],9)
        self.assertEqual(self.row()['citation_retry_at'],'')
        self.assertEqual(self.row()['citation_error'],'')
    def test_single_bad_paper_does_not_block_good_paper(self):
        self.add('bad');self.add('good')
        bad=transport.CitationLookupError('引用接口返回 HTTP 400',status=400)
        with patch.object(transport,'read_batch',side_effect=[bad,bad,[{'citationCount':8}]]):
            result=server.refresh_citation_counts()
        self.assertEqual((result['updated'],result['failed']),(1,1))
        self.assertEqual(result['details'][0]['item_id'],'bad')
        with self.conn() as c:
            self.assertEqual(c.execute("SELECT citations FROM items WHERE id='bad'").fetchone()[0],12)
            self.assertEqual(c.execute("SELECT citations FROM items WHERE id='good'").fetchone()[0],8)
    def test_isolation_stops_on_rate_limit_and_retains_retry_after(self):
        self.add('bad');self.add('later')
        bad=transport.CitationLookupError('HTTP 400',status=400)
        limited=transport.CitationLookupError('HTTP 429',retry_after=14400,status=429)
        with patch.object(transport,'read_batch',side_effect=[bad,limited]) as request:
            result=server.refresh_citation_counts()
        self.assertEqual(request.call_count,2)
        self.assertEqual(result['details'][1]['status'],'deferred')
        self.assertEqual(result['details'][1]['retry_at'],'2026-11-21T16:00:00+08:00')

if __name__=='__main__':unittest.main()
