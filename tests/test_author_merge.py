import sys
import unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'core'),str(Path(__file__).resolve().parents[1])]
from projects.research.desk_research import domain as server

class AliasChainTests(unittest.TestCase):
    def test_chain_follows_hops(self):
        alias={'a':'b','b':'c'}
        self.assertEqual(server.resolve_alias_chain(alias,'a'),('c',['a','b']))
        self.assertEqual(server.resolve_alias_chain(alias,'c'),('c',[]))

    def test_cycle_is_cut_not_looped(self):
        alias={'a':'b','b':'a'}
        canonical,chain=server.resolve_alias_chain(alias,'a')
        self.assertIn(canonical,{'a','b'})
        self.assertLessEqual(len(chain),2)

if __name__=='__main__':unittest.main()
