"""DXF de la planta realista (salida/PLANTA_REALISTA.dxf), en coordenadas CTM-12.

Capas: PAV_FLEXIBLE, PAV_TSD, PAV_RIGIDO_LOSAS, PAV_RIGIDO_MALLA, PAV_RIGIDO_JUNTAS,
CUNETA, BORDILLO, ANDEN, ISLETA_VERDE, DEMARCACION_BLANCA, DEMARCACION_AMARILLA,
DEFENSA_METALICA, EJE, ABSCISAS, LEVANTAMIENTO y ORTOFOTO (entidad IMAGE con ruta
relativa ..\\ortofoto\\ortofoto_las_delicias_10cm.jpg, insertada según el .jgw).

Uso:  python scripts/dxf_salida.py   (requiere build/geometria.pkl)
"""
import sys, os, math, pickle
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import numpy as np
import ezdxf
from ezdxf import colors, const
from ezdxf.enums import TextEntityAlignment
from PIL import Image
from geometria import polys, s_of
from render import leer_jgw, C, ORTO

Image.MAX_IMAGE_PIXELS = None
DESTINO = os.path.join(ROOT, "salida", "PLANTA_REALISTA.dxf")
ORTO_REL = "..\\ortofoto\\ortofoto_las_delicias_10cm.jpg"

CAPAS = {  # nombre: (ACI, rgb, descripción)
    "ORTOFOTO": (7, None, "Ortofoto 10 cm (IMAGE, ruta relativa)"),
    "LEVANTAMIENTO": (253, (190, 190, 190), "Levantamiento topográfico existente (gris claro)"),
    "ANDEN": (254, C["anden"], "Andén en concreto"),
    "ANDEN_JUNTAS": (8, C["anden_junta"], "Juntas de andén c/1,50 m"),
    "BORDILLO": (254, C["bordillo"], "Bordillo"),
    "CUNETA": (9, C["cuneta"], "Cuneta en concreto"),
    "ISLETA_VERDE": (94, C["verde"], "Isletas (zona verde)"),
    "PAV_FLEXIBLE": (250, C["flexible"], "Pavimento flexible MDC-19"),
    "PAV_TSD": (8, C["tsd"], "Tratamiento superficial doble"),
    "PAV_RIGIDO_LOSAS": (9, C["rigido"], "Losas de concreto MR-45 3,50 x 3,75 m"),
    "PAV_RIGIDO_MALLA": (12, (190, 120, 110), "Losas irregulares con malla 1/2\" @ 0,30"),
    "PAV_RIGIDO_JUNTAS": (250, C["junta"], "Juntas del pavimento rígido"),
    "DEMARCACION_BLANCA": (7, C["blanca"], "Demarcación blanca"),
    "DEMARCACION_AMARILLA": (40, C["amarilla"], "Demarcación amarilla"),
    "DEFENSA_METALICA": (252, C["defensa"], "Defensa metálica"),
    "EJE": (1, (192, 0, 0), "Eje de diseño (001, 002, glorieta y cuñas)"),
    "ABSCISAS": (7, None, "Abscisas"),
}


def capa(doc, nombre):
    aci, rgb, desc = CAPAS[nombre]
    l = doc.layers.add(nombre, color=aci)
    if rgb is not None: l.rgb = tuple(int(c) for c in rgb)
    l.description = desc
    return l


def sombreado(msp, geom, layer, rgb, contorno=True, tc_borde=None):
    n = 0
    for p in polys(geom):
        if p.area < 1e-4: continue
        h = msp.add_hatch(dxfattribs={"layer": layer})
        h.set_solid_fill(color=256, style=0, rgb=tuple(int(c) for c in rgb))   # estilo normal (par-impar)
        h.paths.add_polyline_path(list(p.exterior.coords)[:-1], is_closed=True,
                                  flags=const.BOUNDARY_PATH_EXTERNAL)
        for i in p.interiors:
            h.paths.add_polyline_path(list(i.coords)[:-1], is_closed=True, flags=const.BOUNDARY_PATH_OUTERMOST)
        n += 1
        if contorno:
            for ring in [p.exterior] + list(p.interiors):
                e = msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": layer})
                if tc_borde: e.rgb = tc_borde
    return n


def linea(msp, ls, layer, ancho=0.0, rgb=None):
    for g in getattr(ls, "geoms", [ls]):
        cs = list(g.coords)
        if len(cs) < 2: continue
        e = msp.add_lwpolyline(cs, dxfattribs={"layer": layer, "const_width": ancho})
        if rgb: e.rgb = tuple(int(c) for c in rgb)


