"""Dashboard del reporte: una sola pantalla con pestañas (violeta sobre oscuro o claro).

Es el formato definitivo de reporte/<entrega>.html: barra de KPIs y 4 pestañas grandes — Resumen,
Línea de tiempo, Narrativas, Operaciones — cada una ocupando toda el área visible. Las pestañas y el
modo claro/oscuro funcionan solo con CSS (radio inputs): el archivo sigue siendo estático, sin
JavaScript ni internet.

    python -m pipeline.reporte_dashboard --base almacen/final.duckdb --salida reporte/entrega.html --costo entrega/costo.json
"""
import argparse
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import duckdb

from .reporte import DIAS, _fecha, _franja_horaria, _n, _pct, reunir_datos

PAL = {
    "bg": "#08080d", "panel": "#11111c", "panel2": "#0c0c16", "line": "#28284a",
    "ink": "#eceaf6", "dim": "#8f8bb0", "faint": "#4a4763",
    "acc": "#8b5cf6", "acc2": "#c084fc",
    "apoya": "#34d399", "rechaza": "#f87171", "nueva": "#f0abfc",
    "temas": ["#8b5cf6", "#d946ef", "#6366f1", "#a21caf", "#7c3aed", "#c026d3", "#6d28d9"],
    "grupos": ["#a78bfa", "#f472b6", "#fbbf24", "#818cf8", "#e879f9", "#34d399", "#f87171"],
    "conf": {"alta": "#34d399", "media": "#fbbf24", "baja": "#f87171"},
}
TABS = [("resumen", "Resumen"), ("timeline", "Línea de tiempo"), ("narrativas", "Narrativas"),
        ("operaciones", "Operaciones")]


def _color_tema(x: dict, pal: dict) -> str:
    return pal["temas"][x["tema"] % len(pal["temas"])] if x.get("tema") is not None else pal["faint"]


def _trunc(texto: str, largo: int) -> str:
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


