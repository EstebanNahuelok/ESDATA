"""Microgrupos: juntar los textos que son la misma frase con variaciones chicas.

Es un agrupamiento por "líder": se recorren los textos del más repetido al menos repetido; cada uno
se suma al líder más parecido (coseno sobre TF-IDF) o, si no se parece a ninguno, pasa a ser líder.
La cantidad de grupos la deciden los datos (no hay k fijo) y se trabaja por lotes para no usar memoria de más.
"""
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .texto import PALABRAS_VACIAS


def vectorizar(textos: list):
    """TF-IDF de palabras y pares de palabras, filas con norma 1. Devuelve (matriz dispersa, vectorizador)."""
    for min_df in (2, 1):  # con muy pocos textos distintos ningún término se repite: se acepta min_df=1
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=min_df, sublinear_tf=True, stop_words=sorted(PALABRAS_VACIAS),
                              token_pattern=r"(?u)\b\w+\b", dtype=np.float32)
        try:
            return vec.fit_transform(textos).tocsr(), vec
        except ValueError:  # vocabulario vacío (set mínimo o sin texto)
            continue
    return sparse.csr_matrix((len(textos), 1), dtype=np.float32), None


def _centroides(X, etiquetas, pesos, k):
    validos = np.flatnonzero(etiquetas >= 0)
    M = sparse.csr_matrix((pesos[validos].astype(np.float32), (etiquetas[validos], validos)), shape=(k, X.shape[0]))
    return normalize(M @ X, copy=False).tocsr()


def _mas_parecido(X, C, lote):
    """Para cada fila de X, el centroide más parecido y su similitud (por lotes, matriz densa chica)."""
    mejor = np.zeros(X.shape[0], dtype=np.int64)
    sim = np.zeros(X.shape[0], dtype=np.float32)
    Ct = C.T.tocsr()
    for ini in range(0, X.shape[0], lote):
        S = (X[ini:ini + lote] @ Ct).toarray()
        mejor[ini:ini + lote] = S.argmax(axis=1)
        sim[ini:ini + lote] = S.max(axis=1)
    return mejor, sim


def microagrupar(X, pesos: np.ndarray, umbral: float = 0.5, lote: int = 2000, refinar: int = 1,
                 min_peso: int = 30, umbral_absorber: float = 0.25):
    """Devuelve (etiquetas, centroides). Etiqueta -1 = texto sin contenido (vector vacío).

    Los grupos con menos de `min_peso` comentarios (variantes raras de una frase) se disuelven y sus
    textos pasan al grupo grande más parecido, si el parecido llega a `umbral_absorber`.
    """
    n = X.shape[0]
    pesos = np.asarray(pesos)
    con_contenido = np.asarray(X.getnnz(axis=1)).ravel() > 0
    orden = np.lexsort((np.arange(n), -pesos))
    orden = orden[con_contenido[orden]]
    etiquetas = -np.ones(n, dtype=np.int64)
    lideres = []
    for ini in range(0, len(orden), lote):
        idx = orden[ini:ini + lote]
        Xb = X[idx]
        if lideres:
            S = (Xb @ X[lideres].T).toarray()
            mejor, sim = S.argmax(axis=1), S.max(axis=1)
        else:
            mejor, sim = np.zeros(len(idx), dtype=np.int64), np.zeros(len(idx), dtype=np.float32)
        pendientes = np.flatnonzero(sim < umbral)
        etiquetas[idx[sim >= umbral]] = mejor[sim >= umbral]
        if len(pendientes):
            Sb = (Xb[pendientes] @ Xb[pendientes].T).toarray()
            nuevos = []
            for j in range(len(pendientes)):
                if nuevos:
                    s = Sb[j, nuevos]
                    k = int(s.argmax())
                    if s[k] >= umbral:
                        etiquetas[idx[pendientes[j]]] = len(lideres) + k
                        continue
                etiquetas[idx[pendientes[j]]] = len(lideres) + len(nuevos)
                nuevos.append(j)
            lideres.extend(idx[pendientes[nuevos]].tolist())
    k = len(lideres)
    if k == 0:
        return etiquetas, sparse.csr_matrix((0, X.shape[1]), dtype=np.float32)
    C = _centroides(X, etiquetas, pesos, k)
    filas = np.flatnonzero(con_contenido)
    for _ in range(refinar):
        mejor, _sim = _mas_parecido(X[filas], C, lote)
        etiquetas[filas] = mejor
        usados, etiquetas[filas] = np.unique(mejor, return_inverse=True)
        C = _centroides(X, etiquetas, pesos, len(usados))
    peso_grupo = np.bincount(etiquetas[filas], weights=pesos[filas], minlength=C.shape[0])
    grandes = np.flatnonzero(peso_grupo >= min_peso)
    chicos = filas[peso_grupo[etiquetas[filas]] < min_peso]
    if len(grandes) and len(chicos):
        mejor, sim = _mas_parecido(X[chicos], C[grandes], lote)
        mover = sim >= umbral_absorber
        etiquetas[chicos[mover]] = grandes[mejor[mover]]
        usados, etiquetas[filas] = np.unique(etiquetas[filas], return_inverse=True)
        C = _centroides(X, etiquetas, pesos, len(usados))
    return etiquetas, C
