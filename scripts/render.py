"""Render de la planta realista sobre la ortofoto (PNG 300 dpi + PDF).

Lee build/geometria.pkl (scripts/geometria.py) y genera en salida/:
  PLANTA_REALISTA_GENERAL.png / .pdf
  PLANTA_REALISTA_Lxx_<tramo>.png  y  PLANTA_REALISTA_LAMINAS.pdf

Las texturas se generan con numpy (ruido) y se aplican recortadas a cada
polígono rasterizado con PIL (con supermuestreo para suavizar bordes).

Uso:  python scripts/render.py [general] [laminas] [L01 L02 ...]
"""
import sys, os, math, pickle, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Rectangle, Polygon as MPoly, FancyArrow
from shapely.geometry import box, LineString
from shapely.ops import substring
from geometria import s_of, sta_of, polys

Image.MAX_IMAGE_PIXELS = None
SALIDA = os.path.join(ROOT, "salida")
ORTO = os.path.join(ROOT, "ortofoto", "ortofoto_las_delicias_10cm.jpg")
JGW = os.path.join(ROOT, "ortofoto", "ortofoto_las_delicias_10cm.jgw")
FUENTE = "DejaVu Sans"
plt.rcParams["font.family"] = FUENTE

# ------------------------------------------------------------------ colores
C = dict(
    flexible=(0x33, 0x33, 0x33), tsd=(0x76, 0x71, 0x6a), rigido=(0xc3, 0xc0, 0xb9),
    cuneta=(0xa9, 0xa7, 0xa1), cuneta_borde=(0x62, 0x60, 0x5b), bordillo=(0xcf, 0xcc, 0xc5),
    anden=(0xd6, 0xd3, 0xcc), anden_junta=(0x9c, 0x99, 0x92), junta=(0x3c, 0x3a, 0x37),
    blanca=(0xf5, 0xf5, 0xf5), amarilla=(0xf2, 0xc2, 0x00), verde=(0x5d, 0x7a, 0x3c),
    defensa=(0xa9, 0xb0, 0xb6), fondo=(0xff, 0xff, 0xff), topo=(0xc6, 0xc6, 0xc6),
    topo_via=(0xb2, 0xb2, 0xb2),
)


def leer_jgw():
    v = [float(x) for x in open(JGW).read().split()]
    return v[0], v[3], v[4], v[5]          # px, -py, X0 (centro px sup-izq), Y0


# ------------------------------------------------------------------ vista
class Vista:
    """Ventana en coordenadas CTM-12 rasterizada a res m/px."""

    def __init__(self, x0, y0, W, H, res):
        self.x0, self.y1, self.W, self.H, self.res = x0, y0 + H * res, W, H, res
        self.y0 = y0; self.x1 = x0 + W * res
        self.bbox = box(self.x0, self.y0, self.x1, self.y1)

    def px(self, coords, ss=1):
        r = self.res / ss
        return [((x - self.x0) / r, (self.y1 - y) / r) for x, y in coords]

    def mundo(self):
        """Coordenadas mundo de cada píxel (centro)."""
        xs = self.x0 + (np.arange(self.W) + 0.5) * self.res
        ys = self.y1 - (np.arange(self.H) + 0.5) * self.res
        return np.meshgrid(xs, ys)


def mascara(v, geom, ss=3):
    """Máscara 0..1 (antialias por supermuestreo) de polígonos shapely."""
    if geom is None or geom.is_empty: return np.zeros((v.H, v.W), np.float32)
    g = geom.intersection(v.bbox.buffer(5))
    img = Image.new("L", (v.W * ss, v.H * ss), 0); d = ImageDraw.Draw(img)
    for p in sorted(polys(g), key=lambda q: -q.area):
        d.polygon(v.px(p.exterior.coords, ss), fill=255)
        for h in p.interiors: d.polygon(v.px(h.coords, ss), fill=0)
    img = img.resize((v.W, v.H), Image.BOX)
    return np.asarray(img, np.float32) / 255.0


def mascara_lineas(v, lineas, ancho_px, ss=3):
    img = Image.new("L", (v.W * ss, v.H * ss), 0); d = ImageDraw.Draw(img)
    w = max(1, int(round(ancho_px * ss)))
    vb = v.bbox.buffer(5)
    for ls in lineas:
        if not ls.intersects(vb): continue
        for g in getattr(ls, "geoms", [ls]):
            cs = list(g.coords) if g.geom_type != "Polygon" else list(g.exterior.coords)
            if len(cs) >= 2: d.line(v.px(cs, ss), fill=255, width=w, joint="curve")
    img = img.resize((v.W, v.H), Image.BOX)
    return np.asarray(img, np.float32) / 255.0


def caja(m, pad=2):
    ys, xs = np.nonzero(m > 0.003)
    if len(xs) == 0: return None
    return (max(ys.min() - pad, 0), min(ys.max() + pad + 1, m.shape[0]),
            max(xs.min() - pad, 0), min(xs.max() + pad + 1, m.shape[1]))


