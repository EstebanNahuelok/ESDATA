"""Etapa 2: narrativas, ruido y respuestas que heredan del padre.

Idea (ninguna regla depende del tema de los datos):

1. Microgrupos: textos que son la misma frase con variaciones chicas (ver microgrupos.py).
2. Tipo de cada microgrupo, mirando cómo participa en la conversación:
   - ACUERDO: casi solo aparece como respuesta ("tal cual", "exacto") -> hereda narrativa y postura.
   - RUIDO: aparece muchas veces como comentario suelto y nadie le responde nunca
     (una frase de una narrativa recibe respuestas a una tasa conocida; cero respuestas es muy improbable).
   - CONTENIDO: el resto. Son las frases que sostienen o rechazan una narrativa.
3. Grafo entre microgrupos de contenido: una respuesta con contenido propio contradice al comentario
   que responde, así que ambos hablan de la misma narrativa (regla del enunciado). Las comunidades de ese
   grafo (Louvain; decide solo cuántas hay) son las narrativas, y juntan a quienes apoyan y rechazan.
4. Toda respuesta hereda la narrativa del comentario al que responde.
"""
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
from scipy import sparse

from .microgrupos import _mas_parecido, microagrupar, vectorizar
from .texto import corregir_tipeo, normalizar

CONTENIDO, RUIDO, ACUERDO = 0, 1, 2


@dataclass
class Narrativas:
    micro: np.ndarray            # microgrupo de cada comentario (-1 = sin contenido)
    tipo: np.ndarray             # tipo de cada microgrupo
    comunidad: np.ndarray        # narrativa de cada microgrupo (-1 = ninguna)
    narrativa: np.ndarray        # narrativa de cada comentario (-1 = ruido)
    propio: np.ndarray           # True si el comentario aporta contenido propio (no es un "tal cual")
    ancla: np.ndarray            # comentario de contenido más cercano hacia arriba en el hilo (-1 = no hay)
    aristas: sparse.csr_matrix   # contradicciones entre microgrupos (simétrica, con pesos)
    centroides: sparse.csr_matrix
    vocabulario: np.ndarray
    norm_de_texto: np.ndarray    # índice de texto normalizado para cada texto_id
    normalizados: list           # textos normalizados únicos
    micro_de_norm: np.ndarray
    info: dict = field(default_factory=dict)


def _resolver_hilos(valor: np.ndarray, padre: np.ndarray, pendiente: np.ndarray, max_pasos: int = 64) -> np.ndarray:
    """Propaga `valor` de padres a hijos pendientes, nivel por nivel (tolera hilos largos y ciclos)."""
    valor, pendiente = valor.copy(), pendiente.copy()
    for _ in range(max_pasos):
        listos = np.flatnonzero(pendiente & ~pendiente[np.maximum(padre, 0)] & (padre >= 0))
        if len(listos) == 0:
            break
        valor[listos] = valor[padre[listos]]
        pendiente[listos] = False
    return valor


def _de_micro(valores: np.ndarray, micro: np.ndarray, vacio) -> np.ndarray:
    """valores[micro] tolerando micro = -1 (el llamador lo descarta) y el caso sin ningún microgrupo."""
    if len(valores) == 0:
        return np.full(len(micro), vacio)
    return valores[np.maximum(micro, 0)]


def _comunidades(aristas: sparse.csr_matrix, nodos: np.ndarray, semilla: int, resolucion: float) -> np.ndarray:
    """Louvain sobre el grafo de microgrupos. Devuelve la comunidad de cada microgrupo (-1 = fuera del grafo)."""
    com = -np.ones(aristas.shape[0], dtype=np.int64)
    arriba = sparse.triu(aristas, k=1).tocoo()
    G = nx.Graph()
    grado = np.diff(aristas.indptr)
    G.add_nodes_from(int(n) for n in nodos if grado[n])
    G.add_weighted_edges_from((int(a), int(b), float(w)) for a, b, w in zip(arriba.row, arriba.col, arriba.data))
    if G.number_of_edges() == 0:
        return com
    grupos = nx.community.louvain_communities(G, weight="weight", resolution=resolucion, seed=semilla)
    for c, miembros in enumerate(sorted(grupos, key=lambda s: min(s))):
        com[list(miembros)] = c
    return com


