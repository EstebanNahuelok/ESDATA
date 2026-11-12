# PROGRESO — Desafío QualyData

Bitácora de la rama `nucleo-pipeline`. Todo se mide sobre el set de práctica con:

```bash
python -m pipeline.run --datos datos/practica --entrega salida/practica
python evaluacion/puntuar.py --verdad datos/practica/verdad --entrega salida/practica
python -m unittest discover -s pruebas        # pruebas mínimas (20 s)
```

Dependencia nueva instalada en el Python de la máquina: `duckdb` 1.5.6 (13 MB). El resto ya estaba
(`numpy`, `pandas`, `scikit-learn`, `scipy`, `networkx`, `psutil`). Está todo en `requirements.txt`.

## Puntaje final de la sesión (set de práctica, 200.000 comentarios)

| Parte | Métrica | Línea base | Ahora |
|---|---|---|---|
| Narrativas (30) | Agrupamiento B-cubed F1 | 0,35 | **1,000** |
| | Ruido F1 | 0,67 | **1,000** |
| | Postura macro-F1 | 0,49 | **0,927** |
| | Origen de emergentes | 0,33 | **1,000** |
| | Puntos | — | **29,56** |
| Coordinación (25) | Cuentas coordinadas F1 (P / R) | P 0,07 | **1,000** (1,000 / 1,000; 115 de 115) |
| | Grupos B-cubed F1 | — | **1,000** |
| | Puntos | — | **25,00** |
| **Total automático (55)** | | **16,8** | **54,56** |

Costo: 27 segundos de punta a punta, pico de memoria 640 MB, base DuckDB de 35 MB, 0 tokens de IA, 0 USD.
Dos corridas seguidas dan archivos idénticos byte a byte.

## Historial de puntajes

| Fecha y hora | Cambio | Agrup. F1 | Ruido F1 | Postura | Origen | Narrativas /30 | Coord. F1 (P / R) | Grupos | Coord. /25 | Total /55 | Tiempo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (referencia) | Línea base de la organización (`ejemplos/linea_base.py`), dato de CLAUDE.md | 0,35 | 0,67 | 0,49 | 0,33 | — | P 0,07 | — | — | 16,8 | — |
| 2026-11-11 20:40 | Ingesta a DuckDB + narrativas por microgrupos y grafo de respuestas + ruido + herencia + postura por bandos + origen. Coordinación todavía vacía. | 1,000 | 1,000 | 0,927 | 1,000 | 29,56 | 0,000 | 0,051 | 0,38 | 29,94 | 16 s |
| 2026-11-11 20:56 | Coordinación: pares de cuentas que coinciden varias veces en la misma publicación y ventana de 30 min (canal con misma narrativa y bando, y canal solo tiempo), lift contra lo esperable ≥ 40, k-truss 4, grupos de 5+ cuentas. | 1,000 | 1,000 | 0,927 | 1,000 | 29,56 | 0,996 (1,000 / 0,991) | 0,992 | 24,86 | 54,42 | 27 s |
| 2026-11-11 21:08 | Coordinación, segunda pasada: sumar cuentas que coinciden con el grupo completo (2+ celdas dominadas por el grupo, o 1 celda si además la cuenta fue creada en la misma franja de fechas que el grupo). | 1,000 | 1,000 | 0,927 | 1,000 | 29,56 | 1,000 (1,000 / 1,000) | 1,000 | 25,00 | 54,56 | 27 s |
| 2026-11-11 21:18 | Robustez: pruebas mínimas, set vacío, plan B sin hilos (umbral de parecido 0,1; coordinación solo por tiempo) y "celda dominada" exige que el grupo sea 1/3 o más de la celda. Sin cambios en el puntaje de práctica. | 1,000 | 1,000 | 0,927 | 1,000 | 29,56 | 1,000 (1,000 / 1,000) | 1,000 | 25,00 | 54,56 | 27 s |

Ninguna mejora bajó el puntaje, así que no hubo que revertir nada.

## Cómo funciona (en simple)

Paquete `pipeline/`, un módulo por etapa. Ningún id, tema, nombre de narrativa ni fecha del set de práctica está en el código.

1. **`ingesta.py`** — Lee los CSV(.gz) como texto con DuckDB, limpia con SQL (ids duplicados, fechas rotas, números inválidos, respuestas a comentarios que no existen, archivos opcionales faltantes) y deja tablas tipadas en un archivo `almacen/<set>.duckdb`. Guarda los textos únicos aparte: de 200.000 comentarios hay 112.000 textos distintos y 47.000 después de normalizar, y solo esos se procesan.
2. **`texto.py` + `microgrupos.py`** — Normaliza (minúsculas, tildes, emojis, abreviaturas, letras repetidas, errores de tipeo) y junta los textos que son la misma frase con variaciones chicas (TF-IDF + agrupamiento por "líder", por lotes, sin k fijo). Salen ~370 microgrupos puros.
3. **`narrativas.py`** — Mira cómo participa cada microgrupo en los hilos:
   - casi siempre es respuesta ("tal cual") → **acuerdo**: hereda narrativa y postura del padre;
   - aparece muchas veces suelto y nadie le responde nunca → **ruido** (una frase de una narrativa recibe ~0,17 respuestas por comentario; cero respuestas en 30+ apariciones es muy improbable);
   - el resto es **contenido**. Una respuesta con contenido propio contradice al comentario que responde (regla del enunciado, `DESAFIO.md`), así que los dos microgrupos son de la misma narrativa. Con esos enlaces se arma un grafo y sus comunidades (Louvain, decide solo cuántas hay) son las narrativas. Así quedan juntos quienes apoyan y quienes rechazan aunque usen palabras distintas.
   - Toda respuesta hereda la narrativa del comentario al que responde.
4. **`postura.py`** — Dentro de cada narrativa reparte los microgrupos en dos bandos para que las contradicciones queden cruzadas. Después decide cuál bando "apoya" con indicios generales: marcas de desmentida ("mentira", "falso", "nada que ver"...) → rechaza; la campaña coordinada empuja la narrativa → apoya; el bando con más comentarios sueltos, más redacciones y más volumen → apoya.
5. **`origen.py`** — Primer comentario de la narrativa que tiene compañía (5 comentarios en 12 h), para ignorar apariciones aisladas.
6. **`coordinacion.py`** — Para cada par de cuentas suma las veces que coinciden en la misma publicación y ventana de 30 min, pesando cada coincidencia por 1/tamaño de la celda (coincidir en algo viral casi no suma). Lo compara con lo esperable según cuánto comenta cada cuenta (`n_a·n_b/N`): ese cociente ("lift") no depende del tamaño del set. Se quedan los pares con 2-3+ coincidencias y lift ≥ 40, y del grafo solo las zonas densas en triángulos (k-truss): el azar da aristas sueltas, una operación es una malla. Después suma cuentas de poca actividad que coinciden con el grupo como conjunto. La antigüedad se usa solo como señal relativa: si el propio grupo detectado fue creado en una franja de fechas rara en el set, una cuenta de esa misma franja entra con una sola coincidencia.
7. **`salida.py` / `run.py`** — Escribe los 4 archivos, guarda los resultados también en DuckDB (tablas `res_*`, sirven para un dashboard) y mide segundos y memoria por etapa (quedan en `costo.json`). Si falla coordinación o postura, la entrega sale igual y el aviso queda en `costo.json`.

Tiempos en la máquina de 8 GB: ingesta 6 s, narrativas 8 s, coordinación 11 s, resto < 1 s.

## Qué tan confiable es (pruebas con recortes del set de práctica)

Como el puntaje de práctica es casi perfecto, medí el pipeline sobre recortes que nunca usé para ajustar nada.
"Postura" baja cuando una narrativa queda con los bandos al revés; "Coord. R" baja cuando hay menos días (menos repeticiones).

| Recorte | Agrup. F1 | Ruido F1 | Postura | Coord. P | Coord. R |
|---|---|---|---|---|---|
| Días 1 a 7 (100 mil comentarios) | 1,000 | 1,000 | 0,901 | 0,991 | 1,000 |
| Días 8 a 14 | 0,999 | 0,998 | 0,808 | 1,000 | 0,929 |
| Días 5 a 9 (65 mil) | 0,999 | 0,999 | 0,930 | 1,000 | 0,741 |
| Solo el tema litio | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 |
| Sin el tema litio | 1,000 | 1,000 | 0,881 | 1,000 | 0,287 (*) |
| La mitad de las cuentas (rompe la mitad de los hilos) | 0,966 | 0,983 | 0,739 | 1,000 | 0,983 |
| Datos sucios (fechas rotas, duplicados, textos vacíos, sin archivo de cuentas) | 0,998 | 0,995 | 0,925 | 1,000 | 1,000 |
| Sin ninguna respuesta (`respuesta_a` vacío) | 0,376 | 0,725 | 0,337 | 1,000 | 0,983 |

(*) En ese recorte dos de las tres campañas solo tienen actividad de cobertura: no hay nada que detectar.
Todos los números de esta tabla son del código final de la sesión (corrida de las 21:18).

## Qué funciona

- Agrupamiento, ruido y origen: estables en todos los recortes mientras haya hilos de respuestas.
- Coordinación: precisión 1,00 en casi todos los recortes; detecta las tres campañas, incluida la de cuentas viejas con textos variados.
- Un comando, 27 s, 640 MB, sin IA: costo por mil comentarios = 0.
- Datos sucios o archivos faltantes no rompen la corrida; resultado reproducible.

## Qué no funciona o es un riesgo

1. **Orientación de la postura (el punto más flojo).** Los dos bandos de cada narrativa salen bien separados (acierto ~100% o ~0% por narrativa, nunca a medias). El problema es decidir cuál bando "apoya" cuando no hay marcas de desmentida, ni campaña, ni diferencia de volumen. En práctica queda al revés 1 de 13 narrativas (la de la licitación) y en los recortes hasta 3. Eso es semántica y con estadísticas no se resuelve: en el set final espero entre 0,75 y 0,93.
2. **El pipeline depende de los hilos de respuestas.** Usa dos reglas (una del enunciado: la respuesta que contradice es de la misma narrativa; y una observada en práctica: al ruido nadie le responde y el ruido nunca es respuesta). Si el set final viniera sin `respuesta_a`, el plan B por palabras saca solo 0,38 de agrupamiento (parecido a la línea base). Con la mitad de los hilos rotos aguanta bien (0,97).
3. **Coordinación con pocos días.** Con 5 días la campaña de cuentas viejas casi no se ve (5 de 30): necesita repetición. El set final tiene 10 días; el recorte de 7 días dio R entre 0,93 y 1,00.
4. **Umbrales fijos de coordinación** (lift ≥ 40, ventana 30 min, k-truss 4). En práctica hay una meseta ancha (lift entre 20 y 100 da lo mismo), pero una campaña de otro estilo (por ejemplo coordinada entre publicaciones distintas, o con horas de diferencia) podría no verse.
5. ~~Falta el README del equipo~~ Hecho el jueves 12 (ver abajo).
6. `CLAUDE.md` sigue sin versionar (no lo agregué a ningún commit).

## Qué probaría después (en orden)

