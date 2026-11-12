"""Análisis de sensibilidad: mueve cada parámetro ajustable -50% y +50% y mide el puntaje oficial.

    python verificacion/sensibilidad.py                 # corre lo que falte y guarda en salida/verificacion/sensibilidad.jsonl
    python verificacion/sensibilidad.py --tabla         # imprime la tabla en Markdown con lo ya corrido
    python verificacion/sensibilidad.py --solo lift_min k_truss --factores 0.75 1.25
    python verificacion/sensibilidad.py --datos salida/verificacion/primera_mitad/datos --solo k_truss   # sobre un recorte

Usa el mismo código del pipeline (pipeline.run.correr). Para no repetir trabajo, la ingesta se hace una vez y
las etapas de narrativas y coordinación se reutilizan cuando el parámetro que se cambia no las afecta.
Los enteros se redondean al entero más cercano (y cambian al menos en 1).
"""
import argparse
import contextlib
import io
import json
import math
import shutil
import time

import duckdb

from comun import PRACTICA, SALIDA, cordura, dec, puntuar

import pipeline.run as run
from pipeline.ingesta import ingerir
from pipeline.parametros import AJUSTABLES, de_etapa, resolver

CARPETA = SALIDA / "sensibilidad"
REGISTRO = SALIDA / "sensibilidad.jsonl"
DATOS = PRACTICA
# El plan B sin hilos no se usa cuando hay respuestas: esos dos parámetros se prueban aparte (generalizacion.py).
SIN_EFECTO_CON_HILOS = {"umbral_sin_hilos", "largo_ruido_sin_hilos"}
ORDEN_ETAPAS = ["postura", "origen", "coordinacion", "narrativas"]
MINIMOS = {"k_truss": 2, "min_grupo": 2}
MAXIMOS = {"frac_acuerdo": 1.0}


def valor_movido(nombre: str, factor: float):
    base = AJUSTABLES[nombre].valor
    if isinstance(base, int):
        nuevo = int(math.floor(base * factor + 0.5))
        if nuevo == base:
            nuevo = base + (1 if factor > 1 else -1)
        return max(nuevo, MINIMOS.get(nombre, 1))
    return min(base * factor, MAXIMOS.get(nombre, float("inf")))


class Banco:
    """Corre el pipeline en este mismo proceso reutilizando la ingesta y las etapas que no cambian."""

    def __init__(self):
        CARPETA.mkdir(parents=True, exist_ok=True)
        self.ref = CARPETA / "referencia.duckdb"
        con, self.resumen = ingerir(DATOS, self.ref)
        con.close()
        self.memo_nar, self.memo_coord, self.clave_nar = {}, {}, None
        self.nar_real, self.coord_real = run.detectar_narrativas, run.detectar_coordinacion
        self.clave_nar_base = tuple(sorted(de_etapa(resolver(), "narrativas").items()))
        self.clave_coord_base = tuple(sorted(de_etapa(resolver(), "coordinacion").items()))
        run.ingerir = self._ingerir
        run.detectar_narrativas = self._narrativas
        run.detectar_coordinacion = self._coordinacion
        run.validar_entrega = lambda entrega, datos=None: ([], [], {})

    def _ingerir(self, datos, base):
        shutil.copy(self.ref, base)
        con = duckdb.connect(str(base))
        con.execute("SET memory_limit='2GB'")
        return con, dict(self.resumen)

    def _narrativas(self, *args, **kw):
        clave = tuple(sorted((k, v) for k, v in kw.items() if k in AJUSTABLES))
        self.clave_nar = clave
        if clave in self.memo_nar:
            return self.memo_nar[clave]
        resultado = self.nar_real(*args, **kw)
        if clave == self.clave_nar_base:  # solo se guarda la corrida base, para no llenar la memoria
            self.memo_nar[clave] = resultado
        return resultado

    def _coordinacion(self, **kw):
        clave = (self.clave_nar, tuple(sorted((k, v) for k, v in kw.items() if k in AJUSTABLES)))
        if clave in self.memo_coord:
            return self.memo_coord[clave]
        resultado = self.coord_real(**kw)
        if clave == (self.clave_nar_base, self.clave_coord_base):
            self.memo_coord[clave] = resultado
        return resultado

    def evaluar(self, cambios: dict) -> dict:
        entrega = CARPETA / "entrega"
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            run.correr(DATOS, entrega, CARPETA / "trabajo.duckdb", parametros=cambios)
        segundos = time.perf_counter() - t0
        return {**puntuar(DATOS / "verdad", entrega), **cordura(entrega), "segundos": round(segundos, 1)}


