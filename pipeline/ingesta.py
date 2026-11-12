"""Etapa 1: ingesta de los CSV(.gz) a una base DuckDB local.

Se lee todo como texto (los datos pueden venir sucios), se limpia con SQL y quedan
tablas tipadas con índices enteros, que es lo que usa el resto del pipeline:

    comentarios(i, comentario_id, pub, cuenta, ts, hora_local, texto_id, padre, me_gusta)
    textos(texto_id, texto, n)            -- textos únicos: se procesan una sola vez
    cuentas(cuenta, cuenta_id, creada_ts, seguidores, siguiendo)
    publicaciones(pub, publicacion_id, fuente_id, ts, titular)

`ts` es el instante en segundos UTC; `hora_local` es la hora de reloj tal como viene escrita.
"""
import gzip
import shutil
from pathlib import Path

import duckdb

TABLAS = {
    "comentarios": ["comentario_id", "publicacion_id", "cuenta_id", "fecha", "texto", "respuesta_a", "me_gusta"],
    "cuentas": ["cuenta_id", "usuario", "fecha_creacion", "seguidores", "siguiendo"],
    "publicaciones": ["publicacion_id", "fuente_id", "fecha", "titular"],
    "fuentes": ["fuente_id", "nombre", "tipo"],
}
ZONA_POR_DEFECTO = "-03:00"


def _buscar(datos: Path, nombre: str):
    for sufijo in (".csv.gz", ".csv"):
        ruta = datos / f"{nombre}{sufijo}"
        if ruta.exists():
            return ruta
    return None


def _asegurar_utf8(ruta: Path, carpeta: Path):
    """Si el archivo no está en UTF-8, deja una copia convertida desde Windows-1252. Devuelve (ruta a leer, convertido)."""
    abrir = gzip.open if ruta.suffix == ".gz" else open
    try:
        with abrir(ruta, "rt", encoding="utf-8", newline="") as f:
            while f.read(1 << 20):
                pass
        return ruta, False
    except UnicodeDecodeError:
        destino = carpeta / f"_utf8_{ruta.name[:-3] if ruta.suffix == '.gz' else ruta.name}"
        with abrir(ruta, "rt", encoding="cp1252", errors="replace", newline="") as f:
            with open(destino, "w", encoding="utf-8", newline="") as g:
                shutil.copyfileobj(f, g)
        return destino, True


def _cargar_crudo(con, datos: Path, nombre: str, columnas: list, obligatoria: bool, carpeta_tmp: Path, avisos: list,
                  archivos: list):
    """Carga un CSV como texto en `crudo_<nombre>`; las columnas que falten quedan en NULL."""
    ruta = _buscar(datos, nombre)
    if ruta is None:
        if obligatoria:
            raise FileNotFoundError(f"Falta {nombre}.csv(.gz) en {datos}")
        avisos.append(f"no vino {nombre}.csv: se sigue sin ese archivo")
        con.execute(f"CREATE OR REPLACE TABLE crudo_{nombre} AS SELECT "
                    + ", ".join(f"NULL::VARCHAR AS {c}" for c in columnas) + " WHERE false")
        return 0
    archivos.append(ruta)
    ruta, convertido = _asegurar_utf8(ruta, carpeta_tmp)
    if convertido:
        avisos.append(f"{nombre}.csv no estaba en UTF-8: se leyó como Windows-1252")
    ruta_sql = str(ruta).replace("'", "''")
    con.execute(f"""CREATE OR REPLACE TEMP VIEW _lectura AS SELECT * FROM read_csv('{ruta_sql}', all_varchar=true,
                    header=true, ignore_errors=true, null_padding=true, strict_mode=false)""")
    presentes = {r[0] for r in con.execute("DESCRIBE _lectura").fetchall()}
    faltan = [c for c in columnas if c not in presentes]
    if faltan:
        avisos.append(f"{nombre}.csv vino sin las columnas {', '.join(faltan)}")
    seleccion = ", ".join(f"trim({c}) AS {c}" if c in presentes else f"NULL::VARCHAR AS {c}" for c in columnas)
    con.execute(f"CREATE OR REPLACE TABLE crudo_{nombre} AS SELECT {seleccion} FROM _lectura")
    con.execute("DROP VIEW _lectura")
    if convertido:
        ruta.unlink()
    return con.execute(f"SELECT count(*) FROM crudo_{nombre}").fetchone()[0]


