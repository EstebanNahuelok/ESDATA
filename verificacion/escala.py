"""Tabla de escala: el pipeline de punta a punta con 10.000, 50.000, 100.000 y 200.000 comentarios reales del set de práctica.

    python verificacion/escala.py                     # arma las muestras, corre 3 veces cada tamaño y puntúa
    python verificacion/escala.py --repeticiones 1    # una sola corrida por tamaño
    python verificacion/escala.py --tabla             # imprime la tabla con lo ya corrido

Cada muestra son publicaciones completas elegidas al azar (semilla fija) hasta juntar la cantidad pedida, con todos
sus hilos de respuestas; las muestras están anidadas (la de 50.000 contiene a la de 10.000) y 200.000 es el set
entero. Cada corrida es el comando normal en otro proceso, con la validación y el reporte incluidos. El tiempo y la
memoria salen del costo.json de cada corrida; se informa la mediana de las repeticiones y el rango.
"""
import argparse
import json
import statistics
import subprocess
import sys
import time

import numpy as np
import psutil

from comun import PRACTICA, RAIZ, SALIDA, armar_variante, dec, leer_practica, puntuar

REGISTRO = SALIDA / "escala.json"
TAMANOS = (10000, 50000, 100000)


def muestras(t: dict) -> dict:
    c = t["comentarios"]
    por_pub = c.groupby("publicacion_id").size()
    orden = np.random.default_rng(0).permutation(len(por_pub))
    acumulado = np.cumsum(por_pub.to_numpy()[orden])
    armadas = {}
    for n in TAMANOS:
        hasta = int(np.searchsorted(acumulado, n)) + 1
        armadas[f"escala_{n // 1000}k"] = c[c.publicacion_id.isin(por_pub.index[orden[:hasta]])]
    armadas["escala_completo"] = c
    return armadas


def correr_una(datos, nombre: str) -> dict:
    """El comando normal (con validación y reporte) en otro proceso. Devuelve costo.json más el tiempo de reloj."""
    carpeta = SALIDA / nombre
    orden = [sys.executable, "-m", "pipeline.run", "--datos", str(datos), "--entrega", str(carpeta / "entrega"),
             "--base", str(carpeta / "base.duckdb"), "--reporte", str(carpeta / "reporte.html")]
    inicio = time.perf_counter()
    proceso = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    reloj = time.perf_counter() - inicio
    (carpeta / "salida.txt").write_text(proceso.stdout + "\n" + proceso.stderr, encoding="utf-8")
    if proceso.returncode != 0:
        raise RuntimeError(f"el pipeline falló en {nombre}: {(proceso.stderr or proceso.stdout)[-600:]}")
    return {**json.loads((carpeta / "entrega" / "costo.json").read_text(encoding="utf-8")), "reloj": round(reloj, 1)}


def correr(repeticiones: int):
    t = leer_practica()
    resultados = {}
    for nombre, comentarios in muestras(t).items():
        datos = PRACTICA if nombre == "escala_completo" else armar_variante(nombre, t, comentarios)
        corridas = []
        for _ in range(repeticiones):
            libre = psutil.virtual_memory().available / 2**30
            costo = correr_una(datos, nombre)
            corridas.append({"segundos": costo["segundos"], "reloj": costo["reloj"], "memoria_pico_mb": costo["memoria_pico_mb"],
                             "ram_libre_gb": round(libre, 2), "etapas": {k: v["segundos"] for k, v in costo["etapas"].items()}})
        resultados[nombre] = {"comentarios": len(comentarios), "publicaciones": int(comentarios.publicacion_id.nunique()),
                              "cuentas": int(comentarios.cuenta_id.nunique()), "corridas": corridas,
                              "base_mb": costo["almacenamiento_mb"]["base_duckdb"],
                              "entrada_mb": costo["almacenamiento_mb"]["entrada_csv"],
                              "total": puntuar(datos / "verdad", SALIDA / nombre / "entrega")["total"]}
        REGISTRO.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{nombre:16s} {len(comentarios):7d} comentarios  segundos {[c['segundos'] for c in corridas]}  "
              f"pico {[c['memoria_pico_mb'] for c in corridas]} MB  total {resultados[nombre]['total']}", flush=True)


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def tabla() -> str:
    r = json.loads(REGISTRO.read_text(encoding="utf-8"))
    salida = ["| Comentarios | Publicaciones | Cuentas | Tiempo (mediana; rango) | Comentarios por segundo | Memoria pico | "
              "Etapa más lenta | Base DuckDB | Puntaje /55 |", "|---|---|---|---|---|---|---|---|---|"]
    for f in r.values():
        seg = [c["segundos"] for c in f["corridas"]]
        mediana = statistics.median(seg)
        etapas = {k: statistics.median(c["etapas"][k] for c in f["corridas"]) for k in f["corridas"][0]["etapas"]}
        lenta = max(etapas, key=etapas.get)
        salida.append(
            f"| {miles(f['comentarios'])} | {miles(f['publicaciones'])} | {miles(f['cuentas'])} | "
            f"{dec(mediana, 1)} s ({dec(min(seg), 1)} a {dec(max(seg), 1)}) | {miles(f['comentarios'] / mediana)} | "
            f"{max(c['memoria_pico_mb'] for c in f['corridas'])} MB | {lenta} ({dec(etapas[lenta], 1)} s) | "
            f"{dec(f['base_mb'], 1)} MB | {dec(f['total'], 2)} |")
    libres = [c["ram_libre_gb"] for f in r.values() for c in f["corridas"]]
    salida.append(f"\nRAM libre al empezar cada corrida: entre {dec(min(libres), 1)} y {dec(max(libres), 1)} GB.")
    return "\n".join(salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--tabla", action="store_true")
    args = ap.parse_args()
    if not args.tabla:
        correr(args.repeticiones)
    print(tabla())
