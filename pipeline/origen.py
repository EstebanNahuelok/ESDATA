"""Etapa 5: fecha de origen de cada narrativa.

El origen es el primer comentario de la narrativa, pero ignorando apariciones aisladas (un comentario
mal asignado días antes): se pide que ese primer comentario tenga compañía dentro de una ventana corta.
"""
from datetime import datetime, timedelta, timezone

import numpy as np


def fecha_origen(ts: np.ndarray, minimo: int = 5, ventana_s: int = 12 * 3600):
    """Primer instante (segundos UTC) con al menos `minimo` comentarios en las `ventana_s` siguientes."""
    t = np.sort(ts[~np.isnan(ts)]) if ts.dtype.kind == "f" else np.sort(ts)
    if len(t) == 0:
        return None
    m = min(minimo, len(t))
    sostenido = np.flatnonzero(t[m - 1:] - t[:len(t) - m + 1] <= ventana_s)
    return int(t[sostenido[0]] if len(sostenido) else t[0])


def a_iso(ts_utc: int, zona_seg: int) -> str:
    return datetime.fromtimestamp(ts_utc, tz=timezone(timedelta(seconds=zona_seg))).isoformat(timespec="seconds")
