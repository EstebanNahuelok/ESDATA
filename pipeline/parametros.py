"""Todos los parámetros y umbrales del pipeline, en un solo lugar.

Cada uno dice qué hace, cuánto vale y de dónde salió el valor:

- GENERAL:   regla del enunciado, del idioma o de la estadística; no depende del set.
- CRITERIO:  valor razonable elegido a ojo; nunca se ajustó contra la verdad del set de práctica.
- PRACTICA:  valor elegido midiendo contra la verdad del set de práctica (puede no servir igual en otro set).
- TECNICO:   solo cambia memoria o velocidad (o es un resguardo); no debería cambiar el resultado.

Los que tienen `ajustable=True` se pueden cambiar en una corrida con `--param nombre=valor` (queda anotado en
costo.json). `verificacion/sensibilidad.py` los mueve -50% y +50% para ver cuáles son frágiles.

    python -m pipeline.parametros        # imprime la tabla en Markdown
"""
from dataclasses import dataclass

GENERAL, CRITERIO, PRACTICA, TECNICO = "regla general", "criterio, sin ajustar", "ajustado en práctica", "técnico"


@dataclass(frozen=True)
class Parametro:
    nombre: str
    valor: object
    etapa: str
    origen: str
    que_hace: str
    ajustable: bool = True


