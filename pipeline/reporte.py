"""Reporte visual: un solo archivo HTML estático, sin internet ni JavaScript, generado desde la base DuckDB.

Responde en una pantalla: qué narrativas circulan, desde cuándo, quién las apoya o rechaza y qué grupos
de cuentas coordinadas las empujan. El pipeline lo genera al final; también se puede regenerar suelto:

    python -m pipeline.reporte --base almacen/practica.duckdb --salida reporte/practica.html --costo salida/practica/costo.json

Nada de lo que muestra está escrito a mano: los nombres de las narrativas salen de sus palabras más
distintivas, los temas de qué narrativas comparten publicaciones, y los nombres de los grupos de sus rasgos.
Es un extra aislado: si falla, la entrega ya está escrita y validada.
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import duckdb

from .texto import PALABRAS_VACIAS, normalizar

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
COLOR_TEMAS = ["#1d4ed8", "#b45309", "#7c3aed", "#0e7490", "#a21caf", "#4d7c0f", "#475569"]
COLOR_GRUPOS = ["#be123c", "#111827", "#c2410c", "#4338ca", "#0f766e", "#86198f", "#57534e"]
VERDE, ROJO = "#15803d", "#b91c1c"
VISTA = """(SELECT c.i, c.ts, c.cuenta, c.pub, c.hora_local, c.me_gusta, c.texto_id, r.narrativa, r.postura, g.grupo
            FROM comentarios c JOIN res_comentarios r USING (i) JOIN res_cuentas g USING (cuenta))"""
# Palabras del idioma que no sirven como término clave (además de las palabras vacías de texto.py).
POCO_INFORMATIVAS = frozenset("""siendo sigue siguen hubo estan esta estamos porque dos tres nada antes ahora siempre nunca
todos toda todas cada hace hacen tiene tienen puede pueden donde cuando quien cual tambien solo alla despues entonces
bien mucho poco menos mismo misma otra otro otros otras esos esas sino aunque mientras tanto eran habia haber dieron
dice dicen digo vamos quiere quieren sacan dejan llevan vienen venir decir hacer tener nadie algun alguna cosa cosas
gente años dias veces igual asi aqui durante hasta tras""".split()) | PALABRAS_VACIAS
INDICIOS = {"marcas": "un bando usa expresiones de desmentida", "campana": "un grupo coordinado empuja un bando",
            "sueltos": "un bando aparece más como comentario suelto", "variedad": "un bando tiene más redacciones distintas",
            "volumen": "un bando tiene más comentarios", "un solo bando": "solo se encontró un bando"}

CSS = """
*{box-sizing:border-box}
body{font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;margin:0;color:#0f172a;background:#f8fafc}
main{max-width:1280px;margin:0 auto;padding:36px 32px 64px}
h1{font-size:38px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em}
h2{font-size:26px;line-height:1.2;margin:56px 0 6px;letter-spacing:-.01em}
h2 small{display:block;font-size:13px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#64748b;margin-bottom:4px}
h3{font-size:21px;margin:0}
p{margin:0 0 12px} .sub{color:#475569;font-size:17px;margin:0 0 20px;max-width:76ch}
.cod{font:12.5px ui-monospace,Consolas,monospace;color:#64748b;background:#f1f5f9;border-radius:4px;padding:1px 5px;white-space:nowrap}
.resumen{background:#0f172a;color:#f8fafc;border-radius:14px;padding:26px 30px;margin:24px 0 18px}
.resumen .frase{font-size:25px;line-height:1.35;font-weight:600;margin:0}
.resumen b{color:#fde68a} .resumen ul{margin:18px 0 0;padding:16px 0 0 22px;border-top:1px solid #334155;font-size:18px}
.resumen ul{list-style:none;padding-left:0} .resumen li{margin:10px 0} .resumen .cod{background:#1e293b;color:#94a3b8}
.punto{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:6px;vertical-align:baseline}
.alerta{background:#fef2f2;border:2px solid #dc2626;color:#7f1d1d;border-radius:12px;padding:14px 18px;margin:14px 0;font-weight:600}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:18px 0 0}
.kpi{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px 18px}
.kpi b{display:block;font-size:28px;line-height:1.15;letter-spacing:-.01em;white-space:nowrap} .kpi span{color:#475569;font-size:14px}
.leer{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:22px 26px;margin:22px 0 0}
.leer h2{margin:0 0 14px;font-size:20px} .leer dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px 30px;margin:0}
.leer dt{font-weight:700;font-size:17px;margin-bottom:2px} .leer dd{margin:0;color:#334155;font-size:16px}
.caja{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:20px 22px;overflow-x:auto}
.ley{color:#475569;font-size:14.5px;margin:12px 0 0} .ley span{display:inline-block;width:12px;height:12px;border-radius:3px;margin:0 5px 0 14px}
.tema{margin:26px 0 0;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0;background:#fff}
.tema-t{color:#fff;padding:12px 20px;font-size:19px;font-weight:700;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.tema-t span{font-weight:500;font-size:15.5px;opacity:.92}
table{border-collapse:collapse;width:100%;table-layout:fixed}
th:nth-child(1){width:35%} th:nth-child(2){width:15%} th:nth-child(3){width:13%} th:nth-child(4){width:19%} th:nth-child(5){width:18%}
th{font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;color:#64748b;text-align:left;padding:10px 14px;border-bottom:1px solid #e2e8f0;background:#f8fafc}
td{padding:16px 14px;border-bottom:1px solid #eef2f6;vertical-align:top;font-size:16px} tr:last-child td{border-bottom:0}
.nom{font-size:19px;font-weight:700;line-height:1.25}
.rep{color:#334155;font-size:15.5px;margin-top:5px} .rep i{color:#64748b;font-style:normal;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em;font-weight:700}
.term{display:inline-block;background:#f1f5f9;color:#334155;border-radius:6px;padding:1px 8px;font-size:14px;margin:7px 5px 0 0}
.chip{display:inline-block;font-size:13.5px;font-weight:700;border-radius:99px;padding:2px 11px;white-space:nowrap}
.nueva{background:#fde68a;color:#78350f} .vieja{background:#f1f5f9;color:#475569} .gr{color:#fff}
.alta{background:#dcfce7;color:#14532d} .media{background:#fef9c3;color:#713f12} .baja{background:#fee2e2;color:#7f1d1d}
.barra{display:flex;height:16px;border-radius:4px;overflow:hidden;background:#e2e8f0;margin:3px 0 5px;min-width:120px}
.vol{height:16px;border-radius:4px;margin:3px 0 5px}
.det{font-size:14.5px;color:#475569} .fecha{white-space:nowrap;font-weight:600}
.nota{background:#fffbeb;border-left:5px solid #f59e0b;border-radius:8px;padding:12px 16px;color:#451a03;font-size:15.5px;margin:18px 0 0}
.grupos{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:18px;margin-top:16px}
.grupo{background:#fff;border:1px solid #e2e8f0;border-top:7px solid #444;border-radius:14px;padding:20px 22px}
.grupo .rasgo{font-size:16px;color:#334155;margin:2px 0 4px} .grupo ul{margin:12px 0;padding-left:20px} .grupo li{margin:7px 0;font-size:16px}
.cita{color:#1e293b;font-size:15.5px;margin:4px 0;padding-left:12px;border-left:3px solid #cbd5e1}
.mini{font-size:12.5px;color:#64748b;margin:14px 0 4px;text-transform:uppercase;letter-spacing:.07em;font-weight:700}
footer{margin-top:56px;color:#475569;font-size:15px;border-top:1px solid #e2e8f0;padding-top:18px} footer li{margin:6px 0} footer b{color:#0f172a}
svg{display:block;max-width:100%;height:auto} svg text{font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
@media print{body{background:#fff} .tema,.grupo,.caja{break-inside:avoid}}
"""


def _n(valor) -> str:
    """Número con separador de miles a la argentina."""
    return f"{int(valor):,}".replace(",", ".")


def _dec(valor, decimales=1) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")


def _pct(parte, total, decimales=0) -> str:
    return (f"{100 * parte / total:.{decimales}f}".replace(".", ",") + "%") if total else "—"


def _fecha(ts, zona_seg, con_hora=True) -> str:
    if ts is None:
        return "sin fecha"
    d = datetime.fromtimestamp(int(ts), tz=timezone(timedelta(seconds=zona_seg)))
    texto = f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"
    return f"{texto}, {d:%H:%M}" if con_hora else texto


def _zona_seg(con) -> int:
    try:
        zona = con.execute("SELECT valor FROM meta WHERE clave = 'zona'").fetchone()[0]
        return (-1 if zona[0] == "-" else 1) * (int(zona[1:3]) * 3600 + int(zona[4:6]) * 60)
    except Exception:
        return -3 * 3600


def _cubeta(t0, t1, max_cubetas=120) -> int:
    for horas in (1, 2, 3, 4, 6, 12, 24, 48, 168):
        if (t1 - t0) / (horas * 3600) <= max_cubetas:
            return horas * 3600
    return max(3600, int((t1 - t0) / max_cubetas))


def _con_tildes(textos_con_peso) -> dict:
    """Para cada palabra sin tildes, la forma escrita más usada en los textos originales (para mostrar 'médicos')."""
    formas = {}
    for texto, peso in textos_con_peso:
        for palabra in re.findall(r"[^\W\d_]+", str(texto).lower()):
            formas.setdefault(normalizar(palabra), Counter())[palabra] += peso
    return {clave: max(c.items(), key=lambda kv: (kv[1], kv[0]))[0] for clave, c in formas.items() if clave}


def _terminos_limpios(frases: list, tildes: dict, textos: list = (), maximo=4, min_uso=0.08) -> list:
    """Términos clave para mostrar: una sola palabra, sin palabras vacías ni variantes de una ya elegida.

    Se respeta el orden en que vienen (del más al menos distintivo de la narrativa), y se descartan los que
    aparecen en muy pocos comentarios de la narrativa (menos de `min_uso`), que son rarezas de una sola frase.
    """
    uso, total = Counter(), sum(peso for _t, peso in textos) or 1
    for texto, peso in textos:
        for palabra in set(normalizar(str(texto)).split()):
            uso[palabra] += peso
    elegidos = []
    for termino in frases:
        if " " in termino or len(termino) < 4 or termino in POCO_INFORMATIVAS or any(c.isdigit() for c in termino):
            continue
        if textos and uso[termino] < min_uso * total:
            continue
        if any(termino[:5] == otro[:5] for otro in elegidos):
            continue
        elegidos.append(termino)
        if len(elegidos) == maximo:
            break
    return [tildes.get(t, t) for t in elegidos]


def _temas(filas_pub: list, narrativas: list, titulares: dict, umbral=0.15) -> tuple:
    """Agrupa narrativas que se discuten en las mismas publicaciones. Devuelve (tema de cada narrativa, nombres).

    Dos narrativas son del mismo tema si el reparto de sus comentarios entre publicaciones se parece (coseno).
    El nombre del tema sale de las palabras más distintivas de los titulares de sus publicaciones.
    """
    por_narr = {n: {} for n in narrativas}
    for narr, pub, k in filas_pub:
        if narr in por_narr:
            por_narr[narr][pub] = k
    norma = {n: sum(v * v for v in d.values()) ** 0.5 for n, d in por_narr.items()}
    padre = {n: n for n in narrativas}

    def raiz(x):
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    for i, a in enumerate(narrativas):
        for b in narrativas[i + 1:]:
            if norma[a] and norma[b]:
                comun = sum(v * por_narr[b].get(p, 0) for p, v in por_narr[a].items())
                if comun / (norma[a] * norma[b]) >= umbral:
                    padre[raiz(a)] = raiz(b)
    grupos = {}
    for n in narrativas:
        grupos.setdefault(raiz(n), []).append(n)
    if len(grupos) <= 1 or len(grupos) == len(narrativas):
        return {}, []  # no hay estructura de temas que mostrar
    orden = sorted(grupos.values(), key=lambda g: -sum(sum(por_narr[n].values()) for n in g))
    tildes = _con_tildes((t, 1) for t in titulares.values())
    # Cada titular distinto cuenta una vez, en el tema donde tiene más comentarios (así no manda el titular más repetido).
    peso_titular = {}
    for k, g in enumerate(orden):
        for n in g:
            for pub, c in por_narr[n].items():
                titular = normalizar(titulares.get(pub) or "")
                if titular:
                    peso_titular.setdefault(titular, Counter())[k] += c
    conteos = [Counter() for _ in orden]
    for titular, por_tema in peso_titular.items():
        k = max(por_tema.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        for palabra in set(titular.split()):
            if len(palabra) >= 4 and palabra not in POCO_INFORMATIVAS:
                conteos[k][palabra] += 1
    total = sum(conteos, Counter())
    nombres = []
    for k, c in enumerate(conteos):
        prefijo = Counter()  # singular y plural cuentan juntos ("línea", "líneas")
        for w, v in c.items():
            prefijo[w[:5]] += v - (total[w] - v)
        mejores = sorted(c, key=lambda w: (-prefijo[w[:5]], -c[w], len(w), w))
        elegidas = []
        for w in mejores:
            if not any(w[:5] == o[:5] for o in elegidas):
                elegidas.append(w)
            if len(elegidas) == 2:
                break
        nombre = " y ".join(tildes.get(w, w) for w in elegidas) or f"tema {k + 1}"
        nombres.append(nombre[:1].upper() + nombre[1:])
    return {n: k for k, g in enumerate(orden) for n in g}, nombres


def _franja_horaria(histograma: list, cobertura=0.8):
    """La franja de horas corridas más corta que junta `cobertura` de la actividad. Devuelve (desde, hasta, fracción)."""
    total = sum(histograma)
    if not total:
        return None
    for largo in range(1, 25):
        mejor = max(((sum(histograma[(h + k) % 24] for k in range(largo)), -h) for h in range(24)))
        if mejor[0] >= cobertura * total:
            return -mejor[1], (-mejor[1] + largo) % 24, mejor[0] / total
    return None


def _rasgos_grupo(g: dict, edad_resto) -> str:
    """Descripción corta del grupo a partir de sus rasgos: antigüedad de las cuentas y horario."""
    rasgos = []
    if g["edad"] is not None and edad_resto:
        rasgos.append("cuentas recién creadas" if g["edad"] < 0.05 * edad_resto else "cuentas antiguas")
    franja = _franja_horaria(g["horas"])
    if franja:
        desde, largo = franja[0], (franja[1] - franja[0]) % 24 or 24
        if largo > 16:
            rasgos.append("a toda hora")
        elif desde < 6 and desde + largo <= 8:
            rasgos.append("de madrugada")
        elif desde >= 6 and desde + largo <= 21:
            rasgos.append("de día")
        else:
            rasgos.append("de tarde y de noche")
    return ", ".join(rasgos)


def reunir_datos(con) -> dict:
    """Todas las consultas del reporte, sobre las tablas limpias y de resultados de la base."""
    zona = _zona_seg(con)
    uno = lambda sql: con.execute(sql).fetchone()
    total, sin_narr, t0, t1 = uno(f"SELECT count(*), count(*) FILTER (narrativa = 'ninguna'), min(ts), max(ts) FROM {VISTA}")
    n_cuentas, n_coord, n_grupos = uno("SELECT count(*) FILTER (c.cuenta_id <> ''), count(*) FILTER (g.grupo <> ''), count(DISTINCT nullif(g.grupo, '')) FROM cuentas c JOIN res_cuentas g USING (cuenta)")
    n_pubs = uno("SELECT count(*) FROM publicaciones WHERE publicacion_id <> ''")[0]
    d = {"zona": zona, "total": total, "ruido": sin_narr, "t0": t0, "t1": t1, "cuentas": n_cuentas, "coordinadas": n_coord,
         "n_grupos": n_grupos, "publicaciones": n_pubs, "narrativas": [], "grupos": [], "temas": [], "cobertura": 0}
    if not total or t0 is None:
        return d
    cubeta = _cubeta(t0, t1)
    # Las cubetas arrancan en la medianoche local anterior al primer comentario, para que los días queden alineados.
    inicio = (t0 + zona) // 86400 * 86400 - zona
    dias = list(range(inicio, t1 + 1, 86400))
    d.update({"cubeta": cubeta, "inicio": inicio, "fin": dias[-1] + 86400, "dias": dias,
              "serie_total": dict(con.execute(f"""SELECT CAST(floor((ts - {inicio}) / {cubeta}) AS INT), count(*) FROM {VISTA}
                                                  WHERE ts IS NOT NULL GROUP BY 1""").fetchall())})

    posturas = {r[0]: r[1:] for r in con.execute(f"""SELECT narrativa, count(*) FILTER (postura = 'apoya'),
            count(*) FILTER (postura = 'rechaza') FROM {VISTA} GROUP BY 1""").fetchall()}
    por_grupo = {}
    for narr, grupo, n, n_apoya in con.execute(f"""SELECT narrativa, grupo, count(*), count(*) FILTER (postura = 'apoya')
            FROM {VISTA} WHERE grupo <> '' AND narrativa <> 'ninguna' GROUP BY 1, 2""").fetchall():
        por_grupo.setdefault(narr, []).append((n, grupo, n_apoya))
    primeros = {}
    for narr, grupo, n in con.execute(f"""SELECT narrativa, grupo, count(*) FROM (
            SELECT narrativa, grupo, row_number() OVER (PARTITION BY narrativa ORDER BY ts, i) k FROM {VISTA}
            WHERE ts IS NOT NULL AND narrativa <> 'ninguna') WHERE k <= 30 AND grupo <> '' GROUP BY 1, 2""").fetchall():
        primeros.setdefault(narr, []).append((n, grupo))
    textos_top = {}
    for narr, texto, n in con.execute(f"""SELECT narrativa, texto, n FROM (
            SELECT v.narrativa, t.texto, count(*) n, row_number() OVER (PARTITION BY v.narrativa ORDER BY count(*) DESC, t.texto) k
            FROM {VISTA} v JOIN textos t USING (texto_id) WHERE v.narrativa <> 'ninguna' GROUP BY 1, 2) WHERE k <= 60""").fetchall():
        textos_top.setdefault(narr, []).append((texto, n))
    columnas = {r[0] for r in con.execute("DESCRIBE res_narrativas").fetchall()}
    extra = "puntaje_postura, indicio_postura" if "puntaje_postura" in columnas else "NULL, NULL"
    for narr, titulo, frases, origen, n, puntaje, indicio in con.execute(
            f"SELECT narrativa, titulo, frases_clave, fecha_origen, comentarios, {extra} FROM res_narrativas ORDER BY comentarios DESC, narrativa").fetchall():
        try:
            origen_ts = int(datetime.fromisoformat(origen).timestamp())
        except (TypeError, ValueError):
            origen_ts = None
        apoya, rechaza = posturas.get(narr, (0, 0))
        terminos = _terminos_limpios([f for f in (frases or "").split("|") if f], _con_tildes(textos_top.get(narr, [])),
                                     textos_top.get(narr, []))
        nombre = " y ".join(terminos[:2]) if terminos else narr
        confianza = None if puntaje is None else "alta" if puntaje >= 3 else "media" if puntaje >= 1.5 else "baja"
        d["narrativas"].append({
            "id": narr, "nombre": nombre[:1].upper() + nombre[1:], "frase": titulo, "terminos": terminos, "origen": origen_ts,
            "n": n, "apoya": apoya, "rechaza": rechaza, "confianza": confianza, "indicio": indicio or "",
            "grupos": sorted(por_grupo.get(narr, []), reverse=True), "primeros": sorted(primeros.get(narr, []), reverse=True),
            "nueva": origen_ts is not None and origen_ts - t0 > 86400})

    filas_pub = con.execute(f"SELECT narrativa, pub, count(*) FROM {VISTA} WHERE narrativa <> 'ninguna' GROUP BY 1, 2").fetchall()
    titulares = dict(con.execute("SELECT pub, titular FROM publicaciones WHERE titular IS NOT NULL").fetchall())
    tema_de, d["temas"] = _temas(filas_pub, [x["id"] for x in d["narrativas"]], titulares)
    for x in d["narrativas"]:
        x["tema"] = tema_de.get(x["id"])

    media_likes = uno(f"SELECT avg(me_gusta) FROM {VISTA} WHERE grupo = ''")[0]
    edad_resto = uno("""SELECT median((p.ts - c.creada_ts) / 86400.0) FROM cuentas c JOIN res_cuentas g USING (cuenta)
        JOIN (SELECT cuenta, min(ts) ts FROM comentarios GROUP BY 1) p USING (cuenta) WHERE g.grupo = ''""")[0]
    d.update({"likes_resto": media_likes, "edad_resto": edad_resto})
    por_id = {x["id"]: x for x in d["narrativas"]}
    grupos = con.execute("SELECT grupo, count(*) FROM res_cuentas WHERE grupo <> '' GROUP BY 1 ORDER BY 2 DESC, 1").fetchall()
    for k, (grupo, cuentas) in enumerate(grupos):
        filtro = f"grupo = '{grupo}'"
        n, likes, g0, g1 = uno(f"SELECT count(*), avg(me_gusta), min(ts), max(ts) FROM {VISTA} WHERE {filtro}")
        principal = uno(f"""SELECT narrativa, postura, count(*) FROM {VISTA} WHERE {filtro} AND narrativa <> 'ninguna'
                            GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT 1""")
        edad = uno(f"""SELECT median((p.ts - c.creada_ts) / 86400.0) FROM cuentas c JOIN res_cuentas g USING (cuenta)
            JOIN (SELECT cuenta, min(ts) ts FROM comentarios GROUP BY 1) p USING (cuenta) WHERE g.{filtro}""")[0]
        rafagas = uno(f"""SELECT count(*), max(k) FROM (SELECT count(DISTINCT cuenta) k FROM {VISTA}
            WHERE {filtro} AND ts IS NOT NULL GROUP BY pub, CAST(floor(ts / 1800) AS BIGINT)) WHERE k >= 3""")
        horas = [0] * 24
        for h, c in con.execute(f"SELECT CAST(floor(hora_local) AS INT), count(*) FROM {VISTA} WHERE {filtro} AND hora_local IS NOT NULL GROUP BY 1").fetchall():
            horas[max(0, min(23, h))] = c
        serie = dict(con.execute(f"""SELECT CAST(floor((ts - {inicio}) / {cubeta}) AS INT), count(*) FROM {VISTA}
            WHERE {filtro} AND ts IS NOT NULL GROUP BY 1""").fetchall())
        textos = con.execute(f"""SELECT t.texto, count(*) FROM {VISTA} v JOIN textos t USING (texto_id)
            WHERE {filtro} AND narrativa = ? GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 3""", [principal[0] if principal else ""]).fetchall()
        ejemplos = [r[0] for r in con.execute(f"""SELECT c.cuenta_id FROM cuentas c JOIN res_cuentas g USING (cuenta)
            WHERE g.{filtro} ORDER BY 1 LIMIT 5""").fetchall()]
        g = {"id": grupo, "letra": chr(65 + k) if k < 26 else str(k + 1), "cuentas": cuentas, "n": n, "likes": likes,
             "desde": g0, "hasta": g1, "principal": principal, "edad": edad, "rafagas": rafagas, "horas": horas,
             "serie": serie, "textos": textos, "ejemplos": ejemplos, "color": COLOR_GRUPOS[k % len(COLOR_GRUPOS)]}
        g["nombre"] = f"Operación {g['letra']}"
        g["rasgos"] = _rasgos_grupo(g, edad_resto)
        g["cobertura"] = n - (principal[2] if principal else 0)
        d["grupos"].append(g)

    # Qué grupo originó o empuja cada narrativa (un grupo empuja solo su narrativa principal).
    for g in d["grupos"]:
        if not g["principal"] or g["principal"][0] not in por_id:
            continue
        narr, postura, k = g["principal"]
        x = por_id[narr]
        en_inicio = next((c for c, gg in x["primeros"] if gg == g["id"]), 0)
        lado = "apoyándola" if postura == "apoya" else "rechazándola"
        if en_inicio >= 15:
            x["rol"] = ("originó", g, f"{en_inicio} de sus primeros 30 comentarios son del grupo")
        elif "rol" not in x:
            x["rol"] = ("empuja", g, f"{_n(k)} comentarios del grupo, {lado}")
    return d


def _grafico_tiempo(d: dict) -> str:
    """Una sola línea de tiempo: cuándo apareció cada narrativa (arriba) y cuándo actuó cada grupo (abajo)."""
    zona, inicio, fin, cubeta = d["zona"], d["inicio"], d["fin"], d["cubeta"]
    ancho, izq, der = 1180, 16, 16
    util = ancho - izq - der
    x = lambda ts: izq + util * (ts - inicio) / (fin - inicio)
    ancho_barra = max(1.5, util * cubeta / (fin - inicio) - 0.6)
    nuevas = sorted((n for n in d["narrativas"] if n["nueva"]), key=lambda n: n["origen"])
    viejas = [n for n in d["narrativas"] if not n["nueva"]]
    niveles = max(1, min(4, len(nuevas)))
    y_puntos = 34 + 26 * niveles + 26
    y_vol, alto_vol = y_puntos + 58, 64
    y_eje = y_vol + alto_vol
    y_grupos, alto_carril = y_eje + 84, 62
    alto = y_grupos + alto_carril * max(len(d["grupos"]), 0) + 8
    color_tema = lambda n: COLOR_TEMAS[n["tema"] % len(COLOR_TEMAS)] if n.get("tema") is not None else "#334155"
    p = [f'<svg viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
         f'aria-label="Línea de tiempo de narrativas y actividad de grupos coordinados">']
    # Días: bandas alternadas y etiquetas.
    paso = max(1, round(len(d["dias"]) / 16))
    for k, dia in enumerate(d["dias"]):
        if k % 2 == 0:
            p.append(f'<rect x="{x(dia):.1f}" y="0" width="{util * 86400 / (fin - inicio):.1f}" height="{alto}" fill="#f1f5f9"/>')
        if k % paso == 0:
            f = datetime.fromtimestamp(dia, tz=timezone(timedelta(seconds=zona)))
            p.append(f'<text x="{x(dia) + 5:.1f}" y="{y_eje + 20}" font-size="14" fill="#475569">{DIAS[f.weekday()]} {f.day}</text>')
    # Volumen total de comentarios, como contexto.
    tope = max(d["serie_total"].values(), default=1)
    for b, n in sorted(d["serie_total"].items()):
        h = max(1.0, alto_vol * n / tope)
        p.append(f'<rect x="{x(inicio + b * cubeta):.1f}" y="{y_eje - h:.1f}" width="{ancho_barra:.1f}" height="{h:.1f}" fill="#94a3b8"/>')
    p.append(f'<line x1="{izq}" y1="{y_eje}" x2="{ancho - der}" y2="{y_eje}" stroke="#475569" stroke-width="1.5"/>')
    p.append(f'<text x="{izq}" y="{y_vol - 8}" font-size="13" font-weight="700" fill="#64748b" letter-spacing="1">TODOS LOS COMENTARIOS</text>')
    p.append(f'<text x="{izq}" y="16" font-size="13" font-weight="700" fill="#64748b" letter-spacing="1">CUÁNDO APARECIÓ CADA NARRATIVA</text>')
    # Narrativas que ya estaban al empezar: un solo punto con la cantidad.
    if viejas:
        cx = x(min(n["origen"] for n in viejas if n["origen"] is not None) if any(n["origen"] for n in viejas) else inicio)
        p.append(f'<circle cx="{cx:.1f}" cy="{y_puntos}" r="15" fill="#fff" stroke="#334155" stroke-width="2.5"/>'
                 f'<text x="{cx:.1f}" y="{y_puntos + 5.5}" font-size="16" font-weight="700" text-anchor="middle" fill="#0f172a">{len(viejas)}</text>'
                 f'<text x="{cx + 24:.1f}" y="{y_puntos + 5.5}" font-size="15.5" fill="#334155">'
                 f'{"narrativa ya circulaba" if len(viejas) == 1 else "narrativas ya circulaban"} el primer día</text>')
    # Narrativas nuevas: punto resaltado, etiqueta escalonada y guía hacia abajo.
    for k, n in enumerate(nuevas):
        cx, c = x(n["origen"]), color_tema(n)
        y_txt = 40 + 26 * (k % niveles)
        derecha = cx > izq + 0.68 * util
        p.append(f'<line x1="{cx:.1f}" y1="{y_txt + 6}" x2="{cx:.1f}" y2="{alto - 4}" stroke="{c}" stroke-width="1.5" stroke-dasharray="5 4"/>')
        p.append(f'<circle cx="{cx:.1f}" cy="{y_puntos}" r="11" fill="#fde68a" stroke="{c}" stroke-width="4"/>')
        p.append(f'<text x="{cx + (-10 if derecha else 10):.1f}" y="{y_txt}" font-size="16" font-weight="700" fill="{c}" '
                 f'text-anchor="{"end" if derecha else "start"}" paint-order="stroke" stroke="#fff" stroke-width="5">'
                 f'{escape(n["nombre"])} · {_fecha(n["origen"], zona)}</text>')
    # Un carril por grupo coordinado.
    for k, g in enumerate(d["grupos"]):
        y0 = y_grupos + k * alto_carril
        tope_g = max(g["serie"].values(), default=1)
        p.append(f'<text x="{izq}" y="{y0 + 4}" font-size="15" font-weight="700" fill="{g["color"]}" paint-order="stroke" stroke="#fff" '
                 f'stroke-width="5">{escape(g["nombre"])} · {_n(g["cuentas"])} cuentas'
                 + (f' · {escape(g["rasgos"])}' if g["rasgos"] else "") + '</text>')
        base = y0 + alto_carril - 14
        p.append(f'<line x1="{izq}" y1="{base}" x2="{ancho - der}" y2="{base}" stroke="#cbd5e1"/>')
        for b, n in sorted(g["serie"].items()):
            h = max(3.0, 32 * n / tope_g)
            p.append(f'<rect x="{x(inicio + b * cubeta):.1f}" y="{base - h:.1f}" width="{max(ancho_barra, 3):.1f}" height="{h:.1f}" fill="{g["color"]}"/>')
    if d["grupos"]:
        p.append(f'<text x="{izq}" y="{y_grupos - 26}" font-size="13" font-weight="700" fill="#64748b" letter-spacing="1">'
                 f'CUÁNDO ACTUARON LOS GRUPOS COORDINADOS</text>')
    return "".join(p) + "</svg>"


def _horas(histograma: list, color: str) -> str:
    tope = max(histograma) or 1
    barras = "".join(f'<rect x="{h * 12}" y="{36 - 34 * n / tope:.1f}" width="10.5" height="{34 * n / tope:.1f}" fill="{color}"/>'
                     for h, n in enumerate(histograma) if n)
    marcas = "".join(f'<text x="{h * 12}" y="52" font-size="12.5" fill="#64748b">{h:02d} h</text>' for h in (0, 6, 12, 18))
    return (f'<svg viewBox="0 0 288 56" width="288" height="56"><line x1="0" y1="36.5" x2="288" y2="36.5" stroke="#cbd5e1"/>'
            f'{barras}{marcas}</svg>')


def _cod(texto) -> str:
    return f"<span class='cod'>{escape(str(texto))}</span>"


def _fila_narrativa(x: dict, d: dict, mayor: int, con_narrativa: int) -> str:
    zona = d["zona"]
    con_postura = x["apoya"] + x["rechaza"]
    chip = (f"<span class='chip nueva'>nueva · día {datetime.fromtimestamp(x['origen'], tz=timezone(timedelta(seconds=zona))).day}</span>"
            if x["nueva"] else "<span class='chip vieja'>desde el inicio</span>")
    color = COLOR_TEMAS[x["tema"] % len(COLOR_TEMAS)] if x.get("tema") is not None else "#334155"
    rol = x.get("rol")
    if rol:
        verbo, g, detalle = rol
        coord = (f"<span class='chip gr' style='background:{g['color']}'>{escape(g['nombre'])} la {verbo}</span>"
                 f"<div class='det' style='margin-top:5px'>{detalle}</div>")
    else:
        de_cobertura = sum(k for k, _g, _a in x["grupos"])
        coord = "<span class='det'>Sin empuje coordinado</span>" + (
            f"<div class='det'>({_n(de_cobertura)} comentarios de cobertura de los grupos)</div>" if de_cobertura else "")
    confianza = (f"<span class='chip {x['confianza']}'>confianza {x['confianza']}</span>" if x["confianza"] else "")
    porque = f"<div class='det' style='margin-top:4px'>{escape(INDICIOS.get(x['indicio'], ''))}</div>" if x["confianza"] and x["indicio"] else ""
    return (
        f"<tr><td class='n'><div class='nom'>{escape(x['nombre'])} {_cod(x['id'])}</div>"
        f"<div class='rep'><i>Frase representativa</i><br>«{escape(x['frase'])}»</div>"
        + "".join(f"<span class='term'>{escape(t)}</span>" for t in x["terminos"]) + "</td>"
        f"<td><div class='fecha'>{_fecha(x['origen'], zona)}</div><div style='margin-top:5px'>{chip}</div></td>"
        f"<td><div class='vol' style='width:{max(4, 100 * x['n'] / max(mayor, 1)):.0f}%;background:{color}'></div>"
        f"<b>{_n(x['n'])}</b> <span class='det'>comentarios ({_pct(x['n'], con_narrativa)})</span></td>"
        f"<td><div class='barra'><div style='width:{100 * x['apoya'] / max(con_postura, 1):.1f}%;background:{VERDE}'></div>"
        f"<div style='width:{100 * x['rechaza'] / max(con_postura, 1):.1f}%;background:{ROJO}'></div></div>"
        f"<div class='det'><b style='color:{VERDE}'>{_pct(x['apoya'], con_postura)}</b> apoya · "
        f"<b style='color:{ROJO}'>{_pct(x['rechaza'], con_postura)}</b> rechaza</div>"
        f"<div style='margin-top:6px'>{confianza}</div>{porque}</td>"
        f"<td>{coord}</td></tr>")


def _html(d: dict, nombre: str, costo: dict) -> str:
    zona = d["zona"]
    con_narrativa = d["total"] - d["ruido"]
    nuevas = [x for x in d["narrativas"] if x["nueva"]]
    periodo = (f"{_fecha(d['t0'], zona, False)} al {_fecha(d['t1'], zona, False)}" if d.get("t0") is not None else "sin fechas")
    frase = (f"En <b>{_n(d['total'])}</b> comentarios circulan <b>{len(d['narrativas'])} narrativas</b>"
             + (f" sobre <b>{len(d['temas'])} temas</b>" if d["temas"] else "")
             + (f"; <b>{len(nuevas)}</b> aparecieron durante el período" if nuevas else "") + ". "
             + (f"<b>{_n(d['coordinadas'])} cuentas</b> ({_pct(d['coordinadas'], d['cuentas'], 1)} del total) actúan coordinadas en "
                f"<b>{d['n_grupos']} {'grupo' if d['n_grupos'] == 1 else 'grupos'}</b>." if d["coordinadas"] else "No se detectaron cuentas coordinadas."))
    hallazgos = []
    con_rol = {x["rol"][1]["id"]: x for x in d["narrativas"] if x.get("rol")}
    for g in d["grupos"]:
        x = con_rol.get(g["id"])
        if x:
            hallazgos.append(
                f"<li><span class='punto' style='background:{g['color']}'></span><b>{escape(g['nombre'])}</b> "
                f"({_n(g['cuentas'])} {escape(g['rasgos'] or 'cuentas')}) <b>{x['rol'][0]}</b> la narrativa "
                f"<b>{escape(x['nombre'])}</b>: «{escape(x['frase'])}»"
                + (f", que apareció el {_fecha(x['origen'], zona)}" if x["nueva"] else "") + f". {_cod(g['id'])} {_cod(x['id'])}</li>")
    for x in nuevas:
        if not x.get("rol"):
            hallazgos.append(f"<li><span class='punto' style='background:#fde68a'></span>La narrativa <b>{escape(x['nombre'])}</b> "
                             f"(«{escape(x['frase'])}») apareció el {_fecha(x['origen'], zona)}, sin empuje coordinado detectable. {_cod(x['id'])}</li>")
    kpis = [(_n(d["total"]), "comentarios"), (len(d["narrativas"]), "narrativas"),
            (_pct(d["ruido"], d["total"]), "es ruido: reacciones y comentarios fuera de tema"),
            (f"{_n(d['coordinadas'])} en {d['n_grupos']}", "cuentas coordinadas, en grupos"),
            (_n(d["cuentas"]), "cuentas activas")]
    if costo:
        kpis += [(f"{str(costo.get('segundos', '?')).replace('.', ',')} s", "para procesar todo"),
                 (f"USD {costo.get('usd_ia', 0):g}".replace(".", ","), f"gastados en IA ({_n(costo.get('tokens_ia', 0))} tokens)")]
    p = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Narrativas y coordinación · {escape(nombre)}</title><style>{CSS}</style></head><body><main>",
         "<h1>Qué circula, desde cuándo y quién lo empuja</h1>",
         f"<p class='sub'>Set <b>{escape(nombre)}</b> · {periodo} · {_n(d['publicaciones'])} publicaciones · datos sintéticos del Desafío QualyData</p>"]
    alertas = [a for a in re.findall(r"ALERTA: [^;]+?(?=; |\.$|\. |$)", str((costo or {}).get("notas", "")))]
    p += [f"<div class='alerta'>{escape(a)}</div>" for a in alertas]
    p.append(f"<div class='resumen'><p class='frase'>{frase}</p>" + (f"<ul>{''.join(hallazgos)}</ul>" if hallazgos else "") + "</div>")
    p.append("<div class='kpis'>" + "".join(f"<div class='kpi'><b>{v}</b><span>{escape(e)}</span></div>" for v, e in kpis) + "</div>")

    # Cómo leer esta página
    p.append(
        "<section class='leer'><h2>Cómo leer esta página</h2><dl>"
        "<div><dt>Narrativa</dt><dd>Una misma idea dicha con distintas palabras por mucha gente. Junta a quienes la sostienen "
        "y a quienes la discuten. Su nombre son sus dos palabras más características; la <b>frase representativa</b> es el "
        "comentario más repetido que la afirma.</dd></div>"
        f"<div><dt>Apoya / rechaza</dt><dd><b style='color:{VERDE}'>Apoya</b>: el comentario afirma la idea. "
        f"<b style='color:{ROJO}'>Rechaza</b>: la niega. Es una <b>estimación</b>: separar los dos bandos es confiable; decidir cuál "
        "de los dos es el que afirma tiene un nivel de confianza que se indica en cada narrativa.</dd></div>"
        "<div><dt>Fecha de origen</dt><dd>El primer momento en que la narrativa aparece con cierta compañía (varios comentarios "
        "en pocas horas). Una narrativa es <b>nueva</b> si aparece después del primer día.</dd></div>"
        "<div><dt>Grupo coordinado</dt><dd>Cuentas que comentan juntas una y otra vez, en la misma publicación y en la misma "
        "media hora, mucho más de lo que explica el azar. Acá se llaman <b>operaciones</b>.</dd></div>"
        "</dl></section>")

    # 1. Línea de tiempo
    if d["narrativas"] and "inicio" in d:
        p.append("<h2><small>1 · Cuándo</small>Línea de tiempo: narrativas nuevas y actividad de los grupos</h2>")
        p.append("<p class='sub'>Cada punto amarillo es una narrativa que apareció durante el período. Abajo, cuándo comentó cada "
                 "grupo coordinado: si una ráfaga cae sobre la línea punteada de una narrativa, ese grupo estuvo en su origen.</p>")
        p.append(f"<div class='caja'>{_grafico_tiempo(d)}</div>")
        p.append(f"<p class='ley'>Cada barra junta {d['cubeta'] // 3600} h. La altura de las barras de cada grupo es relativa a su propia ráfaga más grande.</p>")

    # 2. Narrativas, agrupadas por tema
    p.append("<h2><small>2 · Qué se dice</small>Narrativas" + (", agrupadas por tema" if d["temas"] else "") + "</h2>")
    if d["narrativas"]:
        if d["temas"]:
            p.append("<p class='sub'>Los temas no están escritos a mano: dos narrativas son del mismo tema cuando se discuten en las mismas "
                     "publicaciones, y el nombre del tema sale de los titulares de esas publicaciones.</p>")
        mayor = max(x["n"] for x in d["narrativas"])
        encabezado = ("<table><thead><tr><th>Narrativa</th><th>Apareció</th><th>Volumen</th>"
                      "<th>Apoya / rechaza (estimación)</th><th>Quién la empuja</th></tr></thead><tbody>")
        bloques = ([(k, t, [x for x in d["narrativas"] if x["tema"] == k]) for k, t in enumerate(d["temas"])]
                   if d["temas"] else [(None, None, d["narrativas"])])
        for k, tema, filas in bloques:
            color = COLOR_TEMAS[k % len(COLOR_TEMAS)] if k is not None else "#334155"
            titulo = (f"Tema: {escape(tema)}" if tema else "Todas las narrativas")
            p.append(f"<div class='tema'><div class='tema-t' style='background:{color}'>{titulo}"
                     f"<span>{len(filas)} {'narrativa' if len(filas) == 1 else 'narrativas'} · {_n(sum(x['n'] for x in filas))} comentarios</span></div>"
                     + encabezado + "".join(_fila_narrativa(x, d, mayor, con_narrativa) for x in filas) + "</tbody></table></div>")
        bajas = [x for x in d["narrativas"] if x["confianza"] == "baja"]
        p.append(
            "<div class='nota'><b>Apoya / rechaza es una estimación.</b> Qué comentarios están de un lado y cuáles del otro sale de quién "
            "le contesta a quién, y es confiable. Cuál de los dos lados es el que <i>afirma</i> la idea se decide con indicios. "
            "<b>Confianza alta</b>: indicios fuertes, como que un bando use expresiones de desmentida («mentira», «falso», «nada que ver»), "
            "que una operación empuje un bando, o varios indicios menores que coinciden. <b>Media</b>: indicios más débiles. "
            "<b>Baja</b>: casi no hay indicios; los porcentajes pueden estar invertidos"
            + (f" (pasa en {len(bajas)} de {len(d['narrativas'])} narrativas de este set)" if bajas else "")
            + ". Los tres niveles son un criterio nuestro, no una probabilidad medida.</div>")
    else:
        p.append("<p>No se detectaron narrativas en este set.</p>")

    # 3. Grupos coordinados
    p.append("<h2><small>3 · Quién lo empuja</small>Grupos coordinados</h2>")
    p.append("<p class='sub'>Cuentas que coinciden una y otra vez en la misma publicación y en la misma media hora, mucho más de lo "
             "esperable por azar. <b>Actividad de cobertura</b>: comentarios comunes, sobre cualquier tema, que estas cuentas "
             "hacen para parecer usuarios normales y pasar desapercibidas.</p>")
    if d["grupos"]:
        p.append("<div class='grupos'>")
        for g in d["grupos"]:
            c = g["color"]
            items = []
            if g["principal"]:
                narr, postura, k = g["principal"]
                x = next((y for y in d["narrativas"] if y["id"] == narr), None)
                items.append(f"Empuja <b>{escape(x['nombre'] if x else narr)}</b> {_cod(narr)}: el {_pct(k, g['n'])} de sus comentarios la "
                             f"<b>{'apoyan' if postura == 'apoya' else 'rechazan'}</b>. "
                             + (f"El otro {_pct(g['cobertura'], g['n'])} es actividad de cobertura."
                                if g["cobertura"] >= 0.005 * g["n"] else "No tiene actividad de cobertura."))
            if g["rafagas"] and g["rafagas"][0]:
                items.append(f"Actúa en <b>{g['rafagas'][0]} ráfagas</b>: hasta {g['rafagas'][1]} cuentas del grupo comentando la misma publicación en 30 minutos.")
            if g["edad"] is not None and d.get("edad_resto"):
                items.append(f"Sus cuentas tenían <b>{_n(max(g['edad'], 0))} días</b> de antigüedad al comentar por primera vez "
                             f"(mediana; el resto del set: {_n(d['edad_resto'])} días).")
            franja = _franja_horaria(g["horas"])
            if franja:
                items.append(f"El {_pct(franja[2], 1)} de su actividad ocurre entre las <b>{franja[0]:02d} y las {franja[1]:02d} h</b>.")
            if g["likes"] is not None and d.get("likes_resto"):
                items.append(f"Reciben <b>{_dec(g['likes'])}</b> me gusta por comentario (resto del set: {_dec(d['likes_resto'])}).")
            p.append(f"<div class='grupo' style='border-top-color:{c}'><h3 style='color:{c}'>{escape(g['nombre'])} {_cod(g['id'])}</h3>"
                     f"<div class='rasgo'><b>{_n(g['cuentas'])} cuentas</b>" + (f" · {escape(g['rasgos'])}" if g["rasgos"] else "") + "</div>"
                     f"<div class='det'>{_n(g['n'])} comentarios · activo del {_fecha(g['desde'], zona, False)} al {_fecha(g['hasta'], zona, False)}</div>"
                     f"<ul>{''.join(f'<li>{i}</li>' for i in items)}</ul>")
            if g["textos"]:
                p.append("<div class='mini'>Lo que más repite</div>" + "".join(
                    f"<p class='cita'>«{escape(' '.join(str(t).split()))}» <span class='det'>×{k}</span></p>" for t, k in g["textos"]))
            p.append("<div class='mini'>A qué hora del día comenta</div>" + _horas(g["horas"], c)
                     + f"<div class='mini'>Algunas de sus cuentas</div><div>{' '.join(_cod(e) for e in g['ejemplos'])}</div></div>")
        p.append("</div>")
    else:
        p.append("<p>No se detectaron grupos coordinados en este set.</p>")

    # Pie
    p.append("<footer><b>Cómo se hizo</b><ul>"
             "<li><b>Narrativas:</b> se juntan las frases que son la misma con variaciones chicas y después se usa la conversación: "
             "una respuesta que contradice a un comentario habla de la misma narrativa.</li>"
             "<li><b>Ruido:</b> se aplica una regla observada en los datos de práctica: a los comentarios de ruido (reacciones, "
             "preguntas sueltas, fuera de tema) nadie les responde. Una frase que aparece muchas veces y nunca recibe una respuesta se "
             "trata como ruido. Si un set no cumple esa regla, esta parte pierde precisión.</li>"
             "<li><b>Coordinación:</b> pares de cuentas que coinciden varias veces y en más de una publicación, comparado contra lo "
             "esperable por azar; se conservan solo las mallas densas de cuentas.</li>"
             "<li><b>Costo:</b> sin IA generativa ni servicios externos; todo corre en CPU sobre una base DuckDB local.</li></ul>")
    if costo:
        p.append(f"<p>{escape(str(costo.get('hardware', '')))} · memoria pico {costo.get('memoria_pico_mb', '?')} MB · "
                 f"{escape(str(costo.get('almacenamiento', '')))}.</p>")
    p.append(f"<p>Generado por <code>pipeline/reporte.py</code> el {datetime.now():%d/%m/%Y %H:%M}. Archivo estático: no necesita internet.</p>"
             "</footer></main></body></html>")
    return "\n".join(p)


def generar_reporte(base, salida, costo: dict = None, nombre: str = None) -> Path:
    """Lee la base DuckDB (solo lectura) y escribe el HTML. Devuelve la ruta escrita."""
    salida = Path(salida)
    con = duckdb.connect(str(base), read_only=True)
    try:
        datos = reunir_datos(con)
    finally:
        con.close()
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(_html(datos, nombre or Path(base).stem, costo or {}), encoding="utf-8")
    return salida


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True, help="Archivo DuckDB que dejó el pipeline")
    ap.add_argument("--salida", type=Path, required=True, help="Archivo HTML a escribir")
    ap.add_argument("--costo", type=Path, default=None, help="costo.json de la corrida (opcional)")
    args = ap.parse_args(argv)
    costo = json.loads(args.costo.read_text(encoding="utf-8")) if args.costo and args.costo.is_file() else {}
    ruta = generar_reporte(args.base, args.salida, costo)
    print(f"Reporte en {ruta} ({ruta.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
