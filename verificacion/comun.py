"""Funciones compartidas por los scripts de verificación.

Estos scripts no son parte del pipeline: sirven para comprobar que el sistema funciona y no solo que
"da buen puntaje en práctica". Usan la verdad del set de práctica, así que no corren sobre el set final.
Todo lo que escriben va a salida/verificacion/ (no se versiona).
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PRACTICA = RAIZ / "datos" / "practica"
SALIDA = RAIZ / "salida" / "verificacion"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")

_especificacion = importlib.util.spec_from_file_location("puntuar", RAIZ / "evaluacion" / "puntuar.py")
puntuar_oficial = importlib.util.module_from_spec(_especificacion)
_especificacion.loader.exec_module(puntuar_oficial)


def puntuar(verdad: Path, entrega: Path) -> dict:
    """Puntaje con el evaluador oficial (evaluacion/puntuar.py), aplanado en un dict."""
    n = puntuar_oficial.score_narratives(Path(verdad), Path(entrega))
    c = puntuar_oficial.score_coordination(Path(verdad), Path(entrega))
    return {"agrup": n["bcubed_f1"], "ruido": n["ruido_f1"], "postura": n["postura_macro_f1"], "origen": n["origen"],
            "origen_detalle": n["origen_por_narrativa"], "pts_narr": n["puntos"], "coord_p": c["precision"],
            "coord_r": c["recall"], "coord_f1": c["f1"], "marcadas": c["cuentas_marcadas"],
            "grupos_f1": c["grupos_bcubed_f1"], "pts_coord": c["puntos"], "total": round(n["puntos"] + c["puntos"], 2)}


def leer_practica() -> dict:
    """Las tablas del set de práctica y su verdad, todo como texto."""
    leer = lambda ruta: pd.read_csv(ruta, dtype=str, keep_default_na=False)
    return {"comentarios": leer(PRACTICA / "comentarios.csv.gz"), "cuentas": leer(PRACTICA / "cuentas.csv.gz"),
            "publicaciones": leer(PRACTICA / "publicaciones.csv.gz"),
            "v_comentarios": leer(PRACTICA / "verdad" / "comentarios.csv.gz"),
            "v_cuentas": leer(PRACTICA / "verdad" / "cuentas.csv.gz"),
            "v_narrativas": leer(PRACTICA / "verdad" / "narrativas.csv")}


def armar_variante(nombre: str, t: dict, comentarios: pd.DataFrame) -> Path:
    """Escribe en salida/verificacion/<nombre>/datos un set recortado, con su verdad recortada igual.

    La verdad de narrativas se rehace para el recorte: se quitan las narrativas sin comentarios, el origen pasa a
    ser el primer comentario de la narrativa dentro del recorte, y solo cuenta como emergente la que nace adentro.
    """
    carpeta = SALIDA / nombre / "datos"
    if carpeta.exists():
        shutil.rmtree(carpeta)
    (carpeta / "verdad").mkdir(parents=True)
    comentarios.to_csv(carpeta / "comentarios.csv.gz", index=False)
    t["cuentas"][t["cuentas"].cuenta_id.isin(comentarios.cuenta_id)].to_csv(carpeta / "cuentas.csv.gz", index=False)
    t["publicaciones"][t["publicaciones"].publicacion_id.isin(comentarios.publicacion_id)].to_csv(
        carpeta / "publicaciones.csv.gz", index=False)
    shutil.copy(PRACTICA / "fuentes.csv", carpeta / "fuentes.csv")
    verdad = t["v_comentarios"][t["v_comentarios"].comentario_id.isin(comentarios.comentario_id)]
    verdad.to_csv(carpeta / "verdad" / "comentarios.csv.gz", index=False)
    t["v_cuentas"][t["v_cuentas"].cuenta_id.isin(comentarios.cuenta_id)].to_csv(carpeta / "verdad" / "cuentas.csv.gz", index=False)
    fechas = comentarios.merge(verdad, on="comentario_id")
    primero = fechas[fechas.narrativa_id != "ninguna"].groupby("narrativa_id").fecha.min()
    inicio = comentarios.fecha.min()
    narrativas = t["v_narrativas"][t["v_narrativas"].narrativa_id.isin(primero.index)].copy()
    adentro = narrativas.fecha_origen >= inicio
    narrativas["emergente"] = [e if a else "no" for e, a in zip(narrativas.emergente, adentro)]
    narrativas["fecha_origen"] = narrativas.narrativa_id.map(primero)
    narrativas.to_csv(carpeta / "verdad" / "narrativas.csv", index=False)
    return carpeta


def correr_pipeline(datos: Path, nombre: str, parametros: dict = None, extra: list = None) -> dict:
    """Corre el pipeline de punta a punta en otro proceso (como lo haría el jurado). Devuelve costo.json."""
    entrega, base = SALIDA / nombre / "entrega", SALIDA / nombre / "base.duckdb"
    orden = [sys.executable, "-m", "pipeline.run", "--datos", str(datos), "--entrega", str(entrega), "--base", str(base),
             "--sin-reporte", *(extra or [])]
    for clave, valor in (parametros or {}).items():
        orden += ["--param", f"{clave}={valor}"]
    proceso = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (SALIDA / nombre / "salida.txt").write_text(proceso.stdout + "\n" + proceso.stderr, encoding="utf-8")
    if proceso.returncode != 0:
        raise RuntimeError(f"el pipeline falló en {nombre}: {(proceso.stderr or proceso.stdout)[-600:]}")
    return json.loads((entrega / "costo.json").read_text(encoding="utf-8"))


def cordura(entrega: Path) -> dict:
    """Los números de los controles de cordura de una entrega."""
    from pipeline.validar import validar_entrega
    _errores, _avisos, r = validar_entrega(entrega)
    total = r.get("comentarios", 0)
    return {"narrativas": len(r.get("tam_narrativas", [])),
            "pct_ruido": 100 * (total - r.get("comentarios_con_narrativa", 0)) / total if total else 0.0,
            "coordinadas": r.get("cuentas_coordinadas", 0), "tam_grupos": r.get("tam_grupos", [])}


def dec(valor, decimales=3) -> str:
    return f"{valor:.{decimales}f}".replace(".", ",")
