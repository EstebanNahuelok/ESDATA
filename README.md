# Narrativas y coordinación a escala — equipo ESDATA

**Desafío QualyData · Hackathon Argentina Space 2026 · Track Datos y Streaming**
Equipo **ESDATA**: Esteban y Damián. Licencia: [MIT](LICENSE).

Un pipeline que lee cientos de miles de comentarios y responde, en menos de medio minuto y sin gastar
un centavo en IA: **qué narrativas circulan, desde cuándo, quién las apoya o las rechaza, y qué cuentas
las empujan de forma coordinada.**

El enunciado original de la organización está en [`DESAFIO.md`](DESAFIO.md) (era el `README.md` del repo base;
lo renombramos sin tocar el contenido). La bitácora con cada medición está en [`PROGRESO.md`](PROGRESO.md).

> Todos los datos son sintéticos y los entrega la organización. No hay datos personales ni claves en el repo.

## Resultado en el set de práctica

Medido con el evaluador oficial (`evaluacion/puntuar.py`) sobre 200.000 comentarios:

| Parte | Línea base de la organización | Nuestro pipeline |
|---|---|---|
| Agrupamiento de narrativas (B-cubed F1) | 0,35 | 1,00 |
| Detección de ruido (F1) | 0,67 | 1,00 |
| Postura (macro-F1) | 0,49 | 0,93 |
| Origen de narrativas emergentes | 0,33 | 1,00 |
| Cuentas coordinadas (F1) | precisión 0,07 | 1,00 (115 de 115, sin falsos positivos) |
| Grupos por operación (B-cubed F1) | — | 1,00 |
| **Total automático** | **16,8 / 55** | **54,56 / 55** |

Costo: **entre 27 y 48 segundos** de punta a punta (según qué más esté corriendo en la notebook), **650 MB** de
memoria pico, base de **35 MB**, **0 tokens de IA, 0 USD**, en una notebook con 8 GB de RAM y sin GPU.
Ese número es del set de práctica; el set final trae otros temas y otras campañas, y abajo decimos con
honestidad qué puede fallar.

## Resultado en el set final

La carpeta [`entrega/`](entrega/) es la salida del comando de abajo sobre el set final (150.000 comentarios, 12.002
cuentas, 372 publicaciones), sin tocar nada a mano. El set final no trae respuesta correcta, así que acá no hay
puntaje: solo lo que el pipeline encontró.

| | Set final |
|---|---|
| Narrativas | 12, sobre 3 temas; 3 aparecen durante el período |
| Ruido | 20,7% de los comentarios |
| Cuentas coordinadas | 102 de 12.002 (0,85%), en 3 grupos de 50, 30 y 22 cuentas |
| Tiempo y memoria | 22,2 s, 567 MB de pico |
| Almacenamiento | base DuckDB de 25,8 MB; entrada 3,4 MB, entrega 2,9 MB |
| IA | 0 tokens, 0 USD |
| Validación y alertas | formato OK; ninguna alerta; el tope de seguridad no se activó |

El reporte visual de esa corrida está en [`reporte/entrega.html`](reporte/entrega.html).

**Para volver a correrlo y comparar.** Tres corridas (dos con el entorno de `requirements-lock.txt` y una con
versiones más viejas de las librerías) dieron los tres CSV idénticos byte a byte. `costo.json` cambia entre
corridas porque trae el tiempo y la memoria medidos. SHA-256 de lo entregado:

```
904fa8f7eed75d7a9cf0fde09429c09e4bd1e55f011dcf6529572bd526ab9b54  entrega/comentarios.csv
f7edca5224afc5a5f2c8a9fcd39657f08af561b35d84ad7be5071c7dd6d96557  entrega/cuentas.csv
4db7053782dbded21839793ea515bc98de03cee242ad6648edf8dffb21e7f489  entrega/narrativas.csv
```

## Cómo correrlo

