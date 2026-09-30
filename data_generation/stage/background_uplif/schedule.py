"""Load precomputed interval-average rates for a later LEM driver."""
from pathlib import Path
import numpy as np


class BackgroundSchedule:
    def __init__(self,path):
        with np.load(Path(path),allow_pickle=False) as z:
            self.start=z["start_yr"].copy()
            self.end=z["end_yr"].copy()
            self.rates=z["rate_m_per_yr"].copy()
        if not (self.start.ndim==self.end.ndim==1 and self.rates.ndim==3
                and len(self.start)>0 and len(self.start)==len(self.end)==len(self.rates)):
            raise ValueError("Inconsistent schedule shapes")
        if (not np.isfinite(self.rates).all() or not np.isfinite(self.start).all()
                or not np.isfinite(self.end).all() or not np.all(self.end>self.start)):
            raise ValueError("Invalid schedule")
        if self.start[0]!=0 or not np.array_equal(self.start[1:],self.end[:-1]):
            raise ValueError("Intervals must be contiguous from time zero")

    def at_time(self,t_yr):
        t=float(t_yr)
        if not np.isfinite(t) or not 0<=t<=self.end[-1]:
            raise ValueError("Time outside the background schedule")
        i=min(int(np.searchsorted(self.end,t,side="right")),len(self.end)-1)
        return self.rates[i].copy()

    def displacement(self,start_yr,end_yr):
        """Integrate exactly across any interval boundaries, metres."""
        a,b=float(start_yr),float(end_yr)
        if not np.isfinite([a,b]).all() or not 0<=a<=b<=self.end[-1]:
            raise ValueError("Invalid integration window")
        duration=np.maximum(0.,np.minimum(self.end,b)-np.maximum(self.start,a))
        return np.tensordot(duration,self.rates,axes=(0,0))

    def mean_rate(self,start_yr,end_yr):
        if end_yr<=start_yr:raise ValueError("Positive step duration required")
        return self.displacement(start_yr,end_yr)/(end_yr-start_yr)
