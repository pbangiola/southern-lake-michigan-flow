#!/usr/bin/env python3
"""Tests for directed confluence identity assignment."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('identity',Path(__file__).with_name('assign_river_identity.py'))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def reach(u,v,name='',dx=0.01):
    return {'type':'Feature','geometry':{'type':'LineString','coordinates':[[0,0],[dx,0]]},'properties':{'from_node':u,'to_node':v,'established_name':name}}

class RiverIdentityTests(unittest.TestCase):
    def test_des_plaines_continues_past_salt_creek(self):
        reaches=[reach('d0','join','Des Plaines River',.1),reach('s0','join','Salt Creek',.01),reach('join','out','Des Plaines River',.01)]
        mod.assign(reaches)
        self.assertEqual(reaches[0]['properties']['river_id'],reaches[2]['properties']['river_id'])
        self.assertNotEqual(reaches[1]['properties']['river_id'],reaches[2]['properties']['river_id'])

    def test_new_name_at_confluence(self):
        reaches=[reach('a','join','Allegheny River',.1),reach('m','join','Monongahela River',.09),reach('join','out','Ohio River',.01)]
        mod.assign(reaches)
        self.assertEqual(len({f['properties']['river_id'] for f in reaches}),3)

    def test_unnamed_continues_longest_parent(self):
        reaches=[reach('a','join','',.1),reach('b','join','',.01),reach('join','out','',.01)]
        mod.assign(reaches)
        self.assertEqual(reaches[0]['properties']['river_id'],reaches[2]['properties']['river_id'])

    def test_rejects_undirected(self):
        with self.assertRaisesRegex(ValueError,'from_node'):
            mod.assign([{'type':'Feature','geometry':{'type':'LineString','coordinates':[[0,0],[1,1]]},'properties':{}}])

if __name__=='__main__':unittest.main()
