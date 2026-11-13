# Guía para Damián: cómo contar el proyecto y grabar el video

Esta guía es para que puedas explicar el proyecto y grabar la demo sin haber tocado el código.
Todos los números salen del repo y de la corrida final (`entrega/costo.json` y `reporte/entrega.html`).
Si un número no está acá, no lo digas.

Dos palabras que vas a escuchar: **pipeline** es el programa, una cadena de pasos que corre sola de principio
a fin con un solo comando. **Set** es un paquete de datos: hubo uno de práctica (200.000 comentarios, con las
respuestas correctas) y uno final (150.000 comentarios, sin respuestas correctas), que es el que se entrega.

---

## 1. El problema en 3 frases

1. QualyData nos dio 150.000 comentarios inventados (sintéticos) de redes sociales sobre noticias locales, y
   pidió un programa que diga solo, sin que nadie lea los comentarios, **qué se está diciendo, desde cuándo y
   quién lo está empujando**.
2. Una **narrativa** es una misma idea dicha con distintas palabras por mucha gente, incluidos los que la
   discuten; el **ruido** son los comentarios que no dicen nada sobre ningún tema.
3. Las **cuentas coordinadas** son cuentas que actúan en equipo para instalar una idea, haciéndose pasar por
   gente común.

Ejemplos del set final (los tres temas son la seguridad en un barrio, un dique y un festival):

| Qué es | Ejemplo real del set final |
|---|---|
| Una narrativa | "Te roban en la puerta de tu casa y el 911 no atiende." Es la más grande: 17.198 comentarios. Adentro están los que la afirman ("Zona liberada total, los chorros lo saben") y los que la discuten ("No es zona liberada, detuvieron a dos la semana pasada"). |
| Ruido | "Comparto", "Qué esquina es?", "Sorteo en mi perfil!!" |
| Cuentas coordinadas | 50 cuentas creadas todas en la misma semana que repiten, juntas y en ráfagas, "Queremos el dique: agua para el riego y para toda la ciudad." |

---

## 2. Cómo lo resolvimos (sin programar)

La idea central: **no intentamos entender cada comentario. Miramos la conversación**: quién repite qué, quién
le contesta a quién y quién aparece siempre con quién.

### Paso 1: juntar los textos casi iguales

- **Qué hace.** Limpia los comentarios (mayúsculas, tildes, emojis, errores de tipeo) y junta los que son la
  misma frase con cambios chicos. "Calle iluminada es calle segura." y "A ver, calle iluminada es calle
  segura. Triste." son la misma frase.
- **Por qué funciona.** La gente se repite. En el set final, los 150.000 comentarios son 79.495 textos
  distintos; después de limpiarlos quedan 32.874, y esos son variaciones de unas 240 frases. El trabajo
  pesado se hace sobre 240 frases, no sobre 150.000 comentarios. Por eso es rápido.

### Paso 2: seguir los hilos de respuestas

- **Qué hace.** Mira quién le contesta a quién. Si alguien responde "Pusieron luces y siguen robando igual"
  a "Calle iluminada es calle segura", los dos hablan de lo mismo aunque opinen lo contrario. Con esos
  enlaces arma un mapa de frases; cada zona del mapa es una narrativa. Dentro de cada narrativa, los que se
  contestan entre sí son los dos bandos: los que **apoyan** (afirman la idea) y los que **rechazan** (la niegan).
- **Por qué funciona.** Buscar palabras no alcanza: el que está a favor y el que está en contra usan casi las
  mismas palabras, y dos frases sobre lo mismo pueden no compartir ninguna. La conversación sí lo muestra.
  En el set final hay 20.628 respuestas (el 13,8% de los comentarios).
- **El ruido sale de acá.** A un "Comparto" o a un "Sorteo en mi perfil!!" nadie le contesta. Una frase que
  aparece muchas veces y nunca recibe una respuesta se trata como ruido. Es una regla que vimos en los datos
  de práctica.
- **Las respuestas cortas heredan.** Un "tal cual" o un "exacto" no dice nada solo: toma la narrativa y la
  postura del comentario al que responde.
- **Desde cuándo.** La fecha de origen de una narrativa es el primer momento en que aparece con compañía
  (varios comentarios en pocas horas), no un comentario aislado.

### Paso 3: detectar cuentas que actúan juntas

