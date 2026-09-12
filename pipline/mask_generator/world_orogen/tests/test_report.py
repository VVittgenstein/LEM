from pathlib import Path
import tempfile
import unittest

from common.io import write_json
from world_orogen.report import write_report


class ReportTests(unittest.TestCase):
    def test_parameter_text_uses_sample_config_and_omits_absent_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            relative='partitions_56/seed1001'
            write_json(output/relative/'selection.json',{'steps':[{'step':0,'chosen_region':1,
                'chosen_probability':1.,'fraction':.55,'R':.1,'Q':1.}]})
            sample={'seed':1001,'partition_count':56,'relative_path':relative,
                'metrics':{'target_fraction':.55,'fraction':.55,'components_4':1,'largest_component_fraction':1,
                           'centroid_offset_km':20,'rms_distance_to_preferred_center_km':170},
                'config':{'center_weight':96,'connection_weight':32,'center_x_km':250,'center_y_km':250},
                'status':{'observations':[]}}
            write_report(output,[sample],[56])
            page=(output/'report.html').read_text(encoding='utf-8')
            self.assertIn('位置权重 96、成片权重 32',page)
            self.assertNotIn('href="distribution.csv"',page)
            self.assertNotIn('__CENTER_WEIGHT__',page)
