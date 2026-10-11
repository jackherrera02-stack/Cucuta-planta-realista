import ezdxf, math
from ezdxf import path
def pts_of(e, tol=0.01):
    p = path.make_path(e)
    return [(v.x, v.y) for v in p.flattening(tol)]
def length(pts): return sum(math.dist(pts[i], pts[i+1]) for i in range(len(pts)-1))
def sig(pts):
    return (round(pts[0][0],2), round(pts[0][1],2), round(pts[-1][0],2), round(pts[-1][1],2), len(pts))
def curves(msp, layers, types=("LWPOLYLINE","POLYLINE","LINE","ARC")):
    seen=set(); out=[]
    for e in msp:
        if e.dxf.layer not in layers or e.dxftype() not in types: continue
        try: pts=pts_of(e)
        except Exception: continue
        if len(pts)<2: continue
        s=(e.dxf.layer,)+sig(pts)
        if s in seen: continue
        seen.add(s); out.append((e,pts))
    return out