def cargar() -> list:
    if not REGISTRO.exists():
        return []
    return [json.loads(linea) for linea in REGISTRO.read_text(encoding="utf-8").splitlines() if linea.strip()]


def correr(nombres: list, factores: list):
    hechos = {(r["parametro"], r["factor"]) for r in cargar()}
    banco = None
    pendientes = [(n, f) for n in nombres for f in factores if (n, f) not in hechos]
    if ("base", 1.0) not in hechos:
        pendientes.insert(0, ("base", 1.0))
    for nombre, factor in pendientes:
        banco = banco or Banco()
        cambios = {} if nombre == "base" else {nombre: valor_movido(nombre, factor)}
        try:
            fila = banco.evaluar(cambios)
        except Exception as e:  # un valor extremo puede romper una etapa: se anota y se sigue
            fila = {"error": f"{type(e).__name__}: {e}"}
        fila.update({"parametro": nombre, "factor": factor, "valor": cambios.get(nombre),
                     "base": None if nombre == "base" else AJUSTABLES[nombre].valor})
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
        print(f"{nombre:26s} x{factor:<4} -> {fila.get('valor')!s:8} total {fila.get('total', 'ERROR')} "
              f"({fila.get('segundos', '?')} s)", flush=True)


def _valor(v) -> str:
    return str(v) if isinstance(v, int) else f"{v:.3g}".replace(".", ",")


def veredicto(delta: float) -> str:
    return "estable" if abs(delta) < 0.25 else "sensible" if abs(delta) < 1.5 else "**FRÁGIL**"


def tabla(factores: list) -> str:
    filas = cargar()
    base = next(r for r in filas if r["parametro"] == "base")
    por = {(r["parametro"], r["factor"]): r for r in filas}
    metricas = [("agrup", "agrup."), ("ruido", "ruido"), ("postura", "postura"), ("origen", "origen"),
                ("coord_f1", "coord. F1"), ("grupos_f1", "grupos")]
    salida = [f"Base: total {dec(base['total'], 2)} · " + " · ".join(f"{e} {dec(base[m])}" for m, e in metricas),
              "",
              "| Parámetro | Valor | " + " | ".join(f"x{f:g}: valor → total (Δ)" for f in factores) + " | Qué se movió | Veredicto |",
              "|---|---|" + "---|" * len(factores) + "---|---|"]
    for etapa in ORDEN_ETAPAS[::-1]:
        for nombre, p in AJUSTABLES.items():
            if p.etapa != etapa or nombre in SIN_EFECTO_CON_HILOS:
                continue
            celdas, movido, peor = [], [], 0.0
            for f in factores:
                r = por.get((nombre, f))
                if r is None:
                    celdas.append("sin correr")
                elif "error" in r:
                    celdas.append(f"{_valor(r['valor'])} → error")
                    peor = -99.0
                else:
                    d = r["total"] - base["total"]
                    peor = d if abs(d) > abs(peor) else peor
                    celdas.append(f"{_valor(r['valor'])} → {dec(r['total'], 2)} ({d:+.2f})".replace(".", ","))
                    for m, e in metricas:
                        if abs(r[m] - base[m]) >= 0.005:
                            movido.append(f"{e} {dec(r[m])} (x{f:g})")
                    if r["narrativas"] != base["narrativas"]:
                        movido.append(f"{r['narrativas']} narrativas (x{f:g})")
                    if r["coordinadas"] != base["coordinadas"]:
                        movido.append(f"{r['coordinadas']} cuentas marcadas (x{f:g})")
            valor = _valor(p.valor)
            salida.append(f"| `{nombre}` ({etapa}) | {valor} | " + " | ".join(celdas) + f" | {'; '.join(movido) or '—'} | {veredicto(peor)} |")
    return "\n".join(salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo", nargs="*", default=None, help="Nombres de parámetros (por defecto, todos los ajustables)")
    ap.add_argument("--factores", nargs="*", type=float, default=[0.5, 1.5])
    ap.add_argument("--tabla", action="store_true", help="Solo imprimir la tabla con lo ya corrido")
    ap.add_argument("--datos", default=None, help="Otra carpeta de datos con su verdad/ (por defecto, datos/practica)")
    args = ap.parse_args()
    if args.datos:
        from pathlib import Path
        DATOS = Path(args.datos).resolve()
        CARPETA = SALIDA / f"sensibilidad_{DATOS.parent.name}"
        REGISTRO = SALIDA / f"sensibilidad_{DATOS.parent.name}.jsonl"
    if not args.tabla:
        todos = [n for etapa in ORDEN_ETAPAS for n, p in AJUSTABLES.items() if p.etapa == etapa and n not in SIN_EFECTO_CON_HILOS]
        correr(args.solo or todos, args.factores)
    print(tabla(args.factores))