- **Qué hace.** Busca cuentas que coinciden **una y otra vez**: comentan la misma publicación, en la misma
  media hora, varias veces y en más de una publicación. Lo compara con lo que pasaría por casualidad y se
  queda solo con los grupos donde las coincidencias se cruzan entre muchas cuentas, no con pares sueltos.
- **Por qué funciona.** La trampa conocida es marcar a todo el que repite un texto: una frase viral la repite
  todo el mundo. Lo que delata a una operación no es lo que dice, sino que **siempre son las mismas cuentas,
  juntas**. Coincidir en una publicación con miles de comentarios no dice nada; coincidir varias veces donde
  casi no hay nadie, sí.
- **Una protección.** Si el programa llegara a marcar más del 5% de las cuentas, se vuelve más exigente solo
  y lo avisa. En el set final no hizo falta: marcó el 0,85%.

### Pasos finales

Escribe los 4 archivos que pide el desafío en `entrega/`, **revisa solo** que tengan el formato exacto, y
arma el reporte visual (`reporte/entrega.html`).

---

## 3. Los números del pitch: qué significan y cómo decirlos

| Número | Qué significa | Cómo lo digo |
|---|---|---|
| **150.000 comentarios** | El set final completo: 12.002 cuentas comentando 372 publicaciones durante 10 días (del 5 al 14 de octubre). | "Procesamos los 150.000 comentarios del set final, todos, sin muestrear." |
| **12 narrativas** | Las ideas distintas que el programa encontró, sobre 3 temas. 9 están desde el primer día y 3 aparecen durante el período. | "Encontramos 12 narrativas sobre tres temas, y tres de ellas nacieron durante esos diez días." |
| **20,7% de ruido** | 1 de cada 5 comentarios no pertenece a ninguna narrativa: reacciones, preguntas sueltas, avisos. | "Uno de cada cinco comentarios es ruido, y el programa lo aparta solo." |
| **102 cuentas en 3 grupos (50, 30, 22)** | De 12.002 cuentas, 102 (el 0,85%) actúan coordinadas, en tres operaciones separadas. | "Menos del 1% de las cuentas está coordinado: 102 cuentas, en tres operaciones de 50, 30 y 22." |
| **22 segundos** | Lo que tarda todo, de leer los archivos a escribir la entrega y el reporte. Medido: 22,2 s. | "Todo eso tarda unos 22 segundos." |
| **567 MB** | La memoria máxima que usó el programa. Una notebook común tiene 8.000 MB. | "Usa medio giga de memoria: entra en cualquier notebook." |
| **0 dólares** | No se pagó ningún servicio. El costo por cada mil comentarios es cero. | "El costo de procesar esto fue cero dólares." |
| **Sin IA** | El programa no le manda ningún comentario a un modelo de inteligencia artificial. Es estadística y conteo. | "No usa inteligencia artificial para leer los comentarios: mira cómo se comporta la conversación." |

Tres aclaraciones para que no te agarren en falta:

- **El reporte muestra "21,2 s" y `costo.json` dice 22,2 s.** Los dos están bien: el reporte anota el tiempo
  antes de terminar de armarse a sí mismo. Decí "unos 22 segundos".
- **El reporte muestra "0,8%" y "21% de ruido"** porque redondea. Los valores exactos son 0,85% y 20,7%.
- **"Sin IA" es sobre el programa cuando corre.** El código lo escribimos con ayuda de un asistente de
  programación con IA, y el README lo declara. Si preguntan, decilo así.

Y un número del set de práctica, que es el único donde hay respuestas correctas para medir: sacamos
**54,56 de 55 puntos** (la solución de ejemplo de la organización saca 16,8) y encontramos las 115 cuentas
coordinadas sin marcar a ninguna cuenta genuina. **En el set final no hay puntaje**: lo mide el jurado.

---

## 4. Cómo identificamos a las operaciones

En el reporte se llaman Operación A, B y C (ordenadas por tamaño). En el archivo `entrega/cuentas.csv`
figuran con un código: g02, g01 y g03.

