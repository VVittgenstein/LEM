from pathlib import Path
import json
import tempfile
import unittest

import numpy as np

from common.io import write_json
from common.report import write_report


class ReportTests(unittest.TestCase):
    def test_in_memory_numpy_status_is_serialized_into_local_viewer(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            write_json(output / "calibration/calibration.json", {"selected": {"stretch": 1, "gain": .5}})
            write_json(output / "audit.json", {"passed": True, "counts": {"mask_count": 12}})
            samples = [{"status": {"geometry_checks": {"fraction_range": np.bool_(True)}},
                        "note": "<sample>", "metric": np.float64(.55)}]
            write_report(output, samples)
            page = (output / "report.html").read_text(encoding="utf-8")
            payload = page.split('<script id="data" type="application/json">', 1)[1].split('</script>', 1)[0]
            restored = json.loads(payload)
            self.assertIs(restored["samples"][0]["status"]["geometry_checks"]["fraction_range"], True)
            self.assertEqual(restored["samples"][0]["note"], "<sample>")
            self.assertNotIn("<sample>", payload)
            self.assertNotIn("__DATA__", page)
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)