def ruido(h, w, celda, rng):
    """Ruido de valor suave (media 0, desv ~1) con celdas de 'celda' px."""
    celda = max(celda, 1.0)
    gh, gw = int(h / celda) + 3, int(w / celda) + 3
    small = Image.fromarray(rng.standard_normal((gh, gw)).astype(np.float32), mode="F")
    big = small.resize((int(gw * celda), int(gh * celda)), Image.BICUBIC)
    a = np.asarray(big, np.float32)[:h, :w]
    return a / (a.std() + 1e-6)


def textura(h, w, base, rng, res, fino=6.0, grano_m=0.0, grano=0.0, mancha_m=1.5,
            mancha=4.0, motas=0.0, motas_amp=25.0, tinte=None):
    """Textura RGB float: base + ruido fino + grano + manchas + motas."""
    t = np.zeros((h, w), np.float32)
    t += rng.standard_normal((h, w)).astype(np.float32) * fino
    if grano:
        t += ruido(h, w, grano_m / res, rng) * grano
    if mancha:
        t += ruido(h, w, mancha_m / res, rng) * mancha
    if motas:
        m = rng.random((h, w)) < motas
        t += np.where(m, rng.choice([-1, 1], size=(h, w)) * motas_amp, 0).astype(np.float32)
    rgb = np.empty((h, w, 3), np.float32)
    for i in range(3):
        rgb[..., i] = base[i] + t * (1.0 if tinte is None else tinte[i])
    return rgb


def pintar(lienzo, m, color_fn, alpha=1.0):
    """color_fn(h, w) -> RGB; se pinta dentro de la caja de la máscara."""
    b = caja(m)
    if b is None: return
    y0, y1, x0, x1 = b
    mm = (m[y0:y1, x0:x1] * alpha)[..., None]
    col = color_fn(y1 - y0, x1 - x0) if callable(color_fn) else np.array(color_fn, np.float32)
    lienzo[y0:y1, x0:x1] = lienzo[y0:y1, x0:x1] * (1 - mm) + col * mm


def blur(m, r):
    if r <= 0: return m
    im = Image.fromarray(np.clip(m * 255, 0, 255).astype(np.uint8), "L")
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255.0


def desplazar(m, dx, dy):
    o = np.zeros_like(m)
    h, w = m.shape
    o[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = m[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)]
    return o


# ------------------------------------------------------------------ ortofoto
_ORTO = None


def orto_ventana(v):
    global _ORTO
    if _ORTO is None: _ORTO = Image.open(ORTO).convert("RGB")
    px, npy, X0, Y0 = leer_jgw()
    # X0,Y0 = centro del píxel superior izquierdo -> esquina = X0 - px/2
    a = v.res / px; c = (v.x0 - (X0 - px / 2)) / px
    e = v.res / (-npy); f = ((Y0 - npy / 2) - v.y1) / (-npy)
    rs = Image.BILINEAR if v.res < px * 1.5 else Image.BOX
    im = _ORTO.transform((v.W, v.H), Image.AFFINE, (a, 0, c, 0, e, f), resample=Image.BILINEAR)
    arr = np.asarray(im, np.float32)
    nod = (arr.max(axis=2) < 12).astype(np.uint8) * 255
    nod = Image.fromarray(nod).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(7))
    alpha = 1.0 - np.asarray(nod.filter(ImageFilter.GaussianBlur(1)), np.float32) / 255.0
    return arr, alpha


