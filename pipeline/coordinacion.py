"""Etapa 3: cuentas coordinadas (pendiente: por ahora no marca ninguna)."""
import numpy as np


def detectar_coordinacion(n_cuentas: int, **_) -> tuple:
    """Devuelve (grupo por cuenta: '' = genuina, detalle)."""
    return np.full(n_cuentas, "", dtype=object), {"grupos": 0, "cuentas_marcadas": 0}
