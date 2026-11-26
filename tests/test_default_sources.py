"""Default source migrations use temporary databases and no remote requests."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOT = '''
import sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd() / 'core'), str(Path.cwd())]
from deskcore import engine, runtime
runtime.load_projects([('research', 'projects.research.desk_research', '论文研究', Path('projects/research/static'))])
engine.init()
def hf():
    with engine.conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM sources WHERE workspace='research' AND type='hf'")]
'''

class DefaultSourceTests(unittest.TestCase):
    def check_migration(self, script):
        with tempfile.TemporaryDirectory() as temp:
            env = {k: v for k, v in os.environ.items() if not k.startswith(('SUMMARY_', 'KNOWLEDGE_'))}
            env.update(KNOWLEDGE_DATA_DIR=temp, KNOWLEDGE_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-c', BOOT + script], cwd=ROOT,
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_new_install_has_three_sources_without_duplicates(self):
        self.check_migration('''
engine.init()
with engine.conn() as c:
    rows=[dict(r) for r in c.execute("SELECT * FROM sources WHERE workspace='research'")]
assert sorted(r['type'] for r in rows)==['alphaxiv','arxiv','hf'], rows
assert len(hf())==1 and hf()[0]['query']=='daily'
assert hf()[0]['enabled']==1 and hf()[0]['source_group']=='hot' and hf()[0]['kind']=='paper'
assert next(r for r in rows if r['type']=='arxiv')['query']=='cat:cs.SD OR cat:eess.AS'
''')

    def test_existing_two_source_install_is_backfilled(self):
        self.check_migration('''
with engine.conn() as c:
    c.execute("DELETE FROM sources WHERE type='hf'")
    c.execute("DELETE FROM app_meta WHERE key='hf_daily_seeded_v1'")
    c.execute("UPDATE sources SET enabled=0 WHERE type='arxiv'")
engine.init()
assert len(hf())==1
with engine.conn() as c:
    assert c.execute("SELECT enabled FROM sources WHERE type='arxiv'").fetchone()[0]==0
''')

    def test_existing_custom_paused_hf_is_preserved(self):
        self.check_migration('''
with engine.conn() as c:
    c.execute("UPDATE sources SET id='custom-hf',name='My HF source',enabled=0 WHERE type='hf'")
    c.execute("DELETE FROM app_meta WHERE key='hf_daily_seeded_v1'")
before=hf()
engine.init()
assert hf()==before, hf()
''')

    def test_user_removal_after_migration_is_preserved(self):
        self.check_migration('''
with engine.conn() as c:
    c.execute("DELETE FROM sources WHERE type='hf'")
engine.init()
assert hf()==[]
''')
