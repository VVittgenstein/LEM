"""Planar use of upstream Park-Miller RNG and 3D Simplex noise.

Adapted from raguilar011095/planet_heightmap_generation at
cc2662b4edd52231c4f65d8765f3ef12cd82d9b7, js/rng.js and js/simplex-noise.js.
Upstream license: GNU GPL version 3. See LICENSE and THIRD_PARTY.md.
"""
import math
import numpy as np


class ParkMiller:
    def __init__(self, seed):
        self.state = abs(math.floor(seed*9301+49297)) % 2147483646 + 1

    def random(self):
        self.state = (self.state*16807) % 2147483647
        return (self.state-1)/2147483646

    def integer(self, maximum):
        return math.floor(self.random()*maximum)


class SimplexNoise:
    gradients = np.array([[1,1,0],[-1,1,0],[1,-1,0],[-1,-1,0],
                          [1,0,1],[-1,0,1],[1,0,-1],[-1,0,-1],
                          [0,1,1],[0,-1,1],[0,1,-1],[0,-1,-1]], dtype=float)

    def __init__(self, seed):
        rng = ParkMiller(seed)
        p = np.arange(256)
        for index in range(255, 0, -1):
            other = rng.integer(index+1)
            p[index], p[other] = p[other], p[index]
        self.perm = np.tile(p, 2)
        self.pm12 = self.perm % 12

    def noise3d(self, x, y, z):
        x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
        skew = (x+y+z)/3
        i, j, k = np.floor(x+skew).astype(int), np.floor(y+skew).astype(int), np.floor(z+skew).astype(int)
        unskew = (i+j+k)/6
        x0, y0, z0 = x-i+unskew, y-j+unskew, z-k+unskew
        conditions = [(x0>=y0)&(y0>=z0), (x0>=y0)&(y0<z0)&(x0>=z0),
                      (x0>=y0)&(x0<z0), (x0<y0)&(y0<z0),
                      (x0<y0)&(y0>=z0)&(x0<z0), (x0<y0)&(x0>=z0)]
        choices = [(1,0,0,1,1,0), (1,0,0,1,0,1), (0,0,1,1,0,1),
                   (0,0,1,0,1,1), (0,1,0,0,1,1), (0,1,0,1,1,0)]
        i1,j1,k1,i2,j2,k2 = [np.select(conditions, [c[d] for c in choices]) for d in range(6)]
        ii,jj,kk = i&255,j&255,k&255
        total = np.zeros(x.shape)
        for ox,oy,oz,u in ((0,0,0,0), (i1,j1,k1,1/6), (i2,j2,k2,1/3), (1,1,1,.5)):
            dx,dy,dz = x0-ox+u, y0-oy+u, z0-oz+u
            amplitude = np.maximum(0, .6-dx*dx-dy*dy-dz*dz)
            index = self.pm12[ii+ox+self.perm[jj+oy+self.perm[kk+oz]]]
            gradient = self.gradients[index]
            total += amplitude**4*(gradient[...,0]*dx+gradient[...,1]*dy+gradient[...,2]*dz)
        return 32*total
