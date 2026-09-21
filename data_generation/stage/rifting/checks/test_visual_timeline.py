"""Synthetic fixtures verify display scheduling only."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reporting'))
from timeline import shared_timeline

class TimelineTests(unittest.TestCase):
    def test_overview(self):
        result=shared_timeline()
        self.assertEqual([r['elapsed_Myr'] for r in result['frames']],list(range(0,49,6)))
        self.assertEqual(result['frames'][-1]['age_Ma_BP'],0)

    def test_modern_truncates_without_rescaling_lifetime(self):
        result=shared_timeline([dict(kind='far',id='test',start_year=40e6,natural_end_year=56e6)])
        times={r['time_year'] for r in result['frames']}
        self.assertTrue({40e6,42e6,44e6,46e6,48e6}<=times)
        self.assertNotIn(41e6,times)
        self.assertTrue(all(t<=48e6 for t in times))

    def test_all_kinds_share_one_chronology(self):
        data=[dict(kind=k,id=k,start_year=s,natural_end_year=s+4e6)
              for k,s in [('far',1e6),('local',2e6),('fault',3e6)]]
        a=shared_timeline(data);b=shared_timeline(list(reversed(data)))
        self.assertEqual(a,b)
        frames=a['frames'];times=[f['time_year'] for f in frames]
        self.assertEqual(times,sorted(set(times)))
        self.assertEqual(sum(len(p['frame_ids']) for p in a['nine_panel_pages']),len(frames))

    def test_zero_duration_and_shared_endpoints(self):
        data=[dict(kind='fault',id='test',start_year=1e6,natural_end_year=3e6,
                   phases=[dict(name='zero',start_year=2e6,end_year=2e6)])]
        rows=[f for f in shared_timeline(data)['frames'] if f['time_year']==2e6]
        self.assertEqual(len(rows),1)
        self.assertTrue(any('phase:zero' in r for r in rows[0]['reasons']))

    def test_context_does_not_cross_adjacent_changes(self):
        events=[dict(kind='fault',id='a',time_year=1000),dict(kind='fault',id='b',time_year=1003)]
        frames=shared_timeline(transitions=events,context_years=100)['frames']
        after=next(f for f in frames if 'fault:a:change:after' in f['reasons'])
        before=next(f for f in frames if 'fault:b:change:before' in f['reasons'])
        self.assertEqual(after['time_year'],1001)
        self.assertEqual(before['time_year'],1002)

    def test_invalid_history_rejected(self):
        with self.assertRaises(ValueError):
            shared_timeline([dict(kind='local',id='x',start_year=2,natural_end_year=1)])

if __name__=='__main__':unittest.main()
