"""Etapa final: describir cada narrativa y escribir los cuatro archivos de la entrega."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .narrativas import CONTENIDO, Narrativas
from .origen import a_iso, fecha_origen


def describir_narrativas(nar: Narrativas, bando: np.ndarray, signo: np.ndarray, textos: list, n_textos: np.ndarray,
                         ts: np.ndarray, zona_seg: int, n_frases: int = 6, origen_min_comentarios: int = 5,
                         origen_ventana_h: float = 12.0) -> tuple:
    """Devuelve (etiqueta por comunidad, filas para narrativas.csv). Etiquetas n01, n02... por tamaño."""
    n_com = int(nar.comunidad.max()) + 1 if len(nar.comunidad) else 0
    tam_com = np.bincount(nar.narrativa[nar.narrativa >= 0], minlength=n_com)
    orden = [c for c in np.argsort(-tam_com, kind="stable") if tam_com[c] > 0]
    etiquetas = np.full(n_com, "", dtype=object)
    k = len(nar.tipo)
    tam_micro = np.bincount(nar.micro[nar.micro >= 0], minlength=k)
    micro_de_texto = nar.micro_de_norm[nar.norm_de_texto]
    # Centroide de palabras por narrativa, para elegir frases clave que la distingan de las demás.
    C = nar.centroides
    perfiles = np.zeros((n_com, C.shape[1]), dtype=np.float32)
    for m in np.flatnonzero((nar.tipo == CONTENIDO) & (nar.comunidad >= 0)):
        perfiles[nar.comunidad[m]] += tam_micro[m] * C[m].toarray().ravel()
    normas = np.linalg.norm(perfiles, axis=1, keepdims=True)
    perfiles = perfiles / np.where(normas > 0, normas, 1)
    media = perfiles[orden].mean(axis=0) if orden else 0
    con_fecha = ts[~np.isnan(ts)]
    respaldo = int(con_fecha.min()) if len(con_fecha) else 0
    filas = []
    for pos, c in enumerate(orden):
        etiquetas[c] = f"n{pos + 1:02d}"
        micros = np.flatnonzero((nar.comunidad == c) & (nar.tipo == CONTENIDO))
        a_favor = micros[bando[micros] * signo[c] > 0]
        candidatos = a_favor if len(a_favor) else micros
        titulo = ""
        if len(candidatos):
            principal = candidatos[np.argmax(tam_micro[candidatos])]
            ids = np.flatnonzero(micro_de_texto == principal)
            if len(ids):
                titulo = " ".join(str(textos[ids[np.argmax(n_textos[ids])]]).split())
        frases = []
        for j in np.argsort(-(perfiles[c] - media), kind="stable")[:4 * n_frases]:
            termino = str(nar.vocabulario[j]) if j < len(nar.vocabulario) else ""
            if termino and perfiles[c][j] > 0 and not any(termino in f or f in termino for f in frases):
                frases.append(termino)
            if len(frases) == n_frases:
                break
        origen = fecha_origen(ts[(nar.narrativa == c) & ~np.isnan(ts)], minimo=origen_min_comentarios,
                              ventana_s=int(origen_ventana_h * 3600))
        # Sin ninguna fecha válida en la narrativa se usa la primera fecha del set (el formato exige una fecha).
        filas.append({"narrativa": etiquetas[c], "titulo": titulo or etiquetas[c],
                      "frases_clave": "|".join(frases) or etiquetas[c],
                      "fecha_origen": a_iso(origen if origen is not None else respaldo, zona_seg),
                      "comentarios": int(tam_com[c]), "sin_fecha": origen is None})
    return etiquetas, filas


def escribir_entrega(con, entrega: Path, etiqueta_com: np.ndarray, narrativa: np.ndarray, postura: np.ndarray,
                     filas_narrativas: list, grupo_cuenta: np.ndarray) -> None:
    """Guarda los resultados en la base y exporta los CSV de la entrega (orden estable por id)."""
    entrega = Path(entrega)
    entrega.mkdir(parents=True, exist_ok=True)
    etiq = np.where(narrativa >= 0, etiqueta_com[np.maximum(narrativa, 0)] if len(etiqueta_com) else "", "ninguna")
    post = np.where(narrativa < 0, "", np.where(postura < 0, "rechaza", "apoya"))
    res_com = pd.DataFrame({"i": np.arange(len(narrativa), dtype=np.int32), "narrativa": etiq, "postura": post})
    res_cta = pd.DataFrame({"cuenta": np.arange(len(grupo_cuenta), dtype=np.int32), "grupo": grupo_cuenta})
    res_nar = pd.DataFrame(filas_narrativas, columns=["narrativa", "titulo", "frases_clave", "fecha_origen", "comentarios"])
    for nombre, df in (("res_comentarios", res_com), ("res_cuentas", res_cta), ("res_narrativas", res_nar)):
        con.register("_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {nombre} AS SELECT * FROM _df")
        con.unregister("_df")

    def exportar(sql: str, archivo: str):
        ruta = str(entrega / archivo).replace("'", "''")
        con.execute(f"COPY ({sql}) TO '{ruta}' (FORMAT csv, HEADER, DELIMITER ',')")

    exportar("""SELECT c.comentario_id, r.narrativa, nullif(r.postura, '') AS postura
                FROM comentarios c JOIN res_comentarios r USING (i) ORDER BY c.comentario_id""", "comentarios.csv")
    exportar("SELECT narrativa, titulo, frases_clave, fecha_origen FROM res_narrativas ORDER BY narrativa", "narrativas.csv")
    exportar("""SELECT c.cuenta_id, nullif(r.grupo, '') AS grupo
                FROM cuentas c JOIN res_cuentas r USING (cuenta) WHERE c.cuenta_id <> '' ORDER BY c.cuenta_id""", "cuentas.csv")


def escribir_costo(entrega: Path, costo: dict) -> None:
    (Path(entrega) / "costo.json").write_text(json.dumps(costo, ensure_ascii=False, indent=2), encoding="utf-8")
