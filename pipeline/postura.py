"""Etapa 4: postura (apoya / rechaza) dentro de cada narrativa.

1. Dos bandos por narrativa: una respuesta con contenido propio contradice al comentario que responde,
   así que sus microgrupos están en bandos opuestos. Se reparten los microgrupos en dos bandos buscando
   que la mayor cantidad posible de contradicciones quede cruzada.
2. Cuál bando "apoya": no se puede saber solo con la estructura. Se suman indicios generales:
   - el bando que usa marcas de desmentida ("mentira", "falso", "nada que ver"...) es el que rechaza;
   - una campaña coordinada empuja la narrativa (apoya);
   - la afirmación original aparece más como comentario suelto, con más redacciones y más volumen.
3. Un "tal cual" hereda la postura del comentario al que responde.
"""
import re

import numpy as np

from .microgrupos import _mas_parecido
from .narrativas import CONTENIDO, Narrativas

MARCAS_RECHAZO = ["mentira", "falso", "falsa", "verso", "fake", "trucho", "trucha", "nada que ver", "no es cierto",
                  "no es verdad", "desmint", "desment", "invent", "dejen de", "no hubo", "nadie va a", "sin pruebas",
                  "no es para tanto", "otra vez con", "bolazo", "chamuyo"]
_RE_RECHAZO = re.compile("|".join(MARCAS_RECHAZO))


def _dos_bandos(W: np.ndarray) -> np.ndarray:
    """Reparte nodos en +1/-1 para que las aristas (contradicciones) queden entre bandos. 0 = sin aristas."""
    m = W.shape[0]
    grado = W.sum(axis=1)
    s = np.zeros(m)
    if m == 0 or grado.max() == 0:
        return s
    pendientes = set(np.flatnonzero(grado > 0).tolist())
    while pendientes:
        campo = W @ s
        cand = sorted(pendientes)
        i = max(cand, key=lambda j: (abs(campo[j]), grado[j], -j))
        s[i] = 1.0 if campo[i] == 0 else -np.sign(campo[i])
        pendientes.discard(i)
    for _ in range(20):
        cambios = 0
        for i in np.argsort(-grado, kind="stable"):
            campo = W[i] @ s
            if grado[i] > 0 and campo != 0 and s[i] != -np.sign(campo):
                s[i] = -np.sign(campo)
                cambios += 1
        if cambios == 0:
            break
    return s


def calcular_bandos(nar: Narrativas) -> np.ndarray:
    """Bando (+1/-1; 0 = desconocido) de cada microgrupo de contenido, dentro de su narrativa."""
    k = len(nar.tipo)
    bando = np.zeros(k)
    for c in np.unique(nar.comunidad[nar.comunidad >= 0]):
        nodos = np.flatnonzero((nar.comunidad == c) & (nar.tipo == CONTENIDO))
        W = nar.aristas[nodos][:, nodos].toarray()
        s = _dos_bandos(W)
        # Microgrupos sin contradicciones: toman el bando del microgrupo más parecido en palabras.
        con, sin = np.flatnonzero(s != 0), np.flatnonzero(s == 0)
        if len(con) and len(sin):
            mejor, _ = _mas_parecido(nar.centroides[nodos[sin]], nar.centroides[nodos[con]], 2000)
            s[sin] = s[con[mejor]]
        bando[nodos] = s
    return bando


def _entropia_efectiva(conteos: np.ndarray) -> float:
    p = conteos[conteos > 0] / max(conteos.sum(), 1)
    return float(np.exp(-(p * np.log(p)).sum())) if len(p) else 1.0


def orientar(nar: Narrativas, bando: np.ndarray, texto_id: np.ndarray, padre: np.ndarray,
             coordinado: np.ndarray = None) -> tuple:
    """Decide qué bando apoya en cada narrativa. Devuelve (signo por comunidad, detalle por comunidad)."""
    n_com = int(nar.comunidad.max()) + 1 if len(nar.comunidad) else 0
    signo = np.ones(n_com)
    detalle = {}
    marca_norm = np.array([bool(_RE_RECHAZO.search(t)) for t in nar.normalizados], dtype=bool)
    marca = marca_norm[nar.norm_de_texto][texto_id] if len(texto_id) else np.zeros(0, dtype=bool)
    idx = np.flatnonzero(nar.propio)
    com = nar.comunidad[nar.micro[idx]]
    lado = bando[nar.micro[idx]]
    suelto = padre[idx] < 0
    coord = coordinado[idx] if coordinado is not None else np.zeros(len(idx), dtype=bool)
    for c in range(n_com):
        est = {}
        for nombre, s in (("mas", 1.0), ("menos", -1.0)):
            sel = (com == c) & (lado == s)
            tot = int(sel.sum())
            est[nombre] = {"n": tot, "marca": float(marca[idx[sel]].mean()) if tot else 0.0,
                           "sueltos": int(suelto[sel].sum()), "coord": float(coord[sel].mean()) if tot else 0.0,
                           "variedad": _entropia_efectiva(np.bincount(nar.micro[idx[sel]])) if tot else 1.0}
        a, b = est["mas"], est["menos"]
        if a["n"] == 0 or b["n"] == 0:
            signo[c] = 1.0 if a["n"] >= b["n"] else -1.0
            detalle[c] = {"puntaje": 0.0, "motivo": "un solo bando"}
            continue
        pa, pb = a["sueltos"] / a["n"], b["sueltos"] / b["n"]
        p = (a["sueltos"] + b["sueltos"]) / (a["n"] + b["n"])
        ee = np.sqrt(max(p * (1 - p) * (1 / a["n"] + 1 / b["n"]), 1e-12))
        partes = {"marcas": 20 * (b["marca"] - a["marca"]), "campana": 20 * (a["coord"] - b["coord"]),
                  "sueltos": 0.5 * float(np.clip((pa - pb) / ee, -3, 3)),
                  "variedad": float(np.log(a["variedad"] / b["variedad"])),
                  "volumen": float(np.log(a["n"] / b["n"]))}
        puntaje = sum(partes.values())
        signo[c] = 1.0 if puntaje >= 0 else -1.0
        detalle[c] = {"puntaje": round(puntaje, 3), **{k: round(v, 3) for k, v in partes.items()}}
    return signo, detalle


def postura_por_comentario(nar: Narrativas, bando: np.ndarray, signo: np.ndarray, padre: np.ndarray) -> np.ndarray:
    """+1 apoya, -1 rechaza, 0 sin postura (ruido)."""
    n = len(nar.micro)
    post = np.zeros(n)
    idx = np.flatnonzero(nar.propio)
    post[idx] = bando[nar.micro[idx]] * signo[nar.comunidad[nar.micro[idx]]]
    # Respuestas con contenido propio pero sin bando conocido: lo opuesto de lo que contradicen.
    for _ in range(8):
        dudosos = np.flatnonzero(nar.propio & (post == 0) & (padre >= 0))
        if len(dudosos) == 0:
            break
        objetivo = nar.ancla[padre[dudosos]]
        nuevo = np.where(objetivo >= 0, -post[np.maximum(objetivo, 0)], 0)
        if not (nuevo != 0).any():
            break
        post[dudosos] = nuevo
    # Respuestas de acuerdo: misma postura que el comentario de contenido más cercano hacia arriba.
    eco = np.flatnonzero(~nar.propio & (padre >= 0) & (nar.ancla >= 0))
    post[eco] = post[nar.ancla[eco]]
    post[(nar.narrativa >= 0) & (post == 0)] = 1.0
    post[nar.narrativa < 0] = 0.0
    return post