# --------------------------------------------------------------------------------------------------
# Gráficos SVG (grandes: ocupan una pestaña completa)
# --------------------------------------------------------------------------------------------------
def _chart_timeline(d: dict, pal: dict) -> str:
    """Línea de tiempo: cuándo apareció cada narrativa (puntos) y cuándo actuó cada grupo (carriles)."""
    zona, inicio, fin, cubeta = d["zona"], d["inicio"], d["fin"], d["cubeta"]
    ancho, izq, der = 1180, 10, 10
    util = ancho - izq - der
    x = lambda ts: izq + util * (ts - inicio) / (fin - inicio)
    ancho_barra = max(1.5, util * cubeta / (fin - inicio) - 0.5)
    nuevas = sorted((n for n in d["narrativas"] if n["nueva"]), key=lambda n: n["origen"])
    viejas = [n for n in d["narrativas"] if not n["nueva"]]
    niveles = max(1, min(4, len(nuevas)))
    y_puntos = 30 + 24 * niveles + 20
    y_vol, alto_vol = y_puntos + 52, 58
    y_eje = y_vol + alto_vol
    y_grupos, alto_carril = y_eje + 80, 58
    alto = y_grupos + alto_carril * max(len(d["grupos"]), 0) + 6
    p = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Línea de tiempo">']
    paso = max(1, round(len(d["dias"]) / 14))
    for k, dia in enumerate(d["dias"]):
        if k % 2 == 0:
            p.append(f'<rect x="{x(dia):.1f}" y="0" width="{util * 86400 / (fin - inicio):.1f}" height="{alto}" '
                     f'fill="var(--band,rgba(255,255,255,.05))"/>')
        if k % paso == 0:
            f = datetime.fromtimestamp(dia, tz=timezone(timedelta(seconds=zona)))
            p.append(f'<text x="{x(dia) + 4:.1f}" y="{y_eje + 18}" font-size="13" fill="{pal["dim"]}">'
                     f'{DIAS[f.weekday()]} {f.day}</text>')
    tope = max(d["serie_total"].values(), default=1)
    for b, n in sorted(d["serie_total"].items()):
        h = max(1.0, alto_vol * n / tope)
        p.append(f'<rect x="{x(inicio + b * cubeta):.1f}" y="{y_eje - h:.1f}" width="{ancho_barra:.1f}" '
                 f'height="{h:.1f}" fill="{pal["faint"]}"/>')
    p.append(f'<line x1="{izq}" y1="{y_eje}" x2="{ancho - der}" y2="{y_eje}" stroke="{pal["dim"]}" stroke-width="1.4"/>')
    p.append(f'<text x="{izq}" y="{y_vol - 8}" font-size="12.5" font-weight="700" fill="{pal["dim"]}" '
             f'letter-spacing="1">COMENTARIOS / {d["cubeta"] // 3600} h</text>'
             f'<text x="{izq}" y="15" font-size="12.5" font-weight="700" fill="{pal["dim"]}" letter-spacing="1">'
             f'APARICIÓN DE NARRATIVAS</text>')
    if viejas:
        cx = x(min(n["origen"] for n in viejas if n["origen"] is not None)
               if any(n["origen"] for n in viejas) else inicio)
        p.append(f'<circle cx="{cx:.1f}" cy="{y_puntos}" r="14" style="fill:var(--svg-halo,#101018)" stroke="{pal["dim"]}" '
                 f'stroke-width="2.5"/><text x="{cx:.1f}" y="{y_puntos + 5}" font-size="14.5" font-weight="700" '
                 f'text-anchor="middle" style="fill:var(--svg-ink,#eceaf6)">{len(viejas)}</text>'
                 f'<text x="{cx + 22:.1f}" y="{y_puntos + 5}" font-size="14" fill="{pal["dim"]}">'
                 f'ya circulaban el día 1</text>')
    for k, n in enumerate(nuevas):
        cx, c = x(n["origen"]), _color_tema(n, pal)
        y_txt = 34 + 24 * (k % niveles)
        derecha = cx > izq + 0.68 * util
        p.append(f'<line x1="{cx:.1f}" y1="{y_txt + 5}" x2="{cx:.1f}" y2="{alto - 4}" stroke="{c}" '
                 f'stroke-width="1.6" stroke-dasharray="5 4" opacity="0.7"/>'
                 f'<circle cx="{cx:.1f}" cy="{y_puntos}" r="11" fill="{pal["nueva"]}" stroke="{c}" stroke-width="4"/>'
                 f'<text x="{cx + (-11 if derecha else 11):.1f}" y="{y_txt}" font-size="15" font-weight="700" fill="{c}" '
                 f'text-anchor="{"end" if derecha else "start"}" paint-order="stroke" '
                 f'style="stroke:var(--svg-halo,#101018);stroke-width:4.5">'
                 f'{escape(_trunc(n["nombre"], 28))} · {_fecha(n["origen"], zona)}</text>')
    for k, g in enumerate(d["grupos"]):
        y0 = y_grupos + k * alto_carril
        tope_g = max(g["serie"].values(), default=1)
        base = y0 + alto_carril - 12
        p.append(f'<rect x="{izq}" y="{y0 - 5}" width="11" height="11" rx="2" fill="{g["color"]}"/>'
                 f'<text x="{izq + 17}" y="{y0 + 4.5}" font-size="14.5" font-weight="700" fill="{g["color"]}" '
                 f'paint-order="stroke" style="stroke:var(--svg-halo,#101018);stroke-width:4.5">'
                 f'{escape(g["nombre"])} · '
                 f'{_n(g["cuentas"])} cuentas' + (f' · {escape(g["rasgos"])}' if g["rasgos"] else "") + '</text>')
        p.append(f'<line x1="{izq}" y1="{base}" x2="{ancho - der}" y2="{base}" stroke="{pal["line"]}"/>')
        for b, n in sorted(g["serie"].items()):
            h = max(2.5, 34 * n / tope_g)
            p.append(f'<rect x="{x(inicio + b * cubeta):.1f}" y="{base - h:.1f}" width="{max(ancho_barra, 3):.1f}" '
                     f'height="{h:.1f}" fill="{g["color"]}"/>')
    if d["grupos"]:
        p.append(f'<text x="{izq}" y="{y_grupos - 28}" font-size="12.5" font-weight="700" fill="{pal["dim"]}" '
                 f'letter-spacing="1">ACTIVIDAD DE LOS GRUPOS COORDINADOS</text>')
    return "".join(p) + "</svg>"


