"""Compara cuatro versiones del pipeline en práctica y en los recortes: la actual, solo A, solo B y A+B.

    python verificacion/comparar_ab.py            # corre todo (unos 20 minutos) e imprime las tablas
    python verificacion/comparar_ab.py --tabla    # imprime las tablas con lo ya corrido

A = `reubicar_consignas` (las frases que dice casi solo un grupo coordinado se ubican por su conversación con gente de
afuera o por palabras). B = `ampliar_misma_frase` (la segunda pasada de coordinación también mira "misma frase").
Los recortes son los de generalizacion.py. Cada corrida es el pipeline de punta a punta en otro proceso, medido con el
evaluador oficial contra la verdad recortada igual.
"""
import argparse
import json

from comun import PRACTICA, SALIDA, armar_variante, cordura, correr_pipeline, dec, leer_practica, puntuar
from generalizacion import recortes

REGISTRO = SALIDA / "comparar_ab.json"
VERSIONES = {"actual": {"reubicar_consignas": 0, "ampliar_misma_frase": 0}, "solo A": {"reubicar_consignas": 1, "ampliar_misma_frase": 0},
             "solo B": {"reubicar_consignas": 0, "ampliar_misma_frase": 1}, "A+B": {"reubicar_consignas": 1, "ampliar_misma_frase": 1}}


def correr():
    t = leer_practica()
    resultados = json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}
    for nombre, comentarios in recortes(t).items():
        datos = PRACTICA if nombre == "completo" else SALIDA / nombre / "datos"
        if not (datos / "verdad" / "narrativas.csv").exists():
            datos = armar_variante(nombre, t, comentarios)
        for version, parametros in VERSIONES.items():
            corrida = f"ab_{nombre}_{version.replace(' ', '_').replace('+', '')}"
            costo = correr_pipeline(datos, corrida, parametros)
            entrega = SALIDA / corrida / "entrega"
            fila = {**puntuar(datos / "verdad", entrega), **cordura(entrega), "alertas": [x for x in costo.get("notas", "").split(" | ") if "ALERTA" in x],
                    "notas": costo.get("notas", ""), "segundos": costo["segundos"]}
            resultados.setdefault(nombre, {})[version] = fila
            REGISTRO.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{nombre:26s} {version:7s} total {fila['total']:5.2f}  narr {fila['pts_narr']:5.2f}  coord {fila['pts_coord']:5.2f}  "
                  f"marcadas {fila['coordinadas']} {fila['tam_grupos']}  {'ALERTA' if 'ALERTA' in fila['notas'] else ''}", flush=True)


def tabla() -> str:
    r = json.loads(REGISTRO.read_text(encoding="utf-8"))
    salida = ["| Set | " + " | ".join(VERSIONES) + " |", "|---|" + "---|" * len(VERSIONES)]
    for nombre, f in r.items():
        salida.append(f"| {nombre} | " + " | ".join(dec(f[v]["total"], 2) if v in f else "—" for v in VERSIONES) + " |")
    salida += ["", "| Set | Versión | Agrup. F1 | Ruido F1 | Postura | Origen | Coord. P / R | Marcadas | Grupos | ALERTA |", "|---|---|---|---|---|---|---|---|---|---|"]
    for nombre, f in r.items():
        for v in VERSIONES:
            if v not in f:
                continue
            x = f[v]
            origen = dec(x["origen"], 2) if x["origen_detalle"] else "—"
            salida.append(f"| {nombre} | {v} | {dec(x['agrup'])} | {dec(x['ruido'])} | {dec(x['postura'])} | {origen} | {dec(x['coord_p'], 2)} / {dec(x['coord_r'], 2)} | "
                          f"{x['coordinadas']} | {', '.join(map(str, x['tam_grupos'])) or '—'} | {'sí' if 'ALERTA' in x['notas'] else 'no'} |")
    return "\n".join(salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tabla", action="store_true")
    args = ap.parse_args()
    if not args.tabla:
        correr()
    print(tabla())