def main():
    G = pickle.load(open(os.path.join(ROOT, "build", "geometria.pkl"), "rb"))
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    doc.header["$INSUNITS"] = 6; doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    for n in CAPAS: capa(doc, n)
    msp = doc.modelspace()

    # 1. ortofoto (IMAGE) según el archivo de mundo
    px, npy, X0, Y0 = leer_jgw(); py = -npy
    W, H = Image.open(ORTO).size
    idef = doc.add_image_def(filename=ORTO_REL, size_in_pixel=(W, H), name="ortofoto_las_delicias_10cm")
    ins = (X0 - px / 2, Y0 + py / 2 - H * py)
    img = msp.add_image(idef, insert=ins, size_in_units=(W * px, H * py), dxfattribs={"layer": "ORTOFOTO"})
    img.dxf.flags = 1 | 2 | 8      # mostrar, sin alinear a pantalla, con recorte desactivado
    print("IMAGE: inserción %.3f, %.3f  tamaño %.2f x %.2f m" % (ins[0], ins[1], W * px, H * py))

    # 2. levantamiento de fondo
    for lay, p in G["fondo"]:
        msp.add_lwpolyline(p, dxfattribs={"layer": "LEVANTAMIENTO"})

    # 3. laterales, isletas y pavimentos (sombreados sólidos con su contorno)
    sombreado(msp, G["anden"], "ANDEN", C["anden"])
    for j in G["anden_juntas"]: linea(msp, j, "ANDEN_JUNTAS")
    sombreado(msp, G["bordillo"], "BORDILLO", C["bordillo"])
    sombreado(msp, G["cuneta"], "CUNETA", C["cuneta"], tc_borde=C["cuneta_borde"])
    sombreado(msp, G["calzada"]["FLEXIBLE"], "PAV_FLEXIBLE", C["flexible"])
    sombreado(msp, G["calzada"]["TSD"], "PAV_TSD", C["tsd"])
    sombreado(msp, G["verde_isletas"], "ISLETA_VERDE", C["verde"])

    rng = np.random.default_rng(11)
    for i, l in enumerate(G["losas"]):
        d = rng.normal(0, 4.0)
        rgb = tuple(int(np.clip(c + d, 0, 255)) for c in C["rigido"])
        sombreado(msp, l["poly"], "PAV_RIGIDO_LOSAS", rgb, contorno=True)
        if l["irregular"]:
            for p in polys(l["poly"]):
                h = msp.add_hatch(dxfattribs={"layer": "PAV_RIGIDO_MALLA"})
                eje = G["eje"]
                a, b = eje.interpolate(s_of(l["sta0"])), eje.interpolate(s_of(l["sta1"]))
                ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
                h.set_pattern_fill("NET", scale=0.30 / 0.125, angle=ang, color=256)
                h.paths.add_polyline_path(list(p.exterior.coords)[:-1], is_closed=True,
                                          flags=const.BOUNDARY_PATH_EXTERNAL)
    for j in G["juntas"]: linea(msp, j, "PAV_RIGIDO_JUNTAS", ancho=0.015)

    # 4. demarcación (polígonos con su ancho real; segmentadas ya partidas según el patrón)
    sombreado(msp, G["dem"]["blanca"], "DEMARCACION_BLANCA", C["blanca"], contorno=False)
    sombreado(msp, G["dem"]["amarilla"], "DEMARCACION_AMARILLA", C["amarilla"], contorno=False)
    for d in G["dem"]["defensa"]: linea(msp, d, "DEFENSA_METALICA", ancho=0.30)

    # 5. ejes y abscisas
    linea(msp, G["eje"], "EJE"); linea(msp, G["glo_eje"], "EJE")
    for ce in G["ejes_cunas"].values(): linea(msp, ce, "EJE")
    for a in G["abscisas"]:
        p = np.array(a["p"]); n = np.array(a["n"]); sta = a["sta"]
        mayor = round(sta) % 100 == 0
        l0, l1 = (-4.0, 4.0)
        msp.add_line(tuple(p + n * l0), tuple(p + n * l1), dxfattribs={"layer": "ABSCISAS"})
        if mayor or round(sta) % 50 == 0:
            k = int(sta // 1000)
            t = msp.add_text("K%d+%03d" % (k, round(sta - 1000 * k)),
                             height=2.0 if mayor else 1.4, dxfattribs={"layer": "ABSCISAS"})
            ang = math.degrees(math.atan2(n[1], n[0]))
            if ang > 90 or ang < -90:
                ang += 180; al = TextEntityAlignment.MIDDLE_RIGHT
            else:
                al = TextEntityAlignment.MIDDLE_LEFT
            t.dxf.rotation = ang
            t.set_placement(tuple(p + n * 9.0), align=al)

    doc.saveas(DESTINO)
    print("OK ->", os.path.relpath(DESTINO, ROOT), "(%.1f MB)" % (os.path.getsize(DESTINO) / 1e6))


if __name__ == "__main__":
    main()