def _chart_rank(d: dict, c: dict, pal: dict) -> str:
    """Ranking horizontal: cada narrativa con su volumen, su split apoya/rechaza y quién la empuja."""
    zona = d["zona"]
    filas = sorted(d["narrativas"], key=lambda x: -x["n"])
    ancho, fila, top = 1100, 50, 30
    alto = top + fila * len(filas) + 8
    mayor = max((x["n"] for x in filas), default=1)
    x_nom, x_bar, x_num, x_split = 225, 245, 660, 725
    w_bar, w_split = x_num - x_bar - 16, 115
    letra_de = {x["id"]: x["rol"][1] for x in d["narrativas"] if x.get("rol")}
    p = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Ranking de narrativas">']
    for tx, txt, anchor in ((x_nom, "NARRATIVA", "end"), (x_bar, "COMENTARIOS", "start"),
                            (x_split + w_split / 2, "APOYA / RECHAZA", "middle"),
                            (880, "CONF.", "middle"), (940, "ORIGEN", "middle"), (1040, "OP", "middle")):
        p.append(f'<text x="{tx}" y="18" font-size="12" font-weight="700" fill="{pal["dim"]}" '
                 f'letter-spacing="1" text-anchor="{anchor}">{txt}</text>')
    for i, x in enumerate(filas):
        y = top + i * fila
        ym = y + fila / 2
        color = _color_tema(x, pal)
        con_postura = x["apoya"] + x["rechaza"]
        w = w_bar * x["n"] / mayor
        titulo = f"{x['nombre']} · «{x['frase']}»" if x.get("frase") else x["nombre"]
        p.append(f'<g><title>{escape(titulo)}</title>'
                 f'<text x="12" y="{ym + 5}" font-size="15" font-weight="700" fill="{pal["faint"]}" '
                 f'font-family="ui-monospace,monospace">{i + 1:02d}</text>'
                 f'<text x="{x_nom}" y="{ym + 5}" font-size="15.5" font-weight="600" style="fill:var(--svg-ink,#eceaf6)" '
                 f'text-anchor="end">{escape(_trunc(x["nombre"], 22))}</text>'
                 f'<rect x="{x_bar}" y="{ym - 10}" width="{w_bar}" height="20" rx="4" fill="var(--band,rgba(255,255,255,.05))"/>'
                 f'<rect x="{x_bar}" y="{ym - 10}" width="{max(3, w):.1f}" height="20" rx="4" fill="{color}"/>'
                 f'<text x="{x_num - 10}" y="{ym + 5}" font-size="15.5" font-weight="700" text-anchor="end" '
                 f'style="fill:var(--svg-ink,#eceaf6)" font-family="ui-monospace,monospace">{_n(x["n"])}</text>'
                 f'<text x="{x_num - 4}" y="{ym + 4.5}" font-size="12" fill="{pal["dim"]}">'
                 f'{_pct(x["n"], c["con_narrativa"])}</text>')
        apoyo_w = w_split * x["apoya"] / max(con_postura, 1)
        p.append(f'<rect x="{x_split}" y="{ym - 8}" width="{w_split}" height="16" rx="3" '
                 f'fill="var(--band,rgba(255,255,255,.05))"/>')
        if con_postura:
            p.append(f'<rect x="{x_split}" y="{ym - 8}" width="{apoyo_w:.1f}" height="16" fill="{pal["apoya"]}"/>'
                     f'<rect x="{x_split + apoyo_w:.1f}" y="{ym - 8}" width="{w_split - apoyo_w:.1f}" height="16" '
                     f'fill="{pal["rechaza"]}"/>'
                     f'<text x="{x_split + w_split + 8}" y="{ym + 4}" font-size="13" fill="{pal["dim"]}">'
                     f'{_pct(x["apoya"], con_postura)}</text>')
        if x["confianza"]:
            p.append(f'<circle cx="880" cy="{ym}" r="7" fill="{pal["conf"][x["confianza"]]}">'
                     f'<title>confianza {x["confianza"]}</title></circle>')
        if x["nueva"]:
            p.append(f'<text x="940" y="{ym + 4.5}" font-size="12.5" font-weight="700" text-anchor="middle" '
                     f'fill="{pal["nueva"]}">día {datetime.fromtimestamp(x["origen"], tz=timezone(timedelta(seconds=zona))).day} · nuevo</text>')
        else:
            p.append(f'<text x="940" y="{ym + 4.5}" font-size="12.5" text-anchor="middle" fill="{pal["faint"]}">día 1</text>')
        g = letra_de.get(x["id"])
        if g:
            verbo = "originó" if x["rol"][0] == "originó" else "empuja"
            p.append(f'<rect x="1024" y="{ym - 13}" width="30" height="26" rx="5" fill="{g["color"]}">'
                     f'<title>{escape(g["nombre"])} la {verbo}</title></rect>'
                     f'<text x="1039" y="{ym + 5}" font-size="14" font-weight="800" text-anchor="middle" '
                     f'fill="#0a0a0f">{g["letra"]}</text>')
        else:
            p.append(f'<text x="1039" y="{ym + 5}" font-size="14" text-anchor="middle" fill="{pal["faint"]}">—</text>')
        p.append('</g>')
    return "".join(p) + "</svg>"


