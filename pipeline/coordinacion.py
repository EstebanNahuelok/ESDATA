"""Etapa 3: cuentas coordinadas, agrupadas por operación. Se prioriza la precisión.

Una ráfaga sola no prueba nada: lo que delata a una operación es que las MISMAS cuentas coincidan
una y otra vez, mucho más de lo esperable por azar. Pasos:

1. "Celdas" de coincidencia: misma publicación y misma ventana corta de tiempo. Se usan dos canales:
   A) además, misma narrativa y mismo bando (empujan lo mismo);  B) sin mirar el texto.
2. Para cada par de cuentas se suman sus coincidencias, cada una pesada por 1/tamaño de la celda
   (coincidir en una publicación viral casi no suma; coincidir donde hay poca gente suma mucho).
3. Se compara contra lo esperable por azar según cuánto comenta cada cuenta: esperado = n_a * n_b / N.
   El cociente observado/esperado ("lift") no depende del tamaño del set.
4. Grafo con los pares que coinciden varias veces y con lift alto. De ahí se conservan solo las zonas
   densas en triángulos (k-truss): las coincidencias por azar son aristas sueltas, una operación es una malla.
5. Cada componente que queda, con un mínimo de cuentas, es una operación.
"""
import networkx as nx
import numpy as np
from scipy import sparse


def _incidencias(cuenta, claves, n_cuentas):
    """Matriz binaria cuenta x celda (solo celdas con 2+ cuentas) y la misma pesada por 1/raíz(tamaño)."""
    _, celda = np.unique(np.stack(claves, axis=1), axis=0, return_inverse=True)
    celda = celda.ravel()
    M = sparse.coo_matrix((np.ones(len(cuenta), dtype=np.float32), (cuenta, celda)),
                          shape=(n_cuentas, int(celda.max()) + 1 if len(celda) else 0)).tocsr()
    M.data[:] = 1
    tam = np.asarray(M.sum(axis=0)).ravel()
    M = M[:, tam > 1].tocsr()
    return M, (M @ sparse.diags(1 / np.sqrt(tam[tam > 1]))).tocsr()


