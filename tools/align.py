import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import math, ezdxf
from geom import *
from shapely.geometry import LineString, Point
def chain(msp, layer, start, tol=0.15, maxgap=0.15):
    segs=[pts for e,pts in curves(msp,[layer])]
    out=[start]; cur=start; used=set()
    while True:
        best=None
        for i,s in enumerate(segs):
            if i in used: continue
            for rev in (False,True):
                p = s[::-1] if rev else s
                d=math.dist(cur,p[0])
                if d<tol and (best is None or d<best[0]): best=(d,i,p)
        if not best: break
        used.add(best[1]); out+=best[2][1:]; cur=out[-1]
    return LineString(out), used
class Align:
    def __init__(self, ls, sta0):
        self.ls=ls; self.sta0=sta0
    def pt(self, sta):
        return self.ls.interpolate(sta-self.sta0)
    def normal(self, sta):
        d=sta-self.sta0; a=self.ls.interpolate(max(d-0.25,0)); b=self.ls.interpolate(min(d+0.25,self.ls.length))
        tx,ty=b.x-a.x,b.y-a.y; n=math.hypot(tx,ty); tx/=n; ty/=n
        return (-ty,tx)  # left normal
    def offsets(self, sta, lines, reach=20):
        """signed offsets (+left) of intersections of the normal with given LineStrings"""
        p=self.pt(sta); nx,ny=self.normal(sta)
        seg=LineString([(p.x-nx*reach,p.y-ny*reach),(p.x+nx*reach,p.y+ny*reach)])
        res=[]
        for L in lines:
            x=seg.intersection(L)
            if x.is_empty: continue
            geoms = getattr(x,'geoms',[x])
            for g in geoms:
                if g.geom_type=='Point': res.append((g.x-p.x)*nx+(g.y-p.y)*ny)
        return sorted(res)
