"""Years since 48 Ma; independent belts map to one fixed 500-km world grid."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from spacetime import Evaluator,clock_values,crop_points
from spatial_binding import field_directory,window_directory
from tcontext import *

class ConvergentSchedule:
    def __init__(self,seed,layout='window',event_index=None):
        if layout not in ('window','complete'):raise ValueError('layout must be window or complete')
        if layout=='complete' and event_index is None:raise ValueError('A complete field requires event_index: each belt has its own source coordinates')
        self.seed=int(seed);self.layout=layout;self.path=OUT/f'seed{seed}';self.record=load(self.path/'schedule.json');self.cache={}
        self.events=[e for e in self.record['events'] if event_index is None or e['event_index']==event_index]
        if event_index is not None and not self.events:raise ValueError('Unknown event_index')
        self.shape=(500,500);self.x_km=np.arange(500)+.5;self.y_km=self.x_km.copy()
        if layout=='complete':
            d=np.load(field_directory(seed,event_index)/'field.npz');self.shape=d['u_m_per_yr'].shape
            self.x_km=d['x_km'];self.y_km=d['y_km']

    def _field(self,event):
        i=event['event_index']
        if i not in self.cache:
            p=self.path/f'event{i:02d}';clocks=dict(np.load(p/'clocks.npz'));noise=load(p/'spatial_time_parameters.json')['noise']
            full=dict(np.load(field_directory(self.seed,i)/'field.npz'))
            if self.layout=='window':
                wp=window_directory(self.seed,i);data=np.load(wp/'window.npz');reference=data['u_m_per_yr'].ravel();points=crop_points(load(wp/'selection.json'))
            else:
                x,y=np.meshgrid(full['x_km'],full['y_km']);points=np.column_stack([x.ravel(),y.ravel()]);reference=full['u_m_per_yr'].ravel()
            active=reference>0;on,off=clock_values(points[active],full,clocks)
            self.cache[i]=(Evaluator(points[active],reference[active],on,off,event,noise),active)
        return self.cache[i]

    @staticmethod
    def _time(years):
        value=float(years)/1e6
        if not 0<=value<=48:raise ValueError('Simulation time must lie in 0..48 million years since 48 Ma')
        return value

    def at_time(self,time_years):
        t=self._time(time_years);out=np.zeros(np.prod(self.shape))
        for event in self.events:
            if event['start_sim_Myr']<t<event['natural_end_sim_Myr']:
                field,active=self._field(event);out[active]+=field.rate(t)
        return out.reshape(self.shape)

    def displacement(self,start_years,end_years,max_step_Myr=.1):
        a=self._time(start_years);b=self._time(end_years)
        if b<a:raise ValueError('Reversed time interval')
        out=np.zeros(np.prod(self.shape))
        for event in self.events:
            if max(a,event['start_sim_Myr'])<min(b,event['natural_end_sim_Myr']):
                field,active=self._field(event);out[active]+=field.displacement(a,b,max_step_Myr)
        return out.reshape(self.shape)

    def mean_rate(self,start_years,end_years,max_step_Myr=.1):
        if end_years<=start_years:raise ValueError('Positive integration interval required')
        return self.displacement(start_years,end_years,max_step_Myr)/(end_years-start_years)
