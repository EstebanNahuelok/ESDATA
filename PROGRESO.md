# PROGRESO — Desafío QualyData

Bitácora de puntajes sobre el set de práctica. Cada fila es una corrida de
`python -m pipeline.run --datos datos/practica --entrega salida/practica` seguida de
`python evaluacion/puntuar.py --verdad datos/practica/verdad --entrega salida/practica`.

## Historial de puntajes

| Fecha y hora | Cambio | Agrup. F1 | Ruido F1 | Postura | Origen | Narrativas /30 | Coord. F1 (P / R) | Grupos | Coord. /25 | Total /55 | Tiempo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (referencia) | Línea base de la organización (`ejemplos/linea_base.py`), dato de CLAUDE.md | 0,35 | 0,67 | 0,49 | 0,33 | — | P 0,07 | — | — | 16,8 | — |
| 2026-11-11 20:40 | Ingesta a DuckDB + narrativas por microgrupos y grafo de respuestas + ruido + herencia + postura por bandos + origen. Coordinación todavía vacía. | 1,000 | 1,000 | 0,927 | 1,000 | 29,56 | 0,000 | 0,051 | 0,38 | 29,94 | 16 s |