| | Operación A (g02) | Operación B (g01) | Operación C (g03) |
|---|---|---|---|
| Cuentas | 50 | 30 | 22 |
| Tipo de cuenta | Recién creadas: 7 días de antigüedad al primer comentario | Antiguas: 1.889 días | Recién creadas: 5 días |
| Comentarios | 337 | 490 | 85 |
| Cuándo actúa | De tarde y de noche (87% entre las 13 y las 22 h) | De día (82% entre las 9 y las 21 h) | De madrugada (100% entre la 1 y las 5 h) |
| Cómo actúa | 15 ráfagas; hasta 25 cuentas en la misma publicación en 30 minutos | 32 ráfagas; hasta 15 cuentas | 11 ráfagas; hasta 18 cuentas |
| Qué empuja | "Agua y dique": que el dique es necesario | "Festival y circo": que el festival es un gasto | "Comisaría y cierra": el rumor de que cierran la comisaría |
| Lo que más repite | "Queremos el dique: agua para el riego y para toda la ciudad." | "Exacto, pan y circo", "Tal cual, primero las prioridades" | "Confirmado: cierran la comisaría del Norte. Compartan." |

(Para comparar: las cuentas del resto del set tienen 3.168 días de antigüedad.)

Tres estilos distintos, y el programa encontró los tres con la misma regla (las mismas cuentas, juntas, una
y otra vez):

- **La A es la ruidosa**: cuentas nuevas que repiten consignas casi idénticas.
- **La B es la difícil**: cuentas viejas, textos variados, horario normal. Mirando una cuenta sola no se ve
  nada raro. Se ve porque siempre aparecen juntas y se dan la razón entre sí ("Exacto, pan y circo").
- **La C es la que inventa**: lanza un rumor de madrugada. La narrativa de la comisaría aparece el viernes 9
  de octubre a la 1:41, justo cuando este grupo empieza a comentar.

Además, las tres hacen **actividad de cobertura**: comentarios comunes sobre cualquier tema, para parecer
usuarios normales. En la Operación A, el 68% de sus comentarios empuja el dique y el otro 32% es cobertura.

### El ejemplo de la Operación A y la consigna del dique

Sirve para contar cómo trabajamos, porque es un problema que encontramos y arreglamos:

1. La campaña usa cinco consignas casi iguales: "Sí a la obra: el dique es agua para la ciudad y para el
   riego", "Queremos el dique: agua para el riego y para toda la ciudad", y variantes.
2. Casi nadie de afuera les contesta. Como el programa ubica cada frase por sus respuestas, con tan pocas
   respuestas las consignas quedaron mal: tres en la narrativa del sobreprecio de la obra y una como ruido.
   El reporte decía que la operación empujaba la narrativa equivocada.
