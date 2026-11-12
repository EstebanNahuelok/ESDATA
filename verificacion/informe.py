"""Junta en un solo Markdown las tablas que generan los otros scripts de verificación.

    python verificacion/informe.py > salida/verificacion/tablas.md

No corre nada pesado: lee lo que ya dejaron sensibilidad.py y generalizacion.py en salida/verificacion/.
"""
import json
import subprocess
import sys
from collections import Counter

from comun import RAIZ, SALIDA, dec

from pipeline.parametros import PARAMETROS, tabla_markdown


def _script(*args) -> str:
    return subprocess.run([sys.executable, *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8").stdout.strip()


def _sin_vacias(tabla: str) -> str:
    return "\n".join(l for l in tabla.splitlines() if "sin correr | sin correr" not in l)


def generalizacion(con_parametros: bool) -> str:
    r = json.loads((SALIDA / "generalizacion.json").read_text(encoding="utf-8"))
    if not con_parametros:
        tabla = _script("verificacion/generalizacion.py", "--tabla").splitlines()
        return "\n".join(l for l in tabla if "[" not in l)
    base = {k: v for k, v in r.items() if "[" not in k}
    variantes = sorted({k.split(" ", 1)[1] for k in r if "[" in k}, key=len)
    filas = ["| Recorte | Actual: total, marcadas, P / R | " + " | ".join(variantes) + " |", "|---|---|" + "---|" * len(variantes)]
    celda = lambda f: f"{dec(f['total'], 2)}, {f['coordinadas']}, {dec(f['coord_p'], 2)} / {dec(f['coord_r'], 2)}"
    for nombre, f in base.items():
        filas.append(f"| {nombre} | {celda(f)} | " + " | ".join(celda(r[f"{nombre} {v}"]) if f"{nombre} {v}" in r else "—" for v in variantes) + " |")
    return "\n".join(filas)


if __name__ == "__main__":
    for flujo in (sys.stdout,):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    cuenta = Counter(p.origen for p in PARAMETROS)
    print("<!-- PARAMETROS -->")
    print(f"{len(PARAMETROS)} parámetros: " + ", ".join(f"{n} «{o}»" for o, n in cuenta.most_common()) + ".\n")
    print(tabla_markdown())
    print("\n<!-- SENSIBILIDAD 50 -->")
    print(_script("verificacion/sensibilidad.py", "--tabla", "--factores", "0.5", "1.5"))
    print("\n<!-- SENSIBILIDAD 25 -->")
    print(_sin_vacias(_script("verificacion/sensibilidad.py", "--tabla", "--factores", "0.75", "1.25")))
    print("\n<!-- SENSIBILIDAD SEGUNDA MITAD 25 -->")
    print(_sin_vacias(_script("verificacion/sensibilidad.py", "--datos", "salida/verificacion/segunda_mitad/datos", "--tabla",
                              "--factores", "0.75", "1.25")))
    print("\n<!-- GENERALIZACION -->")
    print(generalizacion(False))
    print("\n<!-- GENERALIZACION CON PARAMETROS -->")
    print(generalizacion(True))
