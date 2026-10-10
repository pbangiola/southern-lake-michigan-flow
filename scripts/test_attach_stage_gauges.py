import unittest

from attach_stage_gauges import attach


def feature(coords, props):
    return {'type':'Feature','geometry':{'type':'LineString','coordinates':coords},
            'properties':props}


class StageAssociationTests(unittest.TestCase):
    def test_gauge_fields_copy_without_overwriting_river_identity(self):
        named={'type':'FeatureCollection','features':[
            feature([[-90,40],[-90,39.99]],{'river_id':'r1','river_name':'Des Plaines River','filter_river':'Des Plaines River','site':'old'})]}
        gauge={'type':'FeatureCollection','features':[
            feature([[-90,40],[-90,39.99]],{'site':'123','from_gauge':'123','to_gauge':'456','river_name':'Wrong Creek'})]}
        result=attach(named,gauge)
        p=result['features'][0]['properties']
        self.assertEqual(p['river_name'],'Des Plaines River')
        self.assertEqual(p['river_id'],'r1')
        self.assertEqual(p['site'],'123')
        self.assertEqual(p['to_gauge'],'456')

    def test_distant_reach_has_no_gauge(self):
        named={'type':'FeatureCollection','features':[
            feature([[-90,40],[-90,39.99]],{'river_id':'r1','site':'stale'})]}
        gauge={'type':'FeatureCollection','features':[
            feature([[-88,40],[-88,39.99]],{'site':'123'})]}
        result=attach(named,gauge)
        self.assertNotIn('site',result['features'][0]['properties'])
        self.assertEqual(result['metadata']['stage_gauge_association']['unmatched'],1)


if __name__=='__main__':
    unittest.main()