def _chart_donut(d: dict, c: dict, pal: dict) -> str:
    """Donut: composición de los comentarios por tema + ruido."""
    total = max(d["total"], 1)
    segs = []
    for k, t in enumerate(d["temas"]):
        n = sum(x["n"] for x in d["narrativas"] if x["tema"] == k)
        if n:
            segs.append((t, n, pal["temas"][k % len(pal["temas"])]))
    if not segs:
        segs.append(("narrativas", c["con_narrativa"], pal["acc"]))
    segs.append(("ruido / fuera de tema", d["ruido"], "#2e2b45"))
    r, circ = 62, 2 * math.pi * 62
    cx, cy = 82, 82
    p = [f'<svg viewBox="0 0 380 184" role="img" aria-label="Composición de comentarios">']
    acum = 0.0
    for _t, n, color in segs:
        frac = n / total
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="26" '
                 f'stroke-dasharray="{frac * circ:.2f} {circ:.2f}" stroke-dashoffset="{-acum * circ:.2f}" '
                 f'transform="rotate(-90 {cx} {cy})"/>')
        acum += frac
    p.append(f'<text x="{cx}" y="{cy - 5}" font-size="21" font-weight="800" text-anchor="middle" '
             f'style="fill:var(--svg-ink,#eceaf6)" font-family="ui-monospace,monospace">{_n(total)}</text>'
             f'<text x="{cx}" y="{cy + 16}" font-size="11.5" text-anchor="middle" fill="{pal["dim"]}">comentarios</text>')
    for i, (t, n, color) in enumerate(segs):
        y = 36 + i * 27
        p.append(f'<rect x="176" y="{y - 10}" width="12" height="12" rx="2" fill="{color}"/>'
                 f'<text x="194" y="{y}" font-size="14.5" style="fill:var(--svg-ink,#eceaf6)">{escape(_trunc(t, 18))}</text>'
                 f'<text x="372" y="{y}" font-size="14.5" font-weight="700" text-anchor="end" fill="{pal["dim"]}" '
                 f'font-family="ui-monospace,monospace">{_pct(n, total)}</text>')
    return "".join(p) + "</svg>"


def _chart_postura(d: dict, pal: dict) -> str:
    """Postura global: barra apoya/rechaza de todos los comentarios con narrativa + confianza."""
    ap = sum(x["apoya"] for x in d["narrativas"])
    re_ = sum(x["rechaza"] for x in d["narrativas"])
    tot = max(ap + re_, 1)
    conf = {k: sum(1 for x in d["narrativas"] if x["confianza"] == k) for k in ("alta", "media", "baja")}
    w_ap = 380 * ap / tot
    p = ['<svg viewBox="0 0 380 120" role="img" aria-label="Postura global">',
         f'<rect x="0" y="20" width="380" height="30" rx="6" fill="var(--band,rgba(255,255,255,.05))"/>',
         f'<rect x="0" y="20" width="{w_ap:.1f}" height="30" rx="6" fill="{pal["apoya"]}"/>',
         f'<rect x="{w_ap:.1f}" y="20" width="{380 - w_ap:.1f}" height="30" rx="6" fill="{pal["rechaza"]}"/>',
         f'<text x="6" y="14" font-size="14" font-weight="700" fill="{pal["apoya"]}">'
         f'{_pct(ap, tot)} apoya · {_n(ap)}</text>',
         f'<text x="374" y="14" font-size="14" font-weight="700" text-anchor="end" fill="{pal["rechaza"]}">'
         f'{_n(re_)} · {_pct(re_, tot)} rechaza</text>',
         f'<text x="0" y="80" font-size="11.5" fill="{pal["dim"]}" letter-spacing="1">CONFIANZA DE LA ESTIMACIÓN</text>']
    xx = 0
    for k in ("alta", "media", "baja"):
        if conf[k]:
            p.append(f'<circle cx="{xx + 7}" cy="102" r="6" fill="{pal["conf"][k]}"/>'
                     f'<text x="{xx + 19}" y="107" font-size="14" style="fill:var(--svg-ink,#eceaf6)">{conf[k]} {k}</text>')
            xx += 19 + 11 * len(f"{conf[k]} {k}") + 24
    return "".join(p) + "</svg>"


def _horas_spark(histograma: list, color: str, pal: dict, ancho=380, alto=52) -> str:
    tope = max(histograma) or 1
    w = ancho / 24
    barras = "".join(f'<rect x="{h * w:.1f}" y="{alto - 16 - (alto - 22) * n / tope:.1f}" width="{w - 2:.1f}" '
                     f'height="{(alto - 22) * n / tope:.1f}" fill="{color}"/>' for h, n in enumerate(histograma) if n)
    marcas = "".join(f'<text x="{h * w:.0f}" y="{alto - 2}" font-size="11" fill="{pal["dim"]}">{h:02d} h</text>'
                     for h in (0, 6, 12, 18))
    return (f'<svg viewBox="0 0 {ancho} {alto}" class="spark"><line x1="0" y1="{alto - 15.5}" x2="{ancho}" '
            f'y2="{alto - 15.5}" stroke="{pal["line"]}"/>{barras}{marcas}</svg>')


