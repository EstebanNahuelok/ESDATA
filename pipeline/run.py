"""Único comando del pipeline, de punta a punta:

    python -m pipeline.run --datos datos/practica --entrega salida/practica
    python -m pipeline.run --datos datos/final --entrega entrega

Lee los CSV de --datos, los guarda en una base DuckDB local (--base) y escribe en --entrega
comentarios.csv, narrativas.csv, cuentas.csv y costo.json. No usa IA ni servicios externos.
"""
import argparse
import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from .coordinacion import detectar_coordinacion
from .ingesta import ingerir
from .narrativas import detectar_narrativas
from .postura import calcular_bandos, orientar, postura_por_comentario
from .salida import describir_narrativas, escribir_costo, escribir_entrega

try:
    import psutil
except ImportError:  # la medición de memoria es opcional
    psutil = None


def _memoria_mb():
    if psutil is None:
        return None, None
    info = psutil.Process().memory_info()
    pico = getattr(info, "peak_wset", None)
    if pico is None:
        try:
            import resource
            pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
        except ImportError:
            pico = info.rss
    return round(info.rss / 2**20), round(pico / 2**20)


class Reloj:
    """Mide segundos y memoria de cada etapa."""

    def __init__(self):
        self.etapas = {}
        self.inicio = time.perf_counter()

    def etapa(self, nombre, funcion, *args, **kwargs):
        t0 = time.perf_counter()
        resultado = funcion(*args, **kwargs)
        memoria, pico = _memoria_mb()
        self.etapas[nombre] = {"segundos": round(time.perf_counter() - t0, 2), "memoria_mb": memoria, "pico_mb": pico}
        print(f"[{nombre}] {self.etapas[nombre]['segundos']} s, memoria {memoria} MB (pico {pico} MB)", flush=True)
        return resultado


def _hardware() -> str:
    ram = f"{round(psutil.virtual_memory().total / 2**30)} GB RAM" if psutil else "RAM sin medir"
    return f"{platform.system()} {platform.machine()}, {os.cpu_count()} hilos de CPU, {ram}, no usa GPU"


def correr(datos: Path, entrega: Path, base: Path, semilla: int = 0) -> dict:
    reloj = Reloj()
    np.random.seed(semilla)
    con, resumen = reloj.etapa("ingesta", ingerir, datos, base)
    print(f"  {resumen['comentarios']} comentarios, {resumen['textos_unicos']} textos únicos, "
          f"{resumen['cuentas']} cuentas, {resumen['respuestas']} respuestas", flush=True)

    com = con.execute("SELECT texto_id, padre, pub, cuenta, ts, hora_local, me_gusta FROM comentarios ORDER BY i").fetchnumpy()
    texto_id, padre = com["texto_id"].astype(np.int64), com["padre"].astype(np.int64)
    ts = np.ma.filled(com["ts"].astype(np.float64), np.nan) if np.ma.isMaskedArray(com["ts"]) else com["ts"].astype(np.float64)
    tx = con.execute("SELECT texto, n FROM textos ORDER BY texto_id").fetchnumpy()
    textos, n_textos = list(tx["texto"]), tx["n"].astype(np.int64)
    cuentas = con.execute("SELECT creada_ts, seguidores, siguiendo FROM cuentas ORDER BY cuenta").fetchnumpy()

    nar = reloj.etapa("narrativas", detectar_narrativas, textos, n_textos, texto_id, padre, semilla=semilla)
    print(f"  {json.dumps(nar.info, ensure_ascii=False)}", flush=True)

    avisos = []
    n_cuentas = len(cuentas["seguidores"])
    try:
        grupo_cuenta, info_coord = reloj.etapa(
            "coordinacion", detectar_coordinacion, n_cuentas=n_cuentas, cuenta=com["cuenta"].astype(np.int64),
            pub=com["pub"].astype(np.int64), ts=ts, padre=padre, micro=nar.micro, narrativa=nar.narrativa,
            me_gusta=com["me_gusta"], hora_local=com["hora_local"], creada_ts=cuentas["creada_ts"], semilla=semilla)
    except Exception:  # la entrega sale igual, sin grupos
        traceback.print_exc()
        avisos.append("falló la etapa de coordinación: no se marcaron cuentas")
        grupo_cuenta, info_coord = np.full(n_cuentas, "", dtype=object), {"error": True}
    print(f"  {json.dumps(info_coord, ensure_ascii=False)}", flush=True)

    def etapa_postura():
        bando = calcular_bandos(nar)
        coordinado = (grupo_cuenta != "")[com["cuenta"].astype(np.int64)] if n_cuentas else None
        signo, detalle = orientar(nar, bando, texto_id, padre, coordinado)
        return bando, signo, postura_por_comentario(nar, bando, signo, padre), detalle

    try:
        bando, signo, postura, detalle_postura = reloj.etapa("postura", etapa_postura)
    except Exception:
        traceback.print_exc()
        avisos.append("falló la etapa de postura: se asignó 'apoya' a todo")
        k, n_com = len(nar.tipo), int(nar.comunidad.max()) + 1 if len(nar.comunidad) else 0
        bando, signo, postura, detalle_postura = np.ones(k), np.ones(n_com), (nar.narrativa >= 0).astype(float), {}

    etiquetas, filas = reloj.etapa("origen_y_titulos", describir_narrativas, nar, bando, signo, textos, n_textos,
                                   ts, resumen["zona_seg"])
    for f in filas:
        d = detalle_postura.get(int(f["narrativa"][1:]) - 1, {})
        print(f"  {f['narrativa']} {f['comentarios']:>6} {f['fecha_origen']}  {f['titulo'][:70]}", flush=True)
    reloj.etapa("escritura", escribir_entrega, con, entrega, etiquetas, nar.narrativa, postura, filas, grupo_cuenta)
    con.close()

    segundos = round(time.perf_counter() - reloj.inicio, 1)
    _, pico = _memoria_mb()
    costo = {
        "comentarios_procesados": int(resumen["comentarios"]),
        "segundos": segundos,
        "tokens_ia": 0,
        "usd_ia": 0.0,
        "usd_por_mil_comentarios": 0.0,
        "hardware": _hardware(),
        "almacenamiento": f"DuckDB local, un solo archivo ({round(Path(base).stat().st_size / 2**20, 1)} MB)",
        "notas": "Sin IA generativa ni servicios externos: TF-IDF + agrupamiento por lotes + grafos, todo en CPU. "
                 + " ".join(avisos),
        "memoria_pico_mb": pico,
        "etapas": reloj.etapas,
    }
    escribir_costo(entrega, costo)
    print(f"Listo en {segundos} s. Entrega en {entrega}/", flush=True)
    return costo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True, help="Carpeta con comentarios/cuentas/publicaciones/fuentes (.csv o .csv.gz)")
    ap.add_argument("--entrega", type=Path, required=True, help="Carpeta donde se escriben los 4 archivos")
    ap.add_argument("--base", type=Path, default=None, help="Archivo DuckDB (por defecto almacen/<nombre de --datos>.duckdb)")
    ap.add_argument("--semilla", type=int, default=0)
    args = ap.parse_args(argv)
    base = args.base or Path("almacen") / f"{args.datos.resolve().name}.duckdb"
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    correr(args.datos, args.entrega, base, args.semilla)


if __name__ == "__main__":
    main()