1. **Orientar la postura con IA, una sola llamada.** Mandar por narrativa las 3-4 frases más repetidas de cada bando (unas 300 frases cortas en total, ~5.000 tokens, centavos) y preguntar cuál bando sostiene la afirmación y cuál la refuta. No se mandan comentarios: solo frases representativas. Subiría la postura de ~0,93 a ~1,00 en práctica y, sobre todo, la haría confiable en el set final. Requiere elegir proveedor y poner la clave en `.env` (ignorado por git). De paso serviría para escribir un título prolijo por narrativa. Registrar tokens y USD en `costo.json`.
2. **README del equipo** con la justificación de DuckDB y cómo escalaría (particionar por día en Parquet, textos únicos incrementales, coordinación por ventanas deslizantes).
3. **Plan B sin hilos más fuerte**: embeddings multilingües chicos y locales sobre los ~370 microgrupos (no sobre los 200.000 comentarios), solo si hay tiempo; hoy es un riesgo bajo porque el README confirma que el set final trae `respuesta_a`.
4. **Ensayo general** del viernes: bajar el set final a `datos/final/`, correr `python -m pipeline.run --datos datos/final --entrega entrega`, revisar la salida impresa (cantidad de narrativas, títulos, tamaño de los grupos) y recién después commit + push.
5. Dashboard simple leyendo las tablas `res_*` de DuckDB (narrativas, línea de tiempo, grupos). Aislado del núcleo.

## Notas de la sesión

- Rama `nucleo-pipeline`, commits locales, sin push.
- Exploración y recortes de prueba quedaron en `salida/scratch/` y `salida/variantes/` (no se versionan; se pueden borrar).
- No se usó ninguna clave ni servicio externo.

---

# Sesión del jueves 12: lo que mira el jurado y la entrega

Sin IA ni APIs. El núcleo no cambió; el puntaje de práctica se vuelve a medir al final de cada punto.

## Punto 1 — README del equipo (jueves 12, 12:48) ✅

- El `README.md` de la organización pasó a llamarse `DESAFIO.md` (con `git mv`, sin tocar el contenido). El `README.md` de la raíz ahora es el del equipo.
- Contiene: resultado en práctica, cómo correr con un comando, cómo funciona cada etapa, por qué DuckDB, cómo escalaría a millones por día, qué código existía antes (evaluador y línea base de la organización, y qué dos ideas chicas tomamos de la línea base), y tres tablas que separan reglas generales, supuestos vistos en práctica y parámetros elegidos midiendo en práctica (con su sensibilidad).
- Para revisar por el equipo: el README dice que el código se escribió con ayuda de un asistente de programación con IA. Si prefieren otra redacción, es una línea en la sección "Qué existía antes del evento".
- Pendiente declarado en el propio README: no hay una corrida medida con millones de comentarios; la parte de escala es diseño.

## Punto 2 — Robustez e instalación desde cero (jueves 12, 12:59) ✅

- **Entorno virtual nuevo** en `.venv/` (ignorado por git; quedó creado y se puede seguir usando): `python -m venv .venv`, `pip install -r requirements.txt`, correr, medir y pruebas. Todo anduvo a la primera.
- `requirements.txt` ya tenía todo (`duckdb` incluido). El entorno nuevo instaló versiones más nuevas que las del Python global (pandas 3.1, numpy 2.5, scikit-learn 1.9, networkx 3.7, scipy 1.18) y la salida es **idéntica byte a byte** a la del Python global (pandas 2.2, numpy 2.2, scikit-learn 1.6). Versiones exactas en `requirements-lock.txt` (nuevo).
- Práctica en el entorno nuevo: **54,56 / 55**, sin cambios. Primera corrida en frío 47 s; las siguientes 27-30 s.
- Pruebas nuevas de datos sucios (ahora son 12 pruebas, 25 s). Encontraron **tres errores reales**, ya corregidos:
  1. Con muy pocos textos distintos (un solo comentario, o muchos comentarios idénticos) el pipeline se caía por vocabulario vacío.
  2. Un comentario sin `cuenta_id` generaba una fila con cuenta vacía en `cuentas.csv`.
  3. Si ninguna fecha era válida, `fecha_origen` salía vacía (formato inválido). Ahora usa la primera fecha del set y lo avisa en `costo.json`.
- Además: un archivo que no está en UTF-8 se lee como Windows-1252 (antes se perdían las tildes), se aceptan BOM y separador `;`, y la zona horaria del set ya no se confunde cuando muchas fechas vienen rotas.
- Los avisos de la ingesta (archivos o columnas que faltan, filas descartadas, comentarios sin fecha) quedan en `notas` de `costo.json`.
- No probado: Python anterior a 3.13 (es el único instalado en la máquina) ni Linux/Mac.

## Punto 3 — Validador de la entrega (jueves 12, 13:02) ✅

- Nuevo `pipeline/validar.py` (solo librería estándar, como el evaluador). Se puede correr suelto: `python -m pipeline.validar --entrega entrega --datos datos/final` (código de salida 1 si hay errores).
- El pipeline lo ejecuta **solo al final de cada corrida**; si la entrega no cumple, termina con error.
- Qué controla, contra el formato de `DESAFIO.md`:
  - están los 4 archivos y están en UTF-8;
  - encabezados exactos: `comentario_id,narrativa,postura` · `narrativa,titulo,frases_clave,fecha_origen` · `cuenta_id,grupo`;
  - ids sin vacíos ni repetidos; con `--datos`, que estén **exactamente** los comentarios y las cuentas de la entrada (la entrada se vuelve a leer con el módulo `csv` de Python, independiente de DuckDB);
  - postura `apoya`/`rechaza` en todo comentario con narrativa; toda narrativa usada tiene su fila;
  - `titulo` y `frases_clave` (separadas por `|`) no vacíos; `fecha_origen` ISO con zona horaria;
  - `costo.json`: las 8 claves del enunciado con su tipo, sin negativos, y `comentarios_procesados` igual a las filas de `comentarios.csv`.
  - Avisos (no cortan): archivos de más en la carpeta, grupos de una sola cuenta, ninguna cuenta marcada, ruido con postura.
- 8 pruebas nuevas que rompen una entrega buena de a un defecto y verifican que el validador lo señale (ahora son 20 pruebas, 36 s).
- Práctica: validación OK (200.000 comentarios, 13 narrativas, 15.991 cuentas, 115 coordinadas en 3 grupos). Puntaje sin cambios: **54,56 / 55**.

## Punto 4 — `costo.json` real (jueves 12, 13:07) ✅

- Nuevo `pipeline/costo.py`. Todo sale de la corrida, nada escrito a mano. Las 8 claves del enunciado más: `memoria_pico_mb`, `comentarios_por_segundo`, `almacenamiento_mb` (entrada, base, entrega), `etapas` (segundos y memoria de cada una), `semilla` y `versiones`.
- **Hardware detectado solo:** `notebook, Intel(R) Core(TM) i7-10510U CPU @ 1.80GHz (4 núcleos, 8 hilos), 8 GB de RAM, sin GPU (todo corre en CPU), Windows 10`. "Notebook" sale de que el equipo tiene batería; "sin GPU" de que no hay `nvidia-smi`. Si el jurado lo corre en otra máquina, el texto cambia solo. Con `--hardware "texto"` se puede fijar a mano.
- **Almacenamiento:** `DuckDB local, un solo archivo de 35.0 MB (almacen/practica.duckdb) ...; entrada 4.8 MB en CSV comprimido, entrega 3.9 MB en CSV`. La entrada se mide sobre los archivos que realmente se leyeron.
- **Segundos:** ahora incluyen la validación final (antes se cortaba al escribir la entrega). `notas` incluye la memoria pico y los avisos de la corrida.
- **Ojo con el tiempo:** hoy la notebook está más lenta que ayer con el mismo código y el mismo entorno. Corridas de hoy: 29,5 s · 35,6 s · 42,2 s · 46,7 s · 48,4 s; ayer 26-27 s. La memoria pico no cambia (640-650 MB). Es carga de la máquina, no del pipeline (cada etapa se estira en la misma proporción). En el README puse "entre 27 y 48 segundos". Para el número del viernes conviene cerrar lo que no haga falta antes de correr.
- Para que lo sepan: durante la sesión aparecieron en `datos/practica/` y `datos/practica/verdad/` copias descomprimidas de los `.csv.gz` (28 MB, creadas a las 12:56, idénticas a los `.gz`) y unos minutos después ya no estaban. No las creé ni las borré yo, y no entraron en ningún commit. Si conviven `.csv` y `.csv.gz`, el pipeline lee el `.gz`.
- Práctica: **54,56 / 55**, sin cambios.

## Punto 5 — Reporte visual estático (jueves 12, 13:14) ✅

- Nuevo `pipeline/reporte.py`: **un solo archivo HTML**, sin JavaScript, sin internet y sin librerías nuevas (gráficos SVG armados a mano). Pesa 140 KB. Lo genera el pipeline al final (0,9 s) en `reporte/<nombre de la entrega>.html`; el de práctica quedó versionado en `reporte/practica.html`.
- Qué muestra, de arriba hacia abajo:
  1. **Una frase y los hallazgos**: cuántas narrativas, cuántas nuevas, cuántas cuentas coordinadas, y una línea por grupo ("g03 (25 cuentas) originó la narrativa n13 ..., que apareció el dom 6 sep, 01:12").
  2. **Tabla de narrativas**: título y frases clave, fecha de origen con etiqueta "nueva: día N" o "desde el inicio", línea de tiempo con el origen marcado y los comentarios del grupo que la empuja en color, barra apoya/rechaza, y qué grupo la originó o la empuja.
  3. **Una tarjeta por grupo coordinado**: cuántas cuentas, qué narrativa empuja y con qué postura, cuántas ráfagas, antigüedad de las cuentas contra el resto, franja horaria, me gusta contra el resto, las frases que más repite, cuándo actúa y a qué hora.
  4. Pie con el método en tres renglones y el costo.
- En práctica el reporte cuenta la historia correcta (coincide con la verdad): g01 empuja "el litio trae trabajo", g02 empuja "no hubo consulta previa", g03 originó de madrugada "el hospital para la foto", y las otras dos narrativas nuevas no tienen empuje coordinado.
- Lo revisé abriéndolo en un navegador sin interfaz (captura de pantalla, sin errores de consola, sin pedidos de red).
- Aislado del núcleo: se genera después de escribir y validar la entrega, dentro de un `try`. Se regenera suelto con `python -m pipeline.reporte --base ... --salida ...`. Opciones nuevas del pipeline: `--reporte ruta.html` y `--sin-reporte`.
- La base guarda ahora una tabla `meta` con la zona horaria del set (el reporte la usa para mostrar las fechas).
- Las 20 pruebas ahora también generan el reporte (incluso con el set vacío y con datos sucios) y verifican que no tenga recursos externos.
- Límite: en GitHub un HTML no se ve renderizado desde la página del repo; hay que bajarlo o activar GitHub Pages. Para el video de demo alcanza con abrirlo local.
- Práctica: **54,56 / 55**, sin cambios.

## Punto 6 — Borrador de `PITCH.md` (jueves 12, 13:16) ✅

- `PITCH.md` en la raíz: la frase, versión de 3 minutos (problema, idea, coordinación, guion de demo sobre el reporte, resultados y costo, cierre), versión de 60 segundos, qué decir para cada criterio del jurado, las limitaciones dichas de frente, preguntas probables con respuesta y una lista para completar el viernes.
- Todos los números son del set de práctica y están medidos; lo que depende del set final está marcado con **[VIERNES]**.
- Es un borrador: el tono y el orden los tienen que ajustar ustedes ensayando en voz alta.

## Estado al cierre de la sesión del jueves 12

