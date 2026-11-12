"""Pruebas de generalización: el pipeline sobre recortes del set de práctica que no se usaron para ajustar nada.

    python verificacion/generalizacion.py                    # arma los recortes, corre el pipeline y puntúa
    python verificacion/generalizacion.py --solo muestra     # solo los recortes cuyo nombre contiene "muestra"
    python verificacion/generalizacion.py --tabla            # imprime la tabla con lo ya corrido
    python verificacion/generalizacion.py --param min_pubs_compartidas=2     # los mismos recortes con un parámetro cambiado

Cada recorte se corre de punta a punta en otro proceso (python -m pipeline.run) y se mide con el evaluador
oficial contra la verdad recortada igual. Recortes:

- primera_mitad / segunda_mitad: los días 1-7 y 8-14 por separado.
- sin_respuestas: la columna respuesta_a vacía en todos los comentarios.
- mitad_enlaces: respuesta_a vacía en la mitad de las respuestas, elegidas al azar (el comentario queda, suelto).
- mitad_respuestas_borradas: se borra la mitad de las respuestas, elegidas al azar (el comentario desaparece).
- muestra_20k_a/b/c: publicaciones completas elegidas al azar hasta juntar 20.000 comentarios (con todos sus hilos).
"""
import argparse
import json

import numpy as np

from comun import PRACTICA, SALIDA, armar_variante, cordura, correr_pipeline, dec, leer_practica, puntuar

REGISTRO = SALIDA / "generalizacion.json"


def recortes(t: dict) -> dict:
    c = t["comentarios"]
    dia = c.fecha.str.slice(0, 10)
    dias = sorted(dia.unique())
    corte = dias[len(dias) // 2]
    es_resp = (c.respuesta_a != "").to_numpy()
    azar = np.random.default_rng(0)
    mitad = es_resp & (azar.random(len(c)) < 0.5)
    sin_enlace = c.copy()
    sin_enlace.loc[mitad, "respuesta_a"] = ""
    sin_respuestas = c.copy()
    sin_respuestas["respuesta_a"] = ""
    armados = {"completo": c, "primera_mitad": c[dia < corte], "segunda_mitad": c[dia >= corte],
               "sin_respuestas": sin_respuestas, "mitad_enlaces": sin_enlace, "mitad_respuestas_borradas": c[~mitad]}
    por_pub = c.groupby("publicacion_id").size()
    for letra, semilla in zip("abc", (1, 2, 3)):
        orden = np.random.default_rng(semilla).permutation(len(por_pub))
        hasta = int(np.searchsorted(np.cumsum(por_pub.to_numpy()[orden]), 20000)) + 1
        armados[f"muestra_20k_{letra}"] = c[c.publicacion_id.isin(por_pub.index[orden[:hasta]])]
    return armados


def correr(filtro: str = None, parametros: dict = None):
    t = leer_practica()
    resultados = json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}
    campana = dict(zip(t["v_cuentas"].cuenta_id, t["v_cuentas"].campana_id))
    for nombre, comentarios in recortes(t).items():
        if filtro and filtro not in nombre:
            continue
        datos = PRACTICA if nombre == "completo" else armar_variante(nombre, t, comentarios)
        etiqueta = nombre + "".join(f" [{k}={v}]" for k, v in (parametros or {}).items())
        corrida = nombre + ("_param" if parametros else "")
        costo = correr_pipeline(datos, corrida, parametros)
        entrega = SALIDA / corrida / "entrega"
        fila = {**puntuar(datos / "verdad", entrega), **cordura(entrega), "comentarios": len(comentarios),
                "publicaciones": int(comentarios.publicacion_id.nunique()), "cuentas": int(comentarios.cuenta_id.nunique()),
                "respuestas": int((comentarios.respuesta_a != "").sum()),
                "coordinadas_reales": int(sum(1 for x in comentarios.cuenta_id.unique() if campana.get(x))),
                "narrativas_reales": int(t["v_comentarios"][t["v_comentarios"].comentario_id.isin(comentarios.comentario_id)]
                                         .narrativa_id.nunique() - 1),
                "segundos": costo["segundos"], "memoria_pico_mb": costo["memoria_pico_mb"]}
        resultados[etiqueta] = fila
        REGISTRO.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{etiqueta:28s} total {fila['total']:5.2f}  narrativas {fila['narrativas']}  ruido {fila['pct_ruido']:.1f}%  "
              f"marcadas {fila['coordinadas']}  {fila['segundos']} s", flush=True)


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def tabla() -> str:
    r = json.loads(REGISTRO.read_text(encoding="utf-8"))
    salida = ["| Recorte | Comentarios | Narrativas (hay) | Ruido | Agrup. F1 | Ruido F1 | Postura | Origen | Coord. P / R "
              "| Marcadas (hay) | Grupos | Total /55 | Tiempo | Memoria |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nombre, f in r.items():
        origen = dec(f["origen"], 2) if f["origen_detalle"] else "—"
        salida.append(
            f"| {nombre} | {miles(f['comentarios'])} | {f['narrativas']} ({f['narrativas_reales']}) | {dec(f['pct_ruido'], 1)}% | "
            f"{dec(f['agrup'])} | {dec(f['ruido'])} | {dec(f['postura'])} | {origen} | {dec(f['coord_p'], 2)} / {dec(f['coord_r'], 2)} | "
            f"{f['coordinadas']} ({f['coordinadas_reales']}) | {', '.join(map(str, f['tam_grupos'])) or '—'} | "
            f"{dec(f['total'], 2)} | {dec(f['segundos'], 0)} s | {f['memoria_pico_mb']} MB |")
    return "\n".join(salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo", default=None, help="Texto que tiene que estar en el nombre del recorte")
    ap.add_argument("--tabla", action="store_true")
    ap.add_argument("--param", action="append", default=[], metavar="NOMBRE=VALOR", help="Cambiar un parámetro en estas corridas")
    args = ap.parse_args()
    if not args.tabla:
        correr(args.solo, dict(x.split("=", 1) for x in args.param) or None)
    print(tabla())
