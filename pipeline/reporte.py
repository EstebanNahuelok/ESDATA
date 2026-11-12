"""Reporte visual: un solo archivo HTML estático, sin internet ni JavaScript, generado desde la base DuckDB.

Responde en una pantalla: qué narrativas circulan, desde cuándo, quién las apoya o rechaza y qué grupos
de cuentas coordinadas las empujan. El pipeline lo genera al final; también se puede regenerar suelto:

    python -m pipeline.reporte --base almacen/practica.duckdb --salida reporte/practica.html --costo salida/practica/costo.json

Es un extra aislado: si falla, la entrega ya está escrita y validada.
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import duckdb

DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
COLOR_GRUPOS = ["#c2410c", "#7c3aed", "#0e7490", "#be185d", "#4d7c0f", "#b45309", "#1d4ed8", "#525252"]
VISTA = """(SELECT c.i, c.ts, c.cuenta, c.pub, c.hora_local, c.me_gusta, c.texto_id, r.narrativa, r.postura, g.grupo
            FROM comentarios c JOIN res_comentarios r USING (i) JOIN res_cuentas g USING (cuenta))"""

CSS = """
*{box-sizing:border-box} body{font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;margin:0;color:#1c1917;background:#fafaf9}
main{max-width:1240px;margin:0 auto;padding:24px 20px 48px} h1{font-size:26px;margin:0 0 4px} h2{font-size:19px;margin:34px 0 4px}
.sub{color:#57534e;margin:0 0 14px} .resumen ul{margin:8px 0 0;padding-left:20px;font-size:15px} .resumen li{margin:3px 0} td:first-child{min-width:330px}
.resumen{font-size:17px;background:#fff;border:1px solid #e7e5e4;border-left:5px solid #1c1917;border-radius:8px;padding:14px 18px;margin:16px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:#fff;border:1px solid #e7e5e4;border-radius:8px;padding:10px 14px} .kpi b{display:block;font-size:24px;line-height:1.2} .kpi span{color:#57534e;font-size:13px}
table{border-collapse:collapse;width:100%;background:#fff;border:1px solid #e7e5e4;border-radius:8px;overflow:hidden}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#57534e;text-align:left;padding:8px 10px;border-bottom:1px solid #e7e5e4;background:#f5f5f4;vertical-align:bottom}
td{padding:9px 10px;border-bottom:1px solid #f0efed;vertical-align:middle} tr:last-child td{border-bottom:0}
.tit{font-weight:600} .frases{color:#78716c;font-size:12.5px} .id{font:12px ui-monospace,Consolas,monospace;color:#78716c}
.fecha{white-space:nowrap} .chip{display:inline-block;font-size:11.5px;font-weight:600;border-radius:99px;padding:1px 8px;margin-top:3px;white-space:nowrap}
.nueva{background:#fef3c7;color:#92400e} .vieja{background:#f5f5f4;color:#78716c} .gr{color:#fff}
.barra{display:flex;height:14px;width:120px;border-radius:3px;overflow:hidden;background:#e7e5e4} .ap{background:#15803d} .re{background:#b91c1c}
.pct{font-size:12px;color:#57534e;white-space:nowrap} .nota{color:#78716c;font-size:12.5px;margin:6px 0 0}
.grupos{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;margin-top:10px}
.grupo{background:#fff;border:1px solid #e7e5e4;border-top:5px solid #444;border-radius:8px;padding:14px 16px}
.grupo h3{margin:0 0 2px;font-size:18px} .grupo ul{margin:8px 0;padding-left:18px} .grupo li{margin:3px 0}
.cita{color:#44403c;font-style:italic;font-size:13.5px;margin:2px 0} .mini{font-size:12px;color:#78716c;margin:8px 0 2px}
.ley span{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px 0 12px;vertical-align:baseline}
footer{margin-top:34px;color:#57534e;font-size:13px;border-top:1px solid #e7e5e4;padding-top:12px} footer li{margin:3px 0}
svg{display:block}
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


def _linea_tiempo(serie: dict, coordinada: dict, n_cubetas: int, cortes_dia: list, marca=None, color="#c2410c",
                  ancho_cubeta=2.5, alto=38) -> str:
    """Barras por cubeta de tiempo: gris = todos los comentarios, color = cuentas coordinadas. Marca = origen."""
    ancho = n_cubetas * ancho_cubeta
    tope = max(serie.values(), default=0) or 1
    partes = [f'<svg width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}" role="img">']
    partes += [f'<line x1="{c * ancho_cubeta}" y1="0" x2="{c * ancho_cubeta}" y2="{alto}" stroke="#e7e5e4"/>' for c in cortes_dia]
    for b, n in sorted(serie.items()):
        h = max(1.0, (alto - 4) * n / tope)
        partes.append(f'<rect x="{b * ancho_cubeta}" y="{alto - h:.1f}" width="{ancho_cubeta - 0.5}" height="{h:.1f}" fill="#a8a29e"/>')
        nc = coordinada.get(b, 0)
        if nc:
            hc = max(2.0, (alto - 4) * nc / tope)
            partes.append(f'<rect x="{b * ancho_cubeta}" y="{alto - hc:.1f}" width="{ancho_cubeta - 0.5}" height="{hc:.1f}" fill="{color}"/>')
    if marca is not None:
        x = marca * ancho_cubeta + ancho_cubeta / 2
        partes.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{alto}" stroke="#1c1917" stroke-width="1.5"/>'
                      f'<circle cx="{x}" cy="4" r="3.5" fill="#1c1917"/>')
    return "".join(partes) + "</svg>"


def _eje_dias(n_cubetas, cortes_dia, etiquetas_dia, ancho_cubeta=2.5) -> str:
    ancho = n_cubetas * ancho_cubeta
    paso = max(1, round(len(cortes_dia) / 14))
    textos = "".join(f'<text x="{c * ancho_cubeta + 2}" y="11" font-size="10" fill="#78716c">{e}</text>'
                     for k, (c, e) in enumerate(zip(cortes_dia, etiquetas_dia)) if k % paso == 0)
    return f'<svg width="{ancho}" height="14" viewBox="0 0 {ancho} 14">{textos}</svg>'


def _horas(histograma: list, color: str) -> str:
    tope = max(histograma) or 1
    barras = "".join(f'<rect x="{h * 9}" y="{30 - 28 * n / tope:.1f}" width="8" height="{28 * n / tope:.1f}" fill="{color}"/>'
                     for h, n in enumerate(histograma) if n)
    marcas = "".join(f'<text x="{h * 9}" y="41" font-size="9" fill="#78716c">{h:02d}</text>' for h in (0, 6, 12, 18))
    return f'<svg width="216" height="43" viewBox="0 0 216 43"><line x1="0" y1="30.5" x2="216" y2="30.5" stroke="#d6d3d1"/>{barras}{marcas}</svg>'


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


def reunir_datos(con) -> dict:
    """Todas las consultas del reporte, sobre las tablas limpias y de resultados de la base."""
    zona = _zona_seg(con)
    uno = lambda sql: con.execute(sql).fetchone()
    total, sin_narr, t0, t1 = uno(f"SELECT count(*), count(*) FILTER (narrativa = 'ninguna'), min(ts), max(ts) FROM {VISTA}")
    n_cuentas, n_coord, n_grupos = uno("SELECT count(*) FILTER (c.cuenta_id <> ''), count(*) FILTER (g.grupo <> ''), count(DISTINCT nullif(g.grupo, '')) FROM cuentas c JOIN res_cuentas g USING (cuenta)")
    n_pubs = uno("SELECT count(*) FROM publicaciones WHERE publicacion_id <> ''")[0]
    d = {"zona": zona, "total": total, "ruido": sin_narr, "t0": t0, "t1": t1, "cuentas": n_cuentas,
         "coordinadas": n_coord, "n_grupos": n_grupos, "publicaciones": n_pubs, "narrativas": [], "grupos": []}
    if not total or t0 is None:
        return d
    cubeta = _cubeta(t0, t1)
    # Las cubetas arrancan en la medianoche local anterior al primer comentario, para que los días queden alineados.
    inicio = (t0 + zona) // 86400 * 86400 - zona
    d.update({"cubeta": cubeta, "inicio": inicio, "n_cubetas": int((t1 - inicio) // cubeta) + 1})
    dias = range(inicio, t1 + 1, 86400)
    d["cortes_dia"] = [int((x - inicio) // cubeta) for x in dias]
    d["etiquetas_dia"] = [str(datetime.fromtimestamp(x, tz=timezone(timedelta(seconds=zona))).day) for x in dias]

    series, series_grupo = {}, {}
    for narr, grupo, b, n in con.execute(f"""SELECT narrativa, grupo, CAST(floor((ts - {inicio}) / {cubeta}) AS INT), count(*)
            FROM {VISTA} WHERE ts IS NOT NULL GROUP BY 1, 2, 3""").fetchall():
        series.setdefault(narr, {})
        series[narr][b] = series[narr].get(b, 0) + n
        if grupo:
            series_grupo.setdefault((narr, grupo), {})[b] = n
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
    for narr, titulo, frases, origen, n in con.execute(
            "SELECT narrativa, titulo, frases_clave, fecha_origen, comentarios FROM res_narrativas ORDER BY comentarios DESC, narrativa").fetchall():
        try:
            origen_ts = int(datetime.fromisoformat(origen).timestamp())
        except (TypeError, ValueError):
            origen_ts = None
        apoya, rechaza = posturas.get(narr, (0, 0))
        d["narrativas"].append({
            "id": narr, "titulo": titulo, "frases": [f for f in (frases or "").split("|") if f], "origen": origen_ts,
            "n": n, "apoya": apoya, "rechaza": rechaza, "serie": series.get(narr, {}),
            "series_grupo": {g: v for (x, g), v in series_grupo.items() if x == narr},
            "grupos": sorted(por_grupo.get(narr, []), reverse=True),
            "primeros": sorted(primeros.get(narr, []), reverse=True),
            "nueva": origen_ts is not None and origen_ts - t0 > 86400})

    media_likes = uno(f"SELECT avg(me_gusta) FROM {VISTA} WHERE grupo = ''")[0]
    edad_resto = uno("""SELECT median((p.ts - c.creada_ts) / 86400.0) FROM cuentas c JOIN res_cuentas g USING (cuenta)
        JOIN (SELECT cuenta, min(ts) ts FROM comentarios GROUP BY 1) p USING (cuenta) WHERE g.grupo = ''""")[0]
    d.update({"likes_resto": media_likes, "edad_resto": edad_resto})
    titulos = {x["id"]: x["titulo"] for x in d["narrativas"]}
    for grupo, cuentas in con.execute("SELECT grupo, count(*) FROM res_cuentas WHERE grupo <> '' GROUP BY 1 ORDER BY 1").fetchall():
        filtro = f"grupo = '{grupo}'"
        n, likes, g0, g1 = uno(f"SELECT count(*), avg(me_gusta), min(ts), max(ts) FROM {VISTA} WHERE {filtro}")
        principal = uno(f"""SELECT narrativa, postura, count(*) FROM {VISTA} WHERE {filtro} AND narrativa <> 'ninguna'
                            GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT 1""")
        edad = uno(f"""SELECT median((p.ts - c.creada_ts) / 86400.0) FROM cuentas c JOIN res_cuentas g USING (cuenta)
            JOIN (SELECT cuenta, min(ts) ts FROM comentarios GROUP BY 1) p USING (cuenta) WHERE g.{filtro}""")[0]
        rafagas = uno(f"""SELECT count(*), max(k) FROM (SELECT count(DISTINCT cuenta) k FROM {VISTA}
            WHERE {filtro} AND ts IS NOT NULL GROUP BY pub, CAST(floor(ts / 1800) AS BIGINT)) WHERE k >= 3""")
        horas = [0] * 24
        for h, k in con.execute(f"SELECT CAST(floor(hora_local) AS INT), count(*) FROM {VISTA} WHERE {filtro} AND hora_local IS NOT NULL GROUP BY 1").fetchall():
            horas[max(0, min(23, h))] = k
        serie = dict(con.execute(f"""SELECT CAST(floor((ts - {inicio}) / {cubeta}) AS INT), count(*) FROM {VISTA}
            WHERE {filtro} AND ts IS NOT NULL GROUP BY 1""").fetchall())
        textos = con.execute(f"""SELECT t.texto, count(*) FROM {VISTA} v JOIN textos t USING (texto_id)
            WHERE {filtro} AND narrativa = ? GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 3""", [principal[0] if principal else ""]).fetchall()
        ejemplos_cuentas = [r[0] for r in con.execute(f"""SELECT c.cuenta_id FROM cuentas c JOIN res_cuentas g USING (cuenta)
            WHERE g.{filtro} ORDER BY 1 LIMIT 6""").fetchall()]
        d["grupos"].append({"id": grupo, "cuentas": cuentas, "n": n, "likes": likes, "desde": g0, "hasta": g1,
                            "principal": principal, "titulo": titulos.get(principal[0], "") if principal else "",
                            "edad": edad, "rafagas": rafagas, "horas": horas, "serie": serie, "textos": textos,
                            "ejemplos": ejemplos_cuentas})
    return d


def _html(d: dict, nombre: str, costo: dict) -> str:
    zona = d["zona"]
    color = {g["id"]: COLOR_GRUPOS[k % len(COLOR_GRUPOS)] for k, g in enumerate(d["grupos"])}
    con_narrativa = d["total"] - d["ruido"]
    nuevas = [x for x in d["narrativas"] if x["nueva"]]
    periodo = (f"{_fecha(d['t0'], zona, False)} al {_fecha(d['t1'], zona, False)}" if d.get("t0") is not None else "sin fechas")
    frase = (f"En <b>{_n(d['total'])}</b> comentarios circulan <b>{len(d['narrativas'])} narrativas</b>"
             + (f"; <b>{len(nuevas)}</b> aparecieron durante el período" if nuevas else "") + ". "
             + (f"<b>{_n(d['coordinadas'])} cuentas</b> ({_pct(d['coordinadas'], d['cuentas'], 1)} del total) actúan coordinadas en "
                f"<b>{d['n_grupos']} grupos</b>." if d["coordinadas"] else "No se detectaron cuentas coordinadas."))
    kpis = [(_n(d["total"]), "comentarios"), (len(d["narrativas"]), "narrativas"),
            (_pct(d["ruido"], d["total"]), "es ruido (reacciones, fuera de tema)"),
            (f"{_n(d['coordinadas'])} en {d['n_grupos']}", "cuentas coordinadas en grupos"),
            (_n(d["cuentas"]), "cuentas activas")]
    if costo:
        kpis += [(f"{str(costo.get('segundos', '?')).replace('.', ',')} s", "para procesar todo"),
                 (f"USD {costo.get('usd_ia', 0):g}".replace(".", ","), f"en IA ({_n(costo.get('tokens_ia', 0))} tokens)")]
    # Qué grupo originó o empuja cada narrativa (un grupo empuja solo su narrativa principal).
    roles = {}
    por_id = {x["id"]: x for x in d["narrativas"]}
    for g in d["grupos"]:
        if not g["principal"] or g["principal"][0] not in por_id:
            continue
        narr, postura, k = g["principal"]
        en_inicio = next((c for c, gg in por_id[narr]["primeros"] if gg == g["id"]), 0)
        lado = "apoyándola" if postura == "apoya" else "rechazándola"
        if en_inicio >= 15:
            roles[narr] = ("originó", g["id"], f"{en_inicio} de los primeros 30 comentarios son del grupo")
        elif narr not in roles:
            roles[narr] = ("empuja", g["id"], f"{_n(k)} comentarios del grupo, {lado}")
    hallazgos = []
    for g in d["grupos"]:
        narr = g["principal"][0] if g["principal"] else None
        if narr in roles and roles[narr][1] == g["id"]:
            x = por_id[narr]
            hallazgos.append(
                f"<li><b style='color:{color[g['id']]}'>{escape(g['id'])}</b> ({_n(g['cuentas'])} cuentas) "
                f"<b>{roles[narr][0]}</b> la narrativa {escape(narr)} «{escape(x['titulo'])}»"
                + (f", que apareció el {_fecha(x['origen'], zona)}" if x["nueva"] else "") + ".</li>")
    for x in nuevas:
        if x["id"] not in roles:
            hallazgos.append(f"<li>La narrativa {escape(x['id'])} «{escape(x['titulo'])}» apareció el {_fecha(x['origen'], zona)}, "
                             f"sin empuje coordinado detectable.</li>")
    p = [f"<!doctype html><html lang='es'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>Narrativas y coordinación · {escape(nombre)}</title><style>{CSS}</style></head><body><main>",
         "<h1>Qué circula, desde cuándo y quién lo empuja</h1>",
         f"<p class='sub'>Set <b>{escape(nombre)}</b> · {periodo} · {_n(d['publicaciones'])} publicaciones · datos sintéticos del Desafío QualyData</p>",
         f"<div class='resumen'>{frase}" + (f"<ul>{''.join(hallazgos)}</ul>" if hallazgos else "") + "</div>",
         "<div class='kpis'>" + "".join(f"<div class='kpi'><b>{v}</b><span>{escape(e)}</span></div>" for v, e in kpis) + "</div>"]

    # 1. Narrativas
    p.append("<h2>1 · Narrativas: qué se dice y desde cuándo</h2>")
    p.append("<p class='sub'>Ordenadas por volumen. La línea negra con punto marca cuándo apareció cada una.</p>")
    if d["narrativas"]:
        eje = _eje_dias(d["n_cubetas"], d["cortes_dia"], d["etiquetas_dia"])
        horas_cubeta = d["cubeta"] // 3600
        p.append("<table><thead><tr><th>Narrativa</th><th>Apareció</th>"
                 f"<th>Comentarios en el tiempo <span style='text-transform:none;letter-spacing:0'>(cada barra = {horas_cubeta} h; números = día del mes)</span>{eje}</th>"
                 "<th>Apoya / rechaza</th><th>Coordinación</th></tr></thead><tbody>")
        for x in d["narrativas"]:
            marca = int((x["origen"] - d["inicio"]) // d["cubeta"]) if x["origen"] is not None else None
            marca = marca if marca is not None and 0 <= marca < d["n_cubetas"] else None
            rol = roles.get(x["id"])
            linea = _linea_tiempo(x["serie"], x["series_grupo"].get(rol[1], {}) if rol else {}, d["n_cubetas"],
                                  d["cortes_dia"], marca, color.get(rol[1], "#444") if rol else "#444")
            de_cobertura = sum(k for k, g, _a in x["grupos"] if not rol or g != rol[1])
            coord = "<span class='pct'>sin empuje coordinado</span>"
            if rol:
                verbo, g, detalle = rol
                coord = (f"<span class='chip gr' style='background:{color.get(g, '#444')}'>{g} la {verbo}</span>"
                         f"<div class='pct'>{detalle}</div>")
            elif de_cobertura:
                coord = f"<span class='pct'>sin empuje coordinado<br>({_n(de_cobertura)} comentarios de cobertura de los grupos)</span>"
            chip = (f"<span class='chip nueva'>nueva: día {datetime.fromtimestamp(x['origen'], tz=timezone(timedelta(seconds=zona))).day}</span>"
                    if x["nueva"] else "<span class='chip vieja'>desde el inicio</span>")
            con_postura = x["apoya"] + x["rechaza"]
            p.append(
                f"<tr><td><span class='id'>{escape(x['id'])}</span> <span class='tit'>{escape(x['titulo'])}</span>"
                f"<div class='frases'>{escape(' · '.join(x['frases']))} — {_n(x['n'])} comentarios ({_pct(x['n'], con_narrativa)})</div></td>"
                f"<td class='fecha'>{_fecha(x['origen'], zona)}<br>{chip}</td><td>{linea}</td>"
                f"<td><div class='barra' title='apoya {_n(x['apoya'])} · rechaza {_n(x['rechaza'])}'>"
                f"<div class='ap' style='width:{100 * x['apoya'] / max(con_postura, 1):.1f}%'></div>"
                f"<div class='re' style='width:{100 * x['rechaza'] / max(con_postura, 1):.1f}%'></div></div>"
                f"<span class='pct'>{_pct(x['apoya'], con_postura)} apoya · {_pct(x['rechaza'], con_postura)} rechaza</span></td>"
                f"<td>{coord}</td></tr>")
        p.append("</tbody></table>")
        p.append("<p class='nota ley'>Barras:<span style='background:#a8a29e'></span>todos los comentarios"
                 "<span style='background:#c2410c'></span>comentarios del grupo que la origina o la empuja (color del grupo)"
                 "<span style='background:#15803d'></span>apoya<span style='background:#b91c1c'></span>rechaza. "
                 "Cada línea de tiempo tiene su propia escala. Qué bando «apoya» se decide con indicios (marcas de desmentida, "
                 "campañas, volumen): es la parte menos segura del análisis.</p>")
    else:
        p.append("<p>No se detectaron narrativas en este set.</p>")

    # 2. Grupos coordinados
    p.append("<h2>2 · Grupos coordinados: quién lo empuja</h2>")
    p.append("<p class='sub'>Cuentas que coinciden una y otra vez en la misma publicación y en la misma media hora, "
             "mucho más de lo esperable por azar.</p>")
    if d["grupos"]:
        p.append("<div class='grupos'>")
        for g in d["grupos"]:
            c = color[g["id"]]
            items = []
            if g["principal"]:
                narr, postura, k = g["principal"]
                items.append(f"Empuja <b>{escape(narr)}</b> «{escape(g['titulo'])}»: {_pct(k, g['n'])} de sus comentarios la "
                             f"<b>{'apoyan' if postura == 'apoya' else 'rechazan'}</b>. El resto es actividad de cobertura.")
            if g["rafagas"] and g["rafagas"][0]:
                items.append(f"Actúa en <b>{g['rafagas'][0]} ráfagas</b>: hasta {g['rafagas'][1]} cuentas del grupo en la misma publicación en 30 minutos.")
            if g["edad"] is not None and d.get("edad_resto"):
                items.append(f"Antigüedad de las cuentas al primer comentario: mediana <b>{_n(max(g['edad'], 0))} días</b> "
                             f"(resto del set: {_n(d['edad_resto'])} días).")
            franja = _franja_horaria(g["horas"])
            if franja:
                items.append(f"Horario: el {_pct(franja[2], 1)} de su actividad ocurre entre las <b>{franja[0]:02d} y las {franja[1]:02d} h</b>.")
            if g["likes"] is not None and d.get("likes_resto"):
                items.append(f"Me gusta por comentario: <b>{_dec(g['likes'])}</b> (resto del set: {_dec(d['likes_resto'])}).")
            p.append(f"<div class='grupo' style='border-top-color:{c}'><h3 style='color:{c}'>{escape(g['id'])} · {_n(g['cuentas'])} cuentas</h3>"
                     f"<div class='pct'>{_n(g['n'])} comentarios · activo del {_fecha(g['desde'], zona, False)} al {_fecha(g['hasta'], zona, False)}</div>"
                     f"<ul>{''.join(f'<li>{i}</li>' for i in items)}</ul>")
            if g["textos"]:
                p.append("<div class='mini'>Lo que más repiten</div>" + "".join(
                    f"<p class='cita'>«{escape(' '.join(str(t).split()))}» <span class='pct'>×{k}</span></p>" for t, k in g["textos"]))
            p.append("<div class='mini'>Cuándo actúan (mismo eje de tiempo que arriba)</div>"
                     + _linea_tiempo(g["serie"], g["serie"], d["n_cubetas"], d["cortes_dia"], None, c, alto=30)
                     + "<div class='mini'>A qué hora del día</div>" + _horas(g["horas"], c)
                     + f"<div class='mini'>Algunas cuentas: <span class='id'>{escape(', '.join(g['ejemplos']))}…</span></div></div>")
        p.append("</div>")
    else:
        p.append("<p>No se detectaron grupos coordinados en este set.</p>")

    # Pie
    p.append("<footer><b>Cómo se hizo</b><ul>"
             "<li><b>Narrativas:</b> se juntan las frases que son la misma con variaciones y después se usa la conversación: una respuesta que contradice habla de la misma narrativa. Las frases a las que nadie responde son ruido.</li>"
             "<li><b>Coordinación:</b> pares de cuentas que coinciden varias veces, comparado contra lo esperable por azar; se conservan solo las mallas densas de cuentas.</li>"
             "<li><b>Costo:</b> sin IA generativa ni servicios externos; todo corre en CPU sobre una base DuckDB local.</li></ul>")
    if costo:
        p.append(f"<p>{escape(str(costo.get('hardware', '')))} · memoria pico {costo.get('memoria_pico_mb', '?')} MB · "
                 f"{escape(str(costo.get('almacenamiento', '')))}.</p>")
    p.append(f"<p>Generado por <code>pipeline/reporte.py</code> el {datetime.now():%d/%m/%Y %H:%M}. Archivo estático: no necesita internet.</p></footer></main></body></html>")
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