| | |
|---|---|
| Puntaje en práctica | **54,56 / 55** (sin cambios en toda la sesión; salida idéntica byte a byte) |
| Tiempo | 27 a 48 s según la carga de la notebook; memoria pico 640-650 MB |
| Pruebas | 20, todas pasan en el Python global y en el `.venv` nuevo |
| Rama | `nucleo-pipeline`, 8 commits nuevos hoy, sin push |
| IA y APIs | no se usó ninguna |

Archivos nuevos hoy: `README.md` (equipo), `DESAFIO.md` (enunciado, renombrado), `requirements-lock.txt`, `pipeline/validar.py`, `pipeline/costo.py`, `pipeline/reporte.py`, `reporte/practica.html`, `PITCH.md`.

### Nada se trabó. Lo que queda abierto

1. **Postura** sigue en 0,93 en práctica y es lo menos confiable para el set final (sin IA no hay cómo mejorarlo de forma segura).
2. **Escala**: el README explica el diseño pero no hay una corrida medida con millones de comentarios.
3. **No probado**: Python anterior a 3.13, Linux y Mac.
4. `CLAUDE.md` sigue sin versionar; decidan si va al repo público.
5. Falta definir **licencia** (el enunciado propone MIT o Apache 2.0) y el **nombre del equipo** en el README.
6. `main` todavía no tiene nada de esto: hay que unir la rama antes de la entrega.

### Para el viernes 13, en orden

1. Bajar el set final a `datos/final/`.
2. Cerrar lo que no haga falta en la notebook (el tiempo queda en `costo.json`).
3. `python -m pipeline.run --datos datos/final --entrega entrega`
4. Leer la salida: tiene que terminar con "Validación de entrega: OK". Mirar cuántas narrativas y grupos salieron y abrir `reporte/entrega.html`: si algo se ve raro (una sola narrativa gigante, cientos de narrativas, cero grupos), avisar antes de entregar.
5. `git add entrega reporte` + commit, unir a `main`, push.
6. Completar los **[VIERNES]** de `PITCH.md` y cargar en Hacki con el link y el video.

---

# Verificación del jueves 12 a la tarde: ¿funciona, o solo da buen puntaje en práctica?

Cerrado a las 15:12. Todo lo de esta sección se puede volver a generar con los scripts de `verificacion/`
(nuevos, versionados; escriben en `salida/verificacion/`, que no se versiona):

```bash
python -m pipeline.parametros                     # tabla de parámetros
python verificacion/sensibilidad.py               # punto 2 (unos 20 minutos)
python verificacion/generalizacion.py             # puntos 4 y 7 (unos 6 minutos)
python verificacion/ejemplos.py                   # punto 5
python verificacion/informe.py                    # junta todas las tablas
```

## Resumen en diez renglones

1. **Narrativas y ruido son sólidos.** Aguantan mover cualquier parámetro ±50%, medio set, la mitad de los hilos rotos y una muestra de 20.000 comentarios (agrupamiento ≥ 0,96 en todos los casos con respuestas).
2. **La coordinación está parada al borde de un escalón.** Cuatro umbrales enteros (`veces_con_texto`, `veces_sin_texto`, `k_truss`, `ampliar_min_celdas`) se desploman si se aflojan **un solo paso**: de 115 cuentas marcadas se pasa a 137, 202, 283 o 14.437. Endurecerlos un paso casi no cuesta nada. Detalle en el punto 2.
3. **Encontré un falso positivo real**: en una muestra chica dominada por una publicación viral, el pipeline marcó como grupo coordinado a 5 cuentas genuinas. Hay un arreglo de una línea (`min_pubs_compartidas=2`) que lo elimina sin cambiar ningún otro resultado. **No lo activé: es decisión de ustedes** (punto 7).
4. **La postura no mejora tocando pesos**: mover cualquiera de los cinco pesos ±50% no cambia nada, ni en el set completo ni en la segunda mitad. Las narrativas que quedan al revés quedan al revés con cualquier peso razonable. Sigue siendo lo más flojo (0,81 a 0,93 en el set completo y los recortes grandes).
5. **Sin `respuesta_a` el pipeline no sirve para narrativas** (35,6 de 55). Ahora lo avisa con una alerta explícita.
6. **La fecha de origen es frágil cuando el agrupamiento se ensucia o hay pocos datos**: perfecta con el set completo, pero cae a 0,67 con la mitad de los enlaces rotos y a 0,49 en una de las muestras chicas.
7. **Controles de cordura** en práctica: 13 narrativas, 18,9% de ruido, 115 cuentas en grupos de 60, 30 y 25. Ninguno absurdo. Ahora el pipeline los imprime al final de cada corrida, con alertas si algo se sale de rango.
8. **Reproducible**: cuatro corridas seguidas, archivos idénticos byte a byte (y también idénticos a los de antes de los cambios de hoy).
9. **El tiempo depende mucho de la memoria libre de la notebook**: 27 s ayer, 49-51 s hoy con la máquina normal, y **149-177 s** con menos de 0,5 GB de RAM libre. Para el viernes: cerrar Discord, Brave y lo que no haga falta.
10. **Con 20.000 comentarios se puede probar rápido (7-10 s) narrativas, ruido y bandos. Coordinación y origen necesitan el set completo.**

## Qué cambió en el código durante la verificación

Pediste verificar, no cambiar, así que lo que toqué no altera el resultado: la salida de práctica es **idéntica byte a byte** a la de antes (54,56 / 55) y las pruebas pasan (ahora son 23).

- `pipeline/parametros.py` (nuevo): todos los parámetros en un solo lugar, con qué hace cada uno y de dónde salió. Antes estaban repartidos como valores por defecto en seis archivos, y varios estaban escritos como números sueltos dentro del código.
- `--param nombre=valor` en `python -m pipeline.run`: cambia un parámetro solo en esa corrida y lo deja anotado en `costo.json` (`parametros_cambiados`). Sirve para la sensibilidad y para una emergencia el viernes.
- **Controles de cordura** al final de cada corrida (en `pipeline/validar.py`): cantidad de narrativas, % de ruido, cuentas marcadas y tamaño de cada grupo, con alertas si hay menos de 2 o más de 60 narrativas, una narrativa con más de la mitad de los comentarios, ruido fuera de 2%-60%, más del 5% de las cuentas marcadas, un grupo gigante o ningún grupo. No cortan la corrida.
- **Alerta nueva** cuando el set casi no trae respuestas y se usa el plan B.
- `min_pubs_compartidas` (parámetro nuevo de coordinación): **apagado por defecto** (vale 1, no filtra nada). Ver punto 7.
- `verificacion/` (nuevo): cinco scripts. No son parte del pipeline y usan la verdad de práctica.

## 1. Todos los parámetros y umbrales

45 parámetros: 19 «ajustado en práctica», 16 «criterio, sin ajustar», 7 «técnico», 3 «regla general».

| Parámetro | Valor | Etapa | Qué hace | De dónde sale |
|---|---|---|---|---|
| `tipeo_min_largo` | 4 | narrativas | Largo mínimo de una palabra para corregirle errores de tipeo (protege palabras cortas como 'la'/'al'). | criterio, sin ajustar |
| `tipeo_razon` | 10 | narrativas | Una palabra rara se corrige solo si la candidata es al menos esta cantidad de veces más frecuente. | criterio, sin ajustar |
| `tfidf` | palabras y pares, min_df=2, tf sublineal | narrativas | Cómo se representa cada texto para comparar frases (TF-IDF). Con muy pocos textos baja a min_df=1. | criterio, sin ajustar |
| `umbral_micro` | 0.5 | narrativas | Parecido mínimo (coseno) entre dos textos para considerarlos la misma frase (microgrupo). | ajustado en práctica |
| `min_peso` | 30 | narrativas | Comentarios mínimos de un microgrupo; los más chicos se disuelven y pasan al grupo grande más parecido. También es lo mínimo para que la prueba de ruido sea concluyente. | ajustado en práctica |
| `umbral_parecido` | 0.25 | narrativas | Parecido mínimo para absorber una variante rara en un microgrupo grande, y para sumar a una narrativa un microgrupo que quedó sin enlaces de respuesta. | ajustado en práctica |
| `lote` | 2000 | narrativas | Textos que se comparan por tanda al armar microgrupos. | técnico |
| `frac_acuerdo` | 0.9 | narrativas | Si esta fracción (o más) de las apariciones de una frase son respuestas, es una frase de acuerdo ('tal cual'): hereda narrativa y postura del comentario al que responde. | ajustado en práctica |
| `alfa_ruido` | 0.01 | narrativas | Nivel de la prueba de ruido: una frase suelta es ruido si, a la tasa de respuestas del propio set, la probabilidad de que nadie le haya respondido nunca es menor a este valor. | regla general |
| `factor_sin_eco` | 0.2 | narrativas | Una frase 'no tiene eco' si recibió menos de esta fracción de las respuestas esperadas. | criterio, sin ajustar |
| `resolucion` | 1 | narrativas | Resolución de Louvain al partir el grafo de frases en narrativas (1 es el valor estándar). | regla general |
| `min_respuestas` | 50 | narrativas | Con menos respuestas que esto en todo el set no se usan los hilos y se pasa al plan B por palabras. | criterio, sin ajustar |
| `umbral_sin_hilos` | 0.1 | narrativas | Plan B (sin hilos): parecido mínimo entre microgrupos para unirlos en una narrativa. | ajustado en práctica |
| `largo_ruido_sin_hilos` | 5 | narrativas | Plan B (sin hilos): una frase con menos palabras que esto, en promedio, es ruido. | ajustado en práctica |
| `max_pasos_hilo` | 64 | narrativas | Profundidad máxima de un hilo de respuestas. | técnico |
| `marcas_rechazo` | 21 expresiones ('mentira', 'falso', 'nada que ver'...) | postura | Marcas de desmentida: el bando que las usa es el que rechaza. Lista del idioma, completada mirando práctica. | ajustado en práctica |
| `peso_marcas` | 20 | postura | Peso del indicio 'un bando usa más marcas de desmentida'. | ajustado en práctica |
| `peso_campana` | 20 | postura | Peso del indicio 'un grupo coordinado empuja este bando'. | ajustado en práctica |
| `peso_sueltos` | 0.5 | postura | Peso del indicio 'este bando aparece más como comentario suelto que como respuesta'. | ajustado en práctica |
| `tope_sueltos` | 3 | postura | Tope (en desvíos estándar) del indicio de comentarios sueltos. | criterio, sin ajustar |
| `peso_variedad` | 1 | postura | Peso del indicio 'este bando tiene más redacciones distintas'. | ajustado en práctica |
| `peso_volumen` | 1 | postura | Peso del indicio 'este bando tiene más comentarios'. | ajustado en práctica |
| `origen_min_comentarios` | 5 | origen | El origen es el primer comentario de la narrativa que tiene al menos esta compañía... | criterio, sin ajustar |
| `origen_ventana_h` | 12 | origen | ...dentro de esta cantidad de horas (descarta apariciones aisladas). | criterio, sin ajustar |
| `ventana_s` | 1800 | coordinacion | Ventana de coincidencia: dos cuentas coinciden si comentan la misma publicación dentro de estos segundos (se calcula dos veces, corrida media ventana). | ajustado en práctica |
| `lift_min` | 40 | coordinacion | Cuántas veces más que lo esperable por azar tienen que coincidir dos cuentas para ser un par fuerte. | ajustado en práctica |
| `veces_con_texto` | 2 | coordinacion | Coincidencias mínimas de un par cuando además empujan la misma narrativa y el mismo bando. | ajustado en práctica |
| `veces_sin_texto` | 3 | coordinacion | Coincidencias mínimas de un par cuando solo se mira publicación y tiempo. | ajustado en práctica |
| `min_pubs_compartidas` | 1 | coordinacion | Publicaciones distintas que tiene que compartir un par fuerte. Con 1 no filtra nada (valor actual); con 2 descarta pares que solo coinciden dentro de una misma publicación viral. | criterio, sin ajustar |
| `k_truss` | 4 | coordinacion | Densidad de la malla: cada par fuerte tiene que compartir al menos k-2 cuentas en común con otros pares fuertes. | ajustado en práctica |
| `min_grupo` | 5 | coordinacion | Cuentas mínimas para que una malla cuente como operación. | criterio, sin ajustar |
| `ampliar_min_celdas` | 2 | coordinacion | Segunda pasada: una cuenta entra a un grupo si aparece en al menos estas celdas dominadas por el grupo. | criterio, sin ajustar |
| `ampliar_min_miembros` | 3 | coordinacion | Segunda pasada: una celda está dominada por un grupo si tiene al menos estos miembros... | criterio, sin ajustar |
| `ampliar_min_fraccion` | 0.333 | coordinacion | ...y además son al menos esta fracción de la celda. | ajustado en práctica |
| `ampliar_rondas` | 3 | coordinacion | Cuántas veces se repite la segunda pasada. | criterio, sin ajustar |
| `camada_max_rareza` | 0.02 | coordinacion | La franja de fechas de creación de un grupo cuenta como indicio solo si menos de esta fracción de todas las cuentas del set fue creada en esa franja. Con ese indicio alcanza una sola celda dominada. | ajustado en práctica |
| `camada_min_validos` | 5 | coordinacion | Cuentas con fecha de creación válida que necesita un grupo para calcular su franja. | criterio, sin ajustar |
| `camada_franja` | percentiles 10 a 90 del grupo, con un margen igual a su ancho (mínimo 1 día) | coordinacion | Cómo se arma la franja de fechas de creación de un grupo. | criterio, sin ajustar |
| `max_aristas` | 200000 | coordinacion | Resguardo: si hubiera más pares fuertes que esto, se conservan solo los de mayor lift. | técnico |
| `bloque` | 4000 | coordinacion | Cuentas por bloque al cruzar pares (acota la memoria). | técnico |
| `memoria_duckdb` | 2GB | ingesta | Límite de memoria de DuckDB; si hace falta más, usa disco. | técnico |
| `hilos_duckdb` | 4 | ingesta | Hilos de CPU que usa DuckDB. | técnico |
| `zona_por_defecto` | -03:00 | ingesta | Zona horaria si ninguna fecha del set trae zona (si la traen, se usa la más frecuente). | regla general |
| `frases_clave` | 6 | salida | Cantidad de términos en frases_clave de cada narrativa. | criterio, sin ajustar |
| `semilla` | 0 | todas | Semilla de azar (solo la usa Louvain). Se cambia con --semilla. | técnico |

