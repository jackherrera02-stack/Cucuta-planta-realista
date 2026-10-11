"""Geometría de la planta realista (Vía Belén – Las Delicias, Cúcuta).

Construye, a partir de las capas del diseño V2 (PP y SEN), los polígonos de:
calzada por tipo de pavimento (flexible, TSD, rígido), losas y juntas del
rígido, cunetas, bordillos, andenes, isletas, demarcación y defensa metálica.
Todo en coordenadas CTM-12 (m). El resultado se guarda en build/geometria.pkl
y se usa en render.py y dxf_salida.py.

Uso:  python scripts/geometria.py
"""
import sys, os, math, json, pickle
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import numpy as np
import ezdxf
from ezdxf import path as dxfpath
from shapely.geometry import (LineString, Polygon, MultiPolygon, Point,
                              MultiLineString)
from shapely.ops import unary_union, substring
from geom import curves
from align import chain, Align

PP = os.path.join(ROOT, "dxf", "CUCUTA_DG_PP_001-06_V2.dxf")
SEN = os.path.join(ROOT, "dxf", "CUCUTA_DG_SEN_001-03_V2.dxf")
TOPO = os.path.join(ROOT, "dxf", "CAD-DG-LAS_DELICIAS.dxf")
BUILD = os.path.join(ROOT, "build")

EJE_INI = (5050794.454, 2427375.524)
S_EQ, STA_EQ = 171.358, 170.98          # ecuación de empalme eje 001 / eje 002
GLO_INI = (5050955.22, 2427383.247)     # eje de la glorieta
CUNA_ACE = (5050809.467, 2427373.536)   # cuña de aceleración
CUNA_DES = (5050879.1, 2427309.1)       # cuña de desaceleración
TRAMOS = {"E001 K0+000-K0+171": (0, 170.98), "E002 K0+171-K0+390": (170.98, 390),
          "K0+390-K0+600": (390, 600), "K0+600-K0+780": (600, 780),
          "K0+780-K1+540": (780, 1540), "K1+540-K1+609": (1540, 1700)}
PASO = 0.5                               # muestreo perpendicular (m)


def sta_of(s):
    return s if s <= S_EQ else STA_EQ + (s - S_EQ)


def s_of(sta):
    return sta if sta <= STA_EQ else S_EQ + (sta - STA_EQ)


