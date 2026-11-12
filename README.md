# Narrativas y coordinación a escala — solución del equipo

**Desafío QualyData · Hackathon Argentina Space 2026 · Track Datos y Streaming**
Equipo: Esteban y Damián.

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

Costo: **27 segundos**, **640 MB** de memoria pico, base de **35 MB**, **0 tokens de IA, 0 USD**, en una
notebook con 8 GB de RAM y sin GPU. Ese número es del set de práctica; el set final trae otros temas y
otras campañas, y abajo decimos con honestidad qué puede fallar.

## Cómo correrlo

Requisitos: Python 3.10 o superior (lo probamos con 3.13 en Windows). No hace falta GPU, ni internet después de instalar.

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

**Un solo comando, de punta a punta**, sobre el set final:

```bash
python -m pipeline.run --datos datos/final --entrega entrega
```

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

Opciones: `--base ruta.duckdb` (dónde guardar la base; por defecto `almacen/<nombre de la carpeta de datos>.duckdb`)
y `--semilla N` (por defecto 0). Con la misma semilla, dos corridas dan archivos idénticos byte a byte.

Pruebas automáticas (20 segundos):

```bash
python -m unittest discover -s pruebas
```

## Cómo funciona

Paquete `pipeline/`, un módulo por etapa:

| Etapa | Módulo | Qué hace |
|---|---|---|
| Ingesta | `ingesta.py` | Lee los CSV como texto con DuckDB, limpia con SQL y deja tablas tipadas. Separa los **textos únicos**: de 200.000 comentarios solo hay 47.000 textos distintos después de normalizar, y solo esos se procesan. |
| Texto | `texto.py`, `microgrupos.py` | Normaliza (tildes, emojis, abreviaturas, errores de tipeo) y junta las frases que son la misma con variaciones chicas (TF-IDF + agrupamiento por lotes, sin fijar la cantidad de grupos). Quedan unos 370 "microgrupos". |
| Narrativas y ruido | `narrativas.py` | Usa la conversación, no solo las palabras. Una respuesta que contradice a un comentario habla de la misma narrativa: con esos enlaces arma un grafo de microgrupos y sus comunidades son las narrativas (el método decide cuántas hay). Así quedan juntos quienes apoyan y quienes rechazan, aunque usen palabras distintas. Las frases a las que nadie responde nunca son ruido. Un "tal cual" hereda la narrativa del comentario al que responde. |
| Postura | `postura.py` | Dentro de cada narrativa separa dos bandos (los que se contradicen entre sí) y decide cuál apoya con indicios generales: marcas de desmentida, a quién empuja una campaña, volumen. |
| Origen | `origen.py` | Primer comentario de la narrativa que tiene compañía (ignora apariciones aisladas). |
| Coordinación | `coordinacion.py` | Busca cuentas que coinciden **una y otra vez** en la misma publicación y ventana de 30 minutos, y lo compara con lo esperable por azar según cuánto comenta cada una. Coincidir en una publicación viral casi no suma; coincidir donde hay poca gente, sí. Se queda con las mallas densas de cuentas (no con pares sueltos) y cada malla es una operación. |
| Salida | `salida.py`, `run.py` | Escribe la entrega, mide tiempo y memoria de cada etapa y arma `costo.json`. Si coordinación o postura fallan, la entrega sale igual y el aviso queda en `costo.json`. |

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

## Cómo escalaría a millones de comentarios por día

Hoy: 200.000 comentarios en 27 s en una notebook (unos 7.000 comentarios por segundo, de punta a punta).
Lo que cambia al crecer, etapa por etapa:

