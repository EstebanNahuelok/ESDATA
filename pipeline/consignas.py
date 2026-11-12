"""Etapa 3b: consignas de las operaciones coordinadas.

Una frase que dice casi solo una operación (una consigna) casi no recibe respuestas de gente de afuera, así que la
conversación no alcanza para ubicarla: queda donde la llevan dos o tres respuestas, o como ruido porque nadie le
contesta. Regla general, que solo se aplica cuando ya se detectaron grupos:

1. Consigna: familia de frases (microgrupo) en la que más de la mitad de los comentarios son de cuentas de un mismo
   grupo, dicha por varias cuentas de ese grupo.
2. Narrativa: la de las familias de afuera (las que no son consignas) con las que discute. Si no discute con nadie
   de afuera, la de la familia de afuera más parecida en palabras. Si no se parece a ninguna, queda como estaba.
3. Bando: una operación no discute consigo misma. Todas sus consignas dentro de una narrativa van del mismo lado:
   el opuesto al de las familias de afuera que las contradicen o, si nadie las contradice, el de las más parecidas.
"""
import numpy as np
from scipy import sparse

from .narrativas import ACUERDO, CONTENIDO, Narrativas, _por_comentario, recalcular_comentarios


def reubicar_consignas(nar: Narrativas, bando: np.ndarray, grupo_cuenta: np.ndarray, cuenta: np.ndarray, padre: np.ndarray,
                       min_cuentas: int = 3, umbral_parecido: float = 0.25) -> tuple:
    """Cambia en `nar` el tipo y la narrativa de las consignas y devuelve (bando por microgrupo, resumen)."""
    k = len(nar.tipo)
    info = {"consignas": 0, "familias_movidas": 0, "comentarios_movidos": 0}
    bando = bando.copy()
    etiquetas, g_de_cuenta = np.unique(grupo_cuenta.astype(str), return_inverse=True)
    sel = np.flatnonzero((nar.micro >= 0) & (grupo_cuenta[cuenta] != "")) if len(cuenta) else np.zeros(0, dtype=np.int64)
    if k == 0 or len(sel) == 0:
        return bando, info
    m, g = nar.micro[sel], g_de_cuenta[cuenta[sel]]
    forma = (k, len(etiquetas))
    comentarios = sparse.coo_matrix((np.ones(len(sel)), (m, g)), shape=forma).toarray()
    pares = np.unique(np.stack([m, cuenta[sel]], axis=1), axis=0)
    cuentas = sparse.coo_matrix((np.ones(len(pares)), (pares[:, 0], g_de_cuenta[pares[:, 1]])), shape=forma).toarray()
    tam = np.bincount(nar.micro[nar.micro >= 0], minlength=k)
    grupo_de = comentarios.argmax(axis=1)
    fila = np.arange(k)
    es_consigna = (2 * comentarios[fila, grupo_de] > tam) & (cuentas[fila, grupo_de] >= min_cuentas) & (nar.tipo != ACUERDO)
    afuera = (nar.tipo == CONTENIDO) & (nar.comunidad >= 0) & ~es_consigna
    consignas, anclas = np.flatnonzero(es_consigna), np.flatnonzero(afuera)
    info["consignas"] = int(len(consignas))
    if len(consignas) == 0 or len(anclas) == 0:
        return bando, info

    # Conversación con gente de afuera: respuestas con contenido entre una consigna y una familia de afuera, en
    # cualquiera de los dos sentidos, cuando el comentario de la familia de afuera lo escribió una cuenta no marcada.
    # (Las respuestas entre cuentas de la operación no son discusión: son la operación dándose la razón.)
    tipo = nar.tipo.copy()
    tipo[consignas] = CONTENIDO
    propio, _narrativa, ancla = _por_comentario(tipo, nar.comunidad, nar.micro, padre)
    marcada = grupo_cuenta[cuenta] != ""
    hijo = np.flatnonzero(propio & (padre >= 0))
    arriba = ancla[padre[hijo]]
    hijo, arriba = hijo[arriba >= 0], arriba[arriba >= 0]
    pares = []
    for propia, otra in ((hijo, arriba), (arriba, hijo)):
        ok = es_consigna[nar.micro[propia]] & afuera[nar.micro[otra]] & ~marcada[otra]
        pares.append(np.stack([nar.micro[propia[ok]], nar.micro[otra[ok]]], axis=1))
    pares = np.concatenate(pares)
    discusion = sparse.coo_matrix((np.ones(len(pares), dtype=np.float32), (pares[:, 0], pares[:, 1])), shape=(k, k)).tocsr()

    # Narrativa de cada consigna: primero la conversación con gente de afuera; si no hay, las palabras.
    parecido = (nar.centroides[consignas] @ nar.centroides[anclas].T).toarray()
    destino = -np.ones(len(consignas), dtype=np.int64)
    votos = np.zeros(len(consignas))
    for j, c in enumerate(consignas):
        vecinos, pesos = discusion[c].indices, discusion[c].data
        if len(vecinos):
            por_narrativa = np.bincount(nar.comunidad[vecinos], weights=pesos)
            destino[j] = int(por_narrativa.argmax())
            en_destino = nar.comunidad[vecinos] == destino[j]
            votos[j] = -(pesos[en_destino] * bando[vecinos[en_destino]]).sum()
        elif parecido[j].max() >= umbral_parecido:
            destino[j] = nar.comunidad[anclas[int(parecido[j].argmax())]]

    # Bando: uno solo por operación y narrativa.
    antes_narrativa = nar.narrativa.copy()
    for grupo, narrativa in sorted({(int(grupo_de[c]), int(d)) for c, d in zip(consignas, destino) if d >= 0}):
        suyas = np.flatnonzero((grupo_de[consignas] == grupo) & (destino == narrativa))
        voto = votos[suyas].sum()
        if voto == 0:
            en_narrativa = nar.comunidad[anclas] == narrativa
            mas_parecida = anclas[en_narrativa][parecido[suyas][:, en_narrativa].argmax(axis=1)]
            voto = (tam[consignas[suyas]] * bando[mas_parecida]).sum()
        lado = 1.0 if voto >= 0 else -1.0
        for c in consignas[suyas]:
            if nar.tipo[c] != CONTENIDO or nar.comunidad[c] != narrativa or bando[c] != lado:
                info["familias_movidas"] += 1
            nar.tipo[c], nar.comunidad[c], bando[c] = CONTENIDO, narrativa, lado
    recalcular_comentarios(nar, padre)
    info["comentarios_movidos"] = int((nar.narrativa != antes_narrativa).sum())
    return bando, info
