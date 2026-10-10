#!/usr/bin/env python3
"""Synthetic confluence graph regression test; run with python -m unittest."""
import tempfile, unittest
from pathlib import Path
from traverse_edna_graph import traverse
class GraphTraversalTest(unittest.TestCase):
    def test_forks_and_checkpoint(self):
        root=(-90.62,38.97);a=(-90.62,39.0);b=(-90.60,39.02);c=(-90.64,39.02)
        edges={
            "main":{"a":root,"b":a,"coords":[root,a],"source":"synthetic"},
            "right":{"a":a,"b":b,"coords":[a,b],"source":"synthetic"},
            "left":{"a":a,"b":c,"coords":[a,c],"source":"synthetic"},
        }
        adj={root:["main"],a:["main","right","left"],b:["right"],c:["left"]}
        with tempfile.TemporaryDirectory() as directory:
            state=str(Path(directory)/"state.json")
            first=traverse(edges,adj,root,1,state,set())
            self.assertEqual(len(first["features"]),1)
            second=traverse(edges,adj,root,1,state,set())
            self.assertEqual(len(second["features"]),2)
            self.assertEqual(second["metadata"]["total_processed_edges"],3)
            self.assertEqual(second["metadata"]["queue_remaining"],0)
    def test_existing_branch_is_not_expanded(self):
        root=(-90.62,38.97);a=(-90.62,39.0)
        edges={"e":{"a":root,"b":a,"coords":[root,a],"source":"synthetic"}}
        adj={root:["e"],a:["e"]}
        with tempfile.TemporaryDirectory() as directory:
            result=traverse(edges,adj,root,10,str(Path(directory)/"state.json"),{"e"})
            self.assertEqual(result["features"],[])
            self.assertEqual(result["metadata"]["existing_intersections"],["e"])
if __name__=="__main__":unittest.main()
