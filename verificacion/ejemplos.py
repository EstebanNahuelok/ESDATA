"""Ejemplos reales para revisar a ojo: comentarios al azar de tres narrativas y cuentas marcadas con su porqué.

    python verificacion/ejemplos.py                       # sobre almacen/practica.duckdb (hay que haber corrido el pipeline)
    python verificacion/ejemplos.py --base almacen/final.duckdb --sin-verdad

Imprime Markdown. La elección es al azar con semilla fija, sin mirar si el resultado está bien o mal.
"""
import argparse
from datetime import datetime, timedelta, timezone

import duckdb
import numpy as np
import pandas as pd

from comun import PRACTICA, RAIZ

from pipeline.coordinacion import _camada, _matrices, detectar_coordinacion, pares_sincronizados
from pipeline.parametros import POR_DEFECTO as P

VISTA = """(SELECT c.i, c.comentario_id, c.ts, c.cuenta, c.pub, c.padre, c.texto_id, r.narrativa, r.postura, g.grupo
            FROM comentarios c JOIN res_comentarios r USING (i) JOIN res_cuentas g USING (cuenta))"""


def _hora(ts, zona=-3 * 3600) -> str:
    return datetime.fromtimestamp(int(ts), tz=timezone(timedelta(seconds=zona))).strftime("%d/%m %H:%M")


def _limpio(texto: str, largo=110) -> str:
    texto = " ".join(str(texto).split()).replace("|", "/")
    return texto if len(texto) <= largo else texto[:largo - 1] + "…"