PARAMETROS = [
    # --- Texto y microgrupos -------------------------------------------------------------------------------
    Parametro("tipeo_min_largo", 4, "narrativas", CRITERIO,
              "Largo mínimo de una palabra para corregirle errores de tipeo (protege palabras cortas como 'la'/'al')."),
    Parametro("tipeo_razon", 10, "narrativas", CRITERIO,
              "Una palabra rara se corrige solo si la candidata es al menos esta cantidad de veces más frecuente."),
    Parametro("tfidf", "palabras y pares, min_df=2, tf sublineal", "narrativas", CRITERIO,
              "Cómo se representa cada texto para comparar frases (TF-IDF). Con muy pocos textos baja a min_df=1.", False),
    Parametro("umbral_micro", 0.5, "narrativas", PRACTICA,
              "Parecido mínimo (coseno) entre dos textos para considerarlos la misma frase (microgrupo)."),
    Parametro("min_peso", 30, "narrativas", PRACTICA,
              "Comentarios mínimos de un microgrupo; los más chicos se disuelven y pasan al grupo grande más parecido. "
              "También es lo mínimo para que la prueba de ruido sea concluyente."),
    Parametro("umbral_parecido", 0.25, "narrativas", PRACTICA,
              "Parecido mínimo para absorber una variante rara en un microgrupo grande, y para sumar a una narrativa "
              "un microgrupo que quedó sin enlaces de respuesta."),
    Parametro("lote", 2000, "narrativas", TECNICO, "Textos que se comparan por tanda al armar microgrupos.", False),
    # --- Tipos de microgrupo, ruido y narrativas -----------------------------------------------------------
    Parametro("frac_acuerdo", 0.9, "narrativas", PRACTICA,
              "Si esta fracción (o más) de las apariciones de una frase son respuestas, es una frase de acuerdo "
              "('tal cual'): hereda narrativa y postura del comentario al que responde."),
    Parametro("alfa_ruido", 0.01, "narrativas", GENERAL,
              "Nivel de la prueba de ruido: una frase suelta es ruido si, a la tasa de respuestas del propio set, "
              "la probabilidad de que nadie le haya respondido nunca es menor a este valor."),
    Parametro("factor_sin_eco", 0.2, "narrativas", CRITERIO,
              "Una frase 'no tiene eco' si recibió menos de esta fracción de las respuestas esperadas."),
    Parametro("resolucion", 1.0, "narrativas", GENERAL,
              "Resolución de Louvain al partir el grafo de frases en narrativas (1 es el valor estándar)."),
    Parametro("min_respuestas", 50, "narrativas", CRITERIO,
              "Con menos respuestas que esto en todo el set no se usan los hilos y se pasa al plan B por palabras."),
    Parametro("umbral_sin_hilos", 0.1, "narrativas", PRACTICA,
              "Plan B (sin hilos): parecido mínimo entre microgrupos para unirlos en una narrativa."),
    Parametro("largo_ruido_sin_hilos", 5, "narrativas", PRACTICA,
              "Plan B (sin hilos): una frase con menos palabras que esto, en promedio, es ruido."),
    Parametro("max_pasos_hilo", 64, "narrativas", TECNICO, "Profundidad máxima de un hilo de respuestas.", False),
    # --- Postura -------------------------------------------------------------------------------------------
    Parametro("marcas_rechazo", "21 expresiones ('mentira', 'falso', 'nada que ver'...)", "postura", PRACTICA,
              "Marcas de desmentida: el bando que las usa es el que rechaza. Lista del idioma, completada mirando práctica.", False),
    Parametro("peso_marcas", 20.0, "postura", PRACTICA, "Peso del indicio 'un bando usa más marcas de desmentida'."),
    Parametro("peso_campana", 20.0, "postura", PRACTICA, "Peso del indicio 'un grupo coordinado empuja este bando'."),
    Parametro("peso_sueltos", 0.5, "postura", PRACTICA,
              "Peso del indicio 'este bando aparece más como comentario suelto que como respuesta'."),
    Parametro("tope_sueltos", 3.0, "postura", CRITERIO, "Tope (en desvíos estándar) del indicio de comentarios sueltos."),
    Parametro("peso_variedad", 1.0, "postura", PRACTICA, "Peso del indicio 'este bando tiene más redacciones distintas'."),
    Parametro("peso_volumen", 1.0, "postura", PRACTICA, "Peso del indicio 'este bando tiene más comentarios'."),
    # --- Origen --------------------------------------------------------------------------------------------
    Parametro("origen_min_comentarios", 5, "origen", CRITERIO,
              "El origen es el primer comentario de la narrativa que tiene al menos esta compañía..."),
    Parametro("origen_ventana_h", 12.0, "origen", CRITERIO, "...dentro de esta cantidad de horas (descarta apariciones aisladas)."),
    # --- Coordinación --------------------------------------------------------------------------------------
    Parametro("ventana_s", 1800, "coordinacion", PRACTICA,
              "Ventana de coincidencia: dos cuentas coinciden si comentan la misma publicación dentro de estos segundos "
              "(se calcula dos veces, corrida media ventana)."),
    Parametro("lift_min", 40.0, "coordinacion", PRACTICA,
              "Cuántas veces más que lo esperable por azar tienen que coincidir dos cuentas para ser un par fuerte."),
    Parametro("veces_con_texto", 2, "coordinacion", PRACTICA,
              "Coincidencias mínimas de un par cuando además empujan la misma narrativa y el mismo bando."),
    Parametro("veces_sin_texto", 3, "coordinacion", PRACTICA,
              "Coincidencias mínimas de un par cuando solo se mira publicación y tiempo."),
    Parametro("min_pubs_compartidas", 1, "coordinacion", CRITERIO,
              "Publicaciones distintas que tiene que compartir un par fuerte. Con 1 no filtra nada (valor actual); con 2 "
              "descarta pares que solo coinciden dentro de una misma publicación viral."),
    Parametro("k_truss", 4, "coordinacion", PRACTICA,
              "Densidad de la malla: cada par fuerte tiene que compartir al menos k-2 cuentas en común con otros pares fuertes."),
    Parametro("min_grupo", 5, "coordinacion", CRITERIO, "Cuentas mínimas para que una malla cuente como operación."),
    Parametro("ampliar_min_celdas", 2, "coordinacion", CRITERIO,
              "Segunda pasada: una cuenta entra a un grupo si aparece en al menos estas celdas dominadas por el grupo."),
    Parametro("ampliar_min_miembros", 3, "coordinacion", CRITERIO,
              "Segunda pasada: una celda está dominada por un grupo si tiene al menos estos miembros..."),
    Parametro("ampliar_min_fraccion", 1 / 3, "coordinacion", PRACTICA, "...y además son al menos esta fracción de la celda."),
    Parametro("ampliar_rondas", 3, "coordinacion", CRITERIO, "Cuántas veces se repite la segunda pasada.", False),
    Parametro("camada_max_rareza", 0.02, "coordinacion", PRACTICA,
              "La franja de fechas de creación de un grupo cuenta como indicio solo si menos de esta fracción de todas "
              "las cuentas del set fue creada en esa franja. Con ese indicio alcanza una sola celda dominada."),
    Parametro("camada_min_validos", 5, "coordinacion", CRITERIO,
              "Cuentas con fecha de creación válida que necesita un grupo para calcular su franja.", False),
    Parametro("camada_franja", "percentiles 10 a 90 del grupo, con un margen igual a su ancho (mínimo 1 día)", "coordinacion",
              CRITERIO, "Cómo se arma la franja de fechas de creación de un grupo.", False),
    Parametro("max_aristas", 200000, "coordinacion", TECNICO,
              "Resguardo: si hubiera más pares fuertes que esto, se conservan solo los de mayor lift.", False),
    Parametro("bloque", 4000, "coordinacion", TECNICO, "Cuentas por bloque al cruzar pares (acota la memoria).", False),
    # --- Ingesta y salida ----------------------------------------------------------------------------------
    Parametro("memoria_duckdb", "2GB", "ingesta", TECNICO, "Límite de memoria de DuckDB; si hace falta más, usa disco.", False),
    Parametro("hilos_duckdb", 4, "ingesta", TECNICO, "Hilos de CPU que usa DuckDB.", False),
    Parametro("zona_por_defecto", "-03:00", "ingesta", GENERAL,
              "Zona horaria si ninguna fecha del set trae zona (si la traen, se usa la más frecuente).", False),
    Parametro("frases_clave", 6, "salida", CRITERIO, "Cantidad de términos en frases_clave de cada narrativa.", False),
    Parametro("semilla", 0, "todas", TECNICO, "Semilla de azar (solo la usa Louvain). Se cambia con --semilla.", False),
]

