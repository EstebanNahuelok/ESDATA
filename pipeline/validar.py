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


def _ids_de_entrada(datos: Path, avisos: list):
    """Ids de comentarios y de cuentas que deberían estar en la entrega, leídos de los datos de entrada."""
    comentarios, cuentas = None, None
    ruta = _buscar_entrada(datos, "comentarios")
    if ruta is None:
        avisos.append(f"no se encontró comentarios.csv(.gz) en {datos}: no se cruza contra la entrada")
        return None, None
    ignorar = []
    _, filas = _leer_csv(ruta, ignorar)
    comentarios = {(f.get("comentario_id") or "").strip() for f in filas} - {""}
    cuentas = {(f.get("cuenta_id") or "").strip() for f in filas if (f.get("comentario_id") or "").strip()} - {""}
    ruta = _buscar_entrada(datos, "cuentas")
    if ruta is not None:
        _, filas = _leer_csv(ruta, ignorar)
        cuentas |= {(f.get("cuenta_id") or "").strip() for f in filas} - {""}
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
                        "narrativas_usadas": len(usadas)})

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
        resumen.update({"cuentas": len(filas), "cuentas_coordinadas": sum(grupos.values()), "grupos": len(grupos)})

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


def informe(entrega, errores: list, avisos: list, resumen: dict) -> str:
    lineas = [f"Validación de {entrega}: " + ("OK, cumple el formato del enunciado" if not errores else f"{len(errores)} ERRORES")]
    if resumen:
        lineas.append("  " + ", ".join(f"{k}={v}" for k, v in resumen.items()))
    lineas += [f"  ERROR: {e}" for e in errores] + [f"  aviso: {a}" for a in avisos]
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