Requisitos: **Python 3.13** (probado con 3.13.3 en Windows 10). No hace falta GPU, ni internet después de instalar.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements-lock.txt
```

`requirements-lock.txt` trae las versiones exactas con las que se generó la entrega. Con otra versión de Python,
`pip install -r requirements.txt` instala las mismas librerías por rangos de versiones.

El set final se baja a `datos/final/` (no se versiona), desde la raíz del repo:

```bash
mkdir -p datos/final && cd datos/final
for f in fuentes.csv publicaciones.csv.gz comentarios.csv.gz cuentas.csv.gz; do curl -LO https://github.com/qualydata-org/desafio-qualydata/releases/download/set-final/$f; done
cd ../..
```

**Un solo comando, de punta a punta**, sobre el set final:

```bash
python -m pipeline.run --datos datos/final --entrega entrega
```

No hay nada al azar sin fijar: la semilla es 0 por defecto (`--semilla`) y corridas en procesos distintos dan
los mismos archivos.

Sobre el set de práctica, y para medirlo:

```bash
python -m pipeline.run --datos datos/practica --entrega salida/practica
```

```bash
python evaluacion/puntuar.py --verdad datos/practica/verdad --entrega salida/practica
```

`--datos` es la carpeta con `comentarios`, `cuentas`, `publicaciones` y `fuentes` (`.csv` o `.csv.gz`).
Solo `comentarios` es obligatorio. En `--entrega` quedan `comentarios.csv`, `narrativas.csv`, `cuentas.csv`
y `costo.json`, con el formato del enunciado.

Al terminar, el pipeline **valida solo la entrega** (los 4 archivos, encabezados exactos, un id por comentario y
por cuenta, posturas válidas, fechas ISO con zona horaria, claves de `costo.json`) y la cruza contra los datos
de entrada. Si algo no cumple, termina con error. El mismo control se puede correr suelto, por ejemplo antes del
commit final; solo usa la librería estándar:

```bash
python -m pipeline.validar --entrega entrega --datos datos/final
```

### Reporte visual

Cada corrida genera además **un archivo HTML estático** (`reporte/<nombre de la carpeta de entrega>.html`; para el
set final, `reporte/entrega.html`). Se abre con doble clic, no necesita internet ni servidor, y muestra:
un resumen en una frase, una caja "cómo leer esta página", una línea de tiempo con el origen de cada narrativa
nueva y la actividad de cada grupo coordinado, las narrativas agrupadas por tema (con su frase representativa,
apoya / rechaza como estimación con su nivel de confianza, y quién la empuja) y una tarjeta por grupo.
Los nombres de narrativas, temas y grupos se derivan de los datos; no hay nada escrito a mano.
El del set de práctica está en [`reporte/practica.html`](reporte/practica.html).

Se arma con consultas SQL sobre la base DuckDB, así que se puede regenerar sin volver a procesar nada:

```bash
python -m pipeline.reporte --base almacen/final.duckdb --salida reporte/entrega.html --costo entrega/costo.json
```

Es un extra aislado: se genera después de escribir y validar la entrega, y si fallara, la entrega no se ve
afectada. `--sin-reporte` lo apaga y `--reporte ruta.html` cambia dónde se escribe.

`costo.json` se arma con lo medido en cada corrida, nada a mano: comentarios procesados, segundos totales,
memoria pico del proceso, equipo detectado (tipo, procesador, núcleos, RAM, GPU), tamaño de la entrada, de la
base y de la entrega, tiempo y memoria de cada etapa, versiones de las librerías y avisos de la corrida.
Trae las 8 claves del enunciado y algunas más.

Opciones: `--base ruta.duckdb` (dónde guardar la base; por defecto `almacen/<nombre de la carpeta de datos>.duckdb`)
`--semilla N` (por defecto 0) y `--hardware "texto"` (para escribir a mano la descripción del equipo en
`costo.json` en vez de la detectada). Con la misma semilla, dos corridas dan archivos idénticos byte a byte.
`--param nombre=valor` cambia un parámetro de `pipeline/parametros.py` solo en esa corrida y lo deja anotado en
`costo.json`.

Después de validar, el pipeline imprime unos **controles de cordura** (cuántas narrativas, qué porcentaje de ruido,
cuántas cuentas marcadas y de qué tamaño es cada grupo) y avisa si algo es absurdo: una sola narrativa gigante,
cientos de narrativas, casi todo ruido, miles de cuentas marcadas o un set sin respuestas.

La coordinación tiene además un **tope de seguridad**: si se marca más del 5% de las cuentas, los umbrales se
endurecen solos, de a un paso, hasta bajar del tope. Lo que hizo queda en la salida y en `costo.json`
(`tope_coordinacion` y `notas`).

Pruebas automáticas (26 pruebas, unos 45 segundos):

```bash
python -m unittest discover -s pruebas
```

Lo probamos desde cero (clonar el repo de GitHub, entorno virtual nuevo, instalar, correr) con las versiones de
`requirements-lock.txt` y también con versiones de 2025 (pandas 2.2, numpy 2.2, scikit-learn 1.6, networkx 3.4):
los archivos de salida son idénticos byte a byte, en el set de práctica y en el set final.

### Datos sucios o incompletos

El pipeline no se corta con: archivos opcionales faltantes (`cuentas`, `publicaciones`, `fuentes`), columnas
faltantes, ids duplicados o vacíos, fechas imposibles, números inválidos, textos vacíos, respuestas a comentarios
que no existen, hilos circulares, comentarios sin cuenta, archivos con BOM, separador `;` o codificación
Windows-1252, ni con un set vacío o de un solo comentario. Cada caso tiene su prueba en `pruebas/`, y lo que se
tuvo que descartar o suponer queda anotado en el campo `notas` de `costo.json`. Solo `comentarios.csv(.gz)` es
obligatorio: si falta, el pipeline termina con un mensaje claro.

## Cómo funciona

Paquete `pipeline/`, un módulo por etapa:

| Etapa | Módulo | Qué hace |
|---|---|---|
| Ingesta | `ingesta.py` | Lee los CSV como texto con DuckDB, limpia con SQL y deja tablas tipadas. Separa los **textos únicos**: de 200.000 comentarios solo hay 47.000 textos distintos después de normalizar, y solo esos se procesan. |
| Texto | `texto.py`, `microgrupos.py` | Normaliza (tildes, emojis, abreviaturas, errores de tipeo) y junta las frases que son la misma con variaciones chicas (TF-IDF + agrupamiento por lotes, sin fijar la cantidad de grupos). Quedan unos 370 "microgrupos". |
| Narrativas y ruido | `narrativas.py` | Usa la conversación, no solo las palabras. Una respuesta que contradice a un comentario habla de la misma narrativa: con esos enlaces arma un grafo de microgrupos y sus comunidades son las narrativas (el método decide cuántas hay). Así quedan juntos quienes apoyan y quienes rechazan, aunque usen palabras distintas. Las frases a las que nadie responde nunca son ruido. Un "tal cual" hereda la narrativa del comentario al que responde. |
| Postura | `postura.py` | Dentro de cada narrativa separa dos bandos (los que se contradicen entre sí) y decide cuál apoya con indicios generales: marcas de desmentida, a quién empuja una campaña, volumen. |
| Origen | `origen.py` | Primer comentario de la narrativa que tiene compañía (ignora apariciones aisladas). |
| Coordinación | `coordinacion.py` | Busca cuentas que coinciden **una y otra vez** en la misma publicación y ventana de 30 minutos, y lo compara con lo esperable por azar según cuánto comenta cada una. Coincidir en una publicación viral casi no suma; coincidir donde hay poca gente, sí. Se queda con las mallas densas de cuentas (no con pares sueltos) y cada malla es una operación. Después suma a cada operación las cuentas con poca actividad que aparecen en celdas dominadas por ella, mirando también quién repite la misma frase. |
| Consignas | `consignas.py` | Las frases que dice casi solo una operación (sus consignas) casi no reciben respuestas de gente de afuera, así que la conversación no alcanza para ubicarlas. Se ubican por las respuestas de cuentas que no son de la operación o, si no hay, por parecido de palabras; y todas las consignas de una operación van del mismo bando. |
| Salida | `salida.py`, `costo.py`, `validar.py`, `reporte.py`, `run.py` | Escribe la entrega, mide tiempo y memoria de cada etapa, arma `costo.json`, valida el formato y genera el reporte visual. Si coordinación o postura fallan, la entrega sale igual y el aviso queda en `costo.json`. |

No se manda ningún comentario a un modelo de IA. Todo es estadística, álgebra dispersa y grafos en CPU.

## Dónde se guardan los datos y por qué DuckDB

Los CSV de entrada se cargan una sola vez a **un archivo DuckDB local** (`almacen/<set>.duckdb`, ignorado por git).
Ahí quedan las tablas limpias (`comentarios`, `textos`, `cuentas`, `publicaciones`, `fuentes`) y también los
resultados (`res_comentarios`, `res_narrativas`, `res_cuentas`), listos para consultar con SQL o para un tablero.

Por qué DuckDB y no otra cosa:

- **Es una base analítica por columnas.** Nuestras consultas son agregaciones y cruces sobre pocas columnas de muchas filas (contar por publicación y ventana, deduplicar textos, cruzar respuestas con sus padres). Para eso un motor por columnas es mucho más rápido que uno por filas como PostgreSQL o SQLite.
- **No hay servidor que instalar ni administrar.** Es una librería (`pip install duckdb`) y un archivo. El jurado puede volver a correr todo con un comando, sin Docker ni credenciales.
- **Lee CSV comprimido directo y tolera datos sucios.** La limpieza es SQL declarativo (`try_cast`, deduplicación por id), no bucles en Python.
- **Trabaja con más datos que memoria.** Tiene límite de memoria configurable (usamos 2 GB) y vuelca a disco si hace falta. En una notebook de 8 GB eso importa.
- **Es chica y barata.** 200.000 comentarios ocupan 35 MB. No hay costo de nube.
- **El salto a escala es directo.** DuckDB lee y escribe Parquet particionado; el mismo SQL sirve sobre un lago de archivos o sobre MotherDuck/ClickHouse si algún día hace falta un servidor.

Lo que descartamos: PostgreSQL (servidor, por filas, más lento en agregaciones), Elasticsearch (pensado para
búsqueda, pesado para una notebook), solo dataframes en memoria (no escala y no deja nada consultable).

## Escala

### Medido con datos reales del set de práctica

El comando normal, de punta a punta (con validación y reporte), sobre muestras de publicaciones completas con
todos sus hilos de respuestas; la última fila es el set entero. Tres corridas por tamaño.

| Comentarios | Publicaciones | Cuentas | Tiempo (mediana; rango) | Comentarios por segundo | Memoria pico | Etapa más lenta | Base DuckDB | Puntaje /55 |
|---|---|---|---|---|---|---|---|---|
| 10.657 | 38 | 5.634 | 3,7 s (3,3 a 4,0) | 2.880 | 204 MB | ingesta (1,5 s) | 3,0 MB | 27,24 |
| 50.190 | 160 | 12.581 | 9,5 s (9,5 a 9,8) | 5.283 | 302 MB | ingesta (2,9 s) | 12,8 MB | 33,47 |
| 100.287 | 274 | 15.013 | 17,9 s (17,9 a 18,4) | 5.602 | 431 MB | coordinación (5,4 s) | 20,8 MB | 53,84 |
| 200.000 | 506 | 15.991 | 31,1 s (30,5 a 31,2) | 6.430 | 634 MB | coordinación (10,9 s) | 35,3 MB | 54,56 |

Qué se ve:

- **El tiempo crece en línea con los datos, no más rápido:** de 50.000 a 200.000 hay 4 veces más comentarios y 3,3 veces más tiempo.
- **La memoria también:** unos 190 MB fijos más unos 2,3 MB por cada mil comentarios.
- **La base ocupa unos 0,18 MB por cada mil comentarios.**
- **El puntaje baja en las muestras chicas por la coordinación, no por el texto.** Con 10.000 y 50.000 comentarios las narrativas se agrupan igual de bien (0,97 y 1,00), pero las cuentas coordinadas casi no llegan a repetir coincidencias y el pipeline prefiere no marcarlas (0 y 10 marcadas, sin falsos positivos). Detectar coordinación necesita volumen.

Condiciones de la medición (jueves 12/11, 19:00): notebook i7-10510U con 8 GB de RAM, con el editor, un navegador
y un chat abiertos; entre 0,6 y 1,6 GB de RAM libre al empezar cada corrida. Se repite con
`python verificacion/escala.py`.

## Cómo escalaría a millones de comentarios por día

Hoy: 200.000 comentarios en 27 a 48 s en una notebook (entre 4.000 y 7.000 comentarios por segundo, de punta a punta).
Lo que cambia al crecer, etapa por etapa:

1. **Ingesta por lotes diarios a Parquet particionado por fecha.** Cada día se agrega una partición; DuckDB consulta solo las particiones que necesita. Nada se reprocesa.
2. **El texto no crece como los comentarios.** La gente repite frases: se guarda una tabla de textos únicos y solo se normalizan y vectorizan los textos nuevos del día. En práctica, después de normalizar, el 76% de los comentarios repite un texto ya visto.
3. **Microgrupos incrementales.** El agrupamiento por "líder" ya trabaja en una pasada y por lotes: un texto nuevo se compara contra los centroides existentes (unos cientos) y se suma a uno o abre un grupo nuevo. No hay que reagrupar la historia.
4. **Narrativas sobre el grafo de microgrupos, no sobre comentarios.** El grafo tiene cientos de nodos aunque haya millones de comentarios; recalcular comunidades tarda milisegundos. Los enlaces (respuestas) se acumulan como contadores.
5. **Coordinación por ventanas.** Es la etapa más pesada (11 de 27 s en la mejor corrida) porque cruza pares de cuentas. Escala bien porque: solo se cruzan cuentas que coinciden en la misma publicación y ventana; el producto ya se hace por bloques con memoria acotada; las celdas enormes (momentos virales) casi no aportan evidencia y se pueden muestrear; y se puede correr por día guardando los contadores de pares fuertes en una tabla, de modo que la repetición se acumula entre días.
6. **Más de una máquina.** Los pasos 1, 2 y 5 se paralelizan por día o por publicación. Si el volumen pide un servidor, el almacenamiento pasa a ClickHouse o a DuckDB sobre almacenamiento de objetos sin cambiar la lógica.

Lo que **no** medimos todavía: una corrida real con millones de comentarios. Los puntos de arriba son el diseño; el único número medido es el del set de práctica.

## Qué existía antes del evento

Código de la organización, que venía en el repo base y **no modificamos**:

- `evaluacion/puntuar.py` — el evaluador oficial. Lo usamos para medir cada cambio.
- `ejemplos/linea_base.py` — la línea base. No la usamos como punto de partida del pipeline. Tomamos de ahí dos ideas chicas, adaptadas: la normalización de texto (minúsculas, tildes, letras repetidas, abreviaturas de chat) y la idea de una lista de marcas de rechazo ("mentira", "falso", "nada que ver"...).
- `DESAFIO.md` (ex `README.md`), `datos/practica/` y `requirements.txt` original.

Librerías públicas que usamos (todas existían antes): `duckdb`, `numpy`, `scipy`, `scikit-learn` (solo TF-IDF),
`networkx` (Louvain y k-truss), `pandas` (pasar tablas a DuckDB), `psutil` (medir memoria).

Todo lo que está en `pipeline/` y `pruebas/` lo escribimos durante el hackathon (11 al 13 de noviembre de 2026),
con ayuda de un asistente de programación con IA. El pipeline en sí no usa IA al correr.

## Qué ajustamos mirando el set de práctica y qué es regla general

Todos los parámetros y umbrales están en un solo archivo, [`pipeline/parametros.py`](pipeline/parametros.py), cada uno
con qué hace y de dónde salió su valor (`python -m pipeline.parametros` imprime la tabla completa: 50 parámetros).
Abajo va el resumen.

El set final trae otros temas y otras campañas, así que separamos lo que es una regla del problema de lo que
es un número que elegimos midiendo en práctica. **No hay ids, temas, nombres de narrativas ni fechas del set
de práctica en el código.**

### Reglas generales (no dependen de los datos)

| Regla | De dónde sale |
|---|---|
| Una respuesta que contradice pertenece a la misma narrativa, con la postura opuesta. Una respuesta que solo acompaña hereda narrativa y postura. | Enunciado del desafío. |
| Normalización de texto: minúsculas, tildes, emojis, enlaces, menciones, letras repetidas, abreviaturas de chat (`q`, `xq`, `x`, `pa`...), palabras vacías del castellano. | Conocimiento del idioma. |
| Corrección de tipeo: una palabra rara se cambia por otra al menos 10 veces más frecuente que está a una letra invertida o duplicada. | Regla general; el vocabulario sale de cada set. |
| Coincidencia pesada por 1/tamaño de la celda y comparada con lo esperable por azar (`n_a · n_b / N`). | Estadística; no depende del tamaño ni del tema del set. |
| La antigüedad de las cuentas se usa solo en relación al propio grupo detectado (si el grupo fue creado en una franja de fechas rara en el set). No hay umbral de días. | Decisión de diseño para no sobreajustar. |
| Prueba de ruido: "cero respuestas en tantas apariciones es muy improbable" (Poisson con la tasa de respuestas medida en el propio set, α = 0,01). | Estadística; la tasa se mide en cada set. |
| Marcas de desmentida: "mentira", "falso", "verso", "nada que ver", "desmintió", "sin pruebas"... | Idioma. La lista parte de la línea base y la completamos mirando práctica (ver abajo). |
| Consignas: una frase es consigna de una operación si más de la mitad de sus comentarios son de cuentas de esa operación (y la dicen 3 o más). Las respuestas entre cuentas de la misma operación no cuentan como discusión, y una operación no discute consigo misma: sus consignas van todas del mismo bando. | Regla general. La agregamos después de ver el set final (las consignas de una campaña quedaban repartidas entre dos narrativas y el ruido), sin elegir ningún número con ese set: usa "mayoría" y parámetros que ya existían. En práctica no cambia el resultado. |
| Segunda pasada de coordinación también por "misma frase" (misma publicación, misma ventana y la misma frase), con los mismos umbrales que la pasada por narrativa y bando. | Regla general, agregada por el mismo motivo. En práctica y en ocho recortes no cambia nada; en una muestra de 20.000 comentarios encuentra 4 cuentas más, todas reales. |

### Supuestos que vimos en práctica y que el set final podría no cumplir

| Supuesto | Qué pasa si no se cumple |
|---|---|
| Al ruido nadie le responde y el ruido nunca es una respuesta. | Baja la detección de ruido: frases de ruido con respuestas pasarían a ser narrativas chicas. |
| Las respuestas con texto propio contradicen (las que acuerdan son frases cortas tipo "tal cual"). | Se mezclarían los bandos de postura; el agrupamiento no cambia. |
| Hay suficientes respuestas (en práctica, 14% de los comentarios). | Con la mitad de los hilos rotos el agrupamiento da 0,97. Sin ninguna respuesta cae a 0,38 (plan B por palabras). |
| Las campañas repiten: las mismas cuentas coinciden varias veces. | Una campaña que actúa una sola vez no se ve. Con 5 días de datos detectamos 74% de las cuentas; con 7 días, 93-100%. |

### Parámetros elegidos midiendo en práctica

| Parámetro | Valor | Cómo se eligió | Sensibilidad |
|---|---|---|---|
| Parecido mínimo para ser la misma frase (`umbral_micro`) | 0,5 | Pureza de los microgrupos contra la verdad. | Baja: con 0,5 la pureza es 99,99%. |
| Tamaño mínimo de un microgrupo y parecido para absorber variantes raras | 30 comentarios / 0,25 | Pureza de las absorciones (100% por encima de 0,25). | Baja. |
| Fracción de respuestas para tratar una frase como "acuerdo" | 0,9 | Mirando las frases tipo "tal cual". | Baja: las frases son casi todo respuesta o casi nada. |
| Ventana de coincidencia | 30 minutos | Comparamos 15 y 30 minutos. | Baja: entre 15 y 45 minutos cambia menos de 0,15 puntos. |
| Lift mínimo de un par | 40 | Hay una meseta entre 30 y 60. | Baja dentro de la meseta; con 20 aparecen 7 falsos positivos. |
| Repeticiones mínimas de un par | 2 (misma narrativa y bando) / 4 (solo tiempo) | Precisión contra la verdad. En "solo tiempo" alcanzaba con 3 y dejamos un paso de margen. | **Alta hacia abajo** en la primera: con 1 se marcan miles de cuentas genuinas (no tiene margen; lo cubre el tope de seguridad). |
| Publicaciones distintas que comparte un par | 2 | Lo agregamos al encontrar un grupo falso de 5 cuentas genuinas que coincidían dos veces dentro de una misma publicación viral. | Baja: no cambió ningún otro resultado en nueve recortes. |
| Densidad de la malla (k-truss) y tamaño mínimo de grupo | 5 / 5 cuentas | Precisión contra la verdad. En k-truss alcanzaba con 4 y dejamos un paso de margen. | Con 3 aparecen 22 falsos positivos; con 4, 5 o 6 el resultado es el mismo. El tamaño mínimo no influye. |
| Tope de seguridad de coordinación | 5% de las cuentas | Criterio, sin ajustar: una operación coordinada es una minoría chica. | Si se marca más que eso, los umbrales se endurecen solos de a un paso y queda avisado en la salida y en `costo.json`. |
| Ampliación de grupos: celdas "dominadas" | 3+ miembros y 1/3 de la celda; franja de creación rara si cubre < 2% de las cuentas | Probado en recortes del set. | Baja. |
| Pesos de los indicios de postura | 20 / 20 / 0,5 / 1 / 1 | A mano, mirando práctica. Es la parte menos sólida. | Nula: moverlos ±50% no cambia nada. Las narrativas que quedan al revés no se arreglan con pesos. |
| Lista de marcas de desmentida | 21 expresiones | Línea base + las que vimos en práctica. | Media: otras campañas pueden desmentir con otras palabras. |
| Origen: compañía mínima | 5 comentarios en 12 horas | Valor razonable; no se ajustó. | Baja. |
| Plan B sin respuestas: parecido entre microgrupos | 0,1 | El mejor de los que probamos (y aun así flojo). | — |

Para no engañarnos con un puntaje casi perfecto hicimos tres cosas, todas reproducibles con los scripts de
`verificacion/` y con los resultados completos en [`PROGRESO.md`](PROGRESO.md):

- **Sensibilidad:** movimos cada parámetro -50% y +50%. De 29, 23 lo mueven menos de 0,25 puntos. Los frágiles eran cuatro
  umbrales enteros de coordinación, que estaban en el valor mínimo que da precisión perfecta en práctica. A dos les
  dimos un paso de margen sin cambiar el resultado; los otros dos no se pueden endurecer sin perder cuentas reales,
  y para ese caso está el tope de seguridad.
- **Generalización:** corrimos el pipeline sobre recortes que no usamos para elegir nada (cada mitad de los días,
  sin respuestas, con la mitad de las respuestas borradas, muestras de 20.000 comentarios, datos sucios).
- **Ejemplos al azar** de comentarios y de cuentas marcadas, con el porqué de cada cuenta.

## Limitaciones conocidas

- **Postura:** los dos bandos de cada narrativa salen bien separados, pero decidir cuál "apoya" falla cuando no hay marcas de desmentida ni campaña. En práctica queda al revés 1 de 13 narrativas. Es un problema de significado; una sola llamada a un modelo de lenguaje con las frases representativas lo resolvería, y decidimos no usar IA por ahora.
- **Dependencia de los hilos de respuestas:** ver la tabla de supuestos.
- **Campañas de otro estilo** (coordinadas entre publicaciones distintas, o con horas de diferencia) podrían no verse con la ventana de 30 minutos.
- **Coordinación sin margen en dos umbrales:** las repeticiones mínimas con mismo mensaje (2) y las celdas mínimas de la segunda pasada (2) están en el único valor que funciona en práctica. Si en el set final las cuentas genuinas coinciden más, pueden aparecer falsos positivos. El tope de seguridad cubre el caso grave (más del 5% de las cuentas marcadas), no un grupo falso chico. Ya corregimos uno que encontramos: 5 cuentas genuinas que coincidían dos veces dentro de una misma publicación viral; ahora un par tiene que compartir al menos dos publicaciones.
- **La fecha de origen se degrada con pocos datos o con el agrupamiento sucio:** es el primer comentario con compañía, así que un comentario mal asignado puede correrla varios días.
- **No medimos una corrida con millones de comentarios.**

## Estructura del repo

```
pipeline/        nuestro código (un módulo por etapa; entrada: python -m pipeline.run)
pruebas/         pruebas mínimas (formato, datos sucios, reproducibilidad)
verificacion/    sensibilidad, generalización, escala y ejemplos (usan la verdad de práctica; no son parte del pipeline)
entrega/         resultado del set final (los 4 archivos que se puntúan)
reporte/         reporte visual en HTML de cada corrida
evaluacion/      evaluador oficial (de la organización)
ejemplos/        línea base (de la organización)
datos/practica/  set de práctica (de la organización); datos/final/ no se sube
almacen/         bases DuckDB locales (no se sube)
salida/          corridas de práctica (no se sube)
DESAFIO.md       enunciado original
PROGRESO.md      bitácora de mediciones
LICENSE          licencia MIT de nuestro código
```

## Licencia

El código del equipo ESDATA (`pipeline/`, `pruebas/`, `verificacion/`) y la documentación que escribimos se
publican con licencia [MIT](LICENSE). El material de la organización (`DESAFIO.md`, `evaluacion/`, `ejemplos/`,
`datos/practica/`) es de QualyData y no queda alcanzado por esa licencia.