1. **Ingesta por lotes diarios a Parquet particionado por fecha.** Cada día se agrega una partición; DuckDB consulta solo las particiones que necesita. Nada se reprocesa.
2. **El texto no crece como los comentarios.** La gente repite frases: se guarda una tabla de textos únicos y solo se normalizan y vectorizan los textos nuevos del día. En práctica, después de normalizar, el 76% de los comentarios repite un texto ya visto.
3. **Microgrupos incrementales.** El agrupamiento por "líder" ya trabaja en una pasada y por lotes: un texto nuevo se compara contra los centroides existentes (unos cientos) y se suma a uno o abre un grupo nuevo. No hay que reagrupar la historia.
4. **Narrativas sobre el grafo de microgrupos, no sobre comentarios.** El grafo tiene cientos de nodos aunque haya millones de comentarios; recalcular comunidades tarda milisegundos. Los enlaces (respuestas) se acumulan como contadores.
5. **Coordinación por ventanas.** Es la etapa más pesada (11 de los 27 s) porque cruza pares de cuentas. Escala bien porque: solo se cruzan cuentas que coinciden en la misma publicación y ventana; el producto ya se hace por bloques con memoria acotada; las celdas enormes (momentos virales) casi no aportan evidencia y se pueden muestrear; y se puede correr por día guardando los contadores de pares fuertes en una tabla, de modo que la repetición se acumula entre días.
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
| Ventana de coincidencia | 30 minutos | Comparamos 15 y 30 minutos. | Media: depende del ritmo de las campañas. |
| Lift mínimo de un par | 40 | Hay una meseta: entre 20 y 100 el resultado no cambia. | Baja dentro de la meseta. |
| Repeticiones mínimas de un par | 2 (misma narrativa y bando) / 3 (solo tiempo) | Precisión contra la verdad. | Media. |
| Densidad de la malla (k-truss) y tamaño mínimo de grupo | 4 / 5 cuentas | Precisión contra la verdad. | Media: con 3 aparecen falsos positivos. |
| Ampliación de grupos: celdas "dominadas" | 3+ miembros y 1/3 de la celda; franja de creación rara si cubre < 2% de las cuentas | Probado en recortes del set. | Baja. |
| Pesos de los indicios de postura | 20 / 20 / 0,5 / 1 / 1 | A mano, mirando práctica. Es la parte menos sólida. | Alta: es donde más esperamos fallar. |
| Lista de marcas de desmentida | 21 expresiones | Línea base + las que vimos en práctica. | Media: otras campañas pueden desmentir con otras palabras. |
| Origen: compañía mínima | 5 comentarios en 12 horas | Valor razonable; no se ajustó. | Baja. |
| Plan B sin respuestas: parecido entre microgrupos | 0,1 | El mejor de los que probamos (y aun así flojo). | — |

Para no engañarnos con un puntaje casi perfecto, medimos el pipeline sobre recortes del set que no usamos para
elegir nada (por días, por tema, con la mitad de las cuentas, con datos sucios, sin respuestas). La tabla
completa está en [`PROGRESO.md`](PROGRESO.md).

## Limitaciones conocidas

- **Postura:** los dos bandos de cada narrativa salen bien separados, pero decidir cuál "apoya" falla cuando no hay marcas de desmentida ni campaña. En práctica queda al revés 1 de 13 narrativas. Es un problema de significado; una sola llamada a un modelo de lenguaje con las frases representativas lo resolvería, y decidimos no usar IA por ahora.
- **Dependencia de los hilos de respuestas:** ver la tabla de supuestos.
- **Campañas de otro estilo** (coordinadas entre publicaciones distintas, o con horas de diferencia) podrían no verse con la ventana de 30 minutos.
- **No medimos una corrida con millones de comentarios.**

## Estructura del repo

```
pipeline/        nuestro código (un módulo por etapa; entrada: python -m pipeline.run)
pruebas/         pruebas mínimas (formato, datos sucios, reproducibilidad)
entrega/         resultado del set final (se genera el viernes 13)
evaluacion/      evaluador oficial (de la organización)
ejemplos/        línea base (de la organización)
datos/practica/  set de práctica (de la organización); datos/final/ no se sube
almacen/         bases DuckDB locales (no se sube)
salida/          corridas de práctica (no se sube)
DESAFIO.md       enunciado original
PROGRESO.md      bitácora de mediciones
```
