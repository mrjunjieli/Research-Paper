import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

class StandaloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        cls.base = 'http://127.0.0.1:' + str(port)
        env = {k: v for k, v in os.environ.items() if not k.startswith(('SUMMARY_', 'KNOWLEDGE_'))}
        env.update(PORT=str(port), KNOWLEDGE_DATA_DIR=cls.temp.name, PYTHONDONTWRITEBYTECODE='1')
        cls.log = open(Path(cls.temp.name) / 'server.log', 'w+')
        cls.process = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env,
                                      cwd=cls.temp.name, stdout=cls.log, stderr=cls.log)
        cls.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            try:
                cls.get('/api/projects')
                return
            except OSError:
                time.sleep(.1)
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.log.seek(0)
        raise RuntimeError(cls.log.read())

    @classmethod
    def get(cls, path):
        with cls.client.open(cls.base + path, timeout=10) as response:
            return response.read()

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        cls.log.close()
        cls.temp.cleanup()

    def test_research_only(self):
        payload = json.loads(self.get('/api/projects'))
        self.assertEqual([p['id'] for p in payload['projects']], ['research'])
        self.assertTrue(payload['projects'][0]['ok'], payload)
        html = self.get('/research').decode()
        self.assertNotIn('id="switch-news"', html)
        for url in re.findall(r'(?:src|href)="(/[^"#]+)"', html):
            self.assertTrue(self.get(url), url)

    def test_empty_private_data(self):
        state = json.loads(self.get('/api/state'))
        self.assertNotIn('error', state)
        self.assertNotIn('api_key', state['settings'])
        self.assertFalse(state['settings']['api_key_configured'])
        self.assertFalse(state['settings']['auto_refresh'])
        with sqlite3.connect(Path(self.temp.name) / 'desk.sqlite3') as db:
            for table in ('items', 'paper_notes', 'paper_chat'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)

    def test_research_routes(self):
        for route in ('/api/graph', '/api/research-directions', '/api/tasks', '/api/paper-prompt'):
            payload = json.loads(self.get(route))
            self.assertNotIn('error', payload, route)

if __name__ == '__main__':
    unittest.main()
