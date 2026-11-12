"""Valida que una carpeta de entrega tenga los 4 archivos con el formato exacto del enunciado (DESAFIO.md).

    python -m pipeline.validar --entrega entrega
    python -m pipeline.validar --entrega entrega --datos datos/final     # además cruza contra los datos de entrada

Sale con código 0 si está todo bien y 1 si hay errores. Los avisos no cambian el código de salida.
Solo usa la librería estándar, así que corre en cualquier lado sin instalar nada.
El pipeline lo ejecuta solo al terminar; también sirve para revisar `entrega/` antes del commit final.
"""
import argparse
import csv
import gzip
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ARCHIVOS = ("comentarios.csv", "narrativas.csv", "cuentas.csv", "costo.json")
COLUMNAS = {"comentarios.csv": ["comentario_id", "narrativa", "postura"],
            "narrativas.csv": ["narrativa", "titulo", "frases_clave", "fecha_origen"],
            "cuentas.csv": ["cuenta_id", "grupo"]}
CLAVES_COSTO = {"comentarios_procesados": int, "segundos": (int, float), "tokens_ia": int, "usd_ia": (int, float),
                "usd_por_mil_comentarios": (int, float), "hardware": str, "almacenamiento": str, "notas": str}
SIN_NARRATIVA = {"", "ninguna"}
POSTURAS = {"apoya", "rechaza"}
_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
csv.field_size_limit(10**9)


class EntregaInvalida(RuntimeError):
    """La entrega no cumple el formato del enunciado."""


def _leer_csv(ruta: Path, errores: list):
    """Devuelve (encabezado, filas como dict) o (None, []) si no se puede leer."""
    try:
        abrir = gzip.open if ruta.suffix == ".gz" else open
        with abrir(ruta, "rt", encoding="utf-8", newline="") as f:
            lector = csv.reader(f)
            encabezado = next(lector, None)
            if encabezado is None:
                errores.append(f"{ruta.name}: está vacío (falta el encabezado)")
                return None, []
            ancho = len(encabezado)
            filas = []
            for numero, fila in enumerate(lector, start=2):
                if len(fila) != ancho:
                    errores.append(f"{ruta.name}: la línea {numero} tiene {len(fila)} columnas y deberían ser {ancho}")
                    if len(errores) > 50:
                        break
                    continue
                filas.append(dict(zip(encabezado, fila)))
            return encabezado, filas
    except UnicodeDecodeError:
        errores.append(f"{ruta.name}: no está en UTF-8")
    except (OSError, csv.Error) as e:
        errores.append(f"{ruta.name}: no se pudo leer ({e})")
    return None, []


def _buscar_entrada(datos: Path, nombre: str):
    for sufijo in (".csv.gz", ".csv"):
        if (datos / f"{nombre}{sufijo}").exists():
            return datos / f"{nombre}{sufijo}"
    return None


def _leer_entrada(ruta: Path) -> list:
    """Lee un CSV de entrada con tolerancia (BOM, Windows-1252, separador ; o tabulador). Devuelve filas como dict."""
    abrir = gzip.open if ruta.suffix == ".gz" else open
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            with abrir(ruta, "rt", encoding=codificacion, newline="") as f:
                primera = f.readline()
                separador = max(",;\t|", key=primera.count)
                f.seek(0)
                return list(csv.DictReader(f, delimiter=separador))
        except UnicodeDecodeError:
            continue
    return []


def _ids_de_entrada(datos: Path, avisos: list):
    """Ids de comentarios y de cuentas que deberían estar en la entrega, leídos de los datos de entrada."""
    ruta = _buscar_entrada(datos, "comentarios")
    if ruta is None:
        avisos.append(f"no se encontró comentarios.csv(.gz) en {datos}: no se cruza contra la entrada")
        return None, None
    try:
        filas = _leer_entrada(ruta)
        comentarios = {(f.get("comentario_id") or "").strip() for f in filas} - {""}
        cuentas = {(f.get("cuenta_id") or "").strip() for f in filas if (f.get("comentario_id") or "").strip()} - {""}
        ruta = _buscar_entrada(datos, "cuentas")
        if ruta is not None:
            cuentas |= {(f.get("cuenta_id") or "").strip() for f in _leer_entrada(ruta)} - {""}
    except (OSError, csv.Error, EOFError) as e:
        avisos.append(f"no se pudieron leer los datos de entrada ({e}): no se cruza contra la entrada")
        return None, None
    return comentarios, cuentas