3. La regla que agregamos: **una frase que dice casi solo una operación es una consigna de esa operación**.
   Se ubica mirando qué le contesta la gente de afuera (por ejemplo, "El agua del dique es para las fincas
   grandes, no para la ciudad"), sin contar las respuestas con que las cuentas de la operación se dan la
   razón entre sí.
4. Resultado: las cinco consignas quedaron en la narrativa del dique, apoyándola.
5. Agregamos también que, al buscar cuentas, el programa mire quién repite la misma frase junto con el grupo.
   Así aparecieron 4 cuentas de la operación que faltaban (pasó de 46 a 50).
6. En el set de práctica el resultado no cambió con ninguna de las dos reglas.

---

## 5. Qué es DuckDB y por qué lo elegimos

**Qué es.** Una base de datos que vive en un solo archivo de la computadora. No hay que instalar ni encender
ningún servidor: se instala como cualquier otra librería y listo. Está pensada para hacer cuentas sobre
muchas filas (contar, agrupar, cruzar), que es justo lo que hace el programa.

**Dónde están los datos.** Los archivos del desafío se cargan una sola vez a `almacen/final.duckdb`. Ahí
quedan los datos limpios y también los resultados, listos para consultar. En el set final ese archivo pesa
25,8 MB (la entrada comprimida pesa 3,4 MB y la entrega, 2,9 MB).

**Por qué DuckDB** (esto es lo que puntúa el jurado en costo, escala y almacenamiento):

- **No cuesta nada.** Sin servidor, sin nube, sin cuentas ni contraseñas.
- **El jurado puede volver a correr todo con un comando**, sin preparar nada más.
- **Es rápida para este tipo de trabajo.** Guarda los datos por columnas, y nuestras cuentas usan pocas
  columnas de muchas filas.
- **Lee los archivos comprimidos directo y aguanta datos sucios** (fechas rotas, filas repetidas, columnas
  que faltan).
- **Puede trabajar con más datos que la memoria disponible**: si no le alcanza, usa el disco.
- **Crecer es directo**: los mismos pasos sirven si los datos se guardan en archivos por día o si un día hace
  falta un servidor.

Lo que descartamos: PostgreSQL (necesita un servidor y es más lenta para este tipo de cuentas),
Elasticsearch (pensada para buscar texto, pesada para una notebook) y trabajar todo en memoria sin base
(no deja nada guardado para consultar).

---

## 6. Cómo escala

Lo que **sí medimos**, con datos reales del set de práctica, en la misma notebook (8 GB de memoria, sin
placa de video), tres corridas por tamaño:

| Comentarios | Tiempo | Comentarios por segundo | Memoria máxima | Tamaño de la base |
|---|---|---|---|---|
| 10.657 | 3,7 s | 2.880 | 204 MB | 3,0 MB |
| 50.190 | 9,5 s | 5.283 | 302 MB | 12,8 MB |
| 100.287 | 17,9 s | 5.602 | 431 MB | 20,8 MB |
| 200.000 | 31,1 s | 6.430 | 634 MB | 35,3 MB |

Qué muestra la tabla:

- **El tiempo crece parejo con los datos, no se dispara.** De 50.000 a 200.000 hay 4 veces más comentarios y
  3,3 veces más tiempo.
- **La memoria también**: unos 190 MB fijos más unos 2,3 MB por cada mil comentarios.

**Con un millón: no lo medimos.** Decilo así, sin vueltas. Lo que hay es una cuenta hecha con la tabla:

- Memoria: 190 MB más 2,3 MB por cada mil da unos 2,5 GB. Entraría en la notebook de 8 GB.
- Tiempo: si siguiera creciendo parejo, 5 veces los 200.000 serían unos dos minutos y medio. Es una regla de
  tres, no una medición.

Y por qué creemos que aguanta más (es diseño, no medición):

- El trabajo pesado no crece con los comentarios sino con las frases distintas, y la gente se repite.
- Cada día nuevo se puede sumar sin volver a procesar lo anterior.
- La parte más lenta, cruzar cuentas, ya trabaja por partes para no llenar la memoria, y se puede repartir
  por día.

---

## 7. Qué NO hacemos, y por qué es una ventaja

- **No etiquetamos nada a mano.** Nadie leyó los comentarios del set final para decidir nada, y nadie editó
  la entrega. Ventaja: es lo que exige el desafío, y el resultado no depende de la opinión de una persona.
- **No usamos IA para leer los comentarios.** Ventaja: cuesta cero, no necesita internet ni claves, no hay
  límite de uso, y se puede explicar por qué el programa decidió cada cosa.
- **No hay azar.** Si se corre dos veces, da exactamente los mismos archivos. Lo comprobamos: bajamos el repo
  de GitHub a una carpeta nueva, instalamos desde cero, corrimos el comando, y los tres archivos de
  resultados salieron idénticos, byte por byte, a los entregados. Ventaja: el jurado avisó que a los equipos
  del podio les vuelve a correr el programa, y si el resultado no se parece al entregado, quedan afuera. El
  nuestro da lo mismo siempre.
- **No hay nada del set de práctica escrito en el código**: ni temas, ni nombres, ni fechas. Por eso anduvo
  en el set final, que trae otros temas y otras campañas.

---

## 8. Límites, para decirlos si preguntan

Decirlos con tranquilidad suma: muestra que sabemos qué hace y qué no hace el programa.

- **La postura (a favor o en contra) es la parte menos precisa.** El programa separa bien los dos bandos de
  cada narrativa, pero decidir cuál de los dos es el que afirma la idea es más difícil. En práctica acertó en
  12 de 13 narrativas. En el set final no hay forma de medirlo; el reporte marca cada narrativa con un nivel
  de confianza (5 con confianza alta, 7 con media, ninguna con baja), y esos niveles son un criterio nuestro,
  no una medición.
- **Dos consignas quedaron mal ubicadas en el set final:**
  - "Sí a la obra!" (14 comentarios) quedó en la narrativa del dique, pero como si la rechazara.
  - Tres redacciones del rumor de la comisaría (60 comentarios de la Operación C) quedaron como ruido. Las
    cuentas sí están marcadas y la fecha de origen del rumor está bien.
  - Entre las dos son 74 comentarios de 150.000.
- **Depende de que la gente se conteste.** Si un set no tuviera respuestas, el programa pasa a agrupar por
  palabras, que rinde mucho menos, y lo avisa.
- **Necesita repetición.** Una operación que actúa una sola vez no se ve.
- **La regla del ruido** ("a lo que nadie le contesta") la vimos en práctica. Si otro set no la cumple, esa
  parte pierde precisión.
- **La regla de las consignas la agregamos después de ver la salida del set final.** No tocamos la entrega a
  mano ni elegimos ningún número con ese set, pero la idea salió de ahí. Está dicho en el README.
- **No medimos una corrida con un millón de comentarios.**

---

## 9. Guion del video

### Antes de grabar

- Abrí `reporte/entrega.html` con doble clic (se abre en el navegador; no necesita internet). Poné el
  navegador en pantalla completa y con el zoom que se lea bien.
- Para mostrar el comando hace falta tener el programa instalado (los pasos están en el README, sección
  "Cómo correrlo"; lo más simple es grabarlo en la máquina de Esteban). El comando es:

  ```bash
  python -m pipeline.run --datos datos/final --entrega entrega
  ```

  Tarda unos 22 segundos. Al final tiene que decir **"Validación de entrega: OK"**, **"Controles de cordura:
  sin alertas"** y **"Listo en ... s"**. Conviene grabarlo aparte y pegarlo, o acelerarlo en la edición.
- El reporte tiene cuatro partes, de arriba hacia abajo: el **resumen** (bloque oscuro con la frase y las
  operaciones), **"1 · Cuándo"** (la línea de tiempo), **"2 · Qué se dice"** (las narrativas por tema) y
  **"3 · Quién lo empuja"** (una tarjeta por operación).

### Versión de 2 minutos

| Tiempo | Qué mostrar | Qué decir |
|---|---|---|
| 0:00 a 0:15 | El resumen del reporte, arriba de todo. | "Somos ESDATA. El desafío de QualyData: 150.000 comentarios, y hay que decir qué se está diciendo, desde cuándo y quién lo está empujando. Sin leerlos uno por uno." |
| 0:15 a 0:35 | La terminal con el comando corriendo, hasta "Validación de entrega: OK" y "Listo". | "Es un solo comando. En unos 22 segundos, en una notebook común, sin inteligencia artificial y sin gastar un dólar, lee todo, escribe la entrega y la revisa solo." |
| 0:35 a 0:55 | Volver al resumen. Señalar la frase grande y los recuadros con los números. | "Encontró 12 narrativas sobre tres temas: la seguridad, un dique y un festival. Uno de cada cinco comentarios es ruido. Y 102 cuentas, menos del 1%, actúan coordinadas en tres operaciones." |
| 0:55 a 1:15 | Bajar a "2 · Qué se dice". Mostrar una narrativa: su frase representativa y la barra apoya / rechaza. | "¿Cómo lo hace? No intenta entender cada comentario: mira la conversación. La gente se repite, así que 150.000 comentarios son en realidad unas 240 frases. Y la gente se contesta: si uno le discute a otro, hablan de lo mismo. Así salen las narrativas y sus dos bandos." |
| 1:15 a 1:40 | Bajar a "3 · Quién lo empuja". Mostrar la tarjeta de la Operación A y después la de la Operación C. | "Para las cuentas armadas no miramos quién repite un texto, porque lo viral lo repite todo el mundo. Miramos quiénes aparecen juntos una y otra vez. Operación A: 50 cuentas creadas la misma semana, repitiendo 'Queremos el dique'. Operación C: 22 cuentas que comentan solo de madrugada." |
| 1:40 a 1:52 | Subir a "1 · Cuándo", la línea de tiempo. Señalar el punto de la narrativa de la comisaría y la ráfaga del grupo debajo. | "Y esa operación lanzó un rumor: que cierran la comisaría. Aparece el viernes 9 a la 1:41 de la mañana, justo cuando el grupo empieza a comentar." |
| 1:52 a 2:00 | Volver al resumen, o mostrar el repo en GitHub. | "Un comando, 22 segundos, cero dólares, y el mismo resultado cada vez que se corre. Gracias." |

### Versión de 60 segundos

| Tiempo | Qué mostrar | Qué decir |
|---|---|---|
| 0:00 a 0:12 | El resumen del reporte. | "Somos ESDATA. De 150.000 comentarios, nuestro programa dice qué se está diciendo, desde cuándo y quién lo empuja. Con un comando, en 22 segundos, sin inteligencia artificial y por cero dólares." |
| 0:12 a 0:28 | "2 · Qué se dice": una narrativa con su barra apoya / rechaza. | "No intenta entender cada comentario: mira la conversación. La gente se repite y se contesta, y con eso salen las 12 narrativas y los dos bandos de cada una." |
| 0:28 a 0:48 | "3 · Quién lo empuja": las tarjetas de las operaciones. | "Para las cuentas armadas miramos quiénes aparecen juntos una y otra vez. Encontró tres operaciones, 102 cuentas: una repite consignas a favor de un dique, otra lanza un rumor de madrugada." |
| 0:48 a 1:00 | Volver al resumen. | "Corre en una notebook común y da el mismo resultado cada vez. Gracias." |

Consejos: hablá despacio, no leas la pantalla, y mové el mouse hacia lo que estás nombrando. Si te pasás de
tiempo, lo primero que se puede sacar es la parte de la línea de tiempo.

---

## 10. Preguntas probables del jurado

**¿Por qué no usaron IA?**
Porque la conversación ya dice qué frases hablan de lo mismo, y es gratis. Donde sí serviría un modelo es en
decidir qué bando apoya y cuál rechaza; elegimos no usarlo: así no hacen falta claves ni internet y el
resultado es idéntico en cada corrida.

**¿Cómo saben que no marcan gente genuina?**
Pedimos tres cosas a la vez: coincidir varias veces, mucho más de lo que pasaría por casualidad, y formar un
grupo donde las coincidencias se cruzan entre muchas cuentas. En el set de práctica no marcó a ninguna cuenta
genuina. En el set final marcó 102 de 12.002, y las tres operaciones tienen un patrón claro.

**¿Cómo saben que el resultado del set final está bien?**
No hay respuestas correctas para medirlo; eso lo hace el jurado. Lo que sabemos: en práctica sacó 54,56 de 55,
el programa valida solo el formato, y revisamos que las narrativas y los grupos tengan sentido sin corregir
nada a mano.

**¿Usan la antigüedad de las cuentas?**
No como regla fija. Solo como refuerzo: si un grupo ya detectado fue creado todo en la misma semana, otra
cuenta de esa semana que aparece con el grupo entra con menos evidencia. Por eso encontramos también a la
Operación B, que son cuentas viejas.

**¿Qué pasa con un millón de comentarios, o con millones por día?**
No lo medimos. Medimos de 10.000 a 200.000: el tiempo y la memoria crecen parejo con los datos. Con esa
cuenta, un millón necesitaría unos 2,5 GB de memoria. Y el diseño permite sumar cada día sin reprocesar lo
anterior.

**¿Por qué DuckDB?**
Es una base en un solo archivo, sin servidor y sin costo, rápida para contar y cruzar muchas filas. El jurado
puede correr todo con un comando.

**¿Qué es lo más flojo?**
Decidir qué bando apoya y cuál rechaza. Y en el set final quedaron 74 comentarios de campaña mal ubicados.

**¿Y si el set fuera distinto?**
Ya lo fue: el set final trae otros temas y otras campañas que el de práctica, y el programa anduvo sin
cambiarle nada de eso, porque no tiene temas ni nombres escritos. Lo que puede fallar está en el README.

**¿Cambiaron algo después de ver el set final?**
Sí, una regla general sobre las consignas de las operaciones, sin tocar la entrega a mano y sin elegir ningún
número con ese set. En práctica el resultado quedó igual. Está declarado en el README.

**¿Qué parte hicieron ustedes?**
Todo el programa (la carpeta `pipeline/`) y sus pruebas, durante el hackathon, con ayuda de un asistente de
programación. El evaluador y la solución de ejemplo son de la organización y no los tocamos.

**¿Se puede volver a correr?**
Sí. Lo probamos bajando el repo desde cero: mismos archivos, byte por byte. Los pasos están en el README.
