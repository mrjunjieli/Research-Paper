"""End-to-end admission checks against an isolated real database (no network/model)."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'core'),str(Path(__file__).resolve().parents[1])]
from deskcore import engine
from projects.research.desk_research import followed

STAMP='2026-11-27T12:00:00+08:00'
def paper(title='Recent acoustic method with experiments',ext='arxiv:2611.12345',published='2026-11-26T12:00:00Z',group='followed'):
    return dict(kind='paper',workspace='research',title=title,external_id=ext,url='https://arxiv.org/abs/'+ext.removeprefix('arxiv:'),published=published,body='We propose an acoustic method and evaluate results. '*10,coverage='abstract',authors=[{'id':'a','name':'Alex Example'}],source='Followed author' if group=='followed' else 'Daily arXiv',source_id='follow:a' if group=='followed' else 'daily',source_group=group)

class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        cfg={'interest_examples':{},'daily_limit':50,'hot_limit':10,'followed_limit':20,'auto_screen':False,'interest_topics':'声学','api_key':'','ai_engine':'api'}
        self.patches=[patch.object(engine,'DB',root/'desk.sqlite3'),patch.object(engine,'DATA',root),patch.object(engine,'CONFIG',root/'config.json'),patch.object(engine,'now',return_value=STAMP),patch.object(engine,'recommendation_config',return_value=cfg),patch.object(engine,'ai_ready',return_value=False),patch.object(engine.DELIVERY,'history',return_value=[{}]),patch.object(engine,'queue_collected_reviews')]
        for p in self.patches:
            p.start();self.addCleanup(p.stop)
        engine.init();self.desk=engine.enrichment_desk()
        followed.init(self.desk)
        with engine.conn() as c:c.execute("INSERT INTO profiles(id,name,verified,scholar) VALUES('a','Alex Example',1,'https://scholar.google.com/citations?user=abcdefg')")
        followed.save(self.desk,{'id':'a'})
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def check(self,entries):
        self.desk.arxiv=lambda **kw:entries
        with patch.object(followed,'scholar_recent',return_value=[]):return followed.check(self.desk,['a'])
    def test_first_follow_rejects_old_unknown_future_and_keeps_recent(self):
        entries=[paper(),paper('Very old acoustic paper',ext='arxiv:2211.12345',published='2022-11-01T00:00:00Z'),paper('Missing exact date',ext='arxiv:2611.10001',published='2026'),paper('Future acoustic paper',ext='arxiv:2611.10002',published='2026-11-28T00:00:00Z')]
        out=self.check(entries)
        self.assertEqual(out['added'],1);self.assertEqual(out['authors'][0]['skipped']['old_or_undated'],3)
        with engine.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)
    def test_date_window_boundaries_and_timezones(self):
        f=engine.publication_window_reason
        self.assertFalse(f('2026-11-20T04:00:00Z',STAMP))
        for s in ['2026-11-20T03:59:59Z','2026-11-27T04:00:01Z','2026','2026-11','',None]:self.assertTrue(f(s,STAMP),s)
    def test_arxiv_query_is_bounded_to_original_submission_week(self):
        with patch.object(self.desk,'arxiv',return_value=[]) as arxiv:followed.arxiv_recent(self.desk,'Alex Example')
        self.assertIn('submittedDate:[202611200400 TO 202611270400]',arxiv.call_args.kwargs['query'])
    def test_daily_history_same_id_new_version_does_not_change_source_or_report(self):
        iid,_=engine.add_item(paper(group='field'))
        with engine.conn() as c:c.execute('UPDATE items SET summary=?,removed=1 WHERE id=?',(json.dumps({'kept':True}),iid))
        out=self.check([paper('A changed title for the same paper',ext='arxiv:2611.12345v2')])
        self.assertEqual(out['added'],0);self.assertEqual(out['authors'][0]['skipped']['duplicate'],1)
        with engine.conn() as c:
            self.assertEqual(c.execute('SELECT source_group FROM discoveries WHERE item=?',(iid,)).fetchone()[0],'field')
            self.assertEqual(json.loads(c.execute('SELECT summary FROM items WHERE id=?',(iid,)).fetchone()[0]),{'kept':True})
            self.assertEqual(c.execute('SELECT outcome FROM collection_events').fetchone()[0],'duplicate')
        self.assertEqual(engine.daily_recommendations()['items'],[])
    def test_deleted_item_is_still_blocked_by_permanent_history(self):
        iid,_=engine.add_item(paper(group='hot'))
        with engine.conn() as c:c.execute('DELETE FROM items WHERE id=?',(iid,))
        out=self.check([paper()]);self.assertEqual(out['added'],0)
        with engine.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],0)
    def test_normalized_title_across_different_links_is_duplicate(self):
        engine.add_item(paper('Acoustic: Voice & Speech Models',ext='doi:10.1000/abc',group='hot'))
        self.assertEqual(self.check([paper('ACOUSTIC Voice Speech Models')])['added'],0)
    def test_author_tokens_cannot_be_split_between_coauthors(self):
        self.assertFalse(followed._has_author({'authors':['Alex Jones','Alice Example']},'Alex Example'))
    def test_second_admission_gate_rejects_old_followed_paper(self):
        engine.add_item(paper(published='2022-11-01T00:00:00Z'))
        self.assertEqual(engine.daily_recommendations()['items'],[])
    def test_cleanup_preserves_library_and_ledger_and_valid_old_backlog(self):
        old,_=engine.add_item(paper('Old incorrectly delivered paper',published='2022-11-01T00:00:00Z'))
        valid,_=engine.add_item(paper('Valid historical unread paper',ext='arxiv:2610.12345',published='2026-10-20T00:00:00Z'))
        with engine.conn() as c:
            c.execute("UPDATE items SET starred=1,notes='keep my note',summary=? WHERE id=?",(json.dumps({'keep':True}),old))
            c.execute("INSERT INTO recommendation_inbox VALUES(?,?,'followed','author','followed',0.95)",(old,'2026-11-26'))
            c.execute("INSERT INTO recommendation_inbox VALUES(?,?,'followed','author','followed',0.95)",(valid,'2026-10-21'))
        result=followed.withdraw_invalid_admissions(self.desk)
        self.assertEqual([r['id'] for r in result],[old])
        self.assertEqual([r['id'] for r in engine.daily_recommendations()['items']],[valid])
        with engine.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM recommendation_inbox').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT notes,starred FROM items WHERE id=?',(old,)).fetchone()[:],('keep my note',1))
    def test_legacy_duplicate_item_cannot_be_admitted_again(self):
        first,_=engine.add_item(paper(group='field'));engine.daily_recommendations()
        with engine.conn() as c:
            c.execute("INSERT INTO items(id,kind,title,url,published,added,body,coverage,workspace,external_id) SELECT 'legacy-copy',kind,title,'https://example.org/different',published,added,body,coverage,workspace,'doi:10.1000/different' FROM items WHERE id=?",(first,))
            c.execute("INSERT INTO discoveries VALUES('legacy-copy','follow:a','Author','followed',?)",(STAMP,))
        out=engine.daily_recommendations()
        self.assertEqual(len(out['items']),1);self.assertEqual(out['items'][0]['id'],first)
    def test_weekly_schedule_uses_successful_check_time(self):
        self.check([]);self.assertEqual(followed.due(self.desk),[])
        self.desk.now=lambda:'2026-12-04T11:59:59+08:00';self.assertEqual(followed.due(self.desk),[])
        self.desk.now=lambda:'2026-12-04T12:00:00+08:00';self.assertEqual(followed.due(self.desk),['a'])

if __name__=='__main__':unittest.main()