def abscisa(sta):
    k = int(sta // 1000)
    return "K%d+%06.2f" % (k, sta - 1000 * k) if sta % 1 else "K%d+%03d" % (k, round(sta - 1000 * k))


def tipo_pav(sta):
    if sta < 390: return "FLEXIBLE"
    if sta < 600: return "TSD"
    if sta < 780: return "RIGIDO"
    return "TSD"


def U(geoms):
    g = unary_union([x for x in geoms if x is not None and not x.is_empty])
    return g.buffer(0) if not g.is_empty else g


def polys(g):
    if g is None or g.is_empty: return []
    if g.geom_type == "Polygon": return [g]
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon"]


# ---------------------------------------------------------------- muestreo
class Muestreo:
    """Offsets perpendiculares de un eje a las líneas de borde (BV, cuneta, andén)."""

    def __init__(self, ls, bv, cun, anden):
        self.al = Align(ls, 0.0)
        self.ls = ls
        self.bv, self.cun, self.anden = bv, cun, anden

    def pn(self, s):
        p = self.al.pt(s); n = self.al.normal(s)
        return np.array([p.x, p.y]), np.array(n)

    @staticmethod
    def _lado(offs, signo, desde=0.0, hasta=99.0):
        c = [o * signo for o in offs if desde + 1e-6 < o * signo <= hasta]
        return min(c) if c else None

    def lado(self, s, signo, reach=20):
        """Devuelve (bv, cun, and) en valor absoluto para el lado (+1 izq, -1 der)."""
        bv = self._lado(self.al.offsets(s, self.bv, reach), signo)
        cun = an = None
        if bv is not None:
            oc = self.al.offsets(s, self.cun, reach)
            cun = self._lado(oc, signo, bv + 0.12, bv + 0.95)
            if cun is not None:
                oa = self.al.offsets(s, self.anden, reach)
                an = self._lado(oa, signo, cun + 0.6, cun + 1.6)
        return bv, cun, an


def quad(m, s0, s1, a0, b0, a1, b1, signo):
    """Cuadrilátero entre offsets a..b (valores absolutos) del lado signo."""
    p0, n0 = m.pn(s0); p1, n1 = m.pn(s1)
    n0 = n0 * signo; n1 = n1 * signo
    q = Polygon([p0 + n0 * a0, p0 + n0 * b0, p1 + n1 * b1, p1 + n1 * a1])
    return q if q.is_valid else q.buffer(0)


def franja(m, ss, signo, f_ab):
    """Une cuadriláteros entre s consecutivos; f_ab(s) -> (a,b) o None."""
    out = []
    prev = None
    for s in ss:
        ab = f_ab(s)
        if ab is not None and prev is not None and prev[1] is not None:
            (s0, (a0, b0)) = prev[0], prev[1]
            if abs(b0 - ab[1]) < 2.5 and abs(a0 - ab[0]) < 2.5:
                out.append(quad(m, s0, s, a0, b0, ab[0], ab[1], signo))
        prev = (s, ab)
    return out


def main():
    os.makedirs(BUILD, exist_ok=True)
    doc = ezdxf.readfile(PP); msp = doc.modelspace()

    def lines(layer, excl=()):
        return [LineString(p) for e, p in curves(msp, [layer])
                if e.dxf.handle not in excl and LineString(p).length > 0.5]

    bv_all = {e.dxf.handle: p for e, p in curves(msp, ["BV"])}
    BVL = [LineString(p) for h, p in bv_all.items() if LineString(p).length > 0.5]
    CUN = lines("Cuneta"); AND = lines("ANDÉN")
    isleta_glo = Polygon(bv_all["258"]).buffer(0)
    isleta_acc = Polygon(bv_all["3C1"]).buffer(0)

    eje, _ = chain(msp, "SPI-C-ROAD-CNTR-N", EJE_INI)
    L = eje.length
    print("eje principal: %.2f m" % L)
    m = Muestreo(eje, BVL, CUN, AND)

    # Malla de s: cada 0,50 m + cambios de pavimento
    ss = set(np.round(np.arange(0, L, PASO), 3)) | {L}
    for sta in (390, 600, 780, 1540):
        ss.add(round(s_of(sta), 3))
    ss = sorted(ss)

    tabla = {}
    for s in ss:
        izq = m.lado(s, +1); der = m.lado(s, -1)
        tabla[s] = (izq, der)

    def en_glorieta(s):
        return 160.5 < s < 181.5

    # --- calzada del eje principal por tipo
    calz = {"FLEXIBLE": [], "TSD": [], "RIGIDO": []}
    por_tramo = {}
    for signo, k in ((+1, 0), (-1, 1)):
        prev = None
        for s in ss:
            bv = tabla[s][k][0]
            if bv is not None and signo > 0 and s < 44: bv = min(bv, 3.5)
            if en_glorieta(s): bv = None
            if bv is not None and prev is not None and prev[1] is not None and abs(prev[1] - bv) < 3.0:
                tp = tipo_pav(sta_of(0.5 * (prev[0] + s)))
                q = quad(m, prev[0], s, 0, prev[1], 0, bv, signo)
                calz[tp].append(q)
                smid = 0.5 * (prev[0] + s)
                tr = [k_ for k_, (a_, b_) in TRAMOS.items() if a_ <= sta_of(smid) < b_]
                if tr: por_tramo.setdefault(tr[0], []).append(q)
            prev = (s, bv)

    # --- laterales (franja cuneta/bordillo, cuneta sola, andén)
    cuneta, bordillo, anden = [], [], []
    for signo, k in ((+1, 0), (-1, 1)):
        prev = None
        for s in ss:
            cur = tabla[s][k]
            if en_glorieta(s): cur = (None, None, None)
            if prev is not None:
                (s0, (bv0, c0, a0)) = prev
                bv1, c1, a1 = cur
                if c0 is not None and c1 is not None and abs(c0 - c1) < 1 and abs(bv0 - bv1) < 1:
                    if a0 is not None and a1 is not None and abs(a0 - a1) < 1:
                        # franja 0,50 = cuneta (0,30) + bordillo (0,20) ; andén 1,00
                        cuneta.append(quad(m, s0, s, bv0, c0 - 0.20, bv1, c1 - 0.20, signo))
                        bordillo.append(quad(m, s0, s, c0 - 0.20, c0, c1 - 0.20, c1, signo))
                        anden.append(quad(m, s0, s, c0, a0, c1, a1, signo))
                    else:
                        cuneta.append(quad(m, s0, s, bv0, c0, bv1, c1, signo))
            prev = (s, cur)

    # --- glorieta: anillo (calzada 7,00 m) e isletas con bordillo 0,20
    glo_eje, _ = chain(msp, "SPI-C-ROAD-CNTR-N", GLO_INI)
    glo_poly = Polygon(glo_eje.coords).buffer(0)
    anillo = glo_poly.buffer(3.5, quad_segs=64).difference(isleta_glo)
    calz["FLEXIBLE"].append(anillo)
    # laterales exteriores del anillo (andén exterior parcial)
    mg = Muestreo(LineString(glo_eje.coords), BVL, CUN, AND)
    sg = np.arange(0, glo_eje.length, PASO)
    # solo el lado exterior (el que se aleja del centro) y con BV a ~3,50 m
    cx, cy = glo_poly.centroid.x, glo_poly.centroid.y
    glo_bord, glo_and = [], []
    for signo in (+1, -1):
        prev = None
        for s in sg:
            p, n = mg.pn(s)
            q = p + n * signo
            sale = math.dist(q, (cx, cy)) > math.dist(p, (cx, cy))
            cur = mg.lado(s, signo, reach=6) if sale else (None, None, None)
            if cur[0] is not None and not (3.3 < cur[0] < 3.7): cur = (None, None, None)
            if prev is not None:
                (s0, (bv0, c0, a0)) = prev
                bv1, c1, a1 = cur
                if None not in (c0, c1, a0, a1):
                    glo_bord.append(quad(mg, s0, s, bv0, c0, bv1, c1, signo))
                    glo_and.append(quad(mg, s0, s, c0, a0, c1, a1, signo))
            prev = (s, cur)
    bordillo += glo_bord; anden += glo_and
    print("glorieta exterior: bordillo %.1f m2, andén %.1f m2" % (U(glo_bord).area, U(glo_and).area))

    # --- cuñas del anillo vial (ancho = distancia al BV del lado izquierdo del
    #     sentido de circulación; en la convención de Align es el lado -1)
    cunas, ejes_cunas = {}, {}
    for nombre, ini, wmax in (("ACELERACION", CUNA_ACE, 4.6), ("DESACELERACION", CUNA_DES, 8.0)):
        ce, _ = chain(msp, "SPI-C-ROAD-CNTR-N", ini)
        mc = Muestreo(ce, BVL, CUN, AND)
        sc = list(np.arange(0, ce.length, PASO)) + [ce.length]
        qs = []
        for signo, lim in ((-1, wmax), (+1, 0.5)):   # lado de la cuña / holgura a la isleta
            prev = None
            for s in sc:
                w = mc.lado(s, signo, reach=10)[0]
                if w is not None and w > lim: w = None
                if prev is not None and prev[1] is not None and w is not None and abs(prev[1] - w) < 1:
                    qs.append(quad(mc, prev[0], s, 0, prev[1], 0, w, signo))
                prev = (s, w)
        cunas[nombre] = U(qs); ejes_cunas[nombre] = ce
        calz["FLEXIBLE"].append(cunas[nombre])
        print("cuña %s: eje %.1f m, %.1f m2" % (nombre, ce.length, cunas[nombre].area))

    print("calzada del eje por tramo (m2):")
    for k_, v_ in por_tramo.items():
        print("  %-22s %8.1f" % (k_, U(v_).area))
    isletas = U([isleta_glo, isleta_acc])
    calzada = {k: U(v) for k, v in calz.items()}
    # cierre morfológico (0,8 m) en el acceso para sellar ranuras entre cuña, eje e isleta
    zona_acc = isleta_acc.buffer(12)
    f = calzada["FLEXIBLE"]
    cerrado = f.buffer(0.8, join_style=2).buffer(-0.8, join_style=2).intersection(zona_acc)
    calzada["FLEXIBLE"] = U([f, cerrado])
    calzada = {k: v.difference(isletas) for k, v in calzada.items()}
    # prioridad: rígido > TSD > flexible en los empalmes
    calzada["TSD"] = calzada["TSD"].difference(calzada["RIGIDO"])
    calzada["FLEXIBLE"] = calzada["FLEXIBLE"].difference(U([calzada["RIGIDO"], calzada["TSD"]]))
    calz_total = U(list(calzada.values()))

    bord_isletas = U([isleta_glo.difference(isleta_glo.buffer(-0.20)),
                      isleta_acc.difference(isleta_acc.buffer(-0.20))])
    verde_isletas = U([isleta_glo.buffer(-0.20), isleta_acc.buffer(-0.20)])
    cuneta = U(cuneta).difference(calz_total)
    bordillo = U(bordillo + [bord_isletas]).difference(calz_total)
    anden = U(anden).difference(U([calz_total, cuneta, bordillo]))

    # --- losas del rígido: 3,50 m (carril) x 3,75 m, juntas perpendiculares al eje
    losas = []
    sta = 600.0
    while sta < 780 - 1e-6:
        sb = min(sta + 3.75, 780.0)
        s0, s1 = s_of(sta), s_of(sb)
        sv = list(np.arange(s0, s1, 0.25)) + [s1]
        for signo, k, carril in ((+1, 0, "IZQ"), (-1, 1, "DER")):
            pts_eje, pts_bv = [], []
            for s in sv:
                p, n = m.pn(s)
                w = m.lado(s, signo)[0] or 3.5
                pts_eje.append(p); pts_bv.append(p + n * signo * w)
            poly = Polygon(pts_eje + pts_bv[::-1]).buffer(0)
            l_in = LineString(pts_eje).length; l_out = LineString(pts_bv).length
            irregular = abs(l_out - l_in) > 0.10
            losas.append(dict(poly=poly, sta0=sta, sta1=sb, carril=carril,
                              irregular=irregular, l_eje=l_in, l_borde=l_out))
        sta = sb
    juntas = []
    sta = 600.0
    while sta <= 780 + 1e-6:
        s = s_of(sta); p, n = m.pn(s)
        wl = m.lado(s, +1)[0] or 3.5; wr = m.lado(s, -1)[0] or 3.5
        juntas.append(LineString([p - n * wr, p + n * wl]))
        sta += 3.75
    # junta longitudinal: eje entre K0+600 y K0+780
    juntas.append(substring(eje, s_of(600), s_of(780)))

    # --- juntas de andén cada 1,50 m (perpendiculares al eje)
    anden_juntas = []
    for mm, LL in ((m, L), (mg, glo_eje.length)):
        for s in np.arange(0.75, LL, 1.5):
            p, n = mm.pn(s)
            for signo in (+1, -1):
                ln = LineString([p + n * signo * 2.0, p + n * signo * 25.0]).intersection(anden)
                for g in getattr(ln, "geoms", [ln]):
                    if g.geom_type == "LineString" and 0.5 < g.length < 1.6:
                        anden_juntas.append(g)

    # --- demarcación (SEN V2)
    dem = demarcacion(calz_total.buffer(0.4))

    # --- abscisas (cada 10 m; rotuladas cada 100 m)
    absc = []
    for sta in np.arange(0, sta_of(L) + 1e-6, 10.0):
        s = min(s_of(sta), L); p, n = m.pn(s)
        absc.append(dict(sta=float(sta), s=float(s), p=p.tolist(), n=n.tolist()))

    # --- áreas
    areas = {k: v.area for k, v in calzada.items()}
    areas["TOTAL_CALZADA"] = calz_total.area
    areas["CUNETA"] = cuneta.area; areas["BORDILLO"] = bordillo.area; areas["ANDEN"] = anden.area
    areas["ISLETAS_VERDE"] = verde_isletas.area
    areas["LOSAS_N"] = len(losas); areas["LOSAS_IRREGULARES"] = sum(l["irregular"] for l in losas)
    ref = json.load(open(os.path.join(ROOT, "datos", "measures.json")))
    print("\nÁREAS (m2)            calculado   referencia")
    for k, r in (("FLEXIBLE", "CALZ_FLEXIBLE"), ("TSD", "CALZ_TSD"), ("RIGIDO", "CALZ_RIGIDO")):
        print("  %-18s %10.1f %10.1f" % (k, areas[k], ref["areas"][r]))
    print("  %-18s %10.1f %10.1f" % ("TOTAL", areas["TOTAL_CALZADA"], ref["area_calzada_total_union"]))
    print("  %-18s %10.1f %10.1f" % ("CUNETA+BORDILLO", areas["CUNETA"] + areas["BORDILLO"] - bord_isletas.area, ref["areas"]["CUNETA"]))
    print("  %-18s %10.1f %10.1f" % ("ANDEN", areas["ANDEN"], ref["areas"]["ANDEN"]))
    print("  losas: %d (irregulares %d)" % (areas["LOSAS_N"], areas["LOSAS_IRREGULARES"]))

    out = dict(eje=eje, glo_eje=glo_eje, cunas=cunas, ejes_cunas=ejes_cunas, calzada=calzada, calz_total=calz_total,
               cuneta=cuneta, bordillo=bordillo, anden=anden, isletas=isletas,
               verde_isletas=verde_isletas, losas=losas, juntas=juntas, anden_juntas=anden_juntas, dem=dem,
               abscisas=absc, areas=areas, L=L, fondo=fondo())
    with open(os.path.join(BUILD, "geometria.pkl"), "wb") as f:
        pickle.dump(out, f)
    json.dump({k: (round(v, 2) if isinstance(v, float) else v) for k, v in areas.items()},
              open(os.path.join(BUILD, "areas.json"), "w"), indent=1)
    print("OK -> build/geometria.pkl")


# ---------------------------------------------------------------- demarcación
def _dashes(ls, on, off):
    out = []; d = 0.0; L = ls.length
    while d < L:
        out.append(substring(ls, d, min(d + on, L))); d += on + off
    return [g for g in out if g.length > 0.02]


def demarcacion(zona):
    doc = ezdxf.readfile(SEN); msp = doc.modelspace()
    blanca, amarilla = [], []
    lineas = []          # para DXF: (pts, ancho, color, linetype)
    for e in msp.query('LWPOLYLINE[layer=="SEN_BASE_DEM"]'):
        w = e.dxf.const_width or 0.0
        if w <= 0: continue
        pts = [(v.x, v.y) for v in dxfpath.make_path(e).flattening(0.01)]
        if len(pts) < 2: continue
        ls = LineString(pts)
        lt = (e.dxf.get("linetype") or "BYLAYER")
        color = e.dxf.color
        amar = color == 40
        if "3m - 5m" in lt: tramos = _dashes(ls, 3.0, 5.0)
        elif "1m - 1m" in lt: tramos = _dashes(ls, 1.0, 1.0)
        else: tramos = [ls]
        g = U([t.buffer(w / 2, cap_style=2, join_style=2, mitre_limit=3) for t in tramos])
        (amarilla if amar else blanca).append(g)
        lineas.append(dict(pts=pts, ancho=w, amarilla=amar, linetype=lt, closed=e.closed))
    flechas = []
    for i in msp.query("INSERT"):
        if not (i.dxf.layer == "Sen_Horizontal" or i.dxf.name == "P_CP"): continue
        for v in i.virtual_entities():
            if v.dxftype() != "HATCH": continue
            g = Polygon()          # regla par-impar: los contornos interiores son huecos
            for p in dxfpath.from_hatch(v):
                pts = [(q.x, q.y) for q in p.flattening(0.01)]
                if len(pts) >= 3:
                    pg = Polygon(pts).buffer(0)
                    if pg.area > 0.01: g = g.symmetric_difference(pg)
            if not g.is_empty: flechas.append(g)
    fl = U(flechas)
    fl = fl.intersection(zona)
    blanca_g = U(blanca + [fl]).intersection(zona)
    amarilla_g = U(amarilla).intersection(zona)
    defensa = [LineString([(v.x, v.y) for v in dxfpath.make_path(e).flattening(0.01)])
               for e in msp.query('LWPOLYLINE[layer=="Defensa metálica"]')]
    return dict(blanca=blanca_g, amarilla=amarilla_g, flechas=fl, lineas=lineas, defensa=defensa)


# ---------------------------------------------------------------- fondo (levantamiento)
def fondo():
    doc = ezdxf.readfile(TOPO); msp = doc.modelspace()
    capas = {"Vía": 1.0, "Via": 1.0, "Via Concreto": 1.0, "Paramento": 0.8, "Cerca": 0.5,
             "Anden": 0.6, "Bordillo": 0.6, "Cuneta": 0.5, "Cuneta N": 0.5, "Muro": 0.6,
             "Canal": 0.5, "Canal C": 0.5, "Escalera": 0.4, "Rampa": 0.4, "Jardinera": 0.4,
             "Iglesia": 0.6, "Losa": 0.5, "Urbanizacion": 0.5, "Caño": 0.4}
    out = []
    for e, p in curves(msp, list(capas)):
        out.append((e.dxf.layer, p))
    return out


if __name__ == "__main__":
    main()
