import sqlite3, tempfile, unittest, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'core'))
from deskcore import folder_ideas
from deskcore.engine import ManagedConnection

class FolderIdeasTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'test.db'
  def conn():
   c=sqlite3.connect(self.db,factory=ManagedConnection);c.row_factory=sqlite3.Row;return c
  self.conn=conn
  with conn() as c:
   c.execute('CREATE TABLE favorite_folders(id TEXT PRIMARY KEY,name TEXT)')
   c.executemany('INSERT INTO favorite_folders VALUES(?,?)',[('a','Speech'),('b','Models')])
  folder_ideas.init(conn)
 def tearDown(self):self.tmp.cleanup()
 def save(self,content,revision=0,fid='a'):
  return folder_ideas.save(self.conn,dict(folder_id=fid,content=content,revision=revision))
 def test_isolation_persistence_rename_clear(self):
  self.assertEqual(folder_ideas.read(self.conn,'a')['content'],'')
  saved,status=self.save('# My idea\nCompare two methods');self.assertEqual(status,200)
  self.save('Different idea',fid='b');folder_ideas.init(self.conn)
  with self.conn() as c:c.execute("UPDATE favorite_folders SET name='New name' WHERE id='a'")
  self.assertEqual(folder_ideas.read(self.conn,'a')['content'],saved['content'])
  self.assertEqual(folder_ideas.read(self.conn,'b')['content'],'Different idea')
  self.assertEqual(self.save('',1)[0]['content'],'')
 def test_conflict_and_idempotent_retry(self):
  self.save('v1');self.assertEqual(self.save('v1')[0]['revision'],1)
  self.save('v2',1);result,status=self.save('stale v1 edit',1)
  self.assertEqual(status,409);self.assertTrue(result['conflict'])
  self.assertEqual(folder_ideas.read(self.conn,'a')['content'],'v2')
 def test_validation(self):
  for fid in ['', 'all','unfiled','missing',None]:
   with self.assertRaises(ValueError):self.save('x',fid=fid)
  for revision in [None,-1,'1',True]:
   with self.assertRaises(ValueError):self.save('x',revision)
  for content in [None,{},'a'*100001]:
   with self.assertRaises(ValueError):self.save(content)
 def test_http_routes_and_local_access(self):
  import json, threading, urllib.request, urllib.error
  from unittest.mock import patch
  from deskcore import http as web
  server=web.ThreadingHTTPServer(('127.0.0.1',0),web.Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  def call(payload=None,origin=None,fid='a'):
   headers={'Content-Type':'application/json'}
   if origin:headers['Origin']=origin
   request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/folder-ideas?folder_id='+fid,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
   try:
    with opener.open(request,timeout=5) as response:return response.status,json.load(response)
   except urllib.error.HTTPError as error:return error.code,json.load(error)
  try:
   with patch.object(web,'conn',self.conn):
    self.assertEqual(call()[1]['revision'],0)
    self.assertEqual(call({'folder_id':'a','content':'saved through HTTP','revision':0})[0],200)
    self.assertEqual(call()[1]['content'],'saved through HTTP')
    self.assertEqual(call({'folder_id':'a','content':'stale','revision':0})[0],409)
    self.assertEqual(call(fid='all')[0],400)
    self.assertEqual(call(origin='https://example.com')[0],403)
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
