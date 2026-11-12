# PITCH — borrador

Borrador para un pitch de 3 minutos más demo. Los números son del **set de práctica**; lo marcado con
**[VIERNES]** se completa con la corrida del set final. Está escrito para decirlo en voz alta: frases cortas.

## La frase

> Leemos 200.000 comentarios en medio minuto, en una notebook, sin gastar un centavo en IA, y decimos
> **qué se está diciendo, desde cuándo y quién lo está empujando.**

## Versión de 3 minutos

### 1. El problema (20 segundos)

Cuando miles de personas discuten algo, hay dos preguntas que importan: qué ideas circulan, y cuáles son
genuinas y cuáles están armadas. Leerlo comentario por comentario con IA es lento y caro. Buscar palabras
clave no sirve, porque la gente dice lo mismo de mil maneras, y el que está en contra usa las mismas palabras
que el que está a favor.

### 2. La idea (30 segundos)

Nosotros no intentamos entender cada comentario. **Miramos la conversación.**

Dos cosas que pasan siempre en una discusión:

- **La gente se repite.** De 200.000 comentarios, después de limpiar tildes, emojis y errores de tipeo,
  quedan 47.000 textos distintos, y esos son variaciones de unas 370 frases.
- **La gente se contesta.** Si alguien responde "mentira, la obra avanza" a "la obra está parada", los dos
  están hablando de lo mismo, aunque no compartan casi ninguna palabra.

Con eso armamos un mapa: frases unidas por quién le contesta a quién. Las regiones de ese mapa son las
narrativas. Y dentro de cada una, los que se contestan entre sí son los dos bandos.

### 3. La coordinación (30 segundos)

Para las cuentas armadas, la trampa conocida es marcar a todo el que repite un texto: una frase viral la
repite todo el mundo. La línea base de la organización marcó 675 cuentas y acertó en el 7%.

Nosotros miramos otra cosa: **las mismas cuentas, juntas, una y otra vez.** Coincidir en una publicación viral
no dice nada. Coincidir varias veces, en la misma media hora, donde casi no hay nadie, sí. Lo comparamos contra
lo esperable por azar y nos quedamos solo con los grupos donde las coincidencias se cruzan entre muchas
cuentas, no con pares sueltos.

### 4. Demo (60 segundos)

Abrir `reporte/entrega.html` **[VIERNES]** (hoy: `reporte/practica.html`). Recorrido:

1. **Arriba, la respuesta en una frase**: cuántas narrativas, cuántas nuevas, cuántas cuentas coordinadas.
   Leer en voz alta una de las líneas de hallazgos. En práctica: *"g03, 25 cuentas, originó la narrativa del
   hospital para la foto, que apareció el domingo 6 a la 1:12 de la mañana."*
2. **La tabla**: señalar una narrativa "nueva", su fecha de origen y la línea de tiempo donde se ve que nace
   de golpe. Señalar las barras de color: son los comentarios del grupo que la empuja.
3. **Una tarjeta de grupo**: cuentas creadas días antes, actúan de madrugada, en ráfagas, repitiendo tres
   frases. Y la otra, la difícil: cuentas viejas, textos variados, horario normal. Esa no se ve mirando una
   cuenta sola; se ve porque siempre aparecen juntas.
4. Volver a la terminal: **un comando**, y al final dice "Validación OK".

### 5. Resultados y costo (30 segundos)

| | Línea base | Nosotros (práctica) | Set final |
|---|---|---|---|
| Puntaje automático | 16,8 / 55 | **54,56 / 55** | **[VIERNES]** no hay verdad: lo mide el jurado |
| Cuentas coordinadas | 7% de precisión | **115 de 115, sin falsos positivos** | **[VIERNES]** cantidad de cuentas y grupos |
| Tiempo | — | **27 a 48 s** | **[VIERNES]** |
| Memoria pico | — | **650 MB** | **[VIERNES]** |
| Costo en IA | — | **0 tokens, 0 USD** | 0 |

Todo corre en una notebook de 8 GB sin GPU. Los datos viven en un archivo DuckDB de 35 MB: sin servidor, sin
nube, y el jurado lo puede volver a correr con un comando.

### 6. Cierre (10 segundos)

> No hace falta un modelo gigante para entender una conversación. Hace falta mirar cómo se contesta la gente
> y quién aparece siempre con quién.

## Versión de 60 segundos

Leemos 200.000 comentarios en medio minuto, en una notebook, sin IA. No intentamos entender cada comentario:
miramos la conversación. La gente se repite, así que 200.000 comentarios son en realidad unas 370 frases. Y la
gente se contesta: si uno responde contradiciendo a otro, hablan de lo mismo. Con eso sale un mapa de
narrativas y de bandos. Para las cuentas armadas no miramos quién repite un texto, sino quiénes aparecen
juntos una y otra vez, más de lo que explica el azar. En el set de práctica sacamos 54,5 de 55 puntos y
encontramos las 115 cuentas coordinadas sin un solo falso positivo. Costo: cero dólares. *(Mostrar el reporte.)*