# ------------------------------------------------------------------ render
def render(G, v, detalle=True, seed=7):
    rng = np.random.default_rng(seed)
    res = v.res
    L = np.ones((v.H, v.W, 3), np.float32) * np.array(C["fondo"], np.float32)

    # levantamiento (fuera de la ortofoto se ve sobre blanco)
    vias = [LineString(p) for lay, p in G["fondo"] if lay in ("Vía", "Via", "Via Concreto")]
    otras = [LineString(p) for lay, p in G["fondo"] if lay not in ("Vía", "Via", "Via Concreto")]
    pintar(L, mascara_lineas(v, otras, max(1.0, 0.12 / res)), C["topo"])
    pintar(L, mascara_lineas(v, vias, max(1.2, 0.18 / res)), C["topo_via"])

    # ortofoto con máscara de "sin dato"
    arr, alpha = orto_ventana(v)
    L = L * (1 - alpha[..., None]) + arr * alpha[..., None]

    m_calz = {k: mascara(v, g) for k, g in G["calzada"].items()}
    m_cun = mascara(v, G["cuneta"]); m_bor = mascara(v, G["bordillo"])
    m_and = mascara(v, G["anden"]); m_ver = mascara(v, G["verde_isletas"])
    calz = np.clip(sum(m_calz.values()), 0, 1)
    huella = np.clip(calz + m_cun + m_bor + m_and + m_ver, 0, 1)

    # sombra proyectada de toda la obra (1–2 px, hacia el SE)
    d = max(1, int(round(0.12 / res))) if detalle else 1
    sh = np.clip(blur(desplazar(huella, d, d), 1.2 * d) - huella, 0, 1) * 0.55
    L *= (1 - sh[..., None])

    # andén con juntas cada 1,50 m
    pintar(L, m_and, lambda h, w: textura(h, w, C["anden"], rng, res, fino=3.5, mancha=3, mancha_m=2.0))
    if detalle:
        mj = mascara_lineas(v, G["anden_juntas"], max(0.8, 0.02 / res)) * m_and
        pintar(L, mj, C["anden_junta"], 0.85)
    # verde de isletas
    pintar(L, m_ver, lambda h, w: textura(h, w, C["verde"], rng, res, fino=10, grano_m=0.25, grano=10,
                                            mancha_m=2.5, mancha=10, tinte=(0.8, 1.0, 0.55)))
    # cuneta (concreto) con borde oscuro
    pintar(L, m_cun, lambda h, w: textura(h, w, C["cuneta"], rng, res, fino=4, mancha=3))
    borde_cun = [p.exterior for p in polys(G["cuneta"])] + [i for p in polys(G["cuneta"]) for i in p.interiors]
    pintar(L, mascara_lineas(v, borde_cun, max(0.9, 0.03 / res)) * np.clip(m_cun * 3, 0, 1), C["cuneta_borde"], 0.8)
    # bordillo con sombra lateral sutil
    sb = np.clip(blur(desplazar(m_bor, d, d), 0.8 * d) - m_bor, 0, 1) * 0.45
    L *= (1 - sb[..., None])
    pintar(L, m_bor, lambda h, w: textura(h, w, C["bordillo"], rng, res, fino=3, mancha=2))

    # pavimentos
    pintar(L, m_calz["FLEXIBLE"], lambda h, w: textura(
        h, w, C["flexible"], rng, res, fino=7, grano_m=0.04, grano=3, mancha_m=3.0, mancha=3.0,
        motas=0.035, motas_amp=18))
    pintar(L, m_calz["TSD"], lambda h, w: textura(
        h, w, C["tsd"], rng, res, fino=9, grano_m=max(0.06, res), grano=9, mancha_m=2.5, mancha=4.0,
        motas=0.06, motas_amp=30, tinte=(1.0, 0.97, 0.92)))
    rigido(G, v, L, m_calz["RIGIDO"], rng, detalle)

    # volumen: oscurecimiento suave hacia el borde de la calzada
    r = max(1.0, 0.25 / res)
    borde = np.clip(1 - blur(calz, r) * 1.0, 0, 1) * calz
    L *= (1 - 0.35 * borde[..., None])

    # demarcación
    m_bl = mascara(v, G["dem"]["blanca"]); m_am = mascara(v, G["dem"]["amarilla"])
    pintar(L, m_bl, lambda h, w: textura(h, w, C["blanca"], rng, res, fino=5, mancha=4, mancha_m=1.0), 0.97)
    pintar(L, m_am, lambda h, w: textura(h, w, C["amarilla"], rng, res, fino=5, mancha=4, mancha_m=1.0), 0.97)
    # defensa metálica
    dfn = G["dem"]["defensa"]
    if dfn:
        md = mascara_lineas(v, dfn, max(1.5, 0.32 / res))
        sdf = np.clip(blur(desplazar(md, d, d), d) - md, 0, 1) * 0.5
        L *= (1 - sdf[..., None])
        pintar(L, md, C["defensa"])
        pintar(L, mascara_lineas(v, dfn, max(0.7, 0.08 / res)), (0x6c, 0x72, 0x78), 0.9)
    return np.clip(L, 0, 255).astype(np.uint8)


def rigido(G, v, L, m_rig, rng, detalle):
    """Losas con leve variación de tono, malla en losas irregulares y juntas oscuras."""
    res = v.res
    b = caja(m_rig)
    if b is None: return
    y0, y1, x0, x1 = b
    idx = Image.new("I", (v.W, v.H), 0); d = ImageDraw.Draw(idx)
    losas = G["losas"]
    for i, l in enumerate(losas):
        p = l["poly"]
        if not p.intersects(v.bbox): continue
        for q in polys(p.buffer(0.03)):
            d.polygon(v.px(q.exterior.coords), fill=i + 1)
    idx = np.asarray(idx, np.int32)[y0:y1, x0:x1]
    trng = np.random.default_rng(11)
    tono = np.concatenate([[0], trng.normal(0, 4.0, len(losas))]).astype(np.float32)
    h, w = y1 - y0, x1 - x0
    tex = textura(h, w, C["rigido"], rng, res, fino=4.0, grano_m=0.05, grano=1.5, mancha_m=1.2, mancha=3.0,
                  motas=0.01, motas_amp=12)
    tex += tono[idx][..., None]
    if detalle and res <= 0.1:
        # malla (1/2" @ 0,30 m) insinuada en losas irregulares, orientada con la losa
        ang = np.zeros(len(losas) + 1, np.float32); irr = np.zeros(len(losas) + 1, bool)
        eje = G["eje"]
        for i, l in enumerate(losas):
            s0, s1 = s_of(l["sta0"]), s_of(l["sta1"])
            a, c = eje.interpolate(s0), eje.interpolate(s1)
            ang[i + 1] = math.atan2(c.y - a.y, c.x - a.x); irr[i + 1] = l["irregular"]
        X, Y = v.mundo(); X = X[y0:y1, x0:x1] - 5051000; Y = Y[y0:y1, x0:x1] - 2427000
        th = ang[idx]
        u = X * np.cos(th) + Y * np.sin(th); vv = -X * np.sin(th) + Y * np.cos(th)
        sig = max(res * 0.45, 0.012)
        du = np.abs((u / 0.30) % 1 - 0.5) * 0.30; dv = np.abs((vv / 0.30) % 1 - 0.5) * 0.30
        g = np.maximum(np.exp(-((0.15 - du) / sig) ** 2), np.exp(-((0.15 - dv) / sig) ** 2))
        tex -= (g * 14 * irr[idx])[..., None]
    mm = m_rig[y0:y1, x0:x1][..., None]
    L[y0:y1, x0:x1] = L[y0:y1, x0:x1] * (1 - mm) + tex * mm
    # juntas (0,01–0,02 m) en gris oscuro
    mj = mascara_lineas(v, G["juntas"], max(1.0, 0.018 / res)) * np.clip(m_rig * 2, 0, 1)
    pintar(L, mj, C["junta"], 0.9)


