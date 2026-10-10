import copy
import unittest

from prepare_authoritative_rivers import prepare, run


def feature(a,b,name='',sid='x'):
    return {'type':'Feature','geometry':{'type':'LineString','coordinates':[list(a),list(b)]},
            'properties':{'GNIS_Name':name,'segment_id':sid}}


class AuthoritativePipelineTests(unittest.TestCase):
    def test_confluence_keeps_longest_parent(self):
        data={'type':'FeatureCollection','features':[
            feature((-90,40),(-90,39.9),'Des Plaines River','a'),
            feature((-89.99,39.95),(-90,39.9),'Salt Creek','b'),
            feature((-90,39.9),(-90,39.8),'Des Plaines River','c')
        ]}
        result=run(data)
        self.assertEqual(result['metadata']['accepted_segments'],3)
        p=[f['properties'] for f in result['features']]
        by_id={x['segment_id']:x for x in p}
        self.assertEqual(by_id['a']['river_id'],by_id['c']['river_id'])
        self.assertNotEqual(by_id['b']['river_id'],by_id['c']['river_id'])

    def test_new_name_begins_at_confluence(self):
        data={'type':'FeatureCollection','features':[
            feature((-90,40),(-90,39.9),'Allegheny River','a'),
            feature((-89.9,40),(-90,39.9),'Monongahela River','b'),
            feature((-90,39.9),(-90,39.8),'Ohio River','c')
        ]}
        p={f['properties']['segment_id']:f['properties'] for f in run(data)['features']}
        self.assertEqual(len({p[x]['river_id'] for x in 'abc'}),3)

    def test_cycle_is_withheld(self):
        data={'type':'FeatureCollection','features':[
            feature((-90,40),(-90,39.9),'','a'),
            feature((-90,39.9),(-89.9,39.9),'','b'),
            feature((-89.9,39.9),(-90,40),'','c')
        ]}
        result=run(data)
        self.assertEqual(result['metadata']['accepted_segments'],0)
        self.assertEqual(result['metadata']['rejected_segments'],3)

    def test_disconnected_components_have_unique_ids(self):
        data={'type':'FeatureCollection','features':[
            feature((-90,40),(-90,39.9),'','a'),
            feature((-89,40),(-89,39.9),'','b')
        ]}
        p=[f['properties'] for f in run(data)['features']]
        self.assertNotEqual(p[0]['river_id'],p[1]['river_id'])

    def test_usgs_reversed_digitization_is_corrected(self):
        f=feature((-90,39.9),(-90,40),'','reverse')
        f['properties']['flowdirection']=2
        f['properties']['gnisidlabel']='Des Plaines River'
        prepared=prepare({'type':'FeatureCollection','features':[f]})
        self.assertEqual(prepared[0]['geometry']['coordinates'][0],[-90,40])
        self.assertEqual(prepared[0]['properties']['established_name'],'Des Plaines River')

    def test_unknown_flowdirection_is_excluded(self):
        f=feature((-90,40),(-90,39.9),'','unknown')
        f['properties']['flowdirection']=0
        self.assertEqual(prepare({'type':'FeatureCollection','features':[f]}),[])

    def test_usgs_mainstem_survives_divergence(self):
        a=feature((-90,40),(-90,39.9),'','a')
        b=feature((-90,39.9),(-90,39.8),'','b')
        c=feature((-90,39.9),(-89.9,39.8),'','c')
        for f in (a,b,c):
            f['properties']['mainstemid']='M1'
            f['properties']['flowdirection']=1
            f['properties']['gnisidlabel']='Des Plaines River'
        result=run({'type':'FeatureCollection','features':[a,b,c]})
        self.assertEqual(result['metadata']['accepted_segments'],3)
        self.assertEqual(len({f['properties']['river_id'] for f in result['features']}),1)

    def test_divergence_is_withheld(self):
        data={'type':'FeatureCollection','features':[
            feature((-90,40),(-90,39.9),'','a'),
            feature((-90,39.9),(-90,39.8),'','b'),
            feature((-90,39.9),(-89.9,39.8),'','c')
        ]}
        result=run(data)
        self.assertEqual(result['metadata']['rejected_segments'],3)


if __name__=='__main__':
    unittest.main()
