# Planta realista — Vía Belén – Las Delicias (Cúcuta)

Proyecto para generar una **planta realista** de la vía proyectada (diseño geométrico V2) sobre la ortofoto: asfalto en el tramo flexible, tratamiento superficial doble (TSD) en sus tramos, losas de concreto con despiece de juntas en el rígido, cunetas, andenes, bordillos y demarcación. Todo en español.

No hay AutoCAD en este entorno: se trabaja con Python (`pip install -r requirements.txt`) y la salida CAD es **DXF** (el usuario lo abre en AutoCAD y lo guarda como DWG).

## Archivos

| Archivo | Contenido |
|---|---|
| `dxf/CUCUTA_DG_PP_001-06_V2.dxf` | Diseño geométrico V2 (planta-perfil). Sistema **Origen Nacional CTM-12**, metros. |
| `dxf/CUCUTA_DG_SEN_001-03_V2.dxf` | Señalización V2 (misma geometría y sistema). |
| `dxf/CAD-DG-LAS_DELICIAS.dxf` | Levantamiento topográfico (existentes: vías, paramentos, andenes, bordillos), mismo sistema. |
| `ortofoto/ortofoto_las_delicias_10cm.jpg` + `.jgw` | Ortofoto recortada a 0,0993 m/píxel, georreferenciada (archivo de mundo, CTM-12). Cubre X 5.050.758,9 – 5.051.442,7 y Y 2.427.166,5 – 2.427.740,0. **No cubre el tramo final de la vía (X > 5.051.443, ≈ K1+300 a K1+609)**: ahí usar de fondo el levantamiento (`CAD-DG`, capas Vía, Paramento, Cerca) en tonos grises claros. |
| `tools/geom.py`, `tools/align.py` | Utilidades ya probadas: `curves(msp, layers)` (polilíneas aplanadas y sin duplicados), `chain()` (encadena el eje) y `Align` (punto, normal y offsets perpendiculares al eje). |
| `datos/measures.json` | Mediciones ya hechas: muestreo cada 1 m (`muestreo`), áreas, tramos de bordillo/cuneta, glorieta, cuñas. Úsalo para verificar. |
| `referencia/*.png` | Secciones típicas, estructuras de pavimento, despiece del rígido y la planta general por tipo de pavimento (para guiarte). |

Nota de importación: los scripts en `tools/` se importan con `sys.path.insert(0, "tools")`.

## Geometría del diseño (capas del PP V2)

- **Eje**: capa `SPI-C-ROAD-CNTR-N`. Encadenar con `chain(msp, "SPI-C-ROAD-CNTR-N", (5050794.454, 2427375.524))` → 1.609,75 m (eje 001 + eje 002).
  Abscisa: `sta = s` si `s <= 171.358`; si no, `sta = 170.98 + (s - 171.358)`.
- **Bordes de calzada**: capa `BV`. **Cuneta**: capa `Cuneta`. **Andén** (borde exterior): capa `ANDÉN`.
- **Glorieta**: eje desde (5050955.22, 2427383.247), 87,95 m, radio de eje 14,00 m; calzada anular de 7,00 m (radios 10,50 a 17,50). Isleta central = polilínea cerrada de la capa BV con handle `258`; isleta del acceso = BV handle `3C1`.
- **Cuñas del anillo vial** (flexible): aceleración desde (5050809.467, 2427373.536) 131,40 m; desaceleración desde (5050879.1, 2427309.1), medir hasta s = 85 m. El ancho es la distancia al BV del lado izquierdo (0 a 4,43 m).
- En el eje principal, entre s = 160,5 y 181,5 m, el eje cruza la isleta de la glorieta: no dibujar calzada ahí (la cubre el anillo).
- En s < 44 m, lado izquierdo, limitar el ancho a 3,50 m (gore con la cuña).

### Sección por tramos (medida)

| Tramo | Calzada | Pavimento | Laterales |
|---|---|---|---|
| Eje 001 K0+000 – K0+160 | 7,00 m | Flexible | Franja cuneta/bordillo 0,50 m + andén 1,00 m a ambos lados desde ≈K0+020 |
| Eje 002 K0+181 – K0+390 | 7,00 m | Flexible | Der.: cuneta 0,64 m. Izq.: franja 0,50 + andén 1,00 (K0+192–K0+380) |
| K0+390 – K0+600 | 5,00 m | TSD | Sin cuneta ni andén |
| K0+600 – K0+780 | 7,00 m | **Rígido** | Franja 0,50 + andén 1,00 a ambos lados |
| K0+780 – K1+540 | 6,00 m | TSD | Cuneta 0,64 m a ambos lados |
| K1+540 – K1+609,40 | 5,00 m | TSD | Sin cuneta ni andén |
| Glorieta y cuñas | 7,00 m / variable | Flexible | Bordillo 0,20 m en isletas; andén exterior parcial |

