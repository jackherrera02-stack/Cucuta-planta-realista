# Planta realista – Vía Belén – Las Delicias (Cúcuta)

Planta realista de la vía proyectada (diseño geométrico V2) sobre la ortofoto de 10 cm:
pavimento flexible, TSD, losas de concreto con despiece de juntas, cunetas, bordillos,
andenes, isletas, demarcación y defensa metálica. Coordenadas **MAGNA-SIRGAS Origen
Nacional (CTM-12)**, en metros.

## Archivos

| Archivo | Contenido |
|---|---|
| `PLANTA_REALISTA_GENERAL.png` / `.pdf` | Planta completa K0+000 – K1+609,40 a 1:2000 (hoja 24×14 in, 250 dpi). Tiene rótulo, norte, escala gráfica, abscisas cada 100 m, convenciones y cuadro de áreas. |
| `PLANTA_REALISTA_L01_K0000_K0200.png` | Lámina 1/7: acceso, cuñas del anillo vial y glorieta (1:1000). |
| `PLANTA_REALISTA_L02_K0180_K0420.png` | Lámina 2/7: eje 002, flexible y transición a TSD (1:500). |
| `PLANTA_REALISTA_L03_K0380_K0620.png` | Lámina 3/7: TSD de 5,00 m (1:1000). |
| `PLANTA_REALISTA_L04_K0580_K0800.png` | Lámina 4/7: pavimento rígido con despiece de losas (1:1000). |
| `PLANTA_REALISTA_L05_K0780_K1120.png` | Lámina 5/7: TSD de 6,00 m con cunetas (1:1000). |
| `PLANTA_REALISTA_L06_K1100_K1400.png` | Lámina 6/7: TSD de 6,00 m con cunetas (1:1000). |
| `PLANTA_REALISTA_L07_K1380_K1609.png` | Lámina 7/7: tramo final, TSD de 6,00 m y 5,00 m (1:1000). |
| `PLANTA_REALISTA_LAMINAS.pdf` | Las 7 láminas en un PDF multipágina (doble carta horizontal, 300 dpi). |
| `PLANTA_REALISTA.dxf` | Dibujo CAD (AutoCAD 2018) en CTM-12 con sombreados sólidos de color y la ortofoto como IMAGE. |

Las láminas son doble carta horizontal (17×11 in) a 300 dpi. Se usa 1:500 cuando el tramo
cabe a esa escala; si no, 1:1000.

Al este de X ≈ 5.051.443 (≈ K1+300 a K1+609) y en las zonas negras (sin dato) de la
ortofoto, el fondo es el levantamiento topográfico (`CAD-DG`) en gris claro sobre blanco.

## Capas del DXF

| Capa | Contenido |
|---|---|
| `ORTOFOTO` | Entidad IMAGE de la ortofoto, con inserción y tamaño según el `.jgw`. |
| `LEVANTAMIENTO` | Vías, paramentos, cercas, andenes, etc. existentes (CAD-DG). |
| `PAV_FLEXIBLE` | Calzada en MDC-19: eje 001, eje 002 hasta K0+390, glorieta y cuñas. |
| `PAV_TSD` | Tratamiento superficial doble: K0+390–K0+600 y K0+780–K1+609,40. |
| `PAV_RIGIDO_LOSAS` | 96 losas de 3,50 × 3,75 m (K0+600–K0+780), cada una con su sombreado. |
| `PAV_RIGIDO_MALLA` | Sombreado NET a 0,30 m sobre las 60 losas irregulares (trapezoidales en curva). |
| `PAV_RIGIDO_JUNTAS` | Juntas transversales cada 3,75 m, perpendiculares al eje, y la junta longitudinal en el eje (ancho 0,015 m). |
| `CUNETA` | Cuneta en concreto. Donde hay andén, la franja de 0,50 m se divide en cuneta de 0,30 y bordillo de 0,20. |
| `BORDILLO` | Bordillos junto a los andenes y de 0,20 m en las isletas y el borde exterior de la glorieta. |
| `ANDEN`, `ANDEN_JUNTAS` | Andén en concreto con juntas cada 1,50 m. |
| `ISLETA_VERDE` | Zona verde de la isleta central de la glorieta y de la isleta del acceso. |
| `DEMARCACION_BLANCA`, `DEMARCACION_AMARILLA` | Demarcación del SEN V2 con su ancho real, las líneas segmentadas partidas según el patrón (3–5 m y 1–1 m), y las flechas y pictogramas. |
| `DEFENSA_METALICA` | Defensa metálica (ancho 0,30 m). |
| `EJE` | Eje principal (001 + 002), eje de la glorieta y ejes de las cuñas. |
| `ABSCISAS` | Marcas cada 10 m y textos cada 50 m. |