Cómo leer la última columna:

- **regla general**: sale del enunciado, del idioma o de la estadística.
- **criterio, sin ajustar**: un valor razonable que puse a ojo y nunca comparé contra la verdad.
- **ajustado en práctica**: lo elegí midiendo contra la verdad del set de práctica. Son los que pueden no servir igual en el set final.
- **técnico**: solo cambia memoria o velocidad.

Dos aclaraciones honestas sobre "ajustado en práctica":

- En varios casos el "ajuste" fue probar un solo valor, ver que daba bien y quedarme con ese (`umbral_micro` 0,5; `frac_acuerdo` 0,9). No hubo una búsqueda fina, así que el riesgo de sobreajuste por esos es bajo, pero tampoco sé si son óptimos.
- Los de coordinación sí salieron de comparar alternativas contra la verdad (ventana de 15 o 30 minutos, repeticiones 2 o 3, k-truss 3, 4 o 5, lift entre 5 y 100). Ahí está el riesgo real, y es justo donde la sensibilidad muestra escalones.

Además de los parámetros, hay **tres supuestos** que no son números y que el set final podría no cumplir: al ruido nadie le responde, las respuestas con texto propio contradicen, y las campañas repiten. Están en el README.

## 2. Sensibilidad: cada parámetro a -50% y a +50%

Set de práctica completo, evaluador oficial. Los enteros se redondean al entero más cercano. "Estable": cambia menos de 0,25 puntos. "Sensible": menos de 1,5. "FRÁGIL": 1,5 o más.

Base: total 54,56 · agrup. 1,000 · ruido 1,000 · postura 0,927 · origen 1,000 · coord. F1 1,000 · grupos 1,000

| Parámetro | Valor | x0.5: valor → total (Δ) | x1.5: valor → total (Δ) | Qué se movió | Veredicto |
|---|---|---|---|---|---|
| `tipeo_min_largo` (narrativas) | 4 | 2 → 54,56 (+0,00) | 6 → 54,41 (-0,15) | origen 0,973 (x1.5) | estable |
| `tipeo_razon` (narrativas) | 10 | 5 → 54,56 (+0,00) | 15 → 54,56 (+0,00) | — | estable |
| `umbral_micro` (narrativas) | 0,5 | 0,25 → 53,03 (-1,53) | 0,75 → 54,40 (-0,16) | ruido 0,993 (x0.5); origen 0,667 (x0.5); grupos 0,991 (x1.5); 114 cuentas marcadas (x1.5) | **FRÁGIL** |
| `min_peso` (narrativas) | 30 | 15 → 54,55 (-0,01) | 45 → 54,56 (+0,00) | — | estable |
| `umbral_parecido` (narrativas) | 0,25 | 0,125 → 54,56 (+0,00) | 0,375 → 54,56 (+0,00) | — | estable |
| `frac_acuerdo` (narrativas) | 0,9 | 0,45 → 54,56 (+0,00) | 1 → 54,56 (+0,00) | — | estable |
| `alfa_ruido` (narrativas) | 0,01 | 0,005 → 54,56 (+0,00) | 0,015 → 54,56 (+0,00) | — | estable |
| `factor_sin_eco` (narrativas) | 0,2 | 0,1 → 54,56 (+0,00) | 0,3 → 54,56 (+0,00) | — | estable |
| `resolucion` (narrativas) | 1 | 0,5 → 54,56 (+0,00) | 1,5 → 54,56 (+0,00) | — | estable |
| `min_respuestas` (narrativas) | 50 | 25 → 54,56 (+0,00) | 75 → 54,56 (+0,00) | — | estable |
| `ventana_s` (coordinacion) | 1800 | 900 → 54,42 (-0,14) | 2700 → 54,41 (-0,15) | grupos 0,992 (x0.5); 114 cuentas marcadas (x0.5); coord. F1 0,991 (x1.5); 117 cuentas marcadas (x1.5) | estable |
| `lift_min` (coordinacion) | 40 | 20 → 54,04 (-0,52) | 60 → 54,56 (+0,00) | coord. F1 0,970 (x0.5); 122 cuentas marcadas (x0.5) | sensible |
| `veces_con_texto` (coordinacion) | 2 | 1 → 34,06 (-20,50) | 3 → 54,56 (+0,00) | coord. F1 0,016 (x0.5); grupos 0,564 (x0.5); 14437 cuentas marcadas (x0.5) | **FRÁGIL** |
| `veces_sin_texto` (coordinacion) | 3 | 2 → 47,17 (-7,39) | 5 → 54,56 (+0,00) | coord. F1 0,578 (x0.5); 283 cuentas marcadas (x0.5) | **FRÁGIL** |
| `min_pubs_compartidas` (coordinacion) | 1 | 1 → 54,56 (+0,00) | 2 → 54,56 (+0,00) | — | estable |
| `k_truss` (coordinacion) | 4 | 2 → 35,97 (-18,59) | 6 → 54,56 (+0,00) | coord. F1 0,028 (x0.5); grupos 0,789 (x0.5); 8107 cuentas marcadas (x0.5) | **FRÁGIL** |
| `min_grupo` (coordinacion) | 5 | 3 → 54,56 (+0,00) | 8 → 54,56 (+0,00) | — | estable |
| `ampliar_min_celdas` (coordinacion) | 2 | 1 → 49,76 (-4,80) | 3 → 54,42 (-0,14) | coord. F1 0,726 (x0.5); 202 cuentas marcadas (x0.5); grupos 0,992 (x1.5); 114 cuentas marcadas (x1.5) | **FRÁGIL** |
| `ampliar_min_miembros` (coordinacion) | 3 | 2 → 54,56 (+0,00) | 5 → 54,42 (-0,14) | grupos 0,992 (x1.5); 114 cuentas marcadas (x1.5) | estable |
| `ampliar_min_fraccion` (coordinacion) | 0,333 | 0,167 → 54,56 (+0,00) | 0,5 → 54,56 (+0,00) | — | estable |
| `camada_max_rareza` (coordinacion) | 0,02 | 0,01 → 54,56 (+0,00) | 0,03 → 54,56 (+0,00) | — | estable |
| `origen_min_comentarios` (origen) | 5 | 3 → 54,56 (+0,00) | 8 → 54,56 (+0,00) | — | estable |
| `origen_ventana_h` (origen) | 12 | 6 → 54,56 (+0,00) | 18 → 54,56 (+0,00) | — | estable |
| `peso_marcas` (postura) | 20 | 10 → 54,56 (+0,00) | 30 → 54,56 (+0,00) | — | estable |
| `peso_campana` (postura) | 20 | 10 → 54,56 (+0,00) | 30 → 54,56 (+0,00) | — | estable |
| `peso_sueltos` (postura) | 0,5 | 0,25 → 54,56 (+0,00) | 0,75 → 54,56 (+0,00) | — | estable |
| `tope_sueltos` (postura) | 3 | 1,5 → 54,56 (+0,00) | 4,5 → 54,56 (+0,00) | — | estable |
| `peso_variedad` (postura) | 1 | 0,5 → 54,56 (+0,00) | 1,5 → 54,56 (+0,00) | — | estable |
| `peso_volumen` (postura) | 1 | 0,5 → 54,56 (+0,00) | 1,5 → 54,56 (+0,00) | — | estable |

No están en la tabla `umbral_sin_hilos` y `largo_ruido_sin_hilos`: solo actúan en el plan B, cuando no hay respuestas.

### Qué significa

**Estables (23 de 29):** todo lo de narrativas menos un caso, todo lo de postura, todo lo de origen, y de coordinación la ventana, el tamaño mínimo de grupo y tres de los cuatro umbrales de la segunda pasada.

**Frágiles, y siempre hacia el mismo lado (aflojar):**

| Parámetro | Paso que lo rompe | Qué pasa | Hacia el otro lado |
|---|---|---|---|
| `veces_con_texto` | 2 → 1 | Marca 14.437 cuentas (el 90% del set). Coincidir una sola vez no es evidencia de nada. | 3: sin costo en el set completo; -2,66 en la segunda mitad (pierde cuentas con poca actividad). |
| `k_truss` | 4 → 3 | Marca 137 cuentas (22 genuinas). Con 2 marca 8.107. | 5: sin ningún costo, ni en el set completo ni en la segunda mitad. 6: sin costo en el set completo. |
| `veces_sin_texto` | 3 → 2 | Marca 283 cuentas (168 genuinas). | 4 (segunda mitad) y 5 (set completo): sin ningún costo. |
| `ampliar_min_celdas` | 2 → 1 | Marca 202 cuentas (87 genuinas): entra cualquiera que pasó una vez por una ráfaga. | 3: -0,14 en el set completo, -1,06 en la segunda mitad. |
| `umbral_micro` | 0,5 → 0,25 | Se pegan frases distintas: origen 0,67 y ruido 0,993. | Con 0,375 no pasa nada: hay margen. Con 0,75 pierde 0,16. |

