import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'core'))

from deskcore import engine
from deskcore.engine import ManagedConnection


def paper(title, group):
    return {'kind': 'paper', 'workspace': 'research', 'title': title, 'external_id': 'arxiv:2611.' + str(abs(hash(title)) % 100000).zfill(5),
            'body': 'We propose a method and evaluate it with experiments on long audio. ' * 4, 'coverage': 'abstract',
            'published': '2026-11-26T00:00:00+08:00', 'authors': ['Alex Example', 'Other Person'],
            'source': '收藏的作者 · Alex Example' if group == 'followed' else '声学与语音 · cs.SD / eess.AS',
            'source_id': 'follow:' + 's2:999' if group == 'followed' else 'src-1', 'source_group': group}


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'q.db'
        engine.DB = self.db
        engine.DATA = Path(self.tmp.name)
        engine.CONFIG = Path(self.tmp.name) / 'settings.json'
        engine.init()
        self.cfg = {'daily_limit': 2, 'hot_limit': 0, 'followed_limit': 1, 'auto_screen': False,
                    'interest_topics': '声学', 'api_key': '', 'ai_engine': 'api'}
        self.patches = [patch.object(engine, 'recommendation_config', return_value=dict(self.cfg)),
                        patch.object(engine, 'ai_ready', return_value=False),
                        patch.object(engine, 'DELIVERY', _Delivery())]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def admit(self):
        return engine.daily_recommendations(admit_during_collection=True)

    def test_followed_author_papers_use_their_own_quota(self):
        ids = []
        for n in range(3):
            iid, _ = engine.add_item(paper('Acoustic speech method number %d' % n, 'field'))
            ids.append(iid)
        out = self.admit()
        self.assertEqual(len(out['items']), 2, 'the daily 50-style quota still applies to normal sources')

        followed_id, _ = engine.add_item(paper('Hour-scale audio captioning by a followed author', 'followed'))
        out = self.admit()
        groups = [i['daily_group'] for i in out['items']]
        self.assertIn('followed', groups)
        self.assertEqual(groups.count('followed'), 1)
        self.assertEqual(out['followed_limit'], 1)
        self.assertEqual(len([g for g in groups if g != 'followed']), 2, 'the normal quota did not grow')

    def test_followed_quota_is_respected(self):
        for n in range(3):
            engine.add_item(paper('Hour-scale audio captioning number %d' % n, 'followed'))
        out = self.admit()
        self.assertEqual(len([i for i in out['items'] if i['daily_group'] == 'followed']), 1)

    def test_followed_papers_bypass_interest_topics_and_ai_screening(self):
        engine.add_item(paper('Hour-scale audio captioning', 'followed'))
        out = self.admit()
        item = next(i for i in out['items'] if i['daily_group'] == 'followed')
        self.assertIn('关注的作者', item['daily_reason'])
        self.assertEqual(item['daily_screening'], 'followed')


class _Delivery:
    def history(self, desk):
        return [{}]


if __name__ == '__main__':
    unittest.main()
