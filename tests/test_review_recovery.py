import sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'core'),str(ROOT)]
from projects.research.desk_research import domain

class ReviewRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.db'
        def conn():
            c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row;return c
        self.conn=conn
        with conn() as c:
            c.executescript("CREATE TABLE items(id TEXT,summary TEXT);CREATE TABLE paper_work(item TEXT,kind TEXT,state TEXT,updated TEXT,retry_at TEXT,error TEXT);")
            c.executemany('INSERT INTO items VALUES(?,?)',[('target','{"report_sections":[{"part":1}]}'),('other',None)])
            c.executemany('INSERT INTO paper_work VALUES(?,?,?,?,?,?)',[(i,k,'error','old','later','connection failed') for i,k in [('target','review'),('target','authors'),('other','review')]])
        self.jobs={'old':{'item_id':'target','kind':'论文综合 Review','state':'error'},'current':{'item_id':'target','kind':'论文综合 Review','state':'running'},'author':{'item_id':'target','kind':'补全作者资料','state':'error'},'other':{'item_id':'other','kind':'论文综合 Review','state':'error'}}
        self.patches=[patch.object(domain,'conn',conn),patch.object(domain,'JOBS',self.jobs)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def test_success_clears_only_same_paper_review_failure(self):
        self.assertTrue(domain.complete_review_work('target'))
        with self.conn() as c:
            row=c.execute("SELECT * FROM paper_work WHERE item='target' AND kind='review'").fetchone()
            self.assertEqual((row['state'],row['error'],row['retry_at']),('done','',''))
            self.assertEqual(c.execute("SELECT count(*) FROM paper_work WHERE state='error'").fetchone()[0],2)
        self.assertEqual(self.jobs['old']['state'],'done')
        self.assertEqual(self.jobs['current']['state'],'running')
        self.assertEqual(self.jobs['author']['state'],'error')
        self.assertEqual(self.jobs['other']['state'],'error')
        self.assertTrue(domain.complete_review_work('target'))
    def test_no_saved_report_keeps_failure_visible(self):
        self.assertFalse(domain.complete_review_work('other'))
        self.assertEqual(self.jobs['other']['state'],'error')
        self.assertFalse(domain.complete_review_work('missing'))

if __name__=='__main__':unittest.main()