# --------------------------------------------------------------------------------------------------
# Datos comunes
# --------------------------------------------------------------------------------------------------
def _comun(d: dict, nombre: str, costo: dict, pal: dict) -> dict:
    for k, g in enumerate(d["grupos"]):
        g["color"] = pal["grupos"][k % len(pal["grupos"])]
    por_id = {g["id"]: g for g in d["grupos"]}
    for x in d["narrativas"]:  # rol guarda el dict original del grupo: reapuntar al recoloreado
        if x.get("rol"):
            x["rol"] = (x["rol"][0], por_id[x["rol"][1]["id"]], x["rol"][2])
    zona = d["zona"]
    con_narrativa = d["total"] - d["ruido"]
    nuevas = [x for x in d["narrativas"] if x["nueva"]]
    periodo = (f"{_fecha(d['t0'], zona, False)} → {_fecha(d['t1'], zona, False)}"
               if d.get("t0") is not None else "sin fechas")
    kpis = [(_n(d["total"]), "comentarios"), (len(d["narrativas"]), "narrativas"),
            (f"{len(nuevas)} nuevas", "en el período"),
            (_pct(d["ruido"], d["total"]), "ruido"),
            (f"{_n(d['coordinadas'])}", "cuentas coord."),
            (d["n_grupos"], "operaciones")]
    if costo:
        kpis += [(f"{str(costo.get('segundos', '?')).replace('.', ',')} s", "procesamiento"),
                 (f"USD {costo.get('usd_ia', 0):g}".replace(".", ","), "costo IA")]
    hallazgos = []
    con_rol = {x["rol"][1]["id"]: x for x in d["narrativas"] if x.get("rol")}
    for g in d["grupos"]:
        x = con_rol.get(g["id"])
        if x:
            hallazgos.append({"color": g["color"], "quien": g["nombre"], "verbo": x["rol"][0],
                              "que": x["nombre"], "cuando": _fecha(x["origen"], zona) if x["nueva"] else "",
                              "frase": x.get("frase", "")})
    for x in nuevas:
        if not x.get("rol"):
            hallazgos.append({"color": pal["nueva"], "quien": "", "verbo": "nadie empuja",
                              "que": x["nombre"], "cuando": _fecha(x["origen"], zona),
                              "frase": x.get("frase", "")})
    return {"zona": zona, "con_narrativa": con_narrativa, "nuevas": nuevas, "periodo": periodo,
            "kpis": kpis, "hallazgos": hallazgos, "nombre": nombre,
            "sub": f"set {nombre} · {periodo} · {_n(d['publicaciones'])} publicaciones",
            "alertas": re.findall(r"ALERTA: [^;]+?(?=; |\.$|\. |$)", str((costo or {}).get("notas", "")))}


def _kpis(c: dict) -> str:
    return ("<div class='kpis'>" + "".join(
        f"<div class='kpi'><b>{v}</b><span>{escape(e)}</span></div>" for v, e in c["kpis"]) + "</div>")


def _feed(c: dict) -> str:
    items = "".join(
        f"<div class='h'><i style='background:{h['color']}'></i><div>"
        + (f"<b>{escape(h['quien'])}</b> " if h["quien"] else "")
        + f"{escape(h['verbo'])} <b>{escape(h['que'])}</b>"
        + (f"<span>«{escape(_trunc(h['frase'], 90))}»</span>" if h.get("frase") else "")
        + (f"<span class='f'>{escape(h['cuando'])}</span>" if h["cuando"] else "") + "</div></div>"
        for h in c["hallazgos"])
    return items or "<p class='vacio'>Sin hallazgos destacados.</p>"


