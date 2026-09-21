"""Queries of a frozen generated history. No random draws occur here."""
from __future__ import annotations
import numpy as np
from .products import Run
from .faults import rates_at,cumulative_at,geometry_at
from .forcing import stress_at as sample_stress
from .response import field_from_coefficients

class RiftingSchedule:
    def __init__(self,seed=1001):self.run=Run(seed)
    @staticmethod
    def _time(years):
        t=float(years)/1e6
        if not np.isfinite(t) or not 0<=t<=48:raise ValueError('Time is years since 48 Ma and must be in [0,48000000]')
        return t
    def at_time(self,time_years):
        t=self._time(time_years)
        return np.einsum('p,pyx->yx',rates_at(self.run.history,t).ravel(),self.run.vertical,optimize=True)
    def displacement(self,start_years,end_years):
        a,b=self._time(start_years),self._time(end_years)
        if b<a:raise ValueError('Reversed interval')
        c=cumulative_at(self.run.history,b)-cumulative_at(self.run.history,a)
        return np.einsum('p,pyx->yx',c.ravel(),self.run.vertical,optimize=True)
    def mean_rate(self,start_years,end_years):
        if end_years<=start_years:raise ValueError('Positive interval required')
        return self.displacement(start_years,end_years)/(end_years-start_years)
    def velocity_at(self,time_years):
        return field_from_coefficients(self.run.response,rates_at(self.run.history,self._time(time_years)))
    def stress_at(self,global_xy_km,time_years,component='total'):
        if component not in ['far','local','total']:raise ValueError('Unknown stress component')
        t=self._time(time_years)
        points=np.asarray(global_xy_km,dtype=float)
        if points.ndim<1 or points.shape[-1]!=2 or not np.isfinite(points).all():raise ValueError('Coordinates must be finite XY values in km')
        if np.any(points<0) or np.any(points>self.run.length):raise ValueError('Coordinates outside the auxiliary domain')
        return sample_stress(self.run.basis,self.run.episodes,t,points,self.run.length,None if component=='total' else component)
    def faults_at(self,time_years):
        t=self._time(time_years);rates=rates_at(self.run.history,t);cum=cumulative_at(self.run.history,t)
        return [dict(id=f['id'],trace_xy_km=geometry_at(f,t),active=bool(np.max(rates[i])>1e-10),
                slip_rate_m_per_year=rates[i].copy(),cumulative_slip_m=cum[i].copy(),dip_deg=f['dip_deg'],bottom_depth_km=f['bottom_depth_km'])
                for i,f in enumerate(self.run.faults) if t>=f['birth_Myr']]
