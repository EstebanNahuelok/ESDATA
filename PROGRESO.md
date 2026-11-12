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

## Punto 1 — README del equipo (jueves 12, 12:50) ✅

- El `README.md` de la organización pasó a llamarse `DESAFIO.md` (con `git mv`, sin tocar el contenido). El `README.md` de la raíz ahora es el del equipo.
- Contiene: resultado en práctica, cómo correr con un comando, cómo funciona cada etapa, por qué DuckDB, cómo escalaría a millones por día, qué código existía antes (evaluador y línea base de la organización, y qué dos ideas chicas tomamos de la línea base), y tres tablas que separan reglas generales, supuestos vistos en práctica y parámetros elegidos midiendo en práctica (con su sensibilidad).
- Para revisar por el equipo: el README dice que el código se escribió con ayuda de un asistente de programación con IA. Si prefieren otra redacción, es una línea en la sección "Qué existía antes del evento".
- Pendiente declarado en el propio README: no hay una corrida medida con millones de comentarios; la parte de escala es diseño.

## Punto 2 — Robustez e instalación desde cero (jueves 12, 12:58) ✅

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