**Sensible:** `lift_min` a 20 marca 7 cuentas genuinas (-0,52). Entre 30 y 60 no cambia nada.

Para ver dónde está el borde, repetí los que se movieron con ±25%:

Base: total 54,56 · agrup. 1,000 · ruido 1,000 · postura 0,927 · origen 1,000 · coord. F1 1,000 · grupos 1,000

| Parámetro | Valor | x0.75: valor → total (Δ) | x1.25: valor → total (Δ) | Qué se movió | Veredicto |
|---|---|---|---|---|---|
| `umbral_micro` (narrativas) | 0,5 | 0,375 → 54,56 (+0,00) | 0,625 → 54,40 (-0,16) | grupos 0,991 (x1.25); 114 cuentas marcadas (x1.25) | estable |
| `ventana_s` (coordinacion) | 1800 | 1350 → 54,56 (+0,00) | 2250 → 54,56 (+0,00) | — | estable |
| `lift_min` (coordinacion) | 40 | 30 → 54,56 (+0,00) | 50 → 54,56 (+0,00) | — | estable |
| `k_truss` (coordinacion) | 4 | 3 → 53,03 (-1,53) | 5 → 54,56 (+0,00) | coord. F1 0,913 (x0.75); 137 cuentas marcadas (x0.75) | **FRÁGIL** |

Y sobre la **segunda mitad de los días** (un recorte más difícil, que no usé para elegir nada), con ±25%:

Base: total 52,70 · agrup. 0,999 · ruido 0,998 · postura 0,808 · origen 1,000 · coord. F1 0,963 · grupos 0,936

| Parámetro | Valor | x0.75: valor → total (Δ) | x1.25: valor → total (Δ) | Qué se movió | Veredicto |
|---|---|---|---|---|---|
| `lift_min` (coordinacion) | 40 | 30 → 52,70 (+0,00) | 50 → 52,70 (+0,00) | — | estable |
| `veces_con_texto` (coordinacion) | 2 | 1 → 35,01 (-17,69) | 3 → 50,04 (-2,66) | coord. F1 0,017 (x0.75); grupos 0,786 (x0.75); 13459 cuentas marcadas (x0.75); coord. F1 0,847 (x1.25); grupos 0,853 (x1.25); 83 cuentas marcadas (x1.25) | **FRÁGIL** |
| `veces_sin_texto` (coordinacion) | 3 | 2 → 45,07 (-7,63) | 4 → 52,70 (+0,00) | coord. F1 0,528 (x0.75); 285 cuentas marcadas (x0.75) | **FRÁGIL** |
| `min_pubs_compartidas` (coordinacion) | 1 | 1 → 52,70 (+0,00) | 2 → 52,70 (+0,00) | — | estable |
| `k_truss` (coordinacion) | 4 | 3 → 52,25 (-0,45) | 5 → 52,70 (+0,00) | coord. F1 0,938 (x0.75); 111 cuentas marcadas (x0.75) | sensible |
| `ampliar_min_celdas` (coordinacion) | 2 | 1 → 50,58 (-2,12) | 3 → 51,64 (-1,06) | coord. F1 0,836 (x0.75); grupos 0,951 (x0.75); 143 cuentas marcadas (x0.75); coord. F1 0,924 (x1.25); grupos 0,887 (x1.25); 97 cuentas marcadas (x1.25) | **FRÁGIL** |

En la segunda mitad también probé los seis pesos de postura a ±50%: el total no se mueve (52,70 en los doce casos).

### Mi lectura

- **Aviso de fragilidad, como pediste:** `veces_con_texto`, `veces_sin_texto`, `k_truss` y `ampliar_min_celdas` son umbrales enteros y el valor actual es, en los cuatro, **el mínimo que da precisión perfecta en práctica**. Un paso más flojo y aparecen falsos positivos de a decenas o miles. No hay "cambio chico" posible en un entero, así que esto no dice que el sistema sea inestable con los valores actuales; dice que **no tenemos margen de seguridad del lado de los falsos positivos**. Si en el set final las cuentas genuinas coinciden un poco más que en práctica, lo vamos a pagar en precisión.
- `k_truss=5` y `veces_sin_texto=4` darían ese margen **gratis** (cero costo medido en el set completo y en las dos mitades). `veces_con_texto` y `ampliar_min_celdas` no se pueden endurecer sin perder cuentas reales.
- Los pesos de postura no son frágiles, pero por una mala razón: no importan. Las narrativas con marcas de desmentida o con campaña se deciden por mucho margen, y las que no tienen ninguna de las dos se deciden por indicios tan débiles que salen igual con cualquier peso.

## 3. Controles de cordura sobre la salida de práctica

| Control | Resultado | Referencia en práctica | ¿Absurdo? |
|---|---|---|---|
| Narrativas encontradas | **13** | 13 | No |
| Tamaño de las narrativas | de 3.513 a 18.463 comentarios; la mayor es el 11% | de 3.513 a 18.463 | No: coinciden una por una con las reales |
| Comentarios marcados como ruido | **37.710 (18,9%)** | 37.710 (18,9%) | No |
| Cuentas marcadas como coordinadas | **115 de 15.991 (0,72%)** | 115 | No |
| Grupos y tamaños | **3 grupos: 60, 30 y 25 cuentas** | 60, 30 y 25 | No |

Esto es lo que imprime ahora el pipeline al terminar:

```
Validación de salida\practica: OK, cumple el formato del enunciado
Controles de cordura: sin alertas
  narrativas: 13 (la mayor tiene el 11% de los comentarios con narrativa; la menor, 3513 comentarios)
  ruido: 18.9% de los comentarios
  cuentas coordinadas: 115 de 15991 (0.72%) en 3 grupos, de tamaños 60, 30, 25
```

Los controles sí saltan cuando tienen que saltar. Sin respuestas avisa "una sola narrativa junta el 83% de los comentarios"; con `veces_con_texto=1` avisaría que marcó el 90% de las cuentas. Lo que **no** detectan es un error chico: un grupo falso de 5 cuentas pasa sin alerta (ver punto 7).

## 4. Generalización: mitades de días, sin respuestas y con la mitad de las respuestas borradas

Cada recorte se corre de punta a punta en otro proceso y se mide con el evaluador oficial contra la verdad recortada igual. Entre paréntesis, lo que hay de verdad en ese recorte. En "Origen", la verdad se rehízo para el recorte (primer comentario de la narrativa adentro del recorte, y solo cuenta la que nace adentro).

| Recorte | Comentarios | Narrativas (hay) | Ruido | Agrup. F1 | Ruido F1 | Postura | Origen | Coord. P / R | Marcadas (hay) | Grupos | Total /55 | Tiempo | Memoria |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| completo | 200.000 | 13 (13) | 18,9% | 1,000 | 1,000 | 0,927 | 1,00 | 1,00 / 1,00 | 115 (115) | 60, 30, 25 | 54,56 | 33 s | 645 MB |
| primera_mitad | 100.884 | 12 (12) | 18,9% | 1,000 | 1,000 | 0,901 | 1,00 | 0,99 / 1,00 | 115 (114) | 59, 31, 25 | 54,33 | 18 s | 451 MB |
| segunda_mitad | 99.116 | 13 (13) | 18,9% | 0,999 | 0,998 | 0,808 | 1,00 | 1,00 / 0,93 | 105 (113) | 59, 24, 22 | 52,70 | 18 s | 422 MB |
| sin_respuestas | 200.000 | 24 (13) | 15,8% | 0,376 | 0,725 | 0,337 | 0,00 | 1,00 / 0,98 | 113 (115) | 60, 28, 25 | 35,65 | 40 s | 612 MB |
| mitad_enlaces | 200.000 | 13 (13) | 18,5% | 0,966 | 0,982 | 0,883 | 0,67 | 1,00 / 0,99 | 114 (115) | 59, 30, 25 | 52,06 | 53 s | 593 MB |
| mitad_respuestas_borradas | 185.908 | 13 (13) | 20,4% | 0,998 | 0,996 | 0,822 | 1,00 | 1,00 / 0,99 | 114 (115) | 59, 30, 25 | 53,74 | 44 s | 597 MB |
| muestra_20k_a | 20.047 | 14 (13) | 18,6% | 0,997 | 0,995 | 0,999 | 1,00 | 1,00 / 0,33 | 22 (67) | 16, 6 | 40,41 | 7 s | 261 MB |
| muestra_20k_b | 20.415 | 13 (13) | 19,1% | 0,998 | 0,995 | 0,893 | 1,00 | 1,00 / 0,08 | 5 (60) | 5 | 32,60 | 8 s | 258 MB |
| muestra_20k_c | 21.422 | 14 (13) | 19,6% | 0,994 | 0,980 | 0,971 | 0,49 | 0,00 / 0,00 | 5 (36) | 5 | 28,51 | 10 s | 359 MB |

Qué es cada recorte:

- **primera_mitad / segunda_mitad**: días 1 a 7 y días 8 a 14.
- **sin_respuestas**: `respuesta_a` vacío en todos los comentarios.
- **mitad_enlaces**: `respuesta_a` vacío en la mitad de las respuestas, al azar. El comentario queda, pero suelto.
- **mitad_respuestas_borradas**: se borra la mitad de las respuestas, al azar. El comentario desaparece.
- **muestra_20k_a/b/c**: punto 7.

### Comparación

- **Primera mitad contra segunda mitad:** narrativas y ruido iguales (1,000 y 0,999). La diferencia está en dos lugares. Postura: 0,90 contra 0,81. En las dos mitades quedan al revés dos narrativas: la de la licitación en ambas, y otra que cambia según la mitad (la de los turnos en la primera, la de los médicos en la segunda), porque depende de indicios débiles. Coordinación: 115 de 114 marcadas contra 105 de 113; en la segunda mitad la campaña de cuentas viejas actúa menos veces y se pierden 8 cuentas. En la primera mitad hay **un falso positivo** (una cuenta genuina sumada al grupo de cuentas viejas en la segunda pasada).
- **Sin `respuesta_a`:** narrativas 0,376, ruido 0,725, postura 0,337, origen 0. Encuentra 24 "narrativas" y una tiene el 83% de los comentarios. La coordinación sigue andando (113 de 115, sin falsos positivos) porque usa solo publicación y tiempo. Es el punto débil conocido: **todo el análisis de narrativas depende de que haya respuestas.**
- **Mitad de los enlaces borrados:** aguanta (agrupamiento 0,966, ruido 0,982), pero aparece un problema nuevo. Las frases de acuerdo que perdieron su enlace ("ni más ni menos", sueltas desde el día 1) terminan asignadas a una narrativa, y como el origen es "el primer comentario con compañía", **la fecha de origen de esa narrativa se corre nueve días** (del 10 de septiembre al 1). Origen cae a 0,67.
- **Mitad de las respuestas borradas:** casi no se nota en narrativas (0,998) ni en coordinación. Baja la postura (0,82); no investigué cuál narrativa se dio vuelta, pero es esperable: con menos contradicciones hay menos indicios para orientar.