def detectar_narrativas(textos: list, n_textos: np.ndarray, texto_id: np.ndarray, padre: np.ndarray,
                        semilla: int = 0, umbral_micro: float = 0.5, min_peso: int = 30,
                        umbral_parecido: float = 0.25, frac_acuerdo: float = 0.9, alfa_ruido: float = 0.01,
                        resolucion: float = 1.0, min_respuestas: int = 50, umbral_sin_hilos: float = 0.1) -> Narrativas:
    n = len(texto_id)
    es_resp = padre >= 0

    # 1. Textos únicos -> normalizados únicos -> microgrupos.
    norm = corregir_tipeo([normalizar(t or "") for t in textos], list(n_textos))
    normalizados, norm_de_texto = np.unique(np.array(norm, dtype=object).astype(str), return_inverse=True)
    peso_norm = np.bincount(norm_de_texto, weights=n_textos, minlength=len(normalizados))
    X, vec = vectorizar(normalizados.tolist())
    micro_de_norm, C = microagrupar(X, peso_norm, umbral=umbral_micro, min_peso=min_peso, umbral_absorber=umbral_parecido)
    k = C.shape[0]
    micro = micro_de_norm[norm_de_texto][texto_id] if n else np.zeros(0, dtype=np.int64)
    con_micro = micro >= 0

    # 2. Tipo de cada microgrupo según su participación en hilos.
    hijos = np.bincount(padre[es_resp], minlength=n)
    tam = np.bincount(micro[con_micro], minlength=k)
    sueltos = np.bincount(micro[con_micro & ~es_resp], minlength=k)
    resp_recibidas = np.bincount(micro[con_micro & ~es_resp], weights=hijos[con_micro & ~es_resp], minlength=k)
    con_resp = resp_recibidas > 0
    tasa = resp_recibidas[con_resp].sum() / max(sueltos[con_resp].sum(), 1)
    hay_hilos = es_resp.sum() >= min_respuestas and tasa > 0
    tipo = np.full(k, CONTENIDO, dtype=np.int8)
    if hay_hilos:
        frac_resp = 1 - sueltos / np.maximum(tam, 1)
        sin_eco = resp_recibidas <= 0.2 * tasa * sueltos
        seguro = np.exp(-tasa * sueltos) < alfa_ruido
        tipo[sin_eco & (seguro | (sueltos == tam))] = RUIDO
        tipo[frac_resp >= frac_acuerdo] = ACUERDO
    else:
        # Sin hilos no hay evidencia de conversación: el ruido se decide solo por lo corto del texto.
        largo = np.array([len(t.split()) for t in normalizados])
        largo_medio = np.bincount(micro_de_norm[micro_de_norm >= 0], weights=(largo * peso_norm)[micro_de_norm >= 0],
                                  minlength=k) / np.maximum(tam, 1)
        tipo[largo_medio < 5] = RUIDO

    # 3. Comentarios con contenido propio y su "ancla" (a quién contradicen).
    propio = con_micro & (_de_micro(tipo, micro, RUIDO) == CONTENIDO)
    #    El ancla de un comentario con contenido es él mismo; lo que contradice es el ancla de su padre.
    ancla = _resolver_hilos(np.where(propio, np.arange(n), -1), padre, es_resp & ~propio)
    objetivo = np.where(es_resp & propio, ancla[np.maximum(padre, 0)], -1)
    pares = np.flatnonzero(objetivo >= 0)
    a, b = micro[pares], micro[objetivo[pares]]
    a, b = a[a != b], b[a != b]
    aristas = sparse.coo_matrix((np.ones(len(a), dtype=np.float32), (a, b)), shape=(k, k)).tocsr()
    aristas = (aristas + aristas.T).tocsr()

    # 4. Comunidades = narrativas. Los microgrupos de contenido que quedaron fuera del grafo se suman
    #    a la narrativa del microgrupo más parecido en palabras (o quedan sin narrativa).
    nodos = np.flatnonzero(tipo == CONTENIDO)
    comunidad = _comunidades(aristas, nodos, semilla, resolucion) if hay_hilos else -np.ones(k, dtype=np.int64)
    dentro = np.flatnonzero(comunidad >= 0)
    fuera = nodos[comunidad[nodos] < 0]
    if not hay_hilos and len(nodos):
        # Plan B sin hilos: componentes conexas por parecido de palabras entre microgrupos.
        S = (C[nodos] @ C[nodos].T).tocsr()
        S.data = (S.data >= umbral_sin_hilos).astype(np.float32)
        S.eliminate_zeros()
        _, comp = sparse.csgraph.connected_components(S, directed=False)
        comunidad[nodos] = comp
    elif len(fuera) and len(dentro):
        mejor, sim = _mas_parecido(C[fuera], C[dentro], 2000)
        ok = sim >= umbral_parecido
        comunidad[fuera[ok]] = comunidad[dentro[mejor[ok]]]
    sin_narrativa = nodos[comunidad[nodos] < 0]
    if hay_hilos:
        tipo[sin_narrativa[resp_recibidas[sin_narrativa] == 0]] = RUIDO
    huerfanos = np.flatnonzero((tipo == CONTENIDO) & (comunidad < 0))
    comunidad[huerfanos] = (comunidad.max() if k else -1) + 1 + np.arange(len(huerfanos))
    propio = con_micro & (_de_micro(tipo, micro, RUIDO) == CONTENIDO)

    # 5. Narrativa por comentario: los sueltos toman la de su microgrupo; las respuestas heredan del padre.
    propia = np.where(propio, _de_micro(comunidad, micro, -1), -1)
    narrativa = _resolver_hilos(np.where(es_resp, -1, propia), padre, es_resp)
    sin_heredar = es_resp & (narrativa < 0)
    narrativa[sin_heredar] = propia[sin_heredar]

    ancla = _resolver_hilos(np.where(propio, np.arange(n), -1), padre, es_resp & ~propio)
    info = {"textos_normalizados": int(len(normalizados)), "microgrupos": int(k),
            "microgrupos_contenido": int((tipo == CONTENIDO).sum()), "microgrupos_ruido": int((tipo == RUIDO).sum()),
            "microgrupos_acuerdo": int((tipo == ACUERDO).sum()), "tasa_respuestas": float(round(tasa, 4)),
            "usa_hilos": bool(hay_hilos), "narrativas": int(len(np.unique(narrativa[narrativa >= 0]))),
            "comentarios_ruido": int((narrativa < 0).sum())}
    vocabulario = vec.get_feature_names_out() if vec is not None else np.array([], dtype=object)
    return Narrativas(micro=micro, tipo=tipo, comunidad=comunidad, narrativa=narrativa, propio=propio, ancla=ancla,
                      aristas=aristas, centroides=C, vocabulario=vocabulario, norm_de_texto=norm_de_texto,
                      normalizados=normalizados.tolist(), micro_de_norm=micro_de_norm, info=info)