## Qué decir para cada criterio del jurado

**Costo, escala y almacenamiento (20 puntos)**

- Costo por mil comentarios: 0 USD. No hay IA generativa ni servicios pagos.
- DuckDB porque es una base analítica por columnas que no necesita servidor: un archivo, un `pip install`.
  Lee CSV comprimido directo, limpia con SQL y trabaja con más datos que memoria.
- Escala porque el trabajo pesado no crece con los comentarios sino con las frases distintas, y las frases se
  repiten. Lo nuevo de cada día se suma a lo que ya está: particiones por fecha, textos únicos, y el
  agrupamiento ya funciona en una pasada.
- **Decirlo con honestidad:** no medimos una corrida con millones. Es diseño, no medición.

**Robustez (15 puntos)**

- Un comando de punta a punta. Mismo resultado byte a byte en dos corridas y en dos entornos distintos.
- 24 pruebas automáticas: archivos faltantes, columnas faltantes, fechas rotas, duplicados, hilos circulares,
  otra codificación, set vacío.
- El pipeline valida su propia entrega contra el formato del enunciado antes de terminar.
- Lo que tuvo que descartar o suponer queda escrito en `costo.json`.

**Claridad y visualización (10 puntos)**

- Un HTML que se abre con doble clic, sin internet. Arriba, la respuesta en una frase.

## Lo que no hace (decirlo antes de que lo pregunten)

- **Decidir cuál bando "apoya" es lo más flojo.** Separamos bien los dos bandos de cada narrativa, pero
  decidir cuál sostiene la afirmación y cuál la niega es un problema de significado. En práctica erramos 1 de
  13 narrativas. Una sola llamada a un modelo de lenguaje, con unas 300 frases, lo resolvería por centavos.
  Elegimos no usar IA.
- **Depende de que haya respuestas.** Si nadie le contesta a nadie, caemos a agrupar por palabras, que rinde
  como la línea base.
- **Necesita repetición.** Una operación que actúa una sola vez no se ve.
- **Ajustamos algunos umbrales mirando el set de práctica.** Están listados uno por uno en el README, con qué
  tan sensible es cada uno.

## Preguntas probables

**¿Por qué no usaron embeddings o un LLM?**
Porque la estructura de la conversación ya dice qué frases hablan de lo mismo, y es gratis. Las palabras solas
agrupan mal: lo probamos y da 0,38 contra 1,00. Donde sí usaríamos un modelo es en decidir qué bando apoya.

**¿Cómo saben que no marcan gente genuina?**
Pedimos tres cosas a la vez: coincidir varias veces, mucho más de lo esperable según cuánto comenta cada
cuenta, y formar un grupo denso, donde las coincidencias se cruzan entre muchas cuentas. En práctica, cero falsos positivos, y en los
recortes grandes que no usamos para ajustar, precisión entre 0,99 y 1,00. No es infalible: probándolo con una muestra chica
encontramos un grupo falso de 5 cuentas y lo corregimos. Y si en otro set marcara más del 5% de las cuentas, los umbrales
se endurecen solos y queda avisado.

**¿Usan la antigüedad de las cuentas?**
No como umbral. Solo como refuerzo: si un grupo ya detectado fue creado todo en la misma semana, otra cuenta de
esa semana que aparece con el grupo entra con menos evidencia. Así no confundimos cuentas viejas con genuinas
ni cuentas nuevas con armadas.

**¿Y si el set final es distinto?**
Lo es: otros temas y otras campañas. Por eso no hay temas, nombres ni fechas en el código, y probamos el
pipeline sobre recortes por días, por tema y con datos rotos. Lo que puede fallar está escrito en el README.

**¿Cuánto tarda con diez veces más datos?**
No lo medimos. Lo que sí sabemos es qué etapa manda: cruzar pares de cuentas (11 de 27 segundos). Esa etapa ya
trabaja por bloques con memoria acotada y se puede partir por día.

**¿Qué parte hicieron ustedes?**
Todo `pipeline/` y `pruebas/`, durante el hackathon, con ayuda de un asistente de programación. El evaluador y
la línea base son de la organización y no los tocamos.

## Para completar el viernes

- [ ] Números del set final: comentarios, narrativas, grupos, cuentas marcadas, segundos, memoria.
- [ ] Elegir las dos o tres narrativas y el grupo que se van a mostrar en la demo (mirar el reporte antes).
- [ ] Capturas del reporte por si falla el proyector.
- [ ] Ensayar con cronómetro: 3 minutos.
- [ ] Decidir quién habla y quién maneja la pantalla.