def _ops(d: dict, pal: dict) -> str:
    """Tarjetas grandes de cada operación: cifras + sparkline 24 h + qué empuja + lo que más repite."""
    out = []
    for g in d["grupos"]:
        c = g["color"]
        stats = [f"<b>{_n(g['cuentas'])}</b><span>cuentas</span>",
                 f"<b>{_n(g['n'])}</b><span>comentarios</span>"]
        if g["rafagas"] and g["rafagas"][0]:
            stats.append(f"<b>{g['rafagas'][0]}</b><span>ráfagas</span>")
        franja = _franja_horaria(g["horas"])
        if franja:
            stats.append(f"<b>{franja[0]:02d}–{franja[1]:02d} h</b><span>franja</span>")
        if g["edad"] is not None and d.get("edad_resto"):
            viejo = "antiguas" if g["edad"] >= 0.05 * d["edad_resto"] else "nuevas"
            stats.append(f"<b>{_n(max(g['edad'], 0))} d</b><span>edad · {viejo}</span>")
        target = ""
        if g["principal"]:
            narr, postura, k = g["principal"]
            x = next((y for y in d["narrativas"] if y["id"] == narr), None)
            target = (f"<div class='op-t'>▸ empuja <b>{escape(x['nombre'] if x else narr)}</b> "
                      f"<span>{_pct(k, g['n'])} la {'apoya' if postura == 'apoya' else 'rechaza'}</span></div>")
        citas = "".join(f"<p class='cita'>«{escape(_trunc(' '.join(str(t).split()), 80))}» "
                        f"<em>×{k}</em></p>" for t, k in (g["textos"] or [])[:3])
        out.append(f"<div class='op' style='--c:{c}'><div class='op-h'><b>{escape(g['nombre'])}</b>"
                   f"<span>{escape(g['id'])}</span></div><div class='op-s'>{''.join(f'<div>{s}</div>' for s in stats)}</div>"
                   f"{target}<div class='mini'>Actividad por hora del día</div>{_horas_spark(g['horas'], c, pal)}"
                   + (f"<div class='mini'>Lo que más repite</div>{citas}" if citas else "") + "</div>")
    return "".join(out) or "<p class='vacio'>Sin grupos coordinados detectados.</p>"


def _alertas(c: dict) -> str:
    return "".join(f"<div class='alerta'>⚠ {escape(a)}</div>" for a in c["alertas"])


def _legend(pal: dict) -> str:
    return (f"<footer><span><i style='background:{pal['apoya']}'></i>apoya</span>"
            f"<span><i style='background:{pal['rechaza']}'></i>rechaza</span>"
            f"<span><i style='background:{pal['nueva']};border-radius:50%'></i>narrativa nueva</span>"
            f"<span><i style='background:{pal['conf']['alta']};border-radius:50%'></i><i style='background:{pal['conf']['media']};border-radius:50%'></i><i style='background:{pal['conf']['baja']};border-radius:50%'></i>confianza alta/media/baja</span>"
            f"<span><i style='background:{pal['grupos'][0]}'></i>letra = operación que la empuja</span>"
            f"<em>estático · sin IA · DuckDB local · {datetime.now():%d/%m/%Y %H:%M}</em></footer>")


def _pagina(css: str, titulo: str, cuerpo: str) -> str:
    return ("<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{escape(titulo)}</title><style>{css}</style></head><body>{cuerpo}</body></html>")


def _vistas(d, c, pal) -> str:
    """Las 4 vistas grandes, una por pestaña."""
    resumen = (_kpis(c)
               + "<div class='fila3'>"
               + f"<section class='panel'><div class='ph'>Hallazgos</div><div class='pb'>{_feed(c)}</div></section>"
               + f"<section class='panel'><div class='ph'>Composición</div><div class='pb'>{_chart_donut(d, c, pal)}</div></section>"
               + f"<section class='panel'><div class='ph'>Postura global</div><div class='pb'>{_chart_postura(d, pal)}</div></section>"
               + "</div>")
    timeline = (f"<section class='panel'><div class='ph'>Aparición de narrativas y actividad coordinada"
                f"<span>cada barra = {d['cubeta'] // 3600} h</span></div>"
                f"<div class='pb'>{_chart_timeline(d, pal)}</div></section>")
    narrativas = (f"<section class='panel'><div class='ph'>Ranking de narrativas · volumen y postura"
                  f"<span>pasá el mouse sobre una fila para ver la frase representativa</span></div>"
                  f"<div class='pb'>{_chart_rank(d, c, pal)}</div></section>")
    operaciones = f"<div class='ops-grid'>{_ops(d, pal)}</div>"
    return "".join(f"<section class='vista' id='v{i}'>{v}</section>"
                   for i, v in enumerate([resumen, timeline, narrativas, operaciones]))


def _radios() -> str:
    return "".join(f"<input class='ti' type='radio' name='tab' id='tab{i}'{' checked' if i == 0 else ''}>"
                   for i in range(len(TABS)))


def _tabbar() -> str:
    return ("<div class='tabbar'>" + "".join(f"<label for='tab{i}'>{t}</label>"
                                            for i, (_k, t) in enumerate(TABS)) + "</div>")