POR_DEFECTO = {p.nombre: p.valor for p in PARAMETROS}
AJUSTABLES = {p.nombre: p for p in PARAMETROS if p.ajustable}


def resolver(cambios: dict = None) -> dict:
    """Valores vigentes: los de por defecto con los `cambios` aplicados (solo parámetros ajustables)."""
    valores = {n: p.valor for n, p in AJUSTABLES.items()}
    for nombre, valor in (cambios or {}).items():
        if nombre not in AJUSTABLES:
            raise ValueError(f"parámetro desconocido o no ajustable: {nombre}")
        valores[nombre] = type(AJUSTABLES[nombre].valor)(valor)
    return valores


def de_etapa(valores: dict, etapa: str) -> dict:
    """Los parámetros ajustables de una etapa, listos para pasar a su función."""
    return {n: valores[n] for n, p in AJUSTABLES.items() if p.etapa == etapa}


def interpretar(texto: str) -> tuple:
    """'nombre=valor' -> (nombre, valor con el tipo del parámetro)."""
    nombre, _, valor = texto.partition("=")
    nombre = nombre.strip()
    if nombre not in AJUSTABLES or not valor.strip():
        raise ValueError(f"se esperaba nombre=valor con un parámetro ajustable, y llegó '{texto}'")
    return nombre, type(AJUSTABLES[nombre].valor)(float(valor))


def tabla_markdown() -> str:
    filas = ["| Parámetro | Valor | Etapa | Qué hace | De dónde sale |", "|---|---|---|---|---|"]
    for p in PARAMETROS:
        valor = f"{p.valor:.3g}" if isinstance(p.valor, float) else str(p.valor)
        filas.append(f"| `{p.nombre}` | {valor} | {p.etapa} | {p.que_hace} | {p.origen} |")
    return "\n".join(filas)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(tabla_markdown())