def _revisar_ids(nombre: str, columna: str, filas: list, esperados, errores: list):
    ids = [f[columna].strip() for f in filas]
    vacios = sum(1 for i in ids if not i)
    if vacios:
        errores.append(f"{nombre}: {vacios} filas con {columna} vacío")
    repetidos = [i for i, n in Counter(ids).items() if n > 1 and i]
    if repetidos:
        errores.append(f"{nombre}: {len(repetidos)} valores de {columna} repetidos (ej. {repetidos[0]})")
    if esperados is not None:
        presentes = set(ids)
        faltan, sobran = esperados - presentes, presentes - esperados - {""}
        if faltan:
            errores.append(f"{nombre}: faltan {len(faltan)} {columna} que están en los datos (ej. {sorted(faltan)[0]})")
        if sobran:
            errores.append(f"{nombre}: hay {len(sobran)} {columna} que no están en los datos (ej. {sorted(sobran)[0]})")
    return ids


def validar_entrega(entrega, datos=None) -> tuple:
    """Devuelve (errores, avisos, resumen). Sin errores, la entrega cumple el formato del enunciado."""
    entrega = Path(entrega)
    errores, avisos, resumen = [], [], {}
    if not entrega.is_dir():
        return [f"no existe la carpeta {entrega}"], avisos, resumen
    for archivo in ARCHIVOS:
        if not (entrega / archivo).is_file():
            errores.append(f"falta el archivo {archivo}")
    extras = sorted(p.name for p in entrega.iterdir() if p.name not in ARCHIVOS)
    if extras:
        avisos.append(f"hay archivos de más en la carpeta (el enunciado pide solo 4): {', '.join(extras)}")
    ids_com, ids_cta = _ids_de_entrada(Path(datos), avisos) if datos is not None else (None, None)

    tablas = {}
    for archivo, columnas in COLUMNAS.items():
        if not (entrega / archivo).is_file():
            continue
        encabezado, filas = _leer_csv(entrega / archivo, errores)
        if encabezado is None:
            continue
        if encabezado != columnas:
            errores.append(f"{archivo}: el encabezado debe ser exactamente {','.join(columnas)} y es {','.join(encabezado)}")
            if not set(columnas) <= set(encabezado):
                continue
        tablas[archivo] = filas

    usadas = Counter()
    if "comentarios.csv" in tablas:
        filas = tablas["comentarios.csv"]
        _revisar_ids("comentarios.csv", "comentario_id", filas, ids_com, errores)
        mal_postura = con_postura_de_mas = 0
        for f in filas:
            narrativa, postura = f["narrativa"].strip(), f["postura"].strip()
            if narrativa.lower() in SIN_NARRATIVA:
                con_postura_de_mas += bool(postura)
            else:
                usadas[narrativa] += 1
                mal_postura += postura not in POSTURAS
        if mal_postura:
            errores.append(f"comentarios.csv: {mal_postura} comentarios con narrativa y una postura que no es 'apoya' ni 'rechaza'")
        if con_postura_de_mas:
            avisos.append(f"comentarios.csv: {con_postura_de_mas} comentarios de ruido traen postura (se ignora)")
        if filas and not usadas:
            avisos.append("comentarios.csv: ningún comentario tiene narrativa")
        resumen.update({"comentarios": len(filas), "comentarios_con_narrativa": sum(usadas.values()),
                        "narrativas_usadas": len(usadas), "tam_narrativas": sorted(usadas.values(), reverse=True)})

    if "narrativas.csv" in tablas:
        filas = tablas["narrativas.csv"]
        etiquetas = _revisar_ids("narrativas.csv", "narrativa", filas, None, errores)
        if any(e.lower() == "ninguna" for e in etiquetas):
            errores.append("narrativas.csv: 'ninguna' no puede ser una narrativa")
        for f in filas:
            etiqueta, fecha = f["narrativa"].strip(), f["fecha_origen"].strip()
            if not f["titulo"].strip():
                errores.append(f"narrativas.csv: la narrativa {etiqueta} no tiene título")
            frases = f["frases_clave"].split("|")
            if not f["frases_clave"].strip() or any(not x.strip() for x in frases):
                errores.append(f"narrativas.csv: frases_clave de {etiqueta} debe ser una lista de términos separados por |")
            try:
                if not _RE_FECHA.match(fecha) or datetime.fromisoformat(fecha.replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError
            except ValueError:
                errores.append(f"narrativas.csv: fecha_origen de {etiqueta} debe ser ISO con zona horaria, "
                               f"como 2026-09-07T08:15:00-03:00, y es '{fecha}'")
        sin_fila = sorted(set(usadas) - set(etiquetas))
        if sin_fila:
            errores.append(f"narrativas.csv: faltan {len(sin_fila)} narrativas usadas en comentarios.csv (ej. {sin_fila[0]})")
        sin_uso = sorted(set(etiquetas) - set(usadas) - {""})
        if sin_uso and "comentarios.csv" in tablas:
            avisos.append(f"narrativas.csv: {len(sin_uso)} narrativas sin ningún comentario (ej. {sin_uso[0]})")
        resumen["narrativas"] = len(filas)

    if "cuentas.csv" in tablas:
        filas = tablas["cuentas.csv"]
        _revisar_ids("cuentas.csv", "cuenta_id", filas, ids_cta, errores)
        grupos = Counter(f["grupo"].strip() for f in filas if f["grupo"].strip())
        de_una = sorted(g for g, n in grupos.items() if n == 1)
        if de_una:
            avisos.append(f"cuentas.csv: {len(de_una)} grupos con una sola cuenta (ej. {de_una[0]})")
        if filas and not grupos:
            avisos.append("cuentas.csv: ninguna cuenta quedó marcada como coordinada")
        resumen.update({"cuentas": len(filas), "cuentas_coordinadas": sum(grupos.values()), "grupos": len(grupos),
                        "tam_grupos": sorted(grupos.values(), reverse=True)})

    ruta_costo = entrega / "costo.json"
    if ruta_costo.is_file():
        try:
            costo = json.loads(ruta_costo.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            costo = None
            errores.append(f"costo.json: no es un JSON válido en UTF-8 ({e})")
        if costo is not None and not isinstance(costo, dict):
            errores.append("costo.json: debe ser un objeto con claves")
        elif costo is not None:
            for clave, tipo in CLAVES_COSTO.items():
                valor = costo.get(clave)
                if clave not in costo:
                    errores.append(f"costo.json: falta la clave {clave}")
                elif isinstance(valor, bool) or not isinstance(valor, tipo):
                    errores.append(f"costo.json: {clave} debe ser {'texto' if tipo is str else 'un número'}"
                                   f"{' entero' if tipo is int else ''} y es {valor!r}")
                elif tipo is not str and valor < 0:
                    errores.append(f"costo.json: {clave} no puede ser negativo")
                elif tipo is str and clave != "notas" and not valor.strip():
                    errores.append(f"costo.json: {clave} está vacío")
            procesados = costo.get("comentarios_procesados")
            if isinstance(procesados, int) and "comentarios" in resumen and procesados != resumen["comentarios"]:
                errores.append(f"costo.json: comentarios_procesados es {procesados} pero comentarios.csv tiene {resumen['comentarios']} filas")
            usd, por_mil = costo.get("usd_ia"), costo.get("usd_por_mil_comentarios")
            if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (usd, por_mil, procesados)) and procesados:
                if abs(por_mil - usd / (procesados / 1000)) > max(1e-6, 0.02 * por_mil):
                    avisos.append(f"costo.json: usd_por_mil_comentarios ({por_mil}) no coincide con usd_ia / miles de comentarios "
                                  f"({usd / (procesados / 1000):.6f})")
            resumen["segundos"] = costo.get("segundos")
    return errores, avisos, resumen


def controles_de_cordura(resumen: dict) -> tuple:
    """Números que conviene mirar antes de entregar, y alertas si alguno es raro.

    No miden si el resultado es correcto (para eso hace falta la verdad): detectan resultados absurdos, como una
    sola narrativa gigante, cientos de narrativas, casi todo ruido o miles de cuentas marcadas. Los rangos son
    amplios a propósito y no salen del set de práctica. Devuelve (líneas descriptivas, alertas).
    """
    lineas, alertas = [], []
    total, con_narrativa = resumen.get("comentarios", 0), resumen.get("comentarios_con_narrativa", 0)
    tam = resumen.get("tam_narrativas", [])
    if total:
        ruido = 100 * (total - con_narrativa) / total
        lineas.append(f"narrativas: {len(tam)}" + (f" (la mayor tiene el {100 * tam[0] / max(con_narrativa, 1):.0f}% de los "
                      f"comentarios con narrativa; la menor, {tam[-1]} comentarios)" if tam else ""))
        lineas.append(f"ruido: {ruido:.1f}% de los comentarios")
        if len(tam) < 2:
            alertas.append(f"hay {len(tam)} narrativas: se esperan varias")
        elif len(tam) > 60:
            alertas.append(f"hay {len(tam)} narrativas: son demasiadas, probablemente el agrupamiento quedó fragmentado")
        if len(tam) >= 3 and tam[0] > 0.5 * con_narrativa:
            alertas.append(f"una sola narrativa junta el {100 * tam[0] / con_narrativa:.0f}% de los comentarios: puede haber narrativas pegadas")
        chicas = sum(1 for t in tam if t < max(20, 0.001 * total))
        if tam and chicas > len(tam) / 3:
            alertas.append(f"{chicas} de {len(tam)} narrativas son muy chicas (menos del 0,1% de los comentarios)")
        if ruido < 2 or ruido > 60:
            alertas.append(f"el ruido es {ruido:.1f}% de los comentarios: fuera del rango razonable (2% a 60%)")
    cuentas, coordinadas, grupos = resumen.get("cuentas", 0), resumen.get("cuentas_coordinadas", 0), resumen.get("tam_grupos", [])
    if cuentas:
        lineas.append(f"cuentas coordinadas: {coordinadas} de {cuentas} ({100 * coordinadas / cuentas:.2f}%) en {len(grupos)} grupos"
                      + (f", de tamaños {', '.join(map(str, grupos[:12]))}" + ("..." if len(grupos) > 12 else "") if grupos else ""))
        if not grupos:
            alertas.append("no se marcó ninguna cuenta coordinada: o no hay operaciones o no llegan a repetirse lo suficiente")
        if coordinadas > 0.05 * cuentas:
            alertas.append(f"se marcó el {100 * coordinadas / cuentas:.1f}% de las cuentas como coordinadas: es mucho, revisar falsos positivos")
        if grupos and grupos[0] > max(0.03 * cuentas, 200):
            alertas.append(f"el grupo más grande tiene {grupos[0]} cuentas: puede ser gente genuina pegada por un momento viral")
        if len(grupos) > 30:
            alertas.append(f"hay {len(grupos)} grupos coordinados: son muchos, revisar")
    return lineas, alertas


def informe(entrega, errores: list, avisos: list, resumen: dict) -> str:
    lineas = [f"Validación de {entrega}: " + ("OK, cumple el formato del enunciado" if not errores else f"{len(errores)} ERRORES")]
    lineas += [f"  ERROR: {e}" for e in errores] + [f"  aviso: {a}" for a in avisos]
    descripcion, alertas = controles_de_cordura(resumen)
    if descripcion:
        lineas.append("Controles de cordura: " + ("sin alertas" if not alertas else f"{len(alertas)} ALERTAS, revisar antes de entregar"))
        lineas += [f"  {d}" for d in descripcion] + [f"  ALERTA: {a}" for a in alertas]
    return "\n".join(lineas)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entrega", type=Path, required=True, help="Carpeta con comentarios.csv, narrativas.csv, cuentas.csv y costo.json")
    ap.add_argument("--datos", type=Path, default=None, help="Carpeta de datos de entrada, para cruzar ids (opcional)")
    args = ap.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    errores, avisos, resumen = validar_entrega(args.entrega, args.datos)
    print(informe(args.entrega, errores, avisos, resumen))
    sys.exit(1 if errores else 0)


if __name__ == "__main__":
    main()