## 5. Ejemplos reales para revisar a ojo

Elegidos al azar con semilla fija (`python verificacion/ejemplos.py`), sin mirar si estaban bien. La columna "Verdad" es la etiqueta real de práctica, para comparar. Narrativas: la más grande, la del medio y la más chica.

### Comentarios al azar

**n01** — «Los pozos se están secando desde que llegó la minera esa.» (18.463 comentarios)

| Comentario | Texto | Tipo | Postura asignada | Verdad |
|---|---|---|---|---|
| c0001307 | nos dejan sin agua para que la minera saque el litio. | respuesta | apoya | L1 apoya |
| c0004086 | Para mí cada día hay menos agua en Villa Tolar y nadie dice nada de la minera, lo digo en serio. | suelto | apoya | L1 apoya |
| c0007795 | como siempre, la salmuera no es agua potable, dejen de mezclar las cosas. así estamos. | suelto | rechaza | L1 rechaza |
| c0023660 | falso que la mina deja sin agua al pueblo, usan agua salada que no es para consumo, te juro. | suelto | rechaza | L1 rechaza |
| c0033496 | Te digo algo: el problema del agua en Tolar es la red vieja, no la minera eh. 🙄 | suelto | rechaza | L1 rechaza |
| c0037499 | COINCIDO | respuesta | rechaza | L1 rechaza |
| c0074094 | Y el agua? 💧 | suelto | apoya | L1 apoya |
| c0096852 | Primero el agua de la gente, después el litio. | suelto | apoya | L1 apoya |
| c0154733 | Hay q decirlo: sin vegas no hay ganado, y el bombeo las está secando. 😡 | suelto | apoya | L1 apoya |
| c0160112 | jaja mentira que la mina deja sin agua al pueblo, usan agua salada que no es para consumo. despierten. | suelto | rechaza | L1 rechaza |

En esta muestra: 10 de 10 son de la misma narrativa real (L1); 10 de 10 tienen la postura correcta.

**n07** — «Pedí turno en marzo y me lo dieron para agosto.» (12.537 comentarios)

| Comentario | Texto | Tipo | Postura asignada | Verdad |
|---|---|---|---|---|
| c0011096 | Ahora se sacan por teléfono y salen más rápido. 💯 | respuesta | rechaza | H4 rechaza |
| c0041874 | Con el nuveo sistema online mejoró bastante. | suelto | rechaza | H4 rechaza |
| c0067475 | Hay que decirlo: las demoras son por falta de especialistas, no del sistema de turnos. 👏 | respuesta | rechaza | H4 rechaza |
| c0075709 | Sinceramente a mí me atendieron en una semana, depende de la especialidad. Es así. | suelto | rechaza | H4 rechaza |
| c0109286 | Para un turno con el traumatólogo me dieron para dentro de seis meses. 😡 | respuesta | apoya | H4 apoya |
| c0111558 | Para mí hay que ir a las 4 de la mañana a hacer fila para un turno. | suelto | apoya | H4 apoya |
| c0145595 | Ojo, pedí turno en marzo y me lo dieron para agosto. 🤬 | respuesta | apoya | H4 apoya |
| c0154194 | Los turnos tardan meses, la gente se muere esperando. 😔 | suelto | apoya | H4 apoya |
| c0182984 | con el nuevo sistema online mejoró bastante. 🤬 | suelto | rechaza | H4 rechaza |
| c0183137 | Jaja pedi turno en marzo y me lo dieron para agosto. Triste. | respuesta | apoya | H4 apoya |

En esta muestra: 10 de 10 son de la misma narrativa real (H4); 10 de 10 tienen la postura correcta.

**n13** — «Ya van a cortar la cinta en campaña aunque no haya ni camas.» (3.513 comentarios)

| Comentario | Texto | Tipo | Postura asignada | Verdad |
|---|---|---|---|---|
| c0094520 | la verdad que todo para la foto electoral, el hospital es una excusa. abran los ojos. | suelto | apoya | H3 apoya |
| c0095209 | Ojo, todo para la foto electoral, el hospital es una excusa. Qué bronca. | suelto | apoya | H3 apoya |
| c0104917 | siempre buscan la vuelta para criticar, el nosocomio hace falta. 💯 | suelto | rechaza | H3 rechaza |
| c0108039 | 100% de acuerdo | respuesta | rechaza | H3 rechaza |
| c0109373 | Lo van a inaugurar justo antes de las elecciones, para la foto. Así estamos. | suelto | apoya | H3 apoya |
| c0111771 | para mi todo para la foto electoral, el hospital es una excusa. abran los ojos. | respuesta | apoya | H3 apoya |
| c0113307 | che, el hospital lo terminan en campaña, siempre lo mismo. abran los ojos. | suelto | apoya | H3 apoya |
| c0120765 | Che, si lo terminan no importa cuando, importa que funcione. Lamentable. | suelto | rechaza | H3 rechaza |
| c0151542 | che, ya van a cortar la cinta en campaña aunque no haya ni camas. | suelto | apoya | H3 apoya |
| c0154928 | escuchen: inauguran el nosocomio vacío para la foto y después lo cierran. | suelto | apoya | H3 apoya |

En esta muestra: 10 de 10 son de la misma narrativa real (H3); 10 de 10 tienen la postura correcta.

**ninguna** — «comentarios marcados como ruido» (10 de muestra)

| Comentario | Texto | Tipo | Postura asignada | Verdad |
|---|---|---|---|---|
| c0008199 | Buen día a todos | suelto | — | ninguna  |
| c0017390 | Hay que pedir turno por teléfono o presencial? | suelto | — | ninguna  |
| c0019098 | Comparto | suelto | — | ninguna  |
| c0036232 | HAY VIDEO DE LA AUDIENCIA? | suelto | — | ninguna  |
| c0036632 | Mmm no sé | suelto | — | ninguna  |
| c0047493 | Fuerza! | suelto | — | ninguna  |
| c0116450 | alguien sabe a que hora es la asamblea? | suelto | — | ninguna  |
| c0160192 | Primero! | suelto | — | ninguna  |
| c0162273 | desde cuándo rige? | suelto | — | ninguna  |
| c0174116 | y el estudiantil cuánto queda? | suelto | — | ninguna  |

En esta muestra: 10 de 10 son ruido de verdad.

### Cuentas marcadas como coordinadas y por qué

- **g01**: 60 cuentas, 60 en el núcleo (malla densa) y 0 sumadas en la segunda pasada. Fechas de creación en un rango de 3 días (camada: franja rara en el set, cuenta como indicio).
- **g02**: 30 cuentas, 29 en el núcleo (malla densa) y 1 sumadas en la segunda pasada. Fechas de creación en un rango de 2042 días (no forman camada: la antigüedad no se usó).
- **g03**: 25 cuentas, 25 en el núcleo (malla densa) y 0 sumadas en la segunda pasada. Fechas de creación en un rango de 5 días (camada: franja rara en el set, cuenta como indicio).

| Cuenta | Grupo | Cómo entró | Pares fuertes dentro del grupo | Más veces con un mismo par | Lift máximo | Comentarios (en ráfaga con el grupo) | Su mayor ráfaga | Creada | Verdad |
|---|---|---|---|---|---|---|---|---|---|
| u009823 | g01 | núcleo: malla densa de pares fuertes | 36 de 59 | 4 | 936 | 6 (5) | p00135, 04/09 18:53: 26 cuentas más del grupo en ±15 min | 2026-08-29 | C1 |
| u011408 | g01 | núcleo: malla densa de pares fuertes | 52 de 59 | 5 | 933 | 9 (8) | p00135, 04/09 18:50: 26 cuentas más del grupo en ±15 min | 2026-08-29 | C1 |
| u012344 | g01 | núcleo: malla densa de pares fuertes | 53 de 59 | 7 | 779 | 10 (9) | p00302, 09/09 16:47: 26 cuentas más del grupo en ±15 min | 2026-08-27 | C1 |
| u012760 | g01 | núcleo: malla densa de pares fuertes | 19 de 59 | 3 | 1186 | 4 (3) | p00070, 02/09 19:21: 24 cuentas más del grupo en ±15 min | 2026-08-26 | C1 |
| u002416 | g02 | núcleo: malla densa de pares fuertes | 21 de 29 | 5 | 301 | 19 (8) | p00018, 01/09 14:55: 12 cuentas más del grupo en ±15 min | 2020-05-07 | C2 |
| u003533 | g02 | núcleo: malla densa de pares fuertes | 10 de 29 | 4 | 268 | 17 (6) | p00017, 01/09 14:49: 13 cuentas más del grupo en ±15 min | 2024-10-16 | C2 |
| u009692 | g02 | segunda pasada: coincide con el grupo como conjunto | 3 de 29 | 3 | 229 | 15 (3) | p00096, 03/09 19:17: 13 cuentas más del grupo en ±15 min | 2025-06-24 | C2 |
| u000798 | g03 | núcleo: malla densa de pares fuertes | 19 de 24 | 4 | 3569 | 5 (5) | p00342, 11/09 02:44: 17 cuentas más del grupo en ±15 min | 2026-08-30 | C3 |
| u001029 | g03 | núcleo: malla densa de pares fuertes | 23 de 24 | 5 | 2891 | 7 (7) | p00342, 11/09 02:38: 17 cuentas más del grupo en ±15 min | 2026-08-30 | C3 |
| u014047 | g03 | núcleo: malla densa de pares fuertes | 12 de 24 | 3 | 3657 | 3 (3) | p00342, 11/09 02:39: 17 cuentas más del grupo en ±15 min | 2026-08-30 | C3 |

### El caso que esa muestra no deja ver

Las tres narrativas de arriba salieron con 30 de 30 posturas correctas, pero eso es suerte en la elección: hay una narrativa con la postura **entera al revés**. La agrego para que la vean (`python verificacion/ejemplos.py --narrativas n08`):

**n08** — «Nadie quiere venir a dar el servicio acá, no es negocio.» (11.848 comentarios)

| Comentario | Texto | Tipo | Postura asignada | Verdad |
|---|---|---|---|---|
| c0028240 | lo mismo digo | respuesta | apoya | B3 rechaza |
| c0041711 | Te digo algo: hace veinte años que están las mismas empresas, basta. 😔 | suelto | rechaza | B3 apoya |
| c0053476 | sinceramente hay que llamar a licitación y que entren otras empresas. qué bronca. | suelto | rechaza | B3 apoya |
| c0086463 | Con otra compañía el boleto sería más caro. 🙄 | suelto | apoya | B3 rechaza |
| c0102970 | Como siempre, licitar para que ganen los mismos de siempre, no cambia nada. | respuesta | apoya | B3 rechaza |
| c0110361 | ojo, licitacion ya, que vnegan empresas que inviertan. 💯 | suelto | rechaza | B3 apoya |
| c0142311 | Jaja una lciitacion tarda años, no es la solucion. 🙄 | suelto | apoya | B3 rechaza |
| c0163975 | Che, licitar para que ganen los misoms de siempre, no cambia nada, te juro. Asi estamos. | suelto | apoya | B3 rechaza |
| c0181235 | Clarísimo | respuesta | apoya | B3 rechaza |
| c0185252 | A ver, con otra compañía el boleto sería más caro. | suelto | apoya | B3 rechaza |

En esta muestra: 10 de 10 son de la misma narrativa real (B3); 0 de 10 tienen la postura correcta.