# ------------------------------------------------------------------ lámina
LAMINAS = [
    ("L01", 0, 200, "K0+000 – K0+200", "Acceso, cuñas del anillo vial y glorieta"),
    ("L02", 180, 420, "K0+180 – K0+420", "Eje 002 – pavimento flexible"),
    ("L03", 380, 620, "K0+380 – K0+620", "Transición flexible – TSD (5,00 m)"),
    ("L04", 580, 800, "K0+580 – K0+800", "Pavimento rígido – despiece de losas"),
    ("L05", 780, 1120, "K0+780 – K1+120", "TSD 6,00 m con cunetas"),
    ("L06", 1100, 1400, "K1+100 – K1+400", "TSD 6,00 m con cunetas"),
    ("L07", 1380, 1609.4, "K1+380 – K1+609", "TSD 6,00 m / 5,00 m – tramo final"),
]

PROYECTO = "VÍA BELÉN – LAS DELICIAS · CÚCUTA (NORTE DE SANTANDER)"
SISTEMA = "MAGNA-SIRGAS / Origen Nacional (CTM-12) · metros"


def texto_halo(ax, x, y, s, **kw):
    t = ax.text(x, y, s, **kw)
    t.set_path_effects([pe.withStroke(linewidth=2.2, foreground="white")])
    return t