Los anchos reales se toman siempre de las capas (offset perpendicular cada 0,50 m), no de esta tabla.

### Pavimento rígido (K0+600 – K0+780)

Losas de 3,50 m (un carril, junta longitudinal en el eje) × 3,75 m (juntas transversales cada 3,75 m, perpendiculares al eje). Dibujar cada losa como polígono con su textura de concreto y las juntas como líneas de 0,01–0,02 m en gris oscuro. En las curvas las losas quedan trapezoidales (losas irregulares, con malla).

### Demarcación (SEN V2, capa `SEN_BASE_DEM`)

Polilíneas con ancho global: blanca 0,12 (color BYLAYER), amarilla 0,12 (color 40), carril 0,12 con tipo de línea `LCA (3m - 5m)`, segmentada 0,20 (`LCA (1m - 1m)`), borde 0,30. Ignorar las polilíneas con ancho global 0 (son contornos). Flechas y pictogramas = bloques en la capa `Sen_Horizontal` y el bloque `P_CP` (usar sus sombreados). Defensa metálica: capa `Defensa metálica`. Las líneas segmentadas deben verse segmentadas (pintar los tramos según el patrón).

## Estilo visual

- Ortofoto de fondo con brillo normal; fuera de la ortofoto, el levantamiento en gris claro sobre fondo blanco.
- **Flexible (asfalto MDC-19)**: gris muy oscuro (#2b2b2b – #3a3a3a) con ruido fino tipo agregado.
- **TSD**: gris medio-cálido (#6e6a64 – #7d7870) con granulado más grueso y visible.
- **Rígido**: concreto gris claro (#bdbab3 – #c9c6bf) con leve variación entre losas y juntas oscuras.
- **Cunetas**: concreto (#a9a7a1) con borde oscuro; **bordillos**: gris claro con sombra lateral sutil; **andenes**: concreto claro (#d6d3cc) con juntas cada 1,50 m.
- Demarcación blanca (#f5f5f5) y amarilla (#f2c200) con su ancho real; flechas y pictogramas en blanco.
- Sombra suave (1–2 px) en los bordes de calzada para dar volumen.
- Las texturas se generan con numpy (ruido) y se aplican recortadas a cada polígono (`matplotlib` con `set_clip_path` o rasterizando con PIL).

## Entregables (carpeta `salida/`)

1. `PLANTA_REALISTA_GENERAL.png` y `.pdf`: planta completa, rótulo con título, norte, escala gráfica, abscisas cada 100 m y convenciones.
2. Láminas por tramo a escala legible (≈1:500 en carta horizontal o 1:1000 en doble carta), PNG 300 dpi + PDF multipágina: K0+000–K0+200 (acceso, cuñas y glorieta), K0+180–K0+420, K0+380–K0+620, K0+580–K0+800 (rígido), K0+780–K1+120, K1+100–K1+400, K1+380–K1+609.
3. `PLANTA_REALISTA.dxf`: capas `PAV_FLEXIBLE`, `PAV_TSD`, `PAV_RIGIDO_LOSAS`, `PAV_RIGIDO_JUNTAS`, `CUNETA`, `BORDILLO`, `ANDEN`, `DEMARCACION_BLANCA`, `DEMARCACION_AMARILLA`, `EJE`, `ABSCISAS`, con sombreados sólidos de colores y una entidad IMAGE que referencia la ortofoto (relativa) con su inserción y tamaño según el `.jgw`. En coordenadas CTM-12 reales.
4. `LEEME.md`: qué contiene cada archivo y cómo abrir el DXF con la ortofoto en AutoCAD.

## Verificación antes de entregar

- El área de calzada debe dar ≈ 10.906 m² (flexible ≈ 3.669, TSD ≈ 5.977, rígido ≈ 1.260 m², según `datos/measures.json`). Si no, revisar.
- Mirar las imágenes generadas: alineación con la ortofoto, sin huecos en la glorieta, juntas del rígido perpendiculares al eje, demarcación encima del pavimento.
- Hacer commit y push de `salida/` y de los scripts al terminar.