## Cómo abrir el DXF con la ortofoto en AutoCAD

1. Mantén la estructura de carpetas del repositorio. El DXF referencia la imagen con la ruta
   relativa `..\ortofoto\ortofoto_las_delicias_10cm.jpg`, así que `salida/` y `ortofoto/`
   deben quedar como carpetas hermanas.
2. Abre `salida/PLANTA_REALISTA.dxf` en AutoCAD y usa `ZOOM` → `Extensión`.
3. Si la imagen aparece como "no encontrada", abre `XREF` (Referencias externas), selecciona
   `ortofoto_las_delicias_10cm` y en *Encontrado en* apunta al `.jpg`. La inserción y el
   tamaño ya están en el DXF, así que no hay que moverla ni escalarla:
   - inserción (esquina inferior izquierda): E 5.050.758,889 – N 2.427.166,467
   - tamaño: 683,85 × 573,56 m (6889 × 5778 px a 0,099267 m/px)
4. La imagen se dibuja primero, debajo de todo. Si queda encima, selecciónala y usa
   `DRAWORDER` → `Atrás`.
5. Guarda como DWG (`GUARDARCOMO` → *Dibujo de AutoCAD 2018 (*.dwg)*).
6. Las zonas sin dato de la ortofoto se ven negras en AutoCAD. Para ocultarlas, puedes
   recortar la imagen con `IMAGECLIP` o congelar la capa `ORTOFOTO` para trabajar solo
   con el levantamiento.

## Verificación

Áreas medidas sobre los polígonos (y releídas desde los sombreados del DXF), comparadas
con `datos/measures.json`:

| Elemento | Calculado (m²) | Referencia (m²) |
|---|---:|---:|
| Calzada flexible | 3.663,3 | 3.668,8 |
| Calzada TSD | 5.978,8 | 5.977,1 |
| Calzada rígida (96 losas) | 1.259,9 | 1.259,9 |
| **Total calzada** | **10.902,0** | **10.905,8** |
| Cuneta + bordillo de franja | 1.502,8 | 1.498,2 |
| Andenes | 781,1 | 772,1 |

## Cómo regenerar

```bash
pip install -r requirements.txt
python scripts/geometria.py         # polígonos y áreas -> build/geometria.pkl, build/areas.json
python scripts/render.py            # PNG y PDF (general + láminas); o: render.py L04
python scripts/dxf_salida.py        # salida/PLANTA_REALISTA.dxf
```

Notas de método:

- Los anchos se toman de las capas `BV`, `Cuneta` y `ANDÉN` con offsets perpendiculares
  al eje cada 0,50 m.
- La glorieta es la calzada anular de 7,00 m alrededor de su eje, menos la isleta (BV
  handle 258).
- Las cuñas son la franja entre su eje y el BV.
- En el acceso se sellan con un cierre morfológico de 0,80 m las ranuras entre la cuña de
  desaceleración, el eje 001 y la isleta (BV handle 3C1).
- Las tachas reflectivas (bloques THA, THAD y th-) no se dibujan, porque a estas escalas
  miden menos de 1 px.
