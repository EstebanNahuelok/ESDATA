"""Único comando del pipeline, de punta a punta:

    python -m pipeline.run --datos datos/practica --entrega salida/practica
    python -m pipeline.run --datos datos/final --entrega entrega

Lee los CSV de --datos, los guarda en una base DuckDB local (--base) y escribe en --entrega
comentarios.csv, narrativas.csv, cuentas.csv y costo.json. Al final valida el formato de la entrega
(pipeline/validar.py) y termina con error si no cumple. No usa IA ni servicios externos.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from .coordinacion import detectar_coordinacion
from .costo import armar_costo, memoria_mb
from .ingesta import ingerir
from .narrativas import detectar_narrativas
from .postura import calcular_bandos, orientar, postura_por_comentario
from .salida import describir_narrativas, escribir_costo, escribir_entrega
from .validar import EntregaInvalida, informe, validar_entrega


class Reloj:
    """Mide segundos y memoria de cada etapa."""

    def __init__(self):
        self.etapas = {}
        self.inicio = time.perf_counter()

    def etapa(self, nombre, funcion, *args, **kwargs):
        t0 = time.perf_counter()
        resultado = funcion(*args, **kwargs)
        memoria, pico = memoria_mb()
        self.etapas[nombre] = {"segundos": round(time.perf_counter() - t0, 2), "memoria_mb": memoria, "pico_mb": pico}
        print(f"[{nombre}] {self.etapas[nombre]['segundos']} s, memoria {memoria} MB (pico {pico} MB)", flush=True)
        return resultado


def _a_float(columna) -> np.ndarray:
    """Columna numérica de DuckDB a float, con NaN donde había NULL."""
    if np.ma.isMaskedArray(columna):
        return np.ma.filled(columna.astype(np.float64), np.nan)
    return np.asarray(columna, dtype=np.float64)


def correr(datos: Path, entrega: Path, base: Path, semilla: int = 0, hardware: str = None) -> dict:
    reloj = Reloj()
    np.random.seed(semilla)
    con, resumen = reloj.etapa("ingesta", ingerir, datos, base)
    print(f"  {resumen['comentarios']} comentarios, {resumen['textos_unicos']} textos únicos, "
          f"{resumen['cuentas']} cuentas, {resumen['respuestas']} respuestas", flush=True)

    com = con.execute("SELECT texto_id, padre, pub, cuenta, ts, hora_local, me_gusta FROM comentarios ORDER BY i").fetchnumpy()
    texto_id, padre = com["texto_id"].astype(np.int64), com["padre"].astype(np.int64)
    ts = _a_float(com["ts"])
    tx = con.execute("SELECT texto, n FROM textos ORDER BY texto_id").fetchnumpy()
    textos, n_textos = list(tx["texto"]), tx["n"].astype(np.int64)
    cuentas = con.execute("SELECT creada_ts, seguidores, siguiendo FROM cuentas ORDER BY cuenta").fetchnumpy()

    nar = reloj.etapa("narrativas", detectar_narrativas, textos, n_textos, texto_id, padre, semilla=semilla)
    print(f"  {json.dumps(nar.info, ensure_ascii=False)}", flush=True)

    avisos = list(resumen["avisos"])
    n_cuentas = len(cuentas["seguidores"])
    n_com = int(nar.comunidad.max()) + 1 if len(nar.comunidad) else 0
    cuenta = com["cuenta"].astype(np.int64)

    def etapa_bandos():
        bando = calcular_bandos(nar)
        return bando, postura_por_comentario(nar, bando, np.ones(n_com), padre)

    try:
        bando, bando_com = reloj.etapa("bandos", etapa_bandos)
    except Exception:
        traceback.print_exc()
        avisos.append("falló el armado de bandos: se asignó 'apoya' a todo")
        bando, bando_com = np.ones(len(nar.tipo)), (nar.narrativa >= 0).astype(float)

    try:
        grupo_cuenta, info_coord = reloj.etapa(
            "coordinacion", detectar_coordinacion, n_cuentas=n_cuentas, cuenta=cuenta,
            pub=com["pub"].astype(np.int64), ts=ts, narrativa=nar.narrativa, bando=bando_com,
            creada_ts=_a_float(cuentas["creada_ts"]), usar_mensaje=nar.info["usa_hilos"])
    except Exception:  # la entrega sale igual, sin grupos
        traceback.print_exc()
        avisos.append("falló la etapa de coordinación: no se marcaron cuentas")
        grupo_cuenta, info_coord = np.full(n_cuentas, "", dtype=object), {"error": True}
    print(f"  {json.dumps(info_coord, ensure_ascii=False)}", flush=True)

    def etapa_postura():
        coordinado = (grupo_cuenta != "")[cuenta] if n_cuentas else None
        signo, detalle = orientar(nar, bando, texto_id, padre, coordinado)
        return signo, postura_por_comentario(nar, bando, signo, padre), detalle

    try:
        signo, postura, detalle_postura = reloj.etapa("postura", etapa_postura)
    except Exception:
        traceback.print_exc()
        avisos.append("falló la orientación de la postura: quedó el bando sin orientar")
        signo, postura, detalle_postura = np.ones(n_com), bando_com, {}

    etiquetas, filas = reloj.etapa("origen_y_titulos", describir_narrativas, nar, bando, signo, textos, n_textos,
                                   ts, resumen["zona_seg"])
    for f in filas:
        print(f"  {f['narrativa']} {f['comentarios']:>6} {f['fecha_origen']}  {f['titulo'][:70]}", flush=True)
    sin_fecha = sum(f["sin_fecha"] for f in filas)
    if sin_fecha:
        avisos.append(f"{sin_fecha} narrativas sin ninguna fecha válida: su fecha_origen es la primera fecha del set")
    if resumen["comentarios_sin_fecha"]:
        avisos.append(f"{resumen['comentarios_sin_fecha']} comentarios sin fecha válida (no se usan para origen ni coordinación)")
    if resumen["comentarios_descartados"]:
        avisos.append(f"{resumen['comentarios_descartados']} filas de comentarios descartadas (id vacío o repetido)")
    reloj.etapa("escritura", escribir_entrega, con, entrega, etiquetas, nar.narrativa, postura, filas, grupo_cuenta)
    con.close()

    def guardar_costo():
        costo = armar_costo(resumen["comentarios"], time.perf_counter() - reloj.inicio, reloj.etapas, resumen["archivos"],
                            base, entrega, avisos, semilla, hardware)
        escribir_costo(entrega, costo)
        return costo

    # Control final: los 4 archivos con el formato exacto del enunciado y los mismos ids que la entrada.
    guardar_costo()
    errores, avisos_formato, resumen_formato = reloj.etapa("validacion", validar_entrega, entrega, datos)
    print(informe(entrega, errores, avisos_formato, resumen_formato), flush=True)
    costo = guardar_costo()  # se reescribe con el tiempo total, validación incluida
    print(f"Listo en {costo['segundos']} s, memoria pico {costo['memoria_pico_mb']} MB. Entrega en {entrega}/", flush=True)
    if errores:
        raise EntregaInvalida(f"la entrega en {entrega} no cumple el formato: {errores[0]}")
    return costo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True, help="Carpeta con comentarios/cuentas/publicaciones/fuentes (.csv o .csv.gz)")
    ap.add_argument("--entrega", type=Path, required=True, help="Carpeta donde se escriben los 4 archivos")
    ap.add_argument("--base", type=Path, default=None, help="Archivo DuckDB (por defecto almacen/<nombre de --datos>.duckdb)")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--hardware", default=None, help="Texto para costo.json si no se quiere el equipo detectado solo")
    args = ap.parse_args(argv)
    base = args.base or Path("almacen") / f"{args.datos.resolve().name}.duckdb"
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    try:
        correr(args.datos, args.entrega, base, args.semilla, args.hardware)
    except FileNotFoundError as e:
        sys.exit(f"ERROR: {e}")
    except EntregaInvalida as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