def _sql_ts(col: str, zona_seg: int) -> str:
    """Segundos UTC a partir de un texto ISO con zona (o sin zona: se asume la zona dominante)."""
    local = f"try_cast(substr(replace({col}, 'T', ' '), 1, 19) AS TIMESTAMP)"
    zona = f"regexp_extract({col}, '([+-])([0-9]{{2}}):?([0-9]{{2}})$', ['s', 'h', 'm'])"
    desfase = (f"CASE WHEN {col} LIKE '%Z' THEN 0 WHEN ({zona}).h = '' THEN {zona_seg} ELSE "
               f"(CASE WHEN ({zona}).s = '-' THEN -1 ELSE 1 END) * (({zona}).h::INT * 3600 + ({zona}).m::INT * 60) END")
    return f"CAST(epoch({local}) - ({desfase}) AS BIGINT)"


def ingerir(datos: Path, base: Path, memoria: str = "2GB", hilos: int = 4) -> tuple:
    """Crea (o pisa) la base DuckDB en `base` con los datos limpios. Devuelve (conexión, resumen)."""
    datos, base = Path(datos), Path(base)
    if not datos.is_dir():
        raise FileNotFoundError(f"No existe la carpeta de datos: {datos}")
    base.parent.mkdir(parents=True, exist_ok=True)
    for viejo in (base, base.with_suffix(base.suffix + ".wal")):
        if viejo.exists():
            viejo.unlink()
    con = duckdb.connect(str(base))
    con.execute(f"SET memory_limit='{memoria}'")
    con.execute(f"SET threads={hilos}")
    con.execute("SET enable_progress_bar=false")
    avisos, archivos = [], []
    crudos = {n: _cargar_crudo(con, datos, n, cols, n == "comentarios", base.parent, avisos, archivos)
              for n, cols in TABLAS.items()}

    # Zona horaria dominante del set (para escribir fecha_origen y para fechas que vengan sin zona).
    fila = con.execute("""SELECT regexp_extract(fecha, '([+-][0-9]{2}:[0-9]{2})$', 1) z, count(*) n
                          FROM crudo_comentarios GROUP BY 1 HAVING z <> '' ORDER BY n DESC, z LIMIT 1""").fetchone()
    zona = fila[0] if fila and fila[0] else ZONA_POR_DEFECTO
    zona_seg = (-1 if zona[0] == "-" else 1) * (int(zona[1:3]) * 3600 + int(zona[4:6]) * 60)

    con.execute("""CREATE OR REPLACE TABLE _com AS
        SELECT * EXCLUDE (rn) FROM (
            SELECT *, row_number() OVER (PARTITION BY comentario_id ORDER BY fecha, texto) rn
            FROM crudo_comentarios WHERE comentario_id IS NOT NULL AND comentario_id <> '')
        WHERE rn = 1""")
    con.execute("""CREATE OR REPLACE TABLE textos AS
        SELECT (row_number() OVER (ORDER BY texto) - 1)::INT AS texto_id, texto, n
        FROM (SELECT coalesce(texto, '') AS texto, count(*) n FROM _com GROUP BY 1)""")
    con.execute("""CREATE OR REPLACE TABLE publicaciones AS
        SELECT (row_number() OVER (ORDER BY publicacion_id) - 1)::INT AS pub, publicacion_id,
               any_value(fuente_id) fuente_id, any_value(fecha) fecha, any_value(titular) titular
        FROM (SELECT publicacion_id, fuente_id, fecha, titular FROM crudo_publicaciones
              UNION ALL SELECT coalesce(publicacion_id, ''), NULL, NULL, NULL FROM _com)
        WHERE publicacion_id IS NOT NULL GROUP BY publicacion_id""")
    con.execute(f"ALTER TABLE publicaciones ADD COLUMN ts BIGINT; UPDATE publicaciones SET ts = {_sql_ts('fecha', zona_seg)}")
    con.execute("""CREATE OR REPLACE TABLE cuentas AS
        SELECT (row_number() OVER (ORDER BY cuenta_id) - 1)::INT AS cuenta, cuenta_id,
               any_value(usuario) usuario, any_value(fecha_creacion) fecha_creacion,
               coalesce(try_cast(any_value(seguidores) AS BIGINT), 0) seguidores,
               coalesce(try_cast(any_value(siguiendo) AS BIGINT), 0) siguiendo
        FROM (SELECT cuenta_id, usuario, fecha_creacion, seguidores, siguiendo FROM crudo_cuentas
              UNION ALL SELECT coalesce(cuenta_id, ''), NULL, NULL, NULL, NULL FROM _com)
        WHERE cuenta_id IS NOT NULL GROUP BY cuenta_id""")
    con.execute(f"ALTER TABLE cuentas ADD COLUMN creada_ts BIGINT; UPDATE cuentas SET creada_ts = {_sql_ts('fecha_creacion', zona_seg)}")
    con.execute(f"""CREATE OR REPLACE TABLE _com2 AS
        SELECT c.comentario_id, p.pub, a.cuenta, {_sql_ts('c.fecha', zona_seg)} AS ts, t.texto_id,
               nullif(c.respuesta_a, '') AS respuesta_a, greatest(coalesce(try_cast(c.me_gusta AS BIGINT), 0), 0) AS me_gusta
        FROM _com c
        JOIN publicaciones p ON p.publicacion_id = coalesce(c.publicacion_id, '')
        JOIN cuentas a ON a.cuenta_id = coalesce(c.cuenta_id, '')
        JOIN textos t ON t.texto = coalesce(c.texto, '')""")
    # Índice entero ordenado por tiempo; el padre solo vale si existe y no es el mismo comentario.
    con.execute("""CREATE OR REPLACE TABLE _com3 AS
        SELECT (row_number() OVER (ORDER BY ts NULLS LAST, comentario_id) - 1)::INT AS i, * FROM _com2""")
    con.execute(f"""CREATE OR REPLACE TABLE comentarios AS
        SELECT h.i, h.comentario_id, h.pub, h.cuenta, h.ts,
               CAST(((h.ts + {zona_seg}) % 86400) / 3600.0 AS FLOAT) AS hora_local,
               h.texto_id, coalesce(p.i, -1)::INT AS padre, h.me_gusta
        FROM _com3 h LEFT JOIN _com3 p ON p.comentario_id = h.respuesta_a AND p.i <> h.i
        ORDER BY h.i""")
    con.execute("CREATE OR REPLACE TABLE fuentes AS SELECT * FROM crudo_fuentes")
    for t in ("_com", "_com2", "_com3", *(f"crudo_{n}" for n in TABLAS)):
        con.execute(f"DROP TABLE {t}")

    n_com, n_sin_fecha, n_resp = con.execute(
        "SELECT count(*), count(*) FILTER (ts IS NULL), count(*) FILTER (padre >= 0) FROM comentarios").fetchone()
    resumen = {
        "avisos": avisos,
        "archivos": [str(a) for a in archivos],
        "zona": zona,
        "zona_seg": zona_seg,
        "filas_crudas": crudos,
        "comentarios": n_com,
        "comentarios_descartados": crudos["comentarios"] - n_com,
        "comentarios_sin_fecha": n_sin_fecha,
        "respuestas": n_resp,
        "textos_unicos": con.execute("SELECT count(*) FROM textos").fetchone()[0],
        "cuentas": con.execute("SELECT count(*) FROM cuentas").fetchone()[0],
        "publicaciones": con.execute("SELECT count(*) FROM publicaciones").fetchone()[0],
    }
    return con, resumen
