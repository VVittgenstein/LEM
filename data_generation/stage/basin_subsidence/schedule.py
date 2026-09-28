"""Public read-only event APIs. Input years since 48 Ma, output m/yr or m."""
from pathlib import Path
import numpy as np
from .common import OUT, load
from .spatial import FieldMap
from .temporal import NodeHistory

class Event:
    def __init__(self, directory, layout='window'):
        self.directory = Path(directory)
        if layout not in ('window', 'complete'):
            raise ValueError('Unknown layout')
        self.layout = layout
        self.history = NodeHistory(self.directory)
        with np.load(self.directory / 'mesh.npz') as d:
            self.mesh = dict(d)
        self.mapper = FieldMap(self.mesh['points_km'], self.mesh['active'])
        if layout == 'window':
            with np.load(self.directory / 'window.npz') as d:
                self.query = d['query_vertices'], d['query_weights']
            self.x_km = self.y_km = np.arange(500)+.5
        else:
            self.x_km, self.y_km = self.mesh['x_km'], self.mesh['y_km']
            x, y = np.meshgrid(self.x_km, self.y_km)
            self.query = self.mapper.weights(np.column_stack([x.ravel(), y.ravel()]))
        self.shape = (len(self.y_km), len(self.x_km))

    @staticmethod
    def time(years):
        t = float(years)/1e6
        if not np.isfinite(t) or not 0 <= t <= 48:
            raise ValueError('Time is finite years since 48 Ma, in [0,48000000]')
        return t

    def at_time(self, years):
        return self.mapper.evaluate(self.history.rate(self.time(years)), self.query).reshape(self.shape)

    def displacement(self, a_years, b_years):
        return self.mapper.evaluate(self.history.displacement(self.time(a_years), self.time(b_years)), self.query).reshape(self.shape)

    def mean_rate(self, a_years, b_years):
        if b_years <= a_years:
            raise ValueError('Positive time interval required')
        return self.displacement(a_years, b_years)/(b_years-a_years)

    def at_points(self, xy_source_km, years):
        return self.mapper.evaluate(self.history.rate(self.time(years)), self.mapper.weights(xy_source_km))

class BasinSchedule:
    def __init__(self, seed=1001, output=OUT):
        self.directory = Path(output) / f'seed{seed}'
        self.record = load(self.directory / 'schedule.json')
        self.events = [Event(self.directory / f"event{e['event_index']:02d}") for e in self.record['events']]

    def at_time(self, years):
        Event.time(years)
        return sum((e.at_time(years) for e in self.events), start=np.zeros((500, 500)))

    def displacement(self, a_years, b_years):
        a, b = Event.time(a_years), Event.time(b_years)
        if b < a:
            raise ValueError('Reversed integration interval')
        return sum((e.displacement(a_years, b_years) for e in self.events), start=np.zeros((500, 500)))

    def mean_rate(self, a_years, b_years):
        if b_years <= a_years:
            raise ValueError('Positive time interval required')
        return self.displacement(a_years, b_years)/(b_years-a_years)