Los comentarios están bien agrupados y bien separados en dos bandos; lo que está mal es cuál bando se llamó "apoya". La narrativa real es "hay que llamar a licitación", y el pipeline tomó como afirmación la respuesta ("licitar no cambia nada"). Por eso el título que le puso también es el del bando equivocado.

### Qué mirar en las cuentas marcadas

- "Pares fuertes dentro del grupo": con cuántas otras cuentas del grupo coincide varias veces y muy por encima del azar. Ojo: este número solo dice algo en grupos grandes. En el grupo falso de 5 cuentas del punto 7, cada una tenía 4 de 4.
- "Comentarios (en ráfaga con el grupo)": casi todo lo que hacen las de g01 y g03 es en ráfaga. Las de g02 tienen 15-19 comentarios y solo 3-8 en ráfaga: el resto es cobertura. Es la campaña difícil.
- La cuenta que entró por la segunda pasada (u009692) tiene solo 3 pares fuertes: sola no formaba malla, pero aparece tres veces en ráfagas dominadas por el grupo.
- En práctica las diez son campaña de verdad.

## 6. Dos corridas seguidas: mismos archivos, tiempo y memoria

Corrí el pipeline completo cuatro veces seguidas en el entorno `.venv`, cada una a su carpeta y su base:

| Corrida | Tiempo total | Memoria pico | Estado de la notebook |
|---|---|---|---|
| 1 | 176,8 s | 424 MB | 0,45 GB de RAM libre y CPU al 60% (medido al terminar la corrida 2) |
| 2 | 148,6 s | 427 MB | igual |
| 3 | 50,8 s | 654 MB | 1 GB de RAM libre |
| 4 | 48,6 s | 649 MB | igual |

- `comentarios.csv`, `narrativas.csv` y `cuentas.csv` son **idénticos byte a byte en las cuatro** (mismo md5) e idénticos a la salida de antes de los cambios de hoy. `costo.json` cambia, como corresponde: lleva el tiempo.
- Puntaje de esas corridas: **54,56 / 55**.
- **El tiempo varió 3,5 veces sin cambiar nada del código.** En las corridas 1 y 2 la máquina tenía menos de medio giga libre (Discord, Brave, el editor y un proceso de vista web ocupaban entre 200 y 470 MB cada uno) y lo más probable es que Windows le haya ido sacando memoria al proceso: eso explicaría que el "pico" medido sea más bajo (424 MB) y que todo tarde el triple. No lo aislé con una prueba controlada. Con 1 GB libre, 49-51 s. Ayer, con la máquina descansada, 27 s.
- Qué etapa manda: narrativas (14 s) y coordinación (16 s) en una corrida normal; ingesta 11 s; validación 5 s.
- **Para el viernes:** cerrar todo lo que se pueda antes de correr. El resultado no cambia, pero el tiempo queda escrito en `costo.json` y es lo que mira el jurado.

## 7. Muestra chica: 20.000 comentarios de publicaciones completas

Tres muestras distintas: publicaciones completas elegidas al azar hasta juntar 20.000 comentarios, con todos sus hilos (las respuestas siempre son de la misma publicación). Están en la tabla del punto 4.

| | Muestra a | Muestra b | Muestra c | Set completo |
|---|---|---|---|---|
| Total /55 | 40,41 | 32,60 | 28,51 | 54,56 |
| Agrupamiento F1 | 0,997 | 0,998 | 0,994 | 1,000 |
| Ruido F1 | 0,995 | 0,995 | 0,980 | 1,000 |
| Postura | 0,999 | 0,893 | 0,971 | 0,927 |
| Origen | 1,00 | 1,00 | 0,49 | 1,00 |
| Cuentas coordinadas: marcadas (hay) | 22 (67) | 5 (60) | 5 (36) | 115 (115) |
| Coordinación: precisión / recall | 1,00 / 0,33 | 1,00 / 0,08 | **0,00** / 0,00 | 1,00 / 1,00 |
| Tiempo | 7 s | 8 s | 10 s | 27-51 s |

### Qué se puede probar rápido y qué necesita el set completo

| Parte | ¿Sirve la muestra chica? | Por qué |
|---|---|---|
| Agrupamiento de narrativas | **Sí** (0,994 a 0,998) | Con 20.000 comentarios ya hay cientos de respuestas por narrativa. |
| Ruido | **Sí** (0,980 a 0,995) | Las frases de ruido son muy repetidas; alcanzan pocas apariciones. En la muestra c baja a 0,980: una frase de ruido que también se usa como respuesta ("Siempre lo mismo") quedó asignada a una narrativa. |
| Separar los dos bandos | **Sí** | Sale del mismo grafo que las narrativas. |
| Orientar la postura | A medias (0,89 a 1,00) | Varía según qué narrativas tengan marcas de desmentida en la muestra. No dice nada sobre el set completo. |
| Fecha de origen | **No confiable** (1,00, 1,00 y 0,49) | Con pocos comentarios, los primeros de una narrativa quedan muy separados y la regla "5 comentarios en 12 horas" salta al primer momento denso (un día después). Además, una frase de ruido mal asignada corre el origen varios días. |
| Coordinación | **No** (recall 0,00 a 0,33) | Necesita que las mismas cuentas coincidan en **varias** publicaciones. En la muestra entra una o dos ráfagas de cada campaña. No es un error: en esas muestras no hay evidencia para encontrarlas. |

Para iterar rápido: cambios en texto, microgrupos, ruido o narrativas se pueden probar en 10 segundos con una muestra. Cualquier cambio en coordinación, origen u orientación de postura hay que medirlo en el set completo (o en una mitad).

### El falso positivo de la muestra c (esto sí es un defecto)

En la muestra c el pipeline marcó un grupo de 5 cuentas y **las 5 son genuinas**. Lo investigué:

- La muestra tiene 39 publicaciones y una sola, viral, tiene 6.793 de los 21.422 comentarios.
- Esas 5 cuentas tienen 2 comentarios cada una en la muestra, los dos en esa publicación: uno entre las 05:04 y las 05:28 y otro entre las 06:04 y las 06:22, todos apoyando la misma narrativa. En esas dos ventanas había 315 y 170 cuentas diciendo lo mismo.
- Coincidieron "2 veces", que es el mínimo. Y como tienen solo 2 comentarios cada una, lo "esperable por azar" que calcula el pipeline es casi cero, así que el cociente da 49 (el umbral es 40). Las diez parejas posibles pasan, forman una malla perfecta de 5 y el pipeline las llama operación.
- En el set completo las mismas 5 cuentas tienen entre 4 y 34 comentarios, el cociente baja a entre 2 y 64 según el par, la malla no se forma y **no se marcan**.

El defecto de fondo: **dos coincidencias dentro de la misma publicación viral cuentan como "repetición"**, y la comparación contra el azar favorece a las cuentas con muy poca actividad. En el set completo no se manifestó, pero el set final puede tener publicaciones más grandes o cuentas menos activas.

**Arreglo probado, no activado:** pedir que un par fuerte comparta al menos 2 publicaciones distintas (`min_pubs_compartidas=2`). Lo corrí en los nueve recortes:

| Recorte | Actual: total, marcadas, P / R | [min_pubs_compartidas=2] | [k_truss=5] [veces_sin_texto=4] [min_pubs_compartidas=2] |
|---|---|---|---|
| completo | 54,56, 115, 1,00 / 1,00 | 54,56, 115, 1,00 / 1,00 | 54,56, 115, 1,00 / 1,00 |
| primera_mitad | 54,33, 115, 0,99 / 1,00 | 54,33, 115, 0,99 / 1,00 | 54,33, 115, 0,99 / 1,00 |
| segunda_mitad | 52,70, 105, 1,00 / 0,93 | 52,70, 105, 1,00 / 0,93 | 52,70, 105, 1,00 / 0,93 |
| sin_respuestas | 35,65, 113, 1,00 / 0,98 | 35,65, 113, 1,00 / 0,98 | 35,24, 110, 1,00 / 0,96 |
| mitad_enlaces | 52,06, 114, 1,00 / 0,99 | 52,06, 114, 1,00 / 0,99 | 51,92, 113, 1,00 / 0,98 |
| mitad_respuestas_borradas | 53,74, 114, 1,00 / 0,99 | 53,74, 114, 1,00 / 0,99 | 53,74, 114, 1,00 / 0,99 |
| muestra_20k_a | 40,41, 22, 1,00 / 0,33 | 40,41, 22, 1,00 / 0,33 | 40,41, 22, 1,00 / 0,33 |
| muestra_20k_b | 32,60, 5, 1,00 / 0,08 | 32,60, 5, 1,00 / 0,08 | 32,60, 5, 1,00 / 0,08 |
| muestra_20k_c | 28,51, 5, 0,00 / 0,00 | 28,51, 0, 0,00 / 0,00 | 28,51, 0, 0,00 / 0,00 |

Cada celda es total, cuentas marcadas y precisión / recall. Con `min_pubs_compartidas=2` el falso grupo de la muestra c desaparece y **los otros ocho recortes quedan exactamente igual**. La tercera columna suma además `k_truss=5` y `veces_sin_texto=4` (el margen de seguridad del punto 2): igual en siete recortes, y pierde 1 y 3 cuentas en los dos recortes con hilos rotos.

## Qué recomiendo (decisiones para ustedes)

1. **Activar `min_pubs_compartidas=2`.** Es coherente con la idea del método (repetir es coincidir en lugares distintos, no dos veces en el mismo momento viral), arregla el único falso grupo que vi y no cambia nada más. Riesgo: una operación que actúa siempre en una sola publicación dejaría de verse. Para probarlo sin tocar el código: `python -m pipeline.run --datos ... --entrega ... --param min_pubs_compartidas=2`. Para dejarlo fijo, es cambiar un 1 por un 2 en `pipeline/parametros.py`.
2. **Considerar `k_truss=5` y `veces_sin_texto=4`** para tener margen contra falsos positivos. Costo medido: nada en el set completo ni en las mitades; 1 a 3 cuentas en los recortes con hilos rotos. Yo lo haría, pero es menos claro que el punto 1: si las campañas del set final repiten menos que las de práctica, se pierde algo de recall.
3. **No tocar** `veces_con_texto` ni `ampliar_min_celdas`: están en el único valor que funciona.
4. **Postura:** confirmado que no se arregla con parámetros. Sigue en pie la opción de una sola llamada a un modelo de lenguaje, que ustedes decidieron no usar por ahora.
5. **El viernes, mirar los controles de cordura antes de entregar.** Si aparece una alerta, o si los grupos son muchos y chicos (varios de 5 o 6 cuentas), desconfiar de la coordinación.

## Lo que esta verificación no cubre

- Todas las pruebas usan recortes **del mismo set de práctica**: mismos temas, mismas tres campañas, mismo generador. Miden si el método aguanta menos datos y datos rotos; no miden si aguanta **otro estilo de campaña** u otra forma de escribir. Eso solo se va a saber con el set final.
- La sensibilidad mueve los parámetros de a uno. No probé combinaciones, salvo la de la recomendación 2.
- No probé con otra semilla (solo la usa Louvain, y la partición sale igual con resolución 0,5, 1 y 1,5, así que espero que no importe; no lo medí).
- Sigue sin medirse una corrida con millones de comentarios.

---

# Jueves 12, 15:45: umbrales con margen y tope de seguridad

## Umbrales activados (decisión del equipo)

