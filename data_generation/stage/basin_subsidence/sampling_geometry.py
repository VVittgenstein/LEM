"""Continuous support of the existing evaluator and the fixed 1 km platform mask."""
import importlib.util
import importlib.machinery
import sys
from functools import lru_cache
from .common import BASES, REPO, np
from .spatial import FieldMap


def _geometry_library():
    try:
        import shapely
        return shapely
    except ModuleNotFoundError as error:
        if error.name != 'shapely':
            raise
    # Reuse the project's installed geometry library without modifying either
    # environment or adding its other packages to sys.path.
    folder = REPO/'docs/work/2026-09-08-q1-data/D-landform-statistics/.venv/Lib/site-packages'
    spec = importlib.machinery.PathFinder.find_spec('shapely', [str(folder)])
    if spec is None:
        raise ImportError('Shapely is required; the existing D environment was not found')
    library = importlib.util.module_from_spec(spec)
    sys.modules['shapely'] = library
    spec.loader.exec_module(library)
    return library


shapely = _geometry_library()
WORLD = shapely.box(0., 0., 500., 500.)
LOCAL_CORNERS = np.array([[0., 0.], [500., 0.], [500., 500.], [0., 500.], [0., 0.]])


def rotation(angle):
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s], [s, c]])


def to_source(local, center, matrix):
    return (np.asarray(local)-250.)@matrix.T+center


def to_local(source, center, matrix):
    return (np.asarray(source)-center)@matrix+250.


def window_polygon(center, matrix):
    return shapely.Polygon(to_source(LOCAL_CORNERS, center, matrix))


def polygon_parts(geometry):
    if geometry.geom_type == 'Polygon':
        return [geometry]
    return [p for part in geometry.geoms for p in polygon_parts(part)]


def mask_polygon(mask):
    """Exact union of occupied 1 km cells; inland holes remain holes."""
    changes = np.diff(np.pad(mask.astype(np.int8), ((0, 0), (1, 1))), axis=1)
    rows, starts = np.where(changes == 1)
    end_rows, ends = np.where(changes == -1)
    if not np.array_equal(rows, end_rows) or not len(rows):
        raise ValueError('Invalid or empty platform mask')
    geometry = shapely.union_all(shapely.box(starts, rows, ends, rows+1))
    if not geometry.is_valid or abs(geometry.area-mask.sum()) > 1e-8:
        raise ValueError('Platform geometry differs from its cell mask')
    return geometry


class FullSupport:
    """Support closure and natural zero edges of FieldMap's own triangulation."""
    def __init__(self, directory):
        with np.load(directory/'mesh.npz') as mesh:
            self.points = mesh['points_km']
            self.active = mesh['active'].astype(bool)
            self.rate = mesh['reference_u_m_per_yr']
        self.mapper = FieldMap(self.points, self.active)
        triangles = self.mapper.tri.simplices
        keep = np.any(self.active[triangles], axis=1)
        self.geometry = shapely.union_all(shapely.polygons(self.points[triangles[keep]]))
        if not self.geometry.is_valid or self.geometry.area <= 0:
            raise ValueError('Invalid complete field support')
        self.area = float(self.geometry.area)
        self.vertices = shapely.get_coordinates(self.geometry)
        edges = np.sort(np.concatenate([triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]]), axis=1)
        unique, inverse = np.unique(edges, axis=0, return_inverse=True)
        adjoining = np.bincount(inverse, weights=np.tile(keep.astype(float), 3))
        zero = (~self.active[unique]).all(axis=1) & (adjoining > 0)
        self.zero_edges = self.points[unique[zero]]
        self.natural_boundary = shapely.union_all(shapely.linestrings(self.zero_edges))
        values = self.mapper.evaluate(self.rate, self.mapper.weights(self.zero_edges.mean(axis=1)))
        self.boundary_max_rate = float(np.max(np.abs(values)))
        if self.boundary_max_rate > 1e-12:
            raise ValueError('An identified natural boundary is nonzero')
        self.rings = [shapely.orient_polygons(p).exterior for p in polygon_parts(self.geometry)]
        self.ring_lengths = np.array([r.length for r in self.rings])
        self.ring_coordinates = [np.asarray(r.coords) for r in self.rings]
        self.ring_cumulative = [np.r_[0., np.cumsum(np.linalg.norm(np.diff(x, axis=0), axis=1))]
                                for x in self.ring_coordinates]

    def boundary_draw(self, random):
        index = int(random.choice(len(self.rings), p=self.ring_lengths/self.ring_lengths.sum()))
        arc = float(random.uniform(0., self.ring_lengths[index]))
        coordinates, cumulative = self.ring_coordinates[index], self.ring_cumulative[index]
        segment = min(int(np.searchsorted(cumulative, arc, side='right')-1), len(coordinates)-2)
        tangent = coordinates[segment+1]-coordinates[segment]
        tangent /= np.linalg.norm(tangent)
        point = coordinates[segment]+tangent*(arc-cumulative[segment])
        outward = np.array([tangent[1], -tangent[0]])
        return point, outward, dict(boundary_component=index, boundary_arclength_km=arc)

    def local_geometry(self, center, matrix):
        return shapely.transform(self.geometry, lambda x: to_local(x, center, matrix))

    def local_boundary(self, center, matrix):
        return shapely.transform(self.natural_boundary, lambda x: to_local(x, center, matrix))


class Platform:
    def __init__(self, seed):
        self.path = BASES/f'seed{seed}/base.npz'
        with np.load(self.path) as source:
            self.mask = source['mask'].astype(bool)
        self.geometry = mask_polygon(self.mask)
        self.outer_geometry = shapely.union_all([shapely.Polygon(p.exterior) for p in polygon_parts(self.geometry)])
        self.area = float(self.geometry.area)
        y, x = np.nonzero(self.mask)
        self.distance = np.zeros(self.mask.shape)
        self.distance[y, x] = shapely.distance(shapely.points(x+.5, y+.5), self.geometry.boundary)
        self.maximum_distance = float(self.distance.max())

    def interior_measure(self, field_geometry, bounds):
        """Area/mean boundary distance at the same 1 km centers as window.npz."""
        xmin, ymin, xmax, ymax = bounds
        x0, x1 = max(0, int(np.floor(xmin))), min(500, int(np.ceil(xmax)))
        y0, y1 = max(0, int(np.floor(ymin))), min(500, int(np.ceil(ymax)))
        y, x = np.nonzero(self.mask[y0:y1, x0:x1])
        y, x = y+y0, x+x0
        shapely.prepare(field_geometry)
        inside = shapely.contains_xy(field_geometry, x+.5, y+.5)
        distances = self.distance[y[inside], x[inside]]
        return int(len(distances)), float(distances.mean()) if len(distances) else 0.


@lru_cache(maxsize=8)
def platform(seed):
    return Platform(seed)
