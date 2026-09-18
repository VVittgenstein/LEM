"""Fixed, monotone C1 bathymetric profiles, independent of the data-domain size.

Internal depths are positive metres; distance is kilometres. Width W ends at
the start of steepening. All smoothing lengths are fixed per environment.
"""
from dataclasses import dataclass
import numpy as np


def smoothstep(t):
    t=np.clip(np.asarray(t,float),0.,1.)
    return t*t*t*(10.+t*(-15.+6.*t))


@dataclass(frozen=True)
class Profile:
    width_km: float
    break_depth_m: float
    steep_slope_m_per_m: float
    bottom_depth_m: float
    platform_depth_m: float=53.

    def __post_init__(self):
        if not (self.width_km>0 and self.platform_depth_m<self.break_depth_m<self.bottom_depth_m):
            raise ValueError('Profile depths must increase from platform through break to bottom')
        if self.steep_m_per_km<=4*self.gentle_m_per_km/3:
            raise ValueError('Measured post-break slope must exceed the gentle segment slope')

    @property
    def gentle_m_per_km(self):return (self.break_depth_m-self.platform_depth_m)/self.width_km

    @property
    def steep_m_per_km(self):return self.steep_slope_m_per_m*1000.

    @property
    def smoothing_km(self):
        # Up to three 1 km cells; ensure the statistical width and steep slope
        # remain intact and both transition pieces fit in the remaining drop.
        return min(3.,self.width_km/10.,(self.bottom_depth_m-self.break_depth_m)/(2*self.steep_m_per_km))

    @property
    def straight_steep_km(self):
        a,b=self.gentle_m_per_km,self.steep_m_per_km
        return (self.bottom_depth_m-self.break_depth_m-.5*(a+2*b)*self.smoothing_km)/b

    @property
    def foot_km(self):return self.width_km+2*self.smoothing_km+self.straight_steep_km

    def depth(self,distance_km):
        x=np.asarray(distance_km,float);w=self.width_km;h=self.smoothing_km
        a,b=self.gentle_m_per_km,self.steep_m_per_km
        t=np.clip(x/w,0.,1.)
        # Flat tangent at the platform; depth and gentle tangent exact at W.
        z=self.platform_depth_m+(self.break_depth_m-self.platform_depth_m)*(2*t*t-t*t*t)
        u=np.clip(x-w,0.,h);t=u/h
        join=self.break_depth_m+a*u+(b-a)*h*(t**3-.5*t**4)
        z=np.where(x>w,join,z)
        za=self.break_depth_m+.5*(a+b)*h
        v=np.clip(x-w-h,0.,self.straight_steep_km)
        z=np.where(x>w+h,za+b*v,z)
        start=self.foot_km-h;t=np.clip((x-start)/h,0.,1.)
        foot=self.bottom_depth_m-.5*b*h+b*h*(t-t**3+.5*t**4)
        z=np.where(x>start,foot,z)
        return np.where(x>=self.foot_km,self.bottom_depth_m,z)

    def record(self):
        return dict(width_km=self.width_km,break_depth_m=self.break_depth_m,
                    steep_slope_m_per_m=self.steep_slope_m_per_m,bottom_depth_m=self.bottom_depth_m,
                    platform_depth_m=self.platform_depth_m,gentle_mean_slope_m_per_m=self.gentle_m_per_km/1000.,
                    smoothing_km=self.smoothing_km,straight_steep_km=self.straight_steep_km,foot_km=self.foot_km,
                    definition='W is platform-edge to start of steepening; C1 joins; no domain-dependent scaling')


def from_parameters(params,kind):
    p=params['profiles'][kind]
    return Profile(p['width_km'],p['break_depth_m'],p['steep_slope_m_per_m'],p['bottom_depth_m'],params['platform_depth_m'])
