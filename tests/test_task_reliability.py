import io,json,sqlite3,sys,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'core'),str(Path(__file__).resolve().parents[1])]
from deskcore import engine
from projects.research.desk_research import domain, routes, citation_transport as transport

class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.db'
        def conn():
            c=sqlite3.connect(self.db,factory=engine.ManagedConnection);c.row_factory=sqlite3.Row;return c
        self.conn=conn;self.jobs={}
        with conn() as c:
            c.executescript("CREATE TABLE items(id TEXT,kind TEXT,workspace TEXT,summary TEXT,removed INTEGER,body TEXT,starred INTEGER,seen_at TEXT);CREATE TABLE recommendation_inbox(item TEXT);CREATE TABLE recommendation_suppressions(item TEXT);CREATE TABLE paper_work(item TEXT,kind TEXT,state TEXT,attempts INTEGER DEFAULT 0,updated TEXT,retry_at TEXT DEFAULT '',error TEXT DEFAULT '',PRIMARY KEY(item,kind));")
            c.execute("INSERT INTO items VALUES('new','paper','research',NULL,0,'abstract',1,'')")
        self.patches=[patch.object(domain,'conn',conn),patch.object(domain,'JOBS',self.jobs),patch.object(domain,'settings',return_value={'auto_review':True}),patch.object(domain,'ai_ready',return_value=True),patch.object(domain,'queue_signature'),patch.object(domain.ENRICH,'record')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_author_task_does_not_block_review_and_recovery_is_idempotent(self):
        self.jobs['author']={'item_id':'new','kind':'补全作者资料','state':'running'}
        self.assertIs(engine.recover_missing_paper_work,domain.recover_missing_paper_work)
        engine.recover_missing_paper_work();engine.recover_missing_paper_work()
        with self.conn() as c:
            rows=c.execute("SELECT * FROM paper_work WHERE kind='review'").fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['state'],'queued')
    def test_failed_review_is_not_mass_retried(self):
        with self.conn() as c:c.execute("INSERT INTO paper_work(item,kind,state,attempts,updated) VALUES('new','review','error',3,'old')")
        domain.recover_missing_paper_work()
        with self.conn() as c:self.assertEqual(c.execute('SELECT state FROM paper_work').fetchone()[0],'error')
    def test_disabled_auto_review_does_not_queue(self):
        with patch.object(domain,'settings',return_value={'auto_review':False}):domain.recover_missing_paper_work()
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM paper_work').fetchone()[0],0)
    def test_manual_review_only_deduplicates_reviews(self):
        with patch.object(routes,'ai_ready',return_value=True),patch.object(routes,'settings',return_value={}),patch.object(routes,'JOBS',{'author':{'item_id':'new','kind':'补全作者资料','state':'running'}}),patch.object(routes,'enqueue',return_value={'id':'review'}) as enqueue:
            self.assertEqual(routes.post_review(None,{'id':'new'}),{'id':'review'});enqueue.assert_called_once()

class CitationResponseTests(unittest.TestCase):
    def test_exact_not_found_response_is_missing_not_zero(self):
        e=urllib.error.HTTPError(transport.URL,400,'bad',{},io.BytesIO(b'{"error":"No valid paper ids given"}'))
        with patch.object(transport.urllib.request,'urlopen',side_effect=e):self.assertEqual(transport.read_batch(['ARXIV:2610.26233']),[None])
    def test_other_400_is_not_silently_missing_or_leaked(self):
        e=urllib.error.HTTPError(transport.URL,400,'bad',{},io.BytesIO(b'{"error":"SECRET"}'))
        with patch.object(transport.urllib.request,'urlopen',side_effect=e):
            with self.assertRaises(transport.CitationLookupError) as caught:transport.read_batch(['ARXIV:1'])
        self.assertEqual(caught.exception.status,400);self.assertNotIn('SECRET',str(caught.exception))

class TaskDetailTests(unittest.TestCase):
    def test_details_survive_restart_without_raw_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'db'
            def conn():
                c=sqlite3.connect(path,factory=engine.ManagedConnection);c.row_factory=sqlite3.Row;return c
            with conn() as c:
                c.executescript("CREATE TABLE app_meta(key TEXT PRIMARY KEY,value TEXT);CREATE TABLE items(id TEXT,title TEXT,workspace TEXT);CREATE TABLE paper_work(updated TEXT);INSERT INTO items VALUES('p','Paper title','research');")
            job={'id':'j','kind':'每周引用更新','state':'error','started':'2026-11-26T12:00:00+08:00','message':'one failed','workspace':'research','result':{'api_key':'SECRET','details':[{'item_id':'p','status':'error','reason':'HTTP 400','raw':'SECRET'}]}}
            with patch.object(engine,'conn',conn),patch.object(engine,'JOBS',{}):
                engine.persist_citation_task(job);output=engine.task_center()
            self.assertNotIn('SECRET',json.dumps(output));self.assertEqual(output['jobs'][0]['details'][0]['title'],'Paper title')

if __name__=='__main__':unittest.main()