def comentarios_al_azar(con, verdad, semilla=0, por_narrativa=10, pedidas=None) -> str:
    narrativas = con.execute("SELECT narrativa, titulo, comentarios FROM res_narrativas ORDER BY comentarios DESC, narrativa").fetchall()
    if not narrativas:
        return "No hay narrativas."
    elegidas = [narrativas[k] for k in sorted({0, len(narrativas) // 2, len(narrativas) - 1})]
    extra = [("ninguna", "comentarios marcados como ruido", None)]
    if pedidas:
        elegidas, extra = [x for x in narrativas if x[0] in pedidas], []
    salida = []
    for bloque, (narr, titulo, n) in enumerate(elegidas + extra):
        df = con.execute(f"""SELECT v.comentario_id, t.texto, v.postura, v.padre >= 0 AS respuesta
                             FROM {VISTA} v JOIN textos t USING (texto_id) WHERE v.narrativa = ? ORDER BY v.i""", [narr]).df()
        if not len(df):
            continue
        df = df.iloc[np.sort(np.random.default_rng(semilla + bloque).choice(len(df), min(por_narrativa, len(df)), replace=False))]
        salida.append(f"\n**{narr}** — «{_limpio(titulo, 90)}»" + (f" ({n:,} comentarios)".replace(",", ".") if n else f" ({len(df)} de muestra)"))
        encabezado = "| Comentario | Texto | Tipo | Postura asignada |"
        if verdad is not None:
            df = df.merge(verdad, on="comentario_id", how="left")
            encabezado += " Verdad |"
        salida += ["", encabezado, "|" + "---|" * (encabezado.count("|") - 1)]
        for f in df.itertuples():
            linea = f"| {f.comentario_id} | {_limpio(f.texto)} | {'respuesta' if f.respuesta else 'suelto'} | {f.postura or '—'} |"
            if verdad is not None:
                linea += f" {f.narrativa_id} {f.postura_v or ''} |"
            salida.append(linea)
        if verdad is not None and narr != "ninguna":
            mayoria = df.narrativa_id.value_counts().index[0]
            ok_narr, ok_post = int((df.narrativa_id == mayoria).sum()), int((df.postura == df.postura_v).sum())
            salida.append(f"\nEn esta muestra: {ok_narr} de {len(df)} son de la misma narrativa real ({mayoria}); "
                          f"{ok_post} de {len(df)} tienen la postura correcta.")
        elif verdad is not None:
            salida.append(f"\nEn esta muestra: {int((df.narrativa_id == 'ninguna').sum())} de {len(df)} son ruido de verdad.")
    return "\n".join(salida)


def cuentas_marcadas(con, verdad_cuentas, semilla=0, cuantas=10) -> str:
    v = con.execute(f"SELECT cuenta, pub, ts, narrativa, postura FROM {VISTA} WHERE ts IS NOT NULL ORDER BY i").df()
    cuentas = con.execute("SELECT c.cuenta, c.cuenta_id, c.usuario, c.creada_ts, g.grupo FROM cuentas c JOIN res_cuentas g USING (cuenta) ORDER BY cuenta").df()
    marcadas = cuentas[cuentas.grupo != ""]
    if not len(marcadas):
        return "No hay cuentas marcadas."
    n = len(cuentas)
    cuenta, pub, ts = v.cuenta.to_numpy(np.int64), v["pub"].to_numpy(np.int64), v.ts.to_numpy(np.float64)
    narrativa = pd.factorize(v.narrativa)[0].astype(np.int64)
    bando = np.where(v.postura == "apoya", 1, np.where(v.postura == "rechaza", -1, 0)).astype(np.float64)
    creada = cuentas.creada_ts.to_numpy(np.float64)
    # Núcleo (malla densa) contra ampliación: se vuelve a correr la detección sin la segunda pasada.
    nucleo, _ = detectar_coordinacion(n, cuenta, pub, ts, narrativa, bando, ampliar=False, creada_ts=creada)
    en_nucleo = nucleo != ""
    # Pares fuertes de cada canal, como los calcula el pipeline.
    fuertes = {}
    for claves, veces_min in (([pub, narrativa, bando.astype(np.int64)], P["veces_con_texto"]), ([pub], P["veces_sin_texto"])):
        matrices = _matrices(cuenta, claves, ts.astype(np.int64), n, P["ventana_s"])
        a, b, _s, veces, lift = pares_sincronizados(matrices, cuenta, n, min_veces=veces_min)
        for x, y, k, l in zip(a.tolist(), b.tolist(), veces.tolist(), lift.tolist()):
            if l >= P["lift_min"]:
                previo = fuertes.get((x, y), (0, 0.0))
                fuertes[(x, y)] = (max(previo[0], int(k)), max(previo[1], l))
    grupo_de = cuentas.grupo.to_numpy()
    socios = {}
    for (x, y), (k, l) in fuertes.items():
        if grupo_de[x] and grupo_de[x] == grupo_de[y]:
            for p, q in ((x, y), (y, x)):
                socios.setdefault(p, []).append((q, k, l))
    # Elección al azar: dos por grupo, el resto al azar, y si hay cuentas que entraron por la ampliación, una de ellas.
    azar = np.random.default_rng(semilla)
    elegidas = []
    for _g, sub in marcadas.groupby("grupo"):
        elegidas += azar.choice(sub.cuenta.to_numpy(), min(2, len(sub)), replace=False).tolist()
    ampliadas = [c for c in marcadas.cuenta if not en_nucleo[c] and c not in elegidas]
    if ampliadas:
        elegidas.append(int(azar.choice(ampliadas)))
    resto = [c for c in marcadas.cuenta if c not in elegidas]
    elegidas += azar.choice(resto, max(0, min(cuantas - len(elegidas), len(resto))), replace=False).tolist()
    elegidas = sorted(elegidas[:cuantas], key=lambda c: (grupo_de[c], c))

    tam_grupo = marcadas.groupby("grupo").size().to_dict()
    resumen_grupo = []
    for g, sub in marcadas.groupby("grupo"):
        franja = _camada(creada, sub.cuenta.to_numpy(), P["camada_max_rareza"])
        dias = (np.nanmax(creada[sub.cuenta]) - np.nanmin(creada[sub.cuenta])) / 86400
        resumen_grupo.append(f"- **{g}**: {len(sub)} cuentas, {int(en_nucleo[sub.cuenta].sum())} en el núcleo (malla densa) y "
                             f"{int((~en_nucleo[sub.cuenta]).sum())} sumadas en la segunda pasada. Fechas de creación en un rango de "
                             f"{dias:.0f} días" + (" (camada: franja rara en el set, cuenta como indicio)." if franja is not None
                                                  else " (no forman camada: la antigüedad no se usó).") )
    filas = ["| Cuenta | Grupo | Cómo entró | Pares fuertes dentro del grupo | Más veces con un mismo par | Lift máximo | "
             "Comentarios (en ráfaga con el grupo) | Su mayor ráfaga | Creada | Verdad |", "|" + "---|" * 10]
    for c in elegidas:
        g = grupo_de[c]
        mios = socios.get(c, [])
        rafagas = con.execute(f"""SELECT a.i, a.pub, a.ts, count(DISTINCT b.cuenta) k FROM {VISTA} a JOIN {VISTA} b
            ON a.pub = b.pub AND abs(a.ts - b.ts) <= 900 AND b.grupo = a.grupo AND b.cuenta <> a.cuenta
            WHERE a.cuenta = {int(c)} GROUP BY 1, 2, 3 ORDER BY k DESC, a.ts""").fetchall()
        total = con.execute(f"SELECT count(*) FROM comentarios WHERE cuenta = {int(c)}").fetchone()[0]
        en_rafaga = sum(1 for r in rafagas if r[3] >= 2)
        mayor = "—"
        if rafagas:
            pub_id = con.execute(f"SELECT publicacion_id FROM publicaciones WHERE pub = {rafagas[0][1]}").fetchone()[0]
            mayor = f"{pub_id}, {_hora(rafagas[0][2])}: {rafagas[0][3]} cuentas más del grupo en ±15 min"
        fila = cuentas.iloc[c]
        como = "núcleo: malla densa de pares fuertes" if en_nucleo[c] else "segunda pasada: coincide con el grupo como conjunto"
        creada_txt = datetime.fromtimestamp(fila.creada_ts, tz=timezone.utc).strftime("%Y-%m-%d") if not np.isnan(fila.creada_ts) else "sin dato"
        real = "" if verdad_cuentas is None else (verdad_cuentas.get(fila.cuenta_id) or "genuina (FALSO POSITIVO)")
        filas.append(f"| {fila.cuenta_id} | {g} | {como} | {len(mios)} de {tam_grupo[g] - 1} | "
                     f"{max((k for _q, k, _l in mios), default=0)} | {max((l for _q, _k, l in mios), default=0):.0f} | "
                     f"{total} ({en_rafaga}) | {mayor} | {creada_txt} | {real} |")
    return "\n".join(resumen_grupo + [""] + filas)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(RAIZ / "almacen" / "practica.duckdb"))
    ap.add_argument("--sin-verdad", action="store_true", help="No cruzar contra la verdad del set de práctica")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--narrativas", nargs="*", default=None, help="Mostrar solo comentarios de estas narrativas (ej. n08)")
    args = ap.parse_args()
    verdad = verdad_cuentas = None
    if not args.sin_verdad:
        verdad = pd.read_csv(PRACTICA / "verdad" / "comentarios.csv.gz", dtype=str, keep_default_na=False).rename(columns={"postura": "postura_v"})
        vc = pd.read_csv(PRACTICA / "verdad" / "cuentas.csv.gz", dtype=str, keep_default_na=False)
        verdad_cuentas = dict(zip(vc.cuenta_id, vc.campana_id))
    con = duckdb.connect(args.base, read_only=True)
    print("### Comentarios al azar\n" + comentarios_al_azar(con, verdad, args.semilla, pedidas=args.narrativas))
    if args.narrativas:
        raise SystemExit(0)
    print("\n### Cuentas marcadas como coordinadas y por qué\n\n" + cuentas_marcadas(con, verdad_cuentas, args.semilla))