| Parámetro | Antes | Ahora |
|---|---|---|
| `min_pubs_compartidas` | 1 (no filtraba) | **2** |
| `k_truss` | 4 | **5** |
| `veces_sin_texto` | 3 | **4** |

Confirmado en práctica: **54,56 / 55** y `comentarios.csv`, `narrativas.csv` y `cuentas.csv` **idénticos byte a byte** a la salida anterior (mismos md5). 115 cuentas en grupos de 60, 30 y 25.

Lo que cambia con estos valores, medido en la verificación de la tarde: desaparece el grupo falso de 5 cuentas de la muestra chica; el set completo y las dos mitades quedan igual; en los dos recortes con hilos rotos se pierden 1 y 3 cuentas reales.

Efecto lateral: las tablas de sensibilidad de más arriba se midieron con los valores viejos como base. Siguen valiendo como diagnóstico (ahí se ve por qué se movieron), pero "x0.5" y "x1.5" ya no parten del mismo número. No las volví a correr.

## Tope de seguridad de coordinación

- **Regla:** si se marca más del **5% de las cuentas** como coordinadas, el resultado no es creíble (una operación es una minoría chica). El pipeline endurece un umbral, vuelve a detectar, y repite hasta bajar del tope o llegar a 12 pasos.
- **Orden de los pasos** (primero el que más falsos positivos evita, según la sensibilidad): `veces_con_texto` +1 → `k_truss` +1 → `veces_sin_texto` +1 → `ampliar_min_celdas` +1 → `lift_min` ×1,5 → `min_pubs_compartidas` +1, y vuelve a empezar.
- **Dónde se avisa:** una línea `ALERTA: tope de seguridad de coordinación activado...` en la salida; el mismo texto en `notas` de `costo.json`; y el detalle paso a paso en la clave nueva `tope_coordinacion` de `costo.json` (umbral, valor antes y después, cuentas marcadas en cada paso, y si quedó o no por debajo del tope). Si no logra bajar del tope, lo dice.
- Parámetros nuevos en `pipeline/parametros.py`: `tope_fraccion` (0,05) y `tope_max_pasos` (12). Son criterio, no salen de práctica.

Pruebas que hice:

| Prueba | Qué pasó |
|---|---|
| Práctica normal | No se activa (115 cuentas contra un tope de 799). Salida idéntica. |
| Forzado con `--param veces_con_texto=1` | Sin tope marcaba 4.429 cuentas. Se activó, hizo un paso (`veces_con_texto` 1 → 2) y quedó en 115 cuentas, **54,56 / 55**. Tardó 63 s (una detección de más). |
| Forzado con `--param tope_fraccion=0.005` (tope de 79 cuentas, más bajo que las 115 reales) | Hizo 7 pasos y terminó marcando 60 cuentas, todas reales, pero perdió dos campañas enteras (46,81 / 55). |
| Prueba automática nueva | Con un detector simulado: se activa, sigue el orden, corta en el máximo de pasos y avisa si no bajó. Ahora son 24 pruebas. |

Límites del tope, para que no se confíen:

- **Cubre el desastre, no el error chico.** Un grupo falso de 5 o 50 cuentas no llega al 5% y pasa sin que el tope se entere. Para eso están los controles de cordura (tamaño de cada grupo) y mirar el reporte.
- **Si se activa, baja el recall.** La tercera prueba lo muestra: endurecer de más pierde campañas reales. Si el viernes aparece la alerta, el resultado de coordinación hay que mirarlo con desconfianza, no darlo por bueno.
- El 5% es un criterio mío. Si el set final tuviera de verdad más del 5% de cuentas coordinadas, el tope las recortaría.
- Cada paso repite la detección (10 a 20 s más por paso).

---

# Jueves 12, 16:05: reporte HTML rehecho

Los ocho cambios pedidos, más el diseño. `reporte/practica.html` quedó regenerado (55 KB, un solo archivo, sin JavaScript ni recursos externos). La entrega no cambia: **54,56 / 55**, archivos idénticos byte a byte, 24 pruebas.

| Pedido | Cómo quedó |
|---|---|
| 1. Caja "Cómo leer esta página" | Arriba, después del resumen. Define narrativa, apoya / rechaza ("apoya: el comentario afirma la idea; rechaza: la niega"), fecha de origen y grupo coordinado. |
| 2. Nombres legibles | Narrativas: sus dos palabras más características ("Foto y campaña", "Líneas y barrios"). Grupos: "Operación A, B, C" (por tamaño) con sus rasgos ("25 cuentas recién creadas, de madrugada"). El código (`n13`, `g03`) queda chico al lado. |
| 3. Título y frases clave | El título se rotula "Frase representativa". Términos clave: una sola palabra, sin palabras vacías, sin variantes de la misma palabra ("mina"/"minera"), con tildes, máximo 4, y solo los que aparecen en al menos el 8% de los comentarios de la narrativa. |
| 4. Una sola línea de tiempo | Reemplaza los mini gráficos. Arriba, un punto por narrativa nueva (amarillo, con nombre y fecha) y un punto con la cantidad de las que ya circulaban; al medio, el volumen total; abajo, un carril por grupo. Una línea punteada baja de cada narrativa nueva hasta los carriles. |
| 5. Apoya / rechaza como estimación | Rotulado "estimación" en el encabezado y en la caja. Cada narrativa lleva una etiqueta de confianza (alta, media, baja) con el indicio que decidió, y una nota al pie de la tabla. |
| 6. Actividad de cobertura | "Comentarios comunes, sobre cualquier tema, que estas cuentas hacen para parecer usuarios normales y pasar desapercibidas." |
| 7. Temas | Sí se pudo derivar: dos narrativas son del mismo tema si se discuten en las mismas publicaciones. El nombre del tema sale de las palabras más distintivas de los titulares. |
| 8. Pie: ruido | "Se aplica una regla observada en los datos de práctica: a los comentarios de ruido nadie les responde... Si un set no cumple esa regla, esta parte pierde precisión." |
| Diseño | Texto base de 17 px, títulos de 26 a 38 px, resumen en bloque oscuro, un color por tema y otro por grupo, tablas con columnas fijas, más aire. |

Además: si la corrida tuvo alertas (set sin respuestas, tope de seguridad), el reporte las muestra arriba en rojo.

## Cosas que conviene saber del reporte

- **Los nombres automáticos son descriptivos, no lindos.** En práctica salen bien la mayoría ("Agua y mina", "Boleto y aumento", "Regalías y litio"), pero algunos son flojos: "Obra y avanza", "Derrame y compartir", y el tema "Tolar y proyecto" (es el del litio; el titular más distintivo nombra el lugar). Como no se puede escribir nada a mano sobre el set final, es lo que hay: para la demo, apoyarse en la frase representativa.
- **La confianza de la postura es un criterio mío, no una probabilidad medida.** Sale del mismo puntaje con que el pipeline decide qué bando apoya. En práctica marca "baja" 4 narrativas y la que está realmente al revés (licitación) es una de esas 4; las de confianza alta y media están todas bien. Es una sola comprobación, sobre 13 narrativas.
- **La frase representativa de una narrativa con la postura al revés es la del bando equivocado.** Pasa con la de licitación: muestra "Nadie quiere venir a dar el servicio acá, no es negocio", que es la respuesta y no la afirmación. Tiene etiqueta de confianza baja.
- **Los temas dependen de que cada publicación sea de un solo tema.** En práctica es así y salen 3 temas limpios, también en la segunda mitad y en una muestra de 20.000. Si en el set final las publicaciones mezclaran temas, todas las narrativas quedarían en un solo tema y el reporte muestra "Todas las narrativas" sin agrupar (es lo que hace hoy con el set sin respuestas).
- **Para guardar la confianza agregué dos columnas a la tabla `res_narrativas` de la base** (`puntaje_postura`, `indicio_postura`). No van a `narrativas.csv`, que sigue con sus cuatro columnas.

## Cómo lo revisé

- El navegador sin interfaz que usé ayer dejó de funcionar (le falta su Chromium), así que tomé las capturas con Edge en modo sin interfaz y las miré por partes: cabecera, línea de tiempo, tablas por tema, tarjetas y pie.
- Arreglé lo que vi mal: etiquetas encimadas en la línea de tiempo, un tema mal nombrado porque un titular se repetía mucho, un término raro ("firmaron"), columnas desalineadas entre temas y "El otro 0% es cobertura".
- Lo generé también sobre la segunda mitad, una muestra de 20.000 y el set sin respuestas: no se rompe y los nombres salen razonables.
- **No lo vi proyectado ni en otro navegador.** Antes de la demo conviene abrirlo en la máquina y el proyector que se van a usar.


---

# Jueves 12, 16:09: primer push al repo del equipo

- Remotos: el de la organización pasó a llamarse `qualydata` (solo lectura) y `origin` ahora es https://github.com/EstebanNahuelok/ESDATA.git.
- Revisión antes de subir: `.gitignore` ya cubría `.venv/`, `salida/` (incluye `salida/verificacion/`, 750 MB), `almacen/`, `datos/final/` y `__pycache__/`. **Faltaba `.env`**: lo agregué, junto con `.env.*` y `*.duckdb`. `entrega/` y `reporte/` no están ignorados.
- Lo que se sube: 39 archivos, 5,8 MB (el más grande es `datos/practica/comentarios.csv.gz`, 4,7 MB, de la organización). En ningún commit hubo archivos de `.venv`, `salida`, `almacen`, `datos/final`, bases DuckDB ni `.env`.
- Claves y secretos: busqué en todos los commits de todas las ramas patrones de claves (OpenAI, Groq, Google, GitHub, AWS, Slack, claves privadas, `clave=valor` largos) y rutas o usuarios de la máquina. Sin coincidencias. No existe ningún `.env` en el disco.
- Push de `main` y de `nucleo-pipeline`, sin forzar. El repo estaba vacío. Desde ahora, push después de cada commit.
- **Pendiente importante:** `main` en el repo solo tiene el material original de la organización. Todo el trabajo está en `nucleo-pipeline`. Quien entre al repo o lo clone ve `main` por defecto, así que antes de la entrega hay que unir la rama a `main`. (Resuelto a las 18:50, ver abajo.)
- `CLAUDE.md` sigue sin versionar y no se subió.


---

# Jueves 12, 18:50: main unificado, nombre del equipo y licencia

- **`main` ya tiene todo el trabajo.** `nucleo-pipeline` se unió a `main` por avance rápido (sin commit de unión, sin forzar): las dos ramas apuntan al mismo commit, en local y en GitHub. Desde ahora cada commit se sube a las dos.
- **Equipo ESDATA** en el título y la cabecera del README. **Licencia MIT** en `LICENSE`, con una sección en el README que aclara que cubre nuestro código y no el material de la organización.
- **Novedad de la organización** (vista al traer su repo, commits del jueves 12 a las 14:51 y 18:35):
  - El **set final ya está publicado** desde el jueves a las 17, en Releases del repo de la organización (etiqueta `set-final`). Son cuatro archivos que van a `datos/final/`.
  - **Cierre: viernes 13 a las 13:00.** Hay que tener pusheados `entrega/` y el código que la generó.
  - Regla nueva: no se puede editar a mano la entrega, y **a los equipos del podio el jurado les vuelve a correr el comando sobre el set final; si el resultado no se parece al entregado, quedan afuera**. Piden semillas fijas; si se usa IA, aceptan diferencias menores.
  - Nuestro `DESAFIO.md` es la versión anterior del enunciado: todavía no trae estos cambios.