def _matrices(cuenta, claves_extra, ts, n_cuentas, ventana_s):
    """Las ventanas se calculan dos veces, corridas media ventana, para no partir una ráfaga al medio."""
    return [_incidencias(cuenta, [*claves_extra, (ts + corrimiento) // ventana_s], n_cuentas)
            for corrimiento in (0, ventana_s // 2)]


def pares_sincronizados(matrices, cuenta, n_cuentas, min_veces=2, bloque=4000):
    """Pares (a < b) que coinciden en `min_veces`+ celdas. Devuelve a, b, suma pesada, veces, lift.

    El producto de matrices se hace por bloques de cuentas para no llenar la memoria.
    """
    total = len(cuenta)
    actividad = np.bincount(cuenta, minlength=n_cuentas).astype(np.float64)
    partes = []
    for ini in range(0, n_cuentas, bloque):
        S = V = None
        for M, Mp in matrices:
            if M.shape[1] == 0:
                continue
            s, v = Mp[ini:ini + bloque] @ Mp.T, M[ini:ini + bloque] @ M.T
            S, V = (s, v) if S is None else (S.maximum(s), V.maximum(v))
        if S is None:
            continue
        S, V = S.tocsr(), V.tocsr()
        S.sort_indices()
        V.sort_indices()
        fila = np.repeat(np.arange(S.shape[0]), np.diff(S.indptr)) + ini
        ok = (V.data >= min_veces) & (S.indices > fila)
        partes.append((fila[ok], S.indices[ok].astype(np.int64), S.data[ok].astype(np.float64), V.data[ok]))
    if not partes:
        vacio = np.zeros(0, dtype=np.int64)
        return vacio, vacio, np.zeros(0), np.zeros(0), np.zeros(0)
    a, b, s, veces = (np.concatenate(x) for x in zip(*partes))
    lift = s * total / (actividad[a] * actividad[b])
    return a, b, s, veces, lift


def _camada(creada_ts, miembros, max_rareza=0.02, min_validos=5):
    """Si las cuentas del grupo fueron creadas casi todas juntas, devuelve qué cuentas del set caen en esa
    misma franja de fechas. La franja sale del propio grupo (no hay umbral de antigüedad fijo) y solo
    cuenta como indicio si es rara en el set (menos de `max_rareza` de todas las cuentas)."""
    if creada_ts is None:
        return None
    fechas = creada_ts[miembros]
    fechas = fechas[~np.isnan(fechas)]
    if len(fechas) < min_validos:
        return None
    p10, p90 = np.percentile(fechas, [10, 90])
    margen = max(p90 - p10, 86400.0)
    en_franja = (creada_ts >= p10 - margen) & (creada_ts <= p90 + margen)
    return en_franja if en_franja.mean() <= max_rareza else None


def _ampliar(grupos, matrices, cuenta, n_cuentas, lift_min, creada_ts=None, min_celdas=2, min_miembros=3,
             min_fraccion=1 / 3, rondas=3):
    """Suma a cada grupo las cuentas que coinciden con el grupo como conjunto.

    Una cuenta con poca actividad puede no llegar a repetir con ningún par en particular, pero sí aparecer
    en celdas dominadas por el mismo grupo (3+ miembros que además son un tercio o más de la celda).
    Se acepta si eso pasa 2+ veces, o 1 vez cuando además la cuenta fue creada en la misma franja de fechas
    que el grupo (camada). Siempre con lift alto contra el azar.
    """
    total = len(cuenta)
    actividad = np.maximum(np.bincount(cuenta, minlength=n_cuentas), 1).astype(np.float64)
    grupo_de = -np.ones(n_cuentas, dtype=np.int64)
    for g, miembros in enumerate(grupos):
        grupo_de[miembros] = g
    for _ in range(rondas):
        mejor_lift = np.zeros(n_cuentas)
        mejor_grupo = -np.ones(n_cuentas, dtype=np.int64)
        for g in range(len(grupos)):
            es_miembro = (grupo_de == g).astype(np.float32)
            camada = _camada(creada_ts, np.flatnonzero(grupo_de == g))
            for M, _Mp in matrices:
                if M.shape[1] == 0:
                    continue
                en_celda = M.T @ es_miembro
                tam = np.asarray(M.sum(axis=0)).ravel()
                dominada = (en_celda >= min_miembros) & (en_celda >= min_fraccion * tam)
                if not dominada.any():
                    continue
                veces = M @ dominada.astype(np.float32)
                suma = M @ np.where(dominada, en_celda / tam, 0).astype(np.float32)
                lift = suma * total / (actividad * en_celda[dominada].sum())
                repite = veces >= min_celdas
                if camada is not None:
                    repite |= (veces >= 1) & camada
                cand = repite & (lift >= lift_min) & (lift > mejor_lift) & (grupo_de < 0)
                mejor_lift[cand], mejor_grupo[cand] = lift[cand], g
        nuevos = np.flatnonzero(mejor_grupo >= 0)
        if len(nuevos) == 0:
            break
        grupo_de[nuevos] = mejor_grupo[nuevos]
    return [np.flatnonzero(grupo_de == g).tolist() for g in range(len(grupos))]


def detectar_coordinacion(n_cuentas, cuenta, pub, ts, narrativa, bando, ventana_s=1800, lift_min=40.0,
                          veces_con_texto=2, veces_sin_texto=3, k_truss=4, min_grupo=5, max_aristas=200000,
                          ampliar=True, creada_ts=None, usar_mensaje=True, **_):
    """Devuelve (grupo por cuenta: '' = genuina, detalle para el informe).

    `usar_mensaje=False` apaga el canal A (cuando las narrativas no son confiables, por ejemplo si el set
    no trae hilos de respuestas): queda solo el canal de tiempo, que exige más repeticiones.
    """
    grupo = np.full(n_cuentas, "", dtype=object)
    validos = ~np.isnan(ts)
    cuenta, pub, narrativa, bando = cuenta[validos], pub[validos], narrativa[validos], bando[validos]
    ts = ts[validos].astype(np.int64)
    if len(cuenta) == 0:
        return grupo, {"grupos": 0, "cuentas_marcadas": 0}
    canales = {"solo_tiempo": ([pub], veces_sin_texto)}
    if usar_mensaje:
        canales["mismo_mensaje"] = ([pub, narrativa, bando.astype(np.int64)], veces_con_texto)
    aristas = {}
    detalle = {"canales": {}}
    matrices = {nombre: _matrices(cuenta, claves, ts, n_cuentas, ventana_s) for nombre, (claves, _v) in canales.items()}
    for nombre, (_claves, veces_min) in canales.items():
        a, b, _s, veces, lift = pares_sincronizados(matrices[nombre], cuenta, n_cuentas, min_veces=veces_min)
        ok = lift >= lift_min
        detalle["canales"][nombre] = {"pares_candidatos": int(len(a)), "pares_fuertes": int(ok.sum())}
        for x, y, l in zip(a[ok].tolist(), b[ok].tolist(), lift[ok].tolist()):
            aristas[(x, y)] = max(aristas.get((x, y), 0.0), l)
    if len(aristas) > max_aristas:  # resguardo: quedarse con los pares más fuertes
        aristas = dict(sorted(aristas.items(), key=lambda kv: (-kv[1], kv[0]))[:max_aristas])
    G = nx.Graph()
    G.add_weighted_edges_from((x, y, l) for (x, y), l in sorted(aristas.items()))
    G = nx.k_truss(nx.k_core(G, k_truss - 1), k_truss) if G.number_of_edges() else G
    componentes = sorted((sorted(c) for c in nx.connected_components(G) if len(c) >= min_grupo),
                         key=lambda c: (-len(c), c[0]))
    detalle["cuentas_nucleo"] = int(sum(len(c) for c in componentes))
    if ampliar and componentes:
        canal = "mismo_mensaje" if usar_mensaje else "solo_tiempo"
        componentes = _ampliar(componentes, matrices[canal], cuenta, n_cuentas, lift_min, creada_ts)
    detalle["grupos_detalle"] = []
    for pos, miembros in enumerate(componentes):
        etiqueta = f"g{pos + 1:02d}"
        grupo[miembros] = etiqueta
        detalle["grupos_detalle"].append({"grupo": etiqueta, "cuentas": len(miembros)})
    detalle.update({"aristas": len(aristas), "grupos": len(componentes), "cuentas_marcadas": int((grupo != "").sum())})
    return grupo, detalle
