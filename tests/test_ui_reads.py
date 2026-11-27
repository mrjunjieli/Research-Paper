import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'core'),str(Path(__file__).resolve().parents[1])]
from deskcore import engine as server
from deskcore import ui_reads


class ReadPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.db=self.root/'desk.sqlite3'
        def connect():
            c=sqlite3.connect(self.db,factory=server.ManagedConnection);c.row_factory=sqlite3.Row;return c
        self.connect=connect
        with connect() as c:
            c.executescript('''CREATE TABLE items(id TEXT PRIMARY KEY,workspace TEXT,title TEXT,body TEXT,summary TEXT,authors TEXT,tags TEXT,kind TEXT);
             CREATE TABLE discoveries(item TEXT);CREATE TABLE item_topics(item TEXT);
             CREATE TABLE sources(id TEXT,workspace TEXT,name TEXT);
             INSERT INTO items VALUES('a','research','Paper','body','{"text":"old"}','[]','[]','paper');''')
        self.desk=SimpleNamespace(conn=connect,DB=self.db,DATA=self.root,CONFIG=self.root/'settings.json',Path=Path,now=lambda:'2026-11-15T10:00:00+08:00',JOBS={},
          DEFAULT={'api_key':'','ai_engine':'api'},SECRET_STORE=SimpleNamespace(SECRET_FIELDS=('api_key','search_api_key','scholar_key'),RETIRED_FIELDS=()),
          os=SimpleNamespace(environ={}),codex_binary=lambda:None,API_PROVIDERS=[],CODEX_MODELS=[],API_EFFORT_CATALOG=[],API_EFFORTS=[])
        ui_reads.initialize(self.desk);ui_reads._snapshots.clear();ui_reads._preferences.clear()
    def tearDown(self):self.tmp.cleanup()

    def test_pdf_links_prefer_real_cached_files_and_fallback_to_arxiv(self):
        iid='a'*20
        item={'id':iid,'kind':'paper','external_id':'arxiv:2611.12345','url':''}
        self.assertEqual(ui_reads.pdf_link(self.desk,item),'https://arxiv.org/pdf/2611.12345')
        path=self.root/'materials'/iid/'original.pdf';path.parent.mkdir(parents=True);path.write_bytes(b'%PDF-test')
        self.assertEqual(ui_reads.pdf_link(self.desk,item),'/paper-assets/'+iid+'/original.pdf')
        self.assertEqual(ui_reads.pdf_link(self.desk,{'id':'b'*20,'kind':'paper','url':'https://example.org/paper'}),'')
        self.assertEqual(ui_reads.pdf_link(self.desk,{'id':'b'*20,'kind':'paper','url':'javascript:bad.pdf'}),'')

    def test_connections_close_on_success_and_failure(self):
        with self.connect() as c:c.execute("UPDATE items SET title='saved' WHERE id='a'")
        with self.assertRaises(sqlite3.ProgrammingError):c.execute('SELECT 1')
        with self.assertRaisesRegex(ValueError,'rollback'):
            with self.connect() as failed:
                failed.execute("UPDATE items SET title='wrong' WHERE id='a'");raise ValueError('rollback')
        with self.assertRaises(sqlite3.ProgrammingError):failed.execute('SELECT 1')
        with self.connect() as c:self.assertEqual(c.execute('SELECT title FROM items').fetchone()[0],'saved')

    def test_same_length_edits_invalidate_item_revision(self):
        with self.connect() as c:first=c.execute('SELECT revision FROM ui_item_revisions').fetchone()[0]
        before=ui_reads.revision(self.desk,'research')
        with self.connect() as c:c.execute("UPDATE items SET summary=? WHERE id='a'",('{"text":"new"}',))
        with self.connect() as c:self.assertGreater(c.execute('SELECT revision FROM ui_item_revisions').fetchone()[0],first)
        self.assertNotEqual(before,ui_reads.revision(self.desk,'research'))

    def test_list_projection_removes_full_report_body_notes_and_private_author_fields(self):
        paper={'id':'a','kind':'paper','body':'FULL TEXT'*10000,'coverage':'pdf','abstract':'a'*1000,
          'summary':{'report_sections':[{'markdown':'PRIVATE LONG REPORT'}]},'authors':[{'id':'x','name':'Person','internal_notes':'private'}],
          '_incremental_collected':True,'processing':{'details':'huge'}}
        result=ui_reads.compact(paper)
        self.assertEqual(result['body'],'');self.assertIsNone(result['summary']);self.assertTrue(result['has_summary'])
        self.assertLessEqual(len(result['abstract']),600);self.assertNotIn('internal_notes',result['authors'][0]);self.assertNotIn('details',result.get('processing',{}))

    def test_public_config_never_opens_keychain_or_returns_key_reference(self):
        self.desk.CONFIG.write_text(json.dumps({'api_key':{'keychain':'private-reference'},'search_api_key':'legacy-secret'}))
        result=ui_reads.public_settings(self.desk,'research')
        self.assertTrue(result['api_key_configured']);self.assertTrue(result['ai_available'])
        for secret in ('private-reference','legacy-secret'):self.assertNotIn(secret,json.dumps(result))
        self.assertNotIn('api_key',result)

    def test_snapshot_is_read_only_shared_and_daily_does_not_duplicate_full_papers(self):
        paper={'id':'a','kind':'paper','body':'body','abstract':'abstract','summary':{'report_sections':['large']},'authors':[], 'topics':[], '_detail_loaded':False}
        self.desk.daily_recommendations=Mock(return_value={'items':[{**paper,'daily_reason':'reason','recommended_date':'2026-11-15'}]})
        self.desk.DIRECTIONS=SimpleNamespace(read=lambda d:{})
        self.desk.topic_library=lambda:[];self.desk.favorite_folders=lambda:[]
        with patch.object(ui_reads,'cards',return_value=[paper]) as cards:
            before=ui_reads.revision(self.desk,'research')
            first=ui_reads.state(self.desk,'research');second=ui_reads.state(self.desk,'research')
            self.assertEqual(before,ui_reads.revision(self.desk,'research'));self.assertEqual(cards.call_count,1)
            self.desk.daily_recommendations.assert_called_once_with([paper],read_only=True)
            self.assertNotIn('body',first['daily']['items'][0]);self.assertNotIn('summary',first['daily']['items'][0]);self.assertEqual(first,second)

    def test_detail_is_workspace_scoped(self):
        self.desk.decode_item=lambda row:dict(row)
        self.assertIsNone(ui_reads.detail(self.desk,'news','a'))
        self.assertEqual(ui_reads.detail(self.desk,'research','a')['body'],'body')

if __name__=='__main__':unittest.main()