def _radios_tema() -> str:
    """Dos radios ocultos (mismo mecanismo que las pestañas): oscuro por defecto, claro opcional."""
    return ("<input class='ti' type='radio' name='tema' id='tema-o' checked>"
            "<input class='ti' type='radio' name='tema' id='tema-c'>")


def _tema_toggle() -> str:
    return ("<span class='tema'><label class='t-o' for='tema-o'>◐ oscuro</label>"
            "<label class='t-c' for='tema-c'>claro</label></span>")


# Reglas CSS de las pestañas: mismo mecanismo en las 4 variantes.
CSS_TABS = (".ti{position:fixed;opacity:0;pointer-events:none}"
            ".vista{display:none;flex:1;min-height:0;flex-direction:column;gap:14px;overflow:hidden}"
            + "".join(f"#tab{i}:checked~.vistas>.vista:nth-child({i + 1}){{display:flex}}" for i in range(len(TABS)))
            + "".join(f"#tab{i}:checked~.tabbar label:nth-of-type({i + 1}){{color:var(--ink);"
                      f"background:var(--tabon);border-color:var(--tabline);box-shadow:0 0 18px -6px var(--acc)}}"
                      for i in range(len(TABS))))


# --------------------------------------------------------------------------------------------------
# CSS compartido + 4 pieles
# --------------------------------------------------------------------------------------------------
CSS_CORE = """
*{box-sizing:border-box}
body{margin:0;color:var(--ink);background:var(--bg);font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;min-width:0;min-height:0}
.ph{padding:10px 16px;border-bottom:1px solid var(--line);font:700 12px ui-monospace,Consolas,monospace;letter-spacing:.12em;color:var(--dim);text-transform:uppercase;display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex:none}
.ph span{letter-spacing:.02em;text-transform:none;font-weight:400}
.pb{padding:14px 16px;flex:1;min-height:0;overflow:auto;display:flex;flex-direction:column}
.pb>svg{width:100%;height:100%;min-height:0;display:block;margin:auto}
.pb .spark{width:100%;height:56px;margin:0}
.kpis{display:grid;gap:10px;flex:none}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px}
.kpi b{display:block;font:800 27px/1.1 ui-monospace,Consolas,monospace;letter-spacing:-.02em;color:var(--ink);white-space:nowrap}
.kpi span{color:var(--dim);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}
.fila3{flex:1;min-height:0;display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:14px}
.ops-grid{flex:1;min-height:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px;overflow:auto}
.op{border:1px solid var(--line);border-top:3px solid var(--c,#8b5cf6);border-radius:12px;padding:16px 20px;background:var(--panel2)}
.op-h{display:flex;justify-content:space-between;align-items:baseline}
.op-h b{color:var(--c,#c084fc);font-size:19px}
.op-h span{font:700 12px ui-monospace,monospace;color:var(--dim)}
.op-s{display:flex;gap:20px;flex-wrap:wrap;margin:10px 0 4px}
.op-s b{display:block;font:800 20px/1.1 ui-monospace,monospace;color:var(--ink)}
.op-s span{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em}
.op-t{font-size:14px;color:var(--dim);margin:8px 0 4px}
.op-t b{color:var(--ink)} .op-t span{color:var(--c,#c084fc)}
.mini{font:700 11px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:12px 0 4px}
.cita{font-size:13px;color:var(--ink);margin:5px 0;padding-left:10px;border-left:3px solid var(--line)}
.cita em{font-style:normal;color:var(--dim);font-size:11.5px}
.h{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-bottom:1px dashed var(--line);font-size:14px;color:var(--dim)}
.h:last-child{border:0}
.h i{width:10px;height:10px;border-radius:3px;margin-top:4px;flex:none}
.h b{color:var(--ink)}
.h span{display:block;font-size:12.5px;color:var(--dim);margin-top:2px}
.h .f{font-family:ui-monospace,monospace;font-size:11.5px;color:var(--faint)}
.alerta{background:rgba(248,113,113,.1);border:1px solid #f87171;color:var(--alert-ink,#fca5a5);border-radius:8px;padding:9px 14px;font-weight:600;font-size:13px;margin:6px 0;flex:none}
.vacio{color:var(--dim);font-size:13px}
footer{display:flex;gap:18px;flex-wrap:wrap;align-items:center;color:var(--dim);font-size:11.5px;padding:10px 2px 0;flex:none}
footer i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px}
footer em{margin-left:auto;font-style:normal;font-family:ui-monospace,monospace;color:var(--faint)}
header{display:flex;align-items:center;gap:14px;padding:4px 2px;flex:none}
.brand{display:flex;align-items:center;gap:9px;font-size:15px}
.brand i{width:11px;height:11px;border-radius:3px;background:linear-gradient(135deg,var(--acc),#d946ef);box-shadow:0 0 12px var(--acc)}
.brand span{color:var(--dim);font-size:12.5px}
.meta{margin-left:auto;font:12px ui-monospace,Consolas,monospace;color:var(--dim)}
.tabbar{display:flex;gap:8px;flex:none}
.tabbar label{cursor:pointer;padding:8px 18px;border-radius:9px;border:1px solid transparent;font-size:14px;font-weight:600;color:var(--dim);user-select:none}
.tabbar label:hover{color:var(--ink)}
"""