def abscisas(ax, G, v, sta_a, sta_b, cada_lbl, cada_tick, tam):
    obra = G["calz_total"].union(G["isletas"]).union(G["anden"]).union(G["cuneta"])
    for a in G["abscisas"]:
        sta = a["sta"]
        if not (sta_a - 1e-6 <= sta <= sta_b + 1e-6): continue
        if round(sta) % cada_tick: continue
        p = np.array(a["p"]); n = np.array(a["n"])
        if not v.bbox.buffer(-2).contains(LineString([p - n * 9, p + n * 9]).centroid): continue
        mayor = round(sta) % cada_lbl == 0
        l0 = 6.0
        while l0 < 30 and LineString([p + n * l0, p + n * (l0 + 2.5)]).intersects(obra): l0 += 1.0
        l1 = l0 + (4.0 if mayor else 2.0)
        q0, q1 = p + n * l0, p + n * l1
        ax.plot([q0[0], q1[0]], [q0[1], q1[1]], color="k", lw=0.8 if mayor else 0.5, zorder=6,
                path_effects=[pe.withStroke(linewidth=1.8, foreground="white")])
        if mayor:
            ang = math.degrees(math.atan2(n[1], n[0]))
            if ang > 90: ang -= 180; ha = "right"
            elif ang < -90: ang += 180; ha = "right"
            else: ha = "left"
            q = p + n * (l1 + 0.8)
            k = int(sta // 1000)
            texto_halo(ax, q[0], q[1], "K%d+%03d" % (k, round(sta - 1000 * k)), fontsize=tam, rotation=ang,
                       rotation_mode="anchor", ha=ha, va="center", zorder=7, fontweight="bold", clip_on=True)
            ax.plot(*p, marker="o", ms=2.2, color="#c00000", zorder=6, mec="white", mew=0.5)


def norte(ax, x, y, tam=0.06):
    ax.add_patch(MPoly([(x, y + tam), (x - tam * 0.35, y - tam * 0.45), (x, y - tam * 0.2)],
                       closed=True, fc="k", ec="k", lw=0.6, transform=ax.transAxes))
    ax.add_patch(MPoly([(x, y + tam), (x + tam * 0.35, y - tam * 0.45), (x, y - tam * 0.2)],
                       closed=True, fc="white", ec="k", lw=0.6, transform=ax.transAxes))
    ax.text(x, y + tam * 1.25, "N", ha="center", va="bottom", fontsize=11, fontweight="bold", transform=ax.transAxes)


def escala_grafica(fig, rect, escala, largo_m):
    ax = fig.add_axes(rect); ax.set_xlim(0, largo_m); ax.set_ylim(0, 1); ax.axis("off")
    n = 5; paso = largo_m / n
    for i in range(n):
        ax.add_patch(Rectangle((i * paso, 0.45), paso, 0.18, fc="k" if i % 2 == 0 else "white", ec="k", lw=0.6))
        ax.text(i * paso, 0.25, "%g" % (i * paso), ha="center", va="top", fontsize=7)
    ax.text(largo_m, 0.25, "%g m" % largo_m, ha="center", va="top", fontsize=7)
    ax.text(largo_m / 2, 0.85, "ESCALA 1:%d" % escala, ha="center", va="bottom", fontsize=9, fontweight="bold")


def muestra(tipo, G, n=90, res=0.03):
    """Parche de textura para las convenciones."""
    rng = np.random.default_rng(3)
    mapa = {
        "FLEXIBLE": lambda: textura(n, n * 2, C["flexible"], rng, res, fino=7, grano_m=0.04, grano=3, mancha=3, motas=0.035, motas_amp=18),
        "TSD": lambda: textura(n, n * 2, C["tsd"], rng, res, fino=9, grano_m=0.06, grano=9, mancha=4, motas=0.06, motas_amp=30, tinte=(1, .97, .92)),
        "RIGIDO": lambda: textura(n, n * 2, C["rigido"], rng, res, fino=4, mancha=3),
        "CUNETA": lambda: textura(n, n * 2, C["cuneta"], rng, res, fino=4, mancha=3),
        "BORDILLO": lambda: textura(n, n * 2, C["bordillo"], rng, res, fino=3, mancha=2),
        "ANDEN": lambda: textura(n, n * 2, C["anden"], rng, res, fino=3.5, mancha=3),
        "VERDE": lambda: textura(n, n * 2, C["verde"], rng, res, fino=10, grano_m=0.25, grano=10, mancha=10, tinte=(.8, 1, .55)),
    }
    a = mapa[tipo]()
    if tipo == "RIGIDO":
        a[:, n - 1:n + 1] = C["junta"]; a[n // 2 - 1:n // 2 + 1, :] = C["junta"]
    if tipo == "ANDEN":
        for x in range(0, 2 * n, n // 2): a[:, x:x + 1] = C["anden_junta"]
    if tipo == "CUNETA":
        a[:2] = C["cuneta_borde"]; a[-2:] = C["cuneta_borde"]
    return np.clip(a, 0, 255).astype(np.uint8)


def convenciones(fig, rect, G, cols=1, tam=7.5):
    ax = fig.add_axes(rect); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    items = [("FLEXIBLE", "Pavimento flexible (MDC-19)"), ("TSD", "Tratamiento superficial doble (TSD)"),
             ("RIGIDO", "Pavimento rígido MR-45 (losas 3,50 × 3,75 m)"),
             ("MALLA", "Losa irregular con malla 1/2\" @ 0,30"),
             ("CUNETA", "Cuneta en concreto"), ("BORDILLO", "Bordillo"),
             ("ANDEN", "Andén en concreto (juntas c/1,50 m)"), ("VERDE", "Isleta (zona verde)"),
             ("BLANCA", "Demarcación blanca"), ("AMARILLA", "Demarcación amarilla (eje)"),
             ("DEFENSA", "Defensa metálica"), ("EJE", "Abscisa sobre el eje de diseño"),
             ("TOPO", "Levantamiento (fuera de ortofoto)")]
    filas = math.ceil(len(items) / cols)
    ax.text(0, 1, "CONVENCIONES", fontsize=tam + 1.5, fontweight="bold", va="top")
    h = 0.92 / (filas + 0.3)
    for i, (k, txt) in enumerate(items):
        c, r = divmod(i, filas)
        x = c / cols; y = 0.9 - (r + 1) * h
        sw, shh = 0.14 / cols * 1.0, h * 0.62
        if k in ("FLEXIBLE", "TSD", "RIGIDO", "CUNETA", "BORDILLO", "ANDEN", "VERDE"):
            ax.imshow(muestra(k, G), extent=(x, x + sw, y, y + shh), aspect="auto", zorder=2)
            ax.add_patch(Rectangle((x, y), sw, shh, fill=False, ec="#555", lw=0.5, zorder=3))
        elif k == "MALLA":
            a = muestra("RIGIDO", G).astype(np.float32)
            for j in range(0, a.shape[1], 6): a[:, j] -= 22
            for j in range(0, a.shape[0], 6): a[j, :] -= 22
            ax.imshow(np.clip(a, 0, 255).astype(np.uint8), extent=(x, x + sw, y, y + shh), aspect="auto", zorder=2)
            ax.add_patch(Rectangle((x, y), sw, shh, fill=False, ec="#555", lw=0.5, zorder=3))
        elif k in ("BLANCA", "AMARILLA"):
            ax.imshow(muestra("FLEXIBLE", G), extent=(x, x + sw, y, y + shh), aspect="auto", zorder=2)
            col = np.array(C["blanca" if k == "BLANCA" else "amarilla"]) / 255
            if k == "BLANCA":
                for j in range(3):
                    ax.add_patch(Rectangle((x + 0.008 + j * sw / 3, y + shh * 0.42), sw / 5, shh * 0.16, fc=col, ec="none", zorder=3))
            else:
                ax.add_patch(Rectangle((x, y + shh * 0.34), sw, shh * 0.1, fc=col, ec="none", zorder=3))
                ax.add_patch(Rectangle((x, y + shh * 0.56), sw, shh * 0.1, fc=col, ec="none", zorder=3))
        elif k == "DEFENSA":
            ax.plot([x, x + sw], [y + shh / 2] * 2, color=np.array(C["defensa"]) / 255, lw=3.5, solid_capstyle="butt")
            ax.plot([x, x + sw], [y + shh / 2] * 2, color="#6c7278", lw=0.8)
        elif k == "EJE":
            ax.plot([x + sw * 0.3, x + sw * 0.75], [y + shh / 2] * 2, color="k", lw=0.8)
            ax.plot(x + sw * 0.15, y + shh / 2, "o", ms=3, color="#c00000", mec="white", mew=0.5)
        elif k == "TOPO":
            ax.add_patch(Rectangle((x, y), sw, shh, fc="white", ec="#555", lw=0.5))
            ax.plot([x + 0.01, x + sw - 0.01], [y + shh * 0.3, y + shh * 0.7], color="#b2b2b2", lw=1)
            ax.plot([x + 0.01, x + sw - 0.01], [y + shh * 0.6, y + shh * 0.9], color="#c6c6c6", lw=0.8)
        ax.text(x + sw + 0.025, y + shh / 2, txt, fontsize=tam, va="center")


def ticks_coord(ax, v, paso):
    from matplotlib.ticker import FixedLocator, FuncFormatter
    fx = lambda x, _: "E %s" % format(int(round(x)), ",").replace(",", ".")
    fy = lambda y, _: "N %s" % format(int(round(y)), ",").replace(",", ".")
    ax.xaxis.set_major_locator(FixedLocator(np.arange(math.ceil(v.x0 / paso) * paso, v.x1, paso)))
    ax.yaxis.set_major_locator(FixedLocator(np.arange(math.ceil(v.y0 / paso) * paso, v.y1, paso)))
    ax.xaxis.set_major_formatter(FuncFormatter(fx)); ax.yaxis.set_major_formatter(FuncFormatter(fy))
    ax.tick_params(labelsize=6, length=3, direction="in", top=True, right=True, labeltop=False, labelright=False)
    plt.setp(ax.get_yticklabels(), rotation=90, va="center")
    xs = ax.get_xticks(); ys = ax.get_yticks()
    X, Y = np.meshgrid(xs, ys)
    ax.plot(X.ravel(), Y.ravel(), "+", ms=7, mew=0.6, color="#222", alpha=0.7, zorder=4,
            path_effects=[pe.withStroke(linewidth=1.6, foreground="white")])


def localizacion(fig, rect, G, v):
    ax = fig.add_axes(rect)
    for k, col in (("FLEXIBLE", "#3a3a3a"), ("TSD", "#8a847a"), ("RIGIDO", "#b5b2aa")):
        for p in polys(G["calzada"][k].buffer(4)):
            ax.add_patch(MPoly(np.array(p.exterior.coords), closed=True, fc=col, ec="none"))
    ax.add_patch(Rectangle((v.x0, v.y0), v.x1 - v.x0, v.y1 - v.y0, fill=False, ec="#c00000", lw=1.2))
    x0, y0, x1, y1 = G["calz_total"].bounds
    ax.set_xlim(x0 - 20, x1 + 20); ax.set_ylim(y0 - 20, y1 + 20); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_linewidth(0.5)
    ax.set_title("LOCALIZACIÓN DE LA LÁMINA", fontsize=7, fontweight="bold", pad=3)


def rotulo(fig, rect, titulo, subtitulo, lamina, escala, formato):
    ax = fig.add_axes(rect); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_linewidth(1.0)
    filas = [(0.80, 1.00), (0.56, 0.80), (0.38, 0.56), (0.20, 0.38), (0.0, 0.20)]
    for a, b in filas[1:]: ax.axhline(b, color="k", lw=0.6)
    ax.text(0.5, 0.90, "PLANTA REALISTA", ha="center", va="center", fontsize=13, fontweight="bold")
    ax.text(0.5, 0.835, "DISEÑO GEOMÉTRICO V2", ha="center", va="center", fontsize=8)
    ax.text(0.04, 0.75, "PROYECTO", fontsize=6, color="#555", va="center")
    ax.text(0.5, 0.67, "Vía Belén – Las Delicias\nCúcuta, Norte de Santander", ha="center", va="center", fontsize=8.5,
            fontweight="bold", linespacing=1.3)
    ax.text(0.04, 0.53, "CONTENIDO", fontsize=6, color="#555", va="center")
    ax.text(0.5, 0.455, titulo + ("\n" + subtitulo if subtitulo else ""), ha="center", va="center", fontsize=8,
            linespacing=1.3)
    ax.text(0.04, 0.35, "SISTEMA", fontsize=6, color="#555", va="center")
    ax.text(0.5, 0.28, "MAGNA-SIRGAS Origen Nacional\n(CTM-12) · cotas en metros", ha="center", va="center",
            fontsize=7, linespacing=1.3)
    ax.axvline(0.5, ymin=0, ymax=0.2, color="k", lw=0.6)
    ax.text(0.25, 0.15, "ESCALA", fontsize=6, color="#555", ha="center")
    ax.text(0.25, 0.07, "1:%d · %s" % (escala, formato), fontsize=8, ha="center", fontweight="bold")
    ax.text(0.75, 0.15, "LÁMINA", fontsize=6, color="#555", ha="center")
    ax.text(0.75, 0.07, lamina, fontsize=10, ha="center", fontweight="bold")


def nota(fig, x, y, w, tam=6):
    txt = ("Fuente: CUCUTA_DG_PP_001-06_V2 y CUCUTA_DG_SEN_001-03_V2 (diseño V2); "
           "ortofoto 10 cm; levantamiento CAD-DG Las Delicias. Anchos tomados de las capas BV, "
           "Cuneta y ANDÉN con offset perpendicular al eje cada 0,50 m. Abscisas: eje 001 + eje 002 "
           "(ecuación K0+171,358 = K0+170,980).")
    import textwrap
    fig.text(x, y, "\n".join(textwrap.wrap(txt, int(w * 72 / (tam * 0.56)))), fontsize=tam, color="#333", va="top",
             linespacing=1.25)


def lamina(G, cod, sta_a, sta_b, titulo, sub, num, total, dpi=300):
    eje = G["eje"]
    s_a, s_b = s_of(sta_a), min(s_of(sta_b), eje.length)
    g = substring(eje, s_a, s_b).buffer(12)
    if cod == "L01":
        g = g.union(G["cunas"]["ACELERACION"].buffer(5)).union(G["cunas"]["DESACELERACION"].buffer(5))
    bx0, by0, bx1, by1 = g.bounds
    PW, PH = 17.0, 11.0                       # doble carta (tabloide) horizontal
    mx, my, panel = 0.45, 0.45, 3.35
    mw = PW - 2 * mx - panel - 0.2; mh = PH - 2 * my
    escala = 500 if (bx1 - bx0) <= mw * 0.0254 * 500 and (by1 - by0) <= mh * 0.0254 * 500 else 1000
    W = int(round(mw * dpi)); H = int(round(mh * dpi)); res = escala * 0.0254 / dpi
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    v = Vista(cx - W * res / 2, cy - H * res / 2, W, H, res)
    print("  %s %s  1:%d  %dx%d px  res %.3f m/px" % (cod, titulo, escala, W, H, res))
    img = render(G, v, detalle=True, seed=num)

    fig = plt.figure(figsize=(PW, PH), dpi=dpi)
    fig.add_artist(Rectangle((0.15 / PW, 0.15 / PH), 1 - 0.3 / PW, 1 - 0.3 / PH, transform=fig.transFigure,
                             fill=False, lw=1.6, ec="k"))
    ax = fig.add_axes([mx / PW, my / PH, mw / PW, mh / PH])
    ax.imshow(img, extent=(v.x0, v.x1, v.y0, v.y1), interpolation="none", zorder=1)
    ax.set_xlim(v.x0, v.x1); ax.set_ylim(v.y0, v.y1); ax.set_aspect("equal")
    abscisas(ax, G, v, -1, 2000, 50 if escala >= 1000 else 20, 10, 7.5)
    ticks_coord(ax, v, 50 if escala >= 1000 else 25)
    for s in ax.spines.values(): s.set_linewidth(1.0)
    norte(ax, 0.955, 0.88)
    texto_halo(ax, 0.012, 0.985, "%s  ·  %s" % (titulo, sub), transform=ax.transAxes, fontsize=10,
               fontweight="bold", va="top")

    px0 = (PW - mx - panel) / PW; pw = (panel - 0.05) / PW
    rotulo(fig, [px0, 0.45 / PH, pw, 3.2 / PH], "Planta realista – tramo %s" % titulo, sub,
           "%d / %d" % (num, total), escala, "doble carta")
    escala_grafica(fig, [px0 + 0.1 / PW, 3.75 / PH, pw - 0.2 / PW, 0.55 / PH], escala, 50 if escala >= 1000 else 25)
    nota(fig, px0, 4.78 / PH, pw * PW, tam=5.5)
    convenciones(fig, [px0, 4.95 / PH, pw, 3.25 / PH], G)
    localizacion(fig, [px0, 8.4 / PH, pw, 2.1 / PH], G, v)
    nombre = "PLANTA_REALISTA_%s_%s" % (cod, titulo.replace(" – ", "_").replace("+", ""))
    ruta = os.path.join(SALIDA, nombre + ".png")
    fig.savefig(ruta, dpi=dpi)
    plt.close(fig)
    return ruta


def general(G, dpi=250):
    escala = 2000
    PW, PH = 24.0, 14.0
    mx, my = 0.45, 0.45
    banda = 3.1
    mw = PW - 2 * mx; mh = PH - 2 * my - banda - 0.15
    W = int(round(mw * dpi)); H = int(round(mh * dpi)); res = escala * 0.0254 / dpi
    bx0, by0, bx1, by1 = G["calz_total"].bounds
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    v = Vista(cx - W * res / 2, cy - H * res / 2, W, H, res)
    print("  GENERAL 1:%d  %dx%d px  res %.3f m/px" % (escala, W, H, res))
    img = render(G, v, detalle=True, seed=1)
    fig = plt.figure(figsize=(PW, PH), dpi=dpi)
    fig.add_artist(Rectangle((0.15 / PW, 0.15 / PH), 1 - 0.3 / PW, 1 - 0.3 / PH, transform=fig.transFigure,
                             fill=False, lw=1.8, ec="k"))
    ax = fig.add_axes([mx / PW, (my + banda + 0.15) / PH, mw / PW, mh / PH])
    ax.imshow(img, extent=(v.x0, v.x1, v.y0, v.y1), interpolation="none", zorder=1)
    ax.set_xlim(v.x0, v.x1); ax.set_ylim(v.y0, v.y1); ax.set_aspect("equal")
    abscisas(ax, G, v, -1, 2000, 100, 20, 9)
    ticks_coord(ax, v, 100)
    norte(ax, 0.965, 0.83, 0.07)
    texto_halo(ax, 0.01, 0.98, "PLANTA GENERAL – VÍA BELÉN – LAS DELICIAS (K0+000 – K1+609,40)",
               transform=ax.transAxes, fontsize=15, fontweight="bold", va="top")
    # tramos de pavimento (rótulos)
    for sta, txt in ((80, "FLEXIBLE\n7,00 m"), (290, "FLEXIBLE\n7,00 m"), (495, "TSD 5,00 m"),
                     (690, "RÍGIDO 7,00 m\n(losas 3,50×3,75)"), (1000, "TSD 6,00 m\n+ cunetas"),
                     (1330, "TSD 6,00 m\n+ cunetas"), (1575, "TSD 5,00 m")):
        a = [x for x in G["abscisas"] if abs(x["sta"] - sta) < 5.1][0]
        p = np.array(a["p"]); n = np.array(a["n"])
        q = p - n * 22
        texto_halo(ax, q[0], q[1], txt, fontsize=8, ha="center", va="center", color="#222", style="italic",
                   clip_on=True)
    by = my / PH; bh = banda / PH
    rotulo(fig, [(PW - mx - 5.6) / PW, by, 5.6 / PW, bh], "Planta general", "Pavimentos, cunetas, andenes y demarcación",
           "GENERAL", escala, "%g×%g in" % (PW, PH))
    convenciones(fig, [mx / PW, by, 9.6 / PW, bh * 0.98], G, cols=2, tam=8)
    escala_grafica(fig, [(mx + 10.2) / PW, by + bh * 0.62, 4.5 / PW, bh * 0.3], escala, 100)
    # cuadro de áreas
    A = G["areas"]
    axt = fig.add_axes([(mx + 10.2) / PW, by, 4.5 / PW, bh * 0.58]); axt.axis("off")
    filas = [("Calzada flexible (MDC-19)", A["FLEXIBLE"]), ("Calzada TSD", A["TSD"]),
             ("Calzada rígida (%d losas)" % A["LOSAS_N"], A["RIGIDO"]), ("Total calzada", A["TOTAL_CALZADA"]),
             ("Cunetas", A["CUNETA"]), ("Bordillos", A["BORDILLO"]), ("Andenes", A["ANDEN"])]
    axt.text(0, 1, "CUADRO DE ÁREAS (m²)", fontsize=9, fontweight="bold", va="top")
    for i, (t, a) in enumerate(filas):
        y = 0.82 - i * 0.12
        axt.text(0.02, y, t, fontsize=8, va="top", fontweight="bold" if t.startswith("Total") else "normal")
        axt.text(0.98, y, format(round(a, 1), ",.1f").replace(",", "X").replace(".", ",").replace("X", "."),
                 fontsize=8, va="top", ha="right", fontweight="bold" if t.startswith("Total") else "normal")
    nota(fig, (mx + 15.0) / PW, by + bh * 0.97, 2.3, tam=6.5)
    ruta = os.path.join(SALIDA, "PLANTA_REALISTA_GENERAL.png")
    fig.savefig(ruta, dpi=dpi)
    plt.close(fig)
    pdf(ruta, [ruta], os.path.join(SALIDA, "PLANTA_REALISTA_GENERAL.pdf"), dpi)
    return ruta


def pdf(_, pngs, destino, dpi):
    ims = [Image.open(p).convert("RGB") for p in pngs]
    ims[0].save(destino, save_all=True, append_images=ims[1:], resolution=dpi, quality=88)
    print("  PDF ->", os.path.relpath(destino, ROOT))


def main():
    args = sys.argv[1:] or ["general", "laminas"]
    os.makedirs(SALIDA, exist_ok=True)
    G = pickle.load(open(os.path.join(ROOT, "build", "geometria.pkl"), "rb"))
    if "general" in args:
        general(G)
    sel = [l for l in LAMINAS if "laminas" in args or l[0] in args]
    rutas = []
    for i, (cod, a, b, t, sub) in enumerate(LAMINAS, 1):
        if (cod, a, b, t, sub) in sel:
            rutas.append(lamina(G, cod, a, b, t, sub, i, len(LAMINAS)))
    if "laminas" in args and rutas:
        pdf(None, rutas, os.path.join(SALIDA, "PLANTA_REALISTA_LAMINAS.pdf"), 300)


if __name__ == "__main__":
    main()