CSS = CSS_CORE + CSS_TABS + """
:root{--bg:#090911;--panel:#11111c;--panel2:#0c0c16;--line:#28284a;--ink:#f0eefb;--dim:#9792bd;--faint:#514d75;--acc:#7c3aed;--tabon:#2a1b52;--tabline:#7c3aed;--tabbg:#0d0d18;--kline:#33245e;--glow:rgba(124,58,237,.15)}
body{background:var(--bg) radial-gradient(1400px 700px at 50% -20%,var(--glow),transparent 65%) fixed;padding:14px 30px}
.wall{max-width:1680px;margin:0 auto;height:calc(100vh - 28px);display:flex;flex-direction:column;gap:12px}
.vistas{flex:1;min-height:0;display:flex}
.tabbar{justify-content:center;background:var(--tabbg);border:1px solid var(--line);border-radius:99px;padding:5px;width:max-content;margin:0 auto}
.tabbar label{border-radius:99px;padding:7px 22px}
.kpis{grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.kpi{background:linear-gradient(160deg,rgba(139,92,246,.16),transparent 70%),var(--panel);border-color:var(--kline)}
.kpi b{font-size:30px}
.tema{display:flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:2px;gap:2px;margin-left:12px;flex:none}
.tema label{cursor:pointer;padding:4px 13px;border-radius:99px;font:700 10.5px ui-monospace,Consolas,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);user-select:none}
#tema-o:checked~.wall .tema .t-o,#tema-c:checked~.wall .tema .t-c{background:var(--tabon);color:var(--ink)}
body:has(>#tema-c:checked){--bg:#f5f3fb;--panel:#fff;--panel2:#f7f5fd;--line:#dcd6ef;--ink:#241f38;--dim:#5f5a7d;--faint:#a39dc4;--acc:#6d28d9;--tabon:#e9e0fc;--tabline:#6d28d9;--tabbg:#fff;--kline:#e2d8f8;--glow:rgba(124,58,237,.1);--svg-ink:#241f38;--svg-halo:#fff;--band:rgba(38,32,70,.07);--alert-ink:#b91c1c;color-scheme:light}
"""


# --------------------------------------------------------------------------------------------------
# El dashboard
# --------------------------------------------------------------------------------------------------
def _dashboard(d, c, pal):
    cuerpo = (_radios_tema() + f"<div class='wall'>{_radios()}<header><div class='brand'><i></i><b>ESDATA</b></div>"
              f"<div class='meta'>{escape(c['sub'])}</div>{_tema_toggle()}</header>"
              f"{_alertas(c)}{_tabbar()}<div class='vistas'>{_vistas(d, c, pal)}</div>{_legend(pal)}</div>")
    return _pagina(CSS, f"ESDATA · monitor de narrativas · {c['nombre']}", cuerpo)


def generar_dashboard(base, salida, costo: dict = None, nombre: str = None) -> Path:
    """Lee la base DuckDB (solo lectura) y escribe el dashboard HTML en `salida`."""
    con = duckdb.connect(str(base), read_only=True)
    try:
        d = reunir_datos(con)
    finally:
        con.close()
    datos = {**d, "grupos": [dict(g) for g in d["grupos"]]}  # _comun pinta colores por paleta
    c = _comun(datos, nombre or Path(base).stem, costo or {}, PAL)
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(_dashboard(datos, c, PAL), encoding="utf-8")
    return salida


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", type=Path, required=True, help="Archivo DuckDB que dejó el pipeline")
    ap.add_argument("--salida", type=Path, default=Path("reporte") / "entrega.html",
                    help="Archivo HTML a escribir (por defecto reporte/entrega.html)")
    ap.add_argument("--costo", type=Path, default=None, help="costo.json de la corrida (opcional)")
    args = ap.parse_args(argv)
    costo = json.loads(args.costo.read_text(encoding="utf-8")) if args.costo and args.costo.is_file() else {}
    ruta = generar_dashboard(args.base, args.salida, costo)
    print(f"{ruta} ({ruta.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
